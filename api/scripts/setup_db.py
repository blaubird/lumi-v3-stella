#!/usr/bin/env python3
import os
import sys
import argparse

# Add the parent directory to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import Base
from db import engine

def setup_database(drop_existing: bool = False):
    """
    Set up the database schema
    
    Args:
        drop_existing: Whether to drop existing tables before creating new ones
    """
    if drop_existing:
        print("Dropping existing tables...")
        Base.metadata.drop_all(bind=engine)
    
    print("Creating tables...")
    Base.metadata.create_all(bind=engine)
    print("Database setup complete.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Set up the database schema")
    parser.add_argument("--drop", action="store_true", help="Drop existing tables before creating new ones")
    
    args = parser.parse_args()
    
    setup_database(args.drop)
