
from __future__ import annotations

import json
import os
from datetime import datetime
from functools import lru_cache
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from google.oauth2 import service_account
from googleapiclient.discovery import build

_SCOPES = ["https://www.googleapis.com/auth/calendar"]


def _credentials_path() -> Path:
    raw_path = os.environ.get("GOOGLE_CALENDAR_CREDENTIALS")
    if not raw_path:
        raise RuntimeError("GOOGLE_CALENDAR_CREDENTIALS is not configured")
    return Path(raw_path)


def _load_service_account_info(path: Path) -> dict[str, Any]:
    try:
        payload = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:  # pragma: no cover - configuration issue
        raise RuntimeError(
            f"Google Calendar credentials file not found: {path}"  # noqa: EM101
        ) from exc

    try:
        return json.loads(payload)
    except JSONDecodeError as exc:  # pragma: no cover - configuration issue
        raise RuntimeError("Google Calendar credentials file is not valid JSON") from exc


def _get_default_calendar_id() -> str:
    direct = os.environ.get("GOOGLE_CALENDAR_ID")
    if direct:
        return direct

    config_raw = os.environ.get("GOOGLE_CALENDAR_CONFIG", "{}")
    try:
        config = json.loads(config_raw)
    except JSONDecodeError as exc:  # pragma: no cover - configuration issue
        raise RuntimeError("Invalid GOOGLE_CALENDAR_CONFIG value") from exc

    calendar_id = config.get("calendar_id")
    if isinstance(calendar_id, str) and calendar_id.strip():
        return calendar_id
    raise RuntimeError("Google Calendar ID is not configured")


@lru_cache(maxsize=1)
def _get_calendar_service() -> Any:
    info = _load_service_account_info(_credentials_path())
    credentials = service_account.Credentials.from_service_account_info(
        info,
        scopes=_SCOPES,
    )
    return build("calendar", "v3", credentials=credentials)


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
