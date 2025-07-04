from datetime import datetime
from typing import Optional
from logging_utils import get_logger
from utils.google_calendar import create_event as google_create_event

log = get_logger(__name__)


def create_event(
    summary: str,
    starts_at: datetime,
    ends_at: datetime,
    calendar_id: Optional[str] = None,
    guests: Optional[list[str]] = None,
) -> str:
    try:
        return google_create_event(summary, starts_at, ends_at, calendar_id, guests)
    except KeyError:
        raise RuntimeError("Google calendar credentials missing")


# TODO: implement Outlook calendar support
