from __future__ import annotations

import re
from datetime import datetime, timezone

from api.logging_utils import get_logger
from api.models import Appointment, Message, Usage
from api.utils.ics_generator import generate_ics
from api.utils.i18n import detect_lang

from .base import Context

log = get_logger(__name__)
BOOK_RE = re.compile(r"\bbook\s+(\d{1,2}[/-]\d{1,2})\s+(\d{1,2}:\d{2})", re.I)


class BookingHandler:
    async def handle(self, ctx: Context) -> bool:
        m = BOOK_RE.search(ctx["text"])
        if not m:
            return False
        date_part, time_part = m.groups()
        try:
            current_year = datetime.now(timezone.utc).year
            month, day = map(int, re.split(r"[/-]", date_part))
            hour, minute = map(int, time_part.split(":"))
            starts_at = datetime(
                current_year, month, day, hour, minute, tzinfo=timezone.utc
            )
            if starts_at < datetime.now(timezone.utc):
                starts_at = datetime(
                    current_year + 1, month, day, hour, minute, tzinfo=timezone.utc
                )
        except ValueError as exc:
            log.error(
                "Failed to parse booking time",
                extra={"text": ctx["text"], "error": str(exc)},
            )
            return False

        appt = Appointment(
            tenant_id=ctx["tenant_id"],
            customer_phone=ctx["from_number"],
            customer_email=None,
            starts_at=starts_at,
            status="pending",
        )
        ctx["db"].add(appt)
        ctx["db"].flush()

        detect_lang(ctx["text"])
        reply = (
            f"✅ booked for {starts_at.strftime('%d/%m %H:%M')}. You’ll get a reminder."
        )
        token_count = 0

        bot_message = Message(
            tenant_id=ctx["tenant_id"],
            role="assistant",
            text=reply,
            tokens=token_count,
        )
        ctx["db"].add(bot_message)

        outbound_usage = Usage(
            tenant_id=ctx["tenant_id"],
            direction="outbound",
            tokens=token_count,
            msg_ts=ctx["ts"],
        )
        ctx["db"].add(outbound_usage)

        ctx["reply"] = reply
        ctx["attachment"] = generate_ics("Appointment", starts_at)
        return True
