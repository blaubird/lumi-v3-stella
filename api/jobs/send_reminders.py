import os
from datetime import datetime, timedelta
from typing import Any, cast
from sqlalchemy.orm import Session
from database import SessionLocal
from models import Appointment, Tenant
from services.whatsapp import send_whatsapp_message
from utils.i18n import tr
from logging_utils import get_logger

REMINDER_OFFSET_MIN = int(os.getenv("REMINDER_OFFSET_MIN", "60"))
logger = get_logger(__name__)


async def send_reminders() -> None:
    db: Session = SessionLocal()
    try:
        target = datetime.utcnow() + timedelta(minutes=REMINDER_OFFSET_MIN)
        window_start = target - timedelta(minutes=1)
        upcoming = (
            db.query(Appointment)
            .filter(Appointment.status == "confirmed")
            .filter(Appointment.reminded.is_(False))
            .filter(Appointment.starts_at >= window_start)
            .filter(Appointment.starts_at <= target)
            .all()
        )
        for appt in upcoming:
            tenant = db.query(Tenant).filter(Tenant.id == appt.tenant_id).first()
            if tenant is None:
                continue
            appt = cast(Appointment, appt)
            dt = cast(datetime, appt.starts_at).strftime("%d/%m %H:%M")
            text = tr("booking.reminder", dt=dt)
            await send_whatsapp_message(
                cast(str, tenant.phone_id),
                cast(str, tenant.wh_token),
                cast(str, appt.customer_phone),
                text,
            )
            cast(Any, appt).reminded = True
            db.commit()
    except Exception as exc:
        logger.error("send_reminders failed", extra={"error": str(exc)}, exc_info=exc)
    finally:
        db.close()
