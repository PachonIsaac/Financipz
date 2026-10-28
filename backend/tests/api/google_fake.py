"""An in-memory stand-in for the mail provider, behind httpx's mock transport. Nothing touches the network."""

import base64
import json
from urllib.parse import parse_qs

import httpx

# Everything the client may ever ask. A new call fails the tests until it is added on purpose, which is
# the moment to confirm it only reads.
ALLOWED = frozenset(
    {
        ("POST", "/token"),
        ("POST", "/revoke"),
        ("GET", "/gmail/v1/users/me/messages"),
        ("GET", "/gmail/v1/users/me/messages/{id}"),
    }
)


def kind_of(request: httpx.Request) -> tuple[str, str]:
    """The method and the path, with a message id written as {id}."""
    path = request.url.path
    prefix = "/gmail/v1/users/me/messages/"
    return request.method, prefix + "{id}" if path.startswith(prefix) else path


def b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


def plain_message(text: str, sender: str = "alertasynotificaciones@bancolombia.com.co", received_ms: int = 1_793_000_000_000) -> dict:
    return {
        "internalDate": str(received_ms),
        "payload": {
            "mimeType": "multipart/alternative",
            "headers": [{"name": "From", "value": f"Alertas <{sender}>"}, {"name": "Subject", "value": "Aviso"}],
            "parts": [{"mimeType": "text/plain", "body": {"data": b64(text)}}],
        },
    }


def html_message(text: str) -> dict:
    html = f"<html><head><style>p{{color:red}}</style></head><body><p>{text}</p></body></html>"
    return {
        "internalDate": "1793000000000",
        "payload": {
            "mimeType": "text/html",
            "headers": [{"name": "From", "value": "alertasynotificaciones@bancolombia.com.co"}],
            "body": {"data": b64(html)},
        },
    }


class FakeGoogle:
    def __init__(self) -> None:
        self.messages: dict[str, dict] = {}
        self.requests: list[httpx.Request] = []
        self.refresh_token = "refresh-token-value"
        self.token_error: str | None = None
        self.api_status = 200
        self.revoked: list[str] = []

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self.handle), follow_redirects=False)

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        form = {key: values[0] for key, values in parse_qs(request.content.decode()).items()} if request.content else {}

        if path == "/token":
            if self.token_error:
                return httpx.Response(400, json={"error": self.token_error})
            if form.get("grant_type") == "authorization_code":
                if form.get("code") != "good-code":
                    return httpx.Response(400, json={"error": "invalid_grant"})
                return httpx.Response(200, json={"access_token": "access-1", "refresh_token": self.refresh_token})
            if form.get("refresh_token") != self.refresh_token:
                return httpx.Response(400, json={"error": "invalid_grant"})
            return httpx.Response(200, json={"access_token": "access-2", "expires_in": 3600})
        if path == "/revoke":
            self.revoked.append(form.get("token", ""))
            return httpx.Response(200, json={})

        if self.api_status != 200:
            return httpx.Response(self.api_status, json={"error": {"code": self.api_status}})
        if request.headers.get("authorization") != "Bearer access-2":
            return httpx.Response(401, json={"error": {"code": 401}})
        if path == "/gmail/v1/users/me/messages":
            ids = list(self.messages)
            return httpx.Response(200, json={"messages": [{"id": item, "threadId": item} for item in ids]} if ids else {})
        message_id = path.rsplit("/", 1)[-1]
        if path.startswith("/gmail/v1/users/me/messages/") and message_id in self.messages:
            return httpx.Response(200, json=self.messages[message_id])
        return httpx.Response(404, json={"error": {"code": 404}})

    def queries(self) -> list[str]:
        return [request.url.params.get("q", "") for request in self.requests if request.url.path.endswith("/messages")]
