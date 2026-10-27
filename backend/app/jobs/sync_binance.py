"""Job: read the exchange balances and new trades. Run with `python -m app.jobs.sync_binance`."""

import argparse
import sys

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ApiError
from app.db.session import get_engine
from app.services import binance_sync


def main(argv: list[str] | None = None) -> int:
    # The job takes no options, but it must answer --help (and refuse unknown options) instead of
    # silently running a sync. Called without arguments (as the tests do) it reads none.
    parser = argparse.ArgumentParser(description="Store today's balances and any new spot trades of the connected exchange (read-only).")
    parser.parse_args([] if argv is None else argv)

    settings = get_settings()
    if not settings.database_url:
        print("DATABASE_URL is not configured", file=sys.stderr)
        return 2

    try:
        with Session(get_engine(settings.database_url), expire_on_commit=False) as db:
            result = binance_sync.sync_binance(db, settings.encryption_key)
    except ApiError as error:
        print(f"{error.code}: {error.message}", file=sys.stderr)
        return 1

    print(
        f"Snapshot {result.snapshot_date}: {result.assets} assets "
        f"({result.unpriced_assets} without price), total {result.total_usd} USD, "
        f"{result.new_trades} new trades"
    )
    for notice in result.warnings:
        print(f"warning {notice.code}: {notice.message}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
