"""A read-only client for the mailbox.

It asks for one permission (`gmail.readonly`) and only ever calls the two read endpoints below: a new endpoint
has to be added here on purpose. Errors carry a fixed kind, never the text of the provider's answer, because
that text can quote tokens.
"""

import base64
import html
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlencode

import httpx

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
API_URL = "https://gmail.googleapis.com/gmail/v1/users/me"
SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
TIMEOUT_SECONDS = 20
# Only the start of a body is read: notifications are short, and the text comes from outside.
MAX_BODY_CHARS = 100_000
# Messages listed per page, and the most that are listed in one read.
PAGE_SIZE = 100

# Kinds of failure.
REVOKED = "revoked"  # the person withdrew the permission, or the grant expired
REJECTED = "rejected"  # the provider refused the request (bad client, bad code)
UNAVAILABLE = "unavailable"
BAD_RESPONSE = "bad_response"
RATE_LIMITED = "rate_limited"


class GmailError(Exception):
    def __init__(self, kind: str) -> None:
        super().__init__(kind)
        self.kind = kind


@dataclass(frozen=True)
class Message:
    id: str
    sender: str
    received_at: datetime | None
    text: str


def build_http() -> httpx.Client:
    return httpx.Client(timeout=TIMEOUT_SECONDS, follow_redirects=False)


def authorization_url(client_id: str, redirect_uri: str, state: str) -> str:
    query = urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": SCOPE,
            # Offline access with a forced consent page is what makes the provider hand out a refresh token.
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "false",
            "state": state,
        }
    )
    return f"{AUTH_URL}?{query}"


def _json(response: httpx.Response) -> dict:
    try:
        body = response.json()
    except ValueError:
        raise GmailError(BAD_RESPONSE) from None
    if not isinstance(body, dict):
        raise GmailError(BAD_RESPONSE)
    return body


def _token_request(data: dict[str, str]) -> dict:
    try:
        with build_http() as http:
            response = http.post(TOKEN_URL, data=data)
    except httpx.HTTPError:
        raise GmailError(UNAVAILABLE) from None
    if response.status_code >= 500:
        raise GmailError(UNAVAILABLE)
    body = _json(response)
    if response.status_code >= 400:
        raise GmailError(REVOKED if body.get("error") == "invalid_grant" else REJECTED)
    return body


def exchange_code(client_id: str, client_secret: str, redirect_uri: str, code: str) -> str:
    """Trade the code from the consent page for a refresh token."""
    body = _token_request(
        {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
        }
    )
    token = body.get("refresh_token")
    if not isinstance(token, str) or not token:
        raise GmailError(BAD_RESPONSE)
    return token


def refresh_access_token(client_id: str, client_secret: str, refresh_token: str) -> str:
    body = _token_request(
        {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
        }
    )
    token = body.get("access_token")
    if not isinstance(token, str) or not token:
        raise GmailError(BAD_RESPONSE)
    return token


def revoke(token: str) -> None:
    """Withdraw the permission at the provider. A failure is not an error: the local copy is deleted anyway."""
    try:
        with build_http() as http:
            http.post(REVOKE_URL, data={"token": token})
    except httpx.HTTPError:
        pass


class GmailClient:
    def __init__(self, access_token: str) -> None:
        self._headers = {"Authorization": f"Bearer {access_token}"}
        self._http = build_http()

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "GmailClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _get(self, path: str, params: dict[str, str | int]) -> dict:
        try:
            response = self._http.get(f"{API_URL}{path}", params=params, headers=self._headers)
        except httpx.HTTPError:
            raise GmailError(UNAVAILABLE) from None
        if response.status_code in (401, 403):
            raise GmailError(REVOKED)
        if response.status_code == 429:
            raise GmailError(RATE_LIMITED)
        if response.status_code >= 500:
            raise GmailError(UNAVAILABLE)
        if response.status_code >= 400:
            raise GmailError(REJECTED)
        return _json(response)

    def list_message_ids(self, query: str, limit: int) -> tuple[list[str], bool]:
        """Up to `limit` ids, newest first, following the pages. The flag says whether there were more."""
        ids: list[str] = []
        token: str | None = None
        while True:
            params: dict[str, str | int] = {"q": query, "maxResults": min(PAGE_SIZE, limit - len(ids) + 1)}
            if token:
                params["pageToken"] = token
            body = self._get("/messages", params)
            items = body.get("messages", [])
            if not isinstance(items, list):
                raise GmailError(BAD_RESPONSE)
            ids.extend(item["id"] for item in items if isinstance(item, dict) and isinstance(item.get("id"), str))
            token = body.get("nextPageToken") if isinstance(body.get("nextPageToken"), str) else None
            if len(ids) > limit:
                return ids[:limit], True
            if not token:
                return ids, False

    def get_message(self, message_id: str) -> Message:
        body = self._get(f"/messages/{message_id}", {"format": "full"})
        payload = body.get("payload")
        if not isinstance(payload, dict):
            raise GmailError(BAD_RESPONSE)
        headers = {
            str(item.get("name", "")).lower(): str(item.get("value", ""))
            for item in payload.get("headers", [])
            if isinstance(item, dict)
        }
        received = None
        try:
            received = datetime.fromtimestamp(int(body["internalDate"]) / 1000, UTC)
        except (KeyError, ValueError, TypeError, OverflowError):
            received = None
        return Message(id=message_id, sender=headers.get("from", ""), received_at=received, text=_text_of(payload))


def _decode(data: object) -> str:
    if not isinstance(data, str):
        return ""
    # Only the start is decoded: the body comes from outside, and the rest is never read.
    data = data[: MAX_BODY_CHARS * 2]
    try:
        return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", errors="replace")
    except ValueError:
        return ""


def _parts(payload: dict, depth: int = 0) -> list[dict]:
    found = [payload]
    if depth >= 8:
        return found
    for child in payload.get("parts", []) or []:
        if isinstance(child, dict):
            found.extend(_parts(child, depth + 1))
    return found


def _strip_markup(markup: str) -> str:
    """The text of an HTML document, without its tags, scripts and styles.

    Written as one pass that always moves forward: the parsers of the standard library take quadratic time on
    crafted input (an opened tag that never closes), and this text comes from outside.
    """
    lowered = markup.lower()
    out: list[str] = []
    i, n = 0, len(markup)
    while i < n:
        start = markup.find("<", i)
        if start == -1:
            out.append(markup[i:])
            break
        out.append(markup[i:start])
        if markup.startswith("<!--", start):
            end = markup.find("-->", start + 4)
            i = n if end == -1 else end + 3
            continue
        closing = None
        for tag in ("script", "style"):
            if lowered.startswith("<" + tag, start):
                closing = f"</{tag}"
                break
        if closing is not None:
            end = lowered.find(closing, start)
            end = -1 if end == -1 else markup.find(">", end)
            i = n if end == -1 else end + 1
            continue
        end = markup.find(">", start + 1)
        if end == -1:
            break
        out.append(" ")
        i = end + 1
    return html.unescape("".join(out))


def _text_of(payload: dict) -> str:
    """The readable text of a message: its plain part, or its HTML part with the markup removed."""
    plain, rich = "", ""
    for part in _parts(payload):
        data = _decode((part.get("body") or {}).get("data"))
        kind = str(part.get("mimeType", ""))
        if kind == "text/plain" and not plain:
            plain = data
        elif kind == "text/html" and not rich:
            rich = data
    text = plain or _strip_markup(rich)
    return " ".join(text.split())[:MAX_BODY_CHARS]
