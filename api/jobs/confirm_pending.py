from datetime import datetime, timedelta
from typing import Any, cast
from sqlalchemy.orm import Session
from api.database import SessionLocal
from api.models import Appointment, Tenant
from api.services.whatsapp import send_whatsapp_message
from api.services.calendar import create_event
from api.utils.ics_generator import generate_ics
from api.utils.i18n import tr
from api.logging_utils import get_logger

logger = get_logger(__name__)


async def confirm_pending() -> None:
    db: Session = SessionLocal()
    try:
        pending = db.query(Appointment).filter(Appointment.status == "pending").all()
        for appt in pending:
            tenant = db.query(Tenant).filter(Tenant.id == appt.tenant_id).first()
            if tenant is None:
                continue
            appt = cast(Appointment, appt)
            starts_at = cast(datetime, appt.starts_at)
            phone_id = cast(str, tenant.phone_id)
            token = cast(str, tenant.wh_token)
            dt = starts_at.strftime("%d/%m %H:%M")
            text = tr("booking.confirmed", dt=dt)
            ics = generate_ics("Appointment", starts_at)
            await send_whatsapp_message(
                phone_id,
                token,
                cast(str, appt.customer_phone),
                text,
                attachment=ics,
            )
            try:
                cast(Any, appt).google_event_id = create_event(
                    "Appointment",
                    starts_at,
                    starts_at + timedelta(hours=1),
                )
            except RuntimeError:
                logger.info("Calendar disabled")
            cast(Any, appt).status = "confirmed"
            db.commit()
    except Exception as exc:
        logger.error("confirm_pending failed", extra={"error": str(exc)}, exc_info=exc)
    finally:
        db.close()
