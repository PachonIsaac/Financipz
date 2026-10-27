"""Connect the exchange from the terminal: `python -m app.integrations.binance_connect`.

The key and the secret are typed at a hidden prompt, never passed as arguments, so they do not end up in
the shell history or in the process list.
"""

import sys
from getpass import getpass

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ApiError
from app.db.session import get_engine
from app.services import integrations


def main() -> int:
    settings = get_settings()
    if not settings.database_url:
        print("DATABASE_URL is not configured", file=sys.stderr)
        return 2

    api_key = getpass("API key (read-only): ").strip()
    api_secret = getpass("API secret: ").strip()
    if not api_key or not api_secret:
        print("The key and the secret are both required", file=sys.stderr)
        return 2

    try:
        with Session(get_engine(settings.database_url), expire_on_commit=False) as db:
            row = integrations.connect_binance(db, settings.encryption_key, api_key, api_secret)
            warnings = list(row.warnings)
    except ApiError as error:
        print(f"{error.code}: {error.message}", file=sys.stderr)
        if error.details.get("permissions"):
            print("Permissions to turn off: " + ", ".join(error.details["permissions"]), file=sys.stderr)
        return 1

    print("Binance connected (read-only key stored encrypted).")
    for warning in warnings:
        print(f"warning {warning['code']}: {warning['message']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
