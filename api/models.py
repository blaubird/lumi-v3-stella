from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Enum, TIMESTAMP
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector
from db import Base

class Tenant(Base):
    __tablename__ = "tenants"
    
    id = Column(String, primary_key=True, index=True)
    phone_id = Column(String, nullable=False, unique=True, index=True)
    wh_token = Column(Text, nullable=False)
    system_prompt = Column(Text, nullable=False, server_default="You are a helpful assistant.")
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now())
    updated_at = Column(TIMESTAMP, nullable=False, server_default=func.now(), onupdate=func.now())
    
    # Relationships
    messages = relationship("Message", back_populates="tenant")
    faqs = relationship("FAQ", back_populates="tenant")

class Message(Base):
    __tablename__ = "messages"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False, index=True)
    wa_msg_id = Column(String, nullable=True, unique=True)
    role = Column(Enum("user", "bot", name="role_enum"), nullable=False)
    text = Column(Text, nullable=False)
    tokens = Column(Integer, nullable=True)
    ts = Column(TIMESTAMP, nullable=False, server_default=func.now())
    
    # Relationships
    tenant = relationship("Tenant", back_populates="messages")

class FAQ(Base):
    __tablename__ = "faqs"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False, index=True)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    embedding = Column(Vector(1536), nullable=True)
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now())
    updated_at = Column(TIMESTAMP, nullable=False, server_default=func.now(), onupdate=func.now())
    
    # Relationships
    tenant = relationship("Tenant", back_populates="faqs")
