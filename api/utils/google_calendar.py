import json, os
from datetime import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build

_SCOPES = ["https://www.googleapis.com/auth/calendar"]
_creds = service_account.Credentials.from_service_account_info(
    json.loads(os.environ["GOOGLE_SERVICE_JSON"]), scopes=_SCOPES
)
_svc = build("calendar", "v3", credentials=_creds, cache_discovery=False)
_DEFAULT_CAL = os.getenv("DEFAULT_CALENDAR_ID")

def create_event(summary: str,
                 starts_at: datetime,
                 ends_at: datetime,
                 calendar_id: str | None = None,
                 guests: list[str] | None = None) -> str:
    body = {
        "summary": summary,
        "start": {"dateTime": starts_at.isoformat()},
        "end":   {"dateTime": ends_at.isoformat()},
    }
    if guests:
        body["attendees"] = [{"email": g} for g in guests]
    cal_id = calendar_id or _DEFAULT_CAL
    ev = _svc.events().insert(calendarId=cal_id, body=body).execute()
    return ev["id"]
