#!/usr/bin/env python3
import os
import sys
import uuid
import argparse

# Add the parent directory to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import Tenant
from db import SessionLocal

def create_tenant(phone_id: str, wh_token: str = None, system_prompt: str = None):
    """
    Create a new tenant in the database
    
    Args:
        phone_id: WhatsApp phone ID
        wh_token: Webhook verification token (generated if not provided)
        system_prompt: System prompt for the AI (default provided if not specified)
    """
    # Generate webhook token if not provided
    if not wh_token:
        wh_token = str(uuid.uuid4())
    
    # Set default system prompt if not provided
    if not system_prompt:
        system_prompt = "You are a helpful assistant that answers questions based on the provided knowledge base."
    
    # Create database session
    db = SessionLocal()
    
    try:
        # Check if tenant with same phone_id already exists
        existing = db.query(Tenant).filter(Tenant.phone_id == phone_id).first()
        if existing:
            print(f"Tenant with phone_id {phone_id} already exists (ID: {existing.id})")
            return
        
        # Create new tenant
        tenant = Tenant(
            phone_id=phone_id,
            wh_token=wh_token,
            system_prompt=system_prompt
        )
        
        # Add to database
        db.add(tenant)
        db.commit()
        db.refresh(tenant)
        
        print("Tenant created successfully:")
        print(f"  ID: {tenant.id}")
        print(f"  Phone ID: {tenant.phone_id}")
        print(f"  Webhook Token: {tenant.wh_token}")
    finally:
        db.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create a new tenant")
    parser.add_argument("phone_id", help="WhatsApp phone ID")
    parser.add_argument("--token", help="Webhook verification token (generated if not provided)")
    parser.add_argument("--prompt", help="System prompt for the AI")
    
    args = parser.parse_args()
    
    create_tenant(args.phone_id, args.token, args.prompt)
