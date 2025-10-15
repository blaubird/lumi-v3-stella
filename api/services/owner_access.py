from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from logging_utils import get_logger
from models import OwnerContact

logger = get_logger(__name__)


def normalize_phone(value: str) -> str:
    cleaned = value.strip()
    if cleaned.startswith("+"):
        prefix = "+"
        digits = "".join(ch for ch in cleaned[1:] if ch.isdigit())
        return prefix + digits
    return "".join(ch for ch in cleaned if ch.isdigit())


def is_owner_contact(db: Session, tenant_id: str, phone_number: str) -> bool:
    normalized = normalize_phone(phone_number)
    match = (
        db.query(OwnerContact)
        .filter(OwnerContact.tenant_id == tenant_id)
        .filter(OwnerContact.phone_number == normalized)
        .first()
    )
    if match is None:
        logger.debug(
            "Owner contact check failed",
            extra={"tenant_id": tenant_id, "phone_number": normalized},
        )
        return False
    return True


def upsert_owner_contact(
    db: Session,
    tenant_id: str,
    phone_number: str,
    display_name: Optional[str] = None,
) -> OwnerContact:
    normalized = normalize_phone(phone_number)
    contact = (
        db.query(OwnerContact)
        .filter(OwnerContact.tenant_id == tenant_id)
        .filter(OwnerContact.phone_number == normalized)
        .first()
    )
    if contact is None:
        contact = OwnerContact(
            tenant_id=tenant_id,
            phone_number=normalized,
            display_name=display_name,
        )
    else:
        contact.display_name = display_name or contact.display_name
    db.add(contact)
    db.commit()
    db.refresh(contact)
    return contact


__all__ = ["is_owner_contact", "upsert_owner_contact", "normalize_phone"]
