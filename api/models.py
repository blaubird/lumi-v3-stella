from sqlalchemy import (
    Column,
    Integer,
    String,
    ForeignKey,
    Text,
    Enum,
    TIMESTAMP,
    DateTime,
    Date,
    Boolean,
    text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector
from database import Base

# Note on ID types:
# Tenant uses String ID type to support custom identifiers provided during creation
# All other resources use Integer IDs with autoincrement for internal sequence management
# This difference is intentional to allow external systems to reference tenants by their own IDs
# while maintaining simple numeric sequences for child resources


class Tenant(Base):
    __tablename__ = "tenants"

    id = Column(String(255), primary_key=True, index=True)
    phone_id = Column(String(255), nullable=False, unique=True, index=True)
    wh_token = Column(Text, nullable=False)
    system_prompt = Column(
        Text, nullable=False, server_default="You are a helpful assistant."
    )

    # Relationships
    messages = relationship("Message", back_populates="tenant", passive_deletes=True)
    faqs = relationship("FAQ", back_populates="tenant", passive_deletes=True)
    usage = relationship("Usage", back_populates="tenant", passive_deletes=True)


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    tenant_id = Column(
        String(255),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    wa_msg_id = Column(String(255), nullable=True, unique=True)
    role = Column(Enum("inbound", "assistant", name="role_enum"), nullable=False)
    text = Column(Text, nullable=False)
    tokens = Column(Integer, nullable=True)
    ts = Column(TIMESTAMP, nullable=False, server_default=func.now())

    # Relationships
    tenant = relationship("Tenant", back_populates="messages", passive_deletes=True)


class FAQ(Base):
    __tablename__ = "faqs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    tenant_id = Column(
        String(255),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    question = Column(
        String(500), nullable=False
    )  # Changed from Text to String for exact matching
    answer = Column(Text, nullable=False)
    embedding = Column(Vector(1536), nullable=True)

    # Relationships
    tenant = relationship("Tenant", back_populates="faqs", passive_deletes=True)


class Usage(Base):
    __tablename__ = "usage"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    tenant_id = Column(
        String(255),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    direction = Column(String(64), nullable=True)
    tokens = Column(Integer, nullable=True)
    msg_ts = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    model = Column(String(255), nullable=True)
    prompt_tokens = Column(Integer, nullable=False, default=0, server_default=text("0"))
    completion_tokens = Column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    total_tokens = Column(Integer, nullable=False, default=0, server_default=text("0"))
    trace_id = Column(String(255), nullable=True)

    # Relationships
    tenant = relationship("Tenant", back_populates="usage", passive_deletes=True)


class Appointment(Base):
    __tablename__ = "appointments"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(
        String(255),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    customer_phone = Column(
        String(50), nullable=False
    )  # Assuming phone numbers are up to 50 chars
    customer_email = Column(
        String(255), nullable=True
    )  # Assuming email addresses are up to 255 chars
    starts_at = Column(DateTime(timezone=True), nullable=False)
    status = Column(
        Enum("pending", "confirmed", "cancelled", name="appt_status_enum"),
        nullable=False,
        default="pending",
    )
    google_event_id = Column(String(255), nullable=True)
    reminded = Column(Boolean, default=False, nullable=False)
    created_ts = Column(DateTime(timezone=True), server_default=func.now())


class OwnerContact(Base):
    __tablename__ = "owner_contacts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(
        String(255),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    phone_number = Column(String(64), nullable=False, index=True)
    display_name = Column(String(255), nullable=True)
    created_ts = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Unavailability(Base):
    __tablename__ = "unavailability"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(
        String(255),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    owner_phone = Column(String(64), nullable=False)
    starts_on = Column(Date, nullable=False)
    ends_on = Column(Date, nullable=False)
    created_ts = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


__all__ = [
    "Tenant",
    "Message",
    "FAQ",
    "Usage",
    "Appointment",
    "OwnerContact",
    "Unavailability",
]
