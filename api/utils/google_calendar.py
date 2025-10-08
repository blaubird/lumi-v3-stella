
import json
import os
from datetime import datetime
from functools import lru_cache
from json import JSONDecodeError
from typing import Any

from google.oauth2 import service_account
from googleapiclient.discovery import build

_SCOPES = ["https://www.googleapis.com/auth/calendar"]

def create_event(
    summary: str,
    starts_at: datetime,
    ends_at: datetime,
    calendar_id: str | None = None,
    guests: list[str] | None = None,
) -> str:
    body = {
        "summary": summary,
        "start": {"dateTime": starts_at.isoformat()},
        "end": {"dateTime": ends_at.isoformat()},
    }
    if guests:
        body["attendees"] = [{"email": g} for g in guests]
    cal_id = calendar_id or _get_default_calendar_id()
    service = _get_calendar_service()
    event: dict[str, Any] = (
        service.events().insert(calendarId=cal_id, body=body).execute()
    )
    return event["id"]
