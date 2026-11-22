"""Business-date helpers shared by the extract and load CLIs."""
from __future__ import annotations

import argparse
from collections.abc import Iterator
from datetime import date, timedelta


def daterange(start: date, end: date) -> Iterator[date]:
    """Every date from start to end, inclusive."""
    for offset in range((end - start).days + 1):
        yield start + timedelta(days=offset)


def add_date_args(parser: argparse.ArgumentParser, group: argparse._MutuallyExclusiveGroup) -> None:
    group.add_argument("--date", type=date.fromisoformat, help="one business date (YYYY-MM-DD)")
    group.add_argument("--start", type=date.fromisoformat, help="first date of a backfill")
    parser.add_argument("--end", type=date.fromisoformat, help="last date of a backfill (inclusive)")


def resolve_date_range(parser: argparse.ArgumentParser, args: argparse.Namespace) -> argparse.Namespace:
    """Normalise --date / --start --end into args.start and args.end."""
    if args.date:
        args.start = args.end = args.date
    elif args.start and (not args.end or args.end < args.start):
        parser.error("--start needs an --end on or after it")
    return args
