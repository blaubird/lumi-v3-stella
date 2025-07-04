from datetime import datetime, timedelta


def generate_ics(summary: str, starts_at: datetime, duration_min: int = 60) -> bytes:
    dt_start = starts_at.strftime("%Y%m%dT%H%M%SZ")
    dt_end = (starts_at + timedelta(minutes=duration_min)).strftime("%Y%m%dT%H%M%SZ")
    body = (
        "BEGIN:VCALENDAR\n"
        "VERSION:2.0\n"
        "BEGIN:VEVENT\n"
        f"SUMMARY:{summary}\n"
        f"DTSTART:{dt_start}\n"
        f"DTEND:{dt_end}\n"
        "END:VEVENT\n"
        "END:VCALENDAR\n"
    )
    return body.encode()
