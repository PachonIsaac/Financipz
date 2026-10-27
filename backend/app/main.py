from fastapi import Depends, FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.accounts import router as accounts_router
from app.api.categories import router as categories_router
from app.api.health import router as health_router
from app.api.me import router as me_router
from app.api.transactions import router as transactions_router
from app.core.auth import get_current_user
from app.core.config import get_settings
from app.core.errors import ApiError, api_error_handler, http_error_handler, validation_error_handler

settings = get_settings()

app = FastAPI(title=settings.app_name)
app.add_exception_handler(ApiError, api_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)
app.add_exception_handler(StarletteHTTPException, http_error_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Only the health check is public. Every other route needs a signed-in user.
app.include_router(health_router, prefix="/api/v1")
protected = [Depends(get_current_user)]
app.include_router(me_router, prefix="/api/v1")
app.include_router(accounts_router, prefix="/api/v1", dependencies=protected)
app.include_router(categories_router, prefix="/api/v1", dependencies=protected)
app.include_router(transactions_router, prefix="/api/v1", dependencies=protected)
