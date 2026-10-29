from fastapi import APIRouter, Depends, Header
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.errors import ApiError
from app.core.ratelimit import RateLimiter
from app.db.session import get_db
from app.parsers.uala_sms import parse_uala_sms
from app.schemas.ingest import ShortcutIn, ShortcutOut, TokenCreated, TokenStatus
from app.services import ingest as pipeline
from app.services import ingest_token as tokens

router = APIRouter(prefix="/ingest/shortcut", tags=["ingest"])

# The shortcut sends one SMS at a time. These limits stop a guessing attack on the token, and a runaway
# shortcut, without ever getting in the way of real use.
requests_limit = RateLimiter(limit=60, window=60)
failures_limit = RateLimiter(limit=10, window=60)


def _too_many(limiter: RateLimiter) -> ApiError:
    return ApiError(
        429,
        "rate_limited",
        "Demasiadas solicitudes. Intenta de nuevo en un momento.",
        headers={"Retry-After": str(limiter.retry_after())},
    )


@router.post("", response_model=ShortcutOut, status_code=201)
def receive(
    body: ShortcutIn,
    ingest_token: str | None = Header(None, alias="X-Ingest-Token"),
    db: Session = Depends(get_db),
):
    """Receive an SMS from the shortcut and store what it says as a pending movement.

    201 created, 409 already stored, 200 recognized but not a movement, 422 not recognized. The token is the
    only credential and it opens nothing else.
    """
    if not tokens.verify(db, ingest_token):
        if not failures_limit.allow():
            raise _too_many(failures_limit)
        raise ApiError(401, "invalid_ingest_token", "El token de ingesta no es válido.")
    # Only requests with the right token use up this limit, so nobody can spend it for the real shortcut.
    if not requests_limit.allow():
        raise _too_many(requests_limit)

    result = pipeline.ingest(db, parse_uala_sms(body.text, body.received_at))
    match result.outcome:
        case pipeline.Outcome.CREATED:
            return ShortcutOut(result="created", id=result.transaction.id)
        case pipeline.Outcome.IGNORED:
            return JSONResponse(status_code=200, content={"result": "ignored", "id": None})
        case pipeline.Outcome.DUPLICATE:
            raise ApiError(
                409,
                "duplicate_notification",
                "Este mensaje ya se había recibido.",
                {"id": str(result.transaction.id), "possible_duplicate": result.possible_duplicate},
            )
        case _:
            raise ApiError(422, "unrecognized_notification", "No se reconoció el mensaje.")


@router.get("/token", response_model=TokenStatus, dependencies=[Depends(get_current_user)])
def token_status(db: Session = Depends(get_db)):
    """Whether a token exists and when it was last used. Never the token itself."""
    row = tokens.current(db)
    return TokenStatus(
        configured=row is not None,
        created_at=row.created_at if row else None,
        last_used_at=row.last_used_at if row else None,
    )


@router.post("/token/rotate", response_model=TokenCreated, status_code=201, dependencies=[Depends(get_current_user)])
def rotate_token(db: Session = Depends(get_db)):
    """Create a new token and invalidate the previous one. The token is shown only in this answer."""
    token, row = tokens.rotate(db)
    return TokenCreated(token=token, created_at=row.created_at)
