from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.accounts import router as accounts_router
from app.api.categories import router as categories_router
from app.api.crypto import router as crypto_router
from app.api.fx_rates import router as fx_rates_router
from app.api.gmail import router as gmail_router
from app.api.health import router as health_router
from app.api.ingest import router as ingest_router
from app.api.integrations import router as integrations_router
from app.api.me import router as me_router
from app.api.refresh import router as refresh_router
from app.api.reports import router as reports_router
from app.api.transactions import router as transactions_router
from app.core.auth import get_current_user
from app.core.config import get_settings
from app.core.errors import (
    ApiError,
    api_error_handler,
    domain_error_handler,
    http_error_handler,
    validation_error_handler,
)
from app.domain.errors import DomainError
from app.services import refresh

settings = get_settings()



@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # Runs in the background: the service answers requests without waiting for it.
    if settings.refresh_on_startup and settings.database_url:
        refresh.start_in_background(settings)
    yield


docs_urls = {} if settings.docs_enabled else {"docs_url": None, "redoc_url": None, "openapi_url": None}
app = FastAPI(title=settings.app_name, lifespan=lifespan, **docs_urls)
app.add_exception_handler(ApiError, api_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)
app.add_exception_handler(StarletteHTTPException, http_error_handler)
app.add_exception_handler(DomainError, domain_error_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Only the health check is public. Every other route needs a signed-in user.
app.include_router(health_router, prefix="/api/v1")
protected = [Depends(get_current_user)]
# The shortcut route has its own token, the mailbox callback its own signed state, and the routes that
# manage either check the signed-in user themselves.
app.include_router(ingest_router, prefix="/api/v1")
app.include_router(gmail_router, prefix="/api/v1")
app.include_router(me_router, prefix="/api/v1")
app.include_router(accounts_router, prefix="/api/v1", dependencies=protected)
app.include_router(categories_router, prefix="/api/v1", dependencies=protected)
app.include_router(transactions_router, prefix="/api/v1", dependencies=protected)
app.include_router(fx_rates_router, prefix="/api/v1", dependencies=protected)
app.include_router(reports_router, prefix="/api/v1", dependencies=protected)
app.include_router(integrations_router, prefix="/api/v1", dependencies=protected)
app.include_router(crypto_router, prefix="/api/v1", dependencies=protected)
app.include_router(refresh_router, prefix="/api/v1", dependencies=protected)
