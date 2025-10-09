#!/usr/bin/env python3
"""
Helper script to reset user password in Supabase
"""
import os
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

def reset_user_password(email: str, new_password: str):
    """Reset a user's password using service role key"""
    try:
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
        
        # Update user password (requires service_role key)
        response = supabase.auth.admin.update_user_by_id(
            email,
            {"password": new_password}
        )
        
        print(f"✅ Password reset successful for {email}")
        print(f"New password: {new_password}")
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) != 3:
        print("Usage: python reset_password.py <email> <new_password>")
        print("Example: python reset_password.py sajeevs0706@gmail.com MyNewPass123")
        sys.exit(1)
    
    email = sys.argv[1]
    new_password = sys.argv[2]
    
    reset_user_password(email, new_password)
