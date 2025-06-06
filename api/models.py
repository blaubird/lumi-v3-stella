from sqlalchemy import Column, Integer, String, ForeignKey, Text, Enum, TIMESTAMP, DateTime, func
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector
from db import Base

# Note on ID types:
# Tenant uses String ID type to support custom identifiers provided during creation
# All other resources use Integer IDs with autoincrement for internal sequence management
# This difference is intentional to allow external systems to reference tenants by their own IDs
# while maintaining simple numeric sequences for child resources

class Tenant(Base):
    __tablename__ = "tenants"
    
    id = Column(String, primary_key=True, index=True)
    phone_id = Column(String, nullable=False, unique=True, index=True)
    wh_token = Column(Text, nullable=False)
    system_prompt = Column(Text, nullable=False, server_default="You are a helpful assistant.")
    
    # Relationships
    messages = relationship("Message", back_populates="tenant", passive_deletes=True)
    faqs = relationship("FAQ", back_populates="tenant", passive_deletes=True)
    usage = relationship("Usage", back_populates="tenant", passive_deletes=True)

class Message(Base):
    __tablename__ = "messages"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    tenant_id = Column(String, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    wa_msg_id = Column(String, nullable=True, unique=True)
    role = Column(Enum("inbound", "assistant", name="role_enum"), nullable=False)
    text = Column(Text, nullable=False)
    tokens = Column(Integer, nullable=True)
    ts = Column(TIMESTAMP, nullable=False, server_default=func.now())
    
    # Relationships
    tenant = relationship("Tenant", back_populates="messages", passive_deletes=True)

class FAQ(Base):
    __tablename__ = "faqs"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    tenant_id = Column(String, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    question = Column(String, nullable=False)  # Changed from Text to String for exact matching
    answer = Column(Text, nullable=False)
    embedding = Column(Vector(1536), nullable=True)
    
    # Relationships
    tenant = relationship("Tenant", back_populates="faqs", passive_deletes=True)

class Usage(Base):
    __tablename__ = "usage"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    tenant_id = Column(String, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    direction = Column(Enum("inbound", "outbound", name="direction_enum"), nullable=False)
    tokens = Column(Integer, nullable=False)
    msg_ts = Column(DateTime(timezone=True), nullable=False)
    
    # Relationships
    tenant = relationship("Tenant", back_populates="usage", passive_deletes=True)
