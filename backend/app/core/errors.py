from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

HTTP_ERROR_CODES = {
    404: ("not_found", "No se encontró lo que buscas."),
    405: ("method_not_allowed", "Esa acción no está permitida aquí."),
}


class ApiError(Exception):
    """An error with the API's standard shape: {"error": {"code", "message", "details"}}.

    `code` is a stable English identifier for clients; `message` is shown to the user, in Spanish.
    """

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: dict | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}
        self.headers = headers


def error_response(exc: ApiError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message, "details": exc.details}},
        headers=exc.headers,
    )


async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
    return error_response(exc)


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    fields = [
        {"field": ".".join(str(part) for part in error["loc"][1:]), "problem": error["msg"]}
        for error in exc.errors()
    ]
    return error_response(
        ApiError(422, "validation_error", "Revisa los datos enviados.", {"fields": fields})
    )


async def http_error_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    code, message = HTTP_ERROR_CODES.get(exc.status_code, ("http_error", "No se pudo completar la solicitud."))
    return error_response(ApiError(exc.status_code, code, message, headers=getattr(exc, "headers", None)))
