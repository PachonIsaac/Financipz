"""Daily job: store today's TRM. Run with `python -m app.jobs.sync_trm [--backfill-from YYYY-MM-DD]`."""

import argparse
import sys
from datetime import date

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ApiError
from app.db.session import get_engine
from app.services import fx_rates


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Store the USD to COP exchange rate.")
    parser.add_argument(
        "--backfill-from",
        type=date.fromisoformat,
        metavar="YYYY-MM-DD",
        help="Store the rates published since this day (up to 400 days back).",
    )
    args = parser.parse_args(argv)

    url = get_settings().database_url
    if not url:
        print("DATABASE_URL is not configured", file=sys.stderr)
        return 2

    try:
        with Session(get_engine(url)) as db:
            row = fx_rates.sync_rates(db, args.backfill_from)
            print(f"Stored {row.currency} rate {row.value} for {row.date}")
    except ApiError as error:
        print(f"{error.code}: {error.details.get('reason', error.message)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
