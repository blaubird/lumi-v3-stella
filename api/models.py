from sqlalchemy import Column, Integer, String, ForeignKey, Text, Enum, TIMESTAMP
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
# Conditionally import Vector to handle environments without pgvector
try:
    from pgvector.sqlalchemy import Vector
    has_pgvector = True
except ImportError:
    has_pgvector = False
    # Create a placeholder for Vector that won't break imports
    class VectorPlaceholder:
        def __call__(self, *args, **kwargs):
            raise ImportError("pgvector is not installed. Please install it with 'pip install pgvector'")
    Vector = VectorPlaceholder()
from db import Base
class Tenant(Base):
    __tablename__ = "tenants"
    
    id = Column(String, primary_key=True, index=True)
    phone_id = Column(String, nullable=False, unique=True, index=True)
    wh_token = Column(Text, nullable=False)
    system_prompt = Column(Text, nullable=False, server_default="You are a helpful assistant.")
    
    # Relationships
    messages = relationship("Message", back_populates="tenant")
    faqs = relationship("FAQ", back_populates="tenant")
    usage = relationship("Usage", back_populates="tenant")

class Message(Base):
    __tablename__ = "messages"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    tenant_id = Column(String, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
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
    tenant_id = Column(String, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    # Only define embedding column if pgvector is available
    if has_pgvector:
        embedding = Column(Vector(1536), nullable=True)
    else:
        embedding = Column(Text, nullable=True)  # Fallback to Text type
    
    # Relationships
    tenant = relationship("Tenant", back_populates="faqs")

class Usage(Base):
    __tablename__ = "usage"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    tenant_id = Column(String, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    direction = Column(Enum("inbound", "outbound", name="direction_enum"), nullable=False)
    tokens = Column(Integer, nullable=False)
    msg_ts = Column(TIMESTAMP, nullable=False, server_default=func.now())
    
    # Relationships
    tenant = relationship("Tenant", back_populates="usage")
