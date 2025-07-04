from datetime import timedelta
from sqlalchemy.orm import Session
from database import SessionLocal
from models import Appointment, Tenant
from services.whatsapp import send_whatsapp_message
from services.calendar import create_event
from utils.ics_generator import generate_ics
from utils.i18n import tr
from logging_utils import get_logger

logger = get_logger(__name__)


async def confirm_pending() -> None:
    db: Session = SessionLocal()
    try:
        pending = db.query(Appointment).filter(Appointment.status == "pending").all()
        for appt in pending:
            tenant = db.query(Tenant).filter(Tenant.id == appt.tenant_id).first()
            if not tenant:
                continue
            dt = appt.starts_at.strftime("%d/%m %H:%M")
            text = tr("booking.confirmed", dt=dt)
            ics = generate_ics("Appointment", appt.starts_at)
            await send_whatsapp_message(
                tenant.phone_id,
                tenant.wh_token,
                appt.customer_phone,
                text,
                attachment=ics,
            )
            try:
                appt.google_event_id = create_event(
                    "Appointment",
                    appt.starts_at,
                    appt.starts_at + timedelta(hours=1),
                )
            except RuntimeError:
                logger.info("Calendar disabled")
            appt.status = "confirmed"
            db.commit()
    except Exception as exc:
        logger.error("confirm_pending failed", extra={"error": str(exc)}, exc_info=exc)
    finally:
        db.close()
