from datetime import datetime
from typing import Optional
from api.logging_utils import get_logger

log = get_logger(__name__)


def create_event(
    summary: str,
    starts_at: datetime,
    ends_at: datetime,
    calendar_id: Optional[str] = None,
    guests: Optional[list[str]] = None,
) -> str:
    try:
        from api.utils.google_calendar import create_event as google_create_event

        return google_create_event(summary, starts_at, ends_at, calendar_id, guests)
    except KeyError:
        raise RuntimeError("Google calendar credentials missing")


def create_outlook_event(*args, **kwargs) -> str:
    """Placeholder for future Outlook calendar integration."""
    raise NotImplementedError("Outlook calendar integration is not implemented yet")
