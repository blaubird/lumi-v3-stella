from __future__ import annotations

import json
import os
from datetime import datetime
from functools import lru_cache
from json import JSONDecodeError
from typing import Any

from google.oauth2 import service_account
from googleapiclient.discovery import build

_SCOPES = ["https://www.googleapis.com/auth/calendar"]


def _load_service_account_info() -> dict[str, object]:
    raw_credentials = os.getenv("GOOGLE_SERVICE_JSON")
    if not raw_credentials:
        raise RuntimeError(
            "Environment variable GOOGLE_SERVICE_JSON must be set with the service"
            " account JSON payload to use Google Calendar APIs."
        )
    try:
        return json.loads(raw_credentials)
    except JSONDecodeError as exc:
        raise RuntimeError("GOOGLE_SERVICE_JSON is not valid JSON.") from exc


def _get_default_calendar_id() -> str:
    calendar_id = os.getenv("DEFAULT_CALENDAR_ID")
    if not calendar_id:
        raise RuntimeError(
            "Environment variable DEFAULT_CALENDAR_ID must be set to create calendar"
            " events."
        )
    return calendar_id


@lru_cache(maxsize=1)
def _get_calendar_service() -> Any:
    credentials = service_account.Credentials.from_service_account_info(
        _load_service_account_info(), scopes=_SCOPES
    )
    return build("calendar", "v3", credentials=credentials, cache_discovery=False)


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
