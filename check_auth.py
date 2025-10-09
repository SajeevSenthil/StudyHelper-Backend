"""
Helper script to check authentication status and create test user if needed
"""
import os
import psycopg2
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

def check_auth_users():
    """Check existing users in auth.users table"""
    try:
        conn = psycopg2.connect(
            host=os.getenv('DB_HOST'),
            database=os.getenv('DB_NAME'),
            user=os.getenv('DB_USER'),
            password=os.getenv('DB_PASSWORD'),
            port=os.getenv('DB_PORT')
        )
        cursor = conn.cursor()
        
        print("=" * 70)
        print("AUTHENTICATION STATUS CHECK")
        print("=" * 70)
        
        # Check auth.users
        cursor.execute("""
            SELECT id, email, created_at, email_confirmed_at
            FROM auth.users 
            ORDER BY created_at DESC 
            LIMIT 10;
        """)
        
        users = cursor.fetchall()
        if users:
            print(f"\n✅ Found {len(users)} user(s) in auth.users:\n")
            for user in users:
                confirmed = "✓ Confirmed" if user[3] else "✗ Not Confirmed"
                print(f"  User ID: {user[0]}")
                print(f"  Email: {user[1]}")
                print(f"  Created: {user[2]}")
                print(f"  Status: {confirmed}")
                print()
        else:
            print("\n❌ No users found in auth.users table")
            print("\nTo create a user:")
            print("1. Go to http://localhost:3000/login")
            print("2. Click 'Sign Up'")
            print("3. Enter email and password")
            print("4. Check Supabase dashboard if email confirmation is required")
        
        # Check documents
        cursor.execute("SELECT COUNT(*) FROM documents;")
        doc_count = cursor.fetchone()[0]
        print(f"\n📄 Documents in database: {doc_count}")
        
        if doc_count > 0:
            cursor.execute("""
                SELECT d.doc_id, d.user_id, d.topic, u.email
                FROM documents d
                LEFT JOIN auth.users u ON d.user_id = u.id
                ORDER BY d.doc_id DESC
                LIMIT 5;
            """)
            print("\nRecent documents:")
            for doc in cursor.fetchall():
                user_email = doc[3] if doc[3] else "❌ User not found"
                print(f"  Doc #{doc[0]}: {doc[2]} (User: {user_email})")
        
        cursor.close()
        conn.close()
        
        print("\n" + "=" * 70)
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_auth_users()
