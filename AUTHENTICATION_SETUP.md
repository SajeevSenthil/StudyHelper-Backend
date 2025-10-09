# Authentication Setup Guide

## Issue: 422 Error on Login

The 422 error from Supabase usually means:
1. **Email confirmation is required** but email not confirmed
2. **Invalid credentials**
3. **Email provider not configured**

## Quick Fix: Disable Email Confirmation

### Step 1: Go to Supabase Dashboard
1. Open: https://ayleiamfxchlqyaxklnq.supabase.co
2. Go to **Authentication** → **Providers**
3. Click on **Email** provider

### Step 2: Disable Email Confirmation
1. Scroll down to **Email Settings**
2. Find **"Confirm email"** toggle
3. **Turn it OFF** (for development)
4. Click **Save**

### Step 3: Confirm Existing Users (If needed)
Run this SQL in Supabase SQL Editor:

```sql
-- Manually confirm all existing users
UPDATE auth.users 
SET email_confirmed_at = NOW(), 
    confirmed_at = NOW()
WHERE email_confirmed_at IS NULL;
```

### Step 4: Test Login
1. Go to http://localhost:3001/login
2. Try logging in with: `sajeevs0706@gmail.com`
3. Use your password

## Alternative: Create New User via SQL

If you want to create a test user directly:

```sql
-- This requires running from Supabase SQL Editor with appropriate permissions
-- Contact Supabase support or use the Auth UI
```

## Verify User Status

Run this to check user confirmation status:

```bash
cd StudyHelper-Backend
python -c "
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

conn = psycopg2.connect(
    host=os.getenv('DB_HOST'),
    database=os.getenv('DB_NAME'),
    user=os.getenv('DB_USER'),
    password=os.getenv('DB_PASSWORD'),
    port=os.getenv('DB_PORT')
)
cursor = conn.cursor()

cursor.execute('''
    SELECT email, email_confirmed_at, confirmed_at
    FROM auth.users;
''')

for row in cursor.fetchall():
    print(f'Email: {row[0]}')
    print(f'  Email Confirmed: {row[1]}')
    print(f'  User Confirmed: {row[2]}')
    print()
    
cursor.close()
conn.close()
"
```

## Development Mode Settings

For development, recommended Supabase Auth settings:
- ✅ **Email Confirmation**: OFF
- ✅ **Email Auth**: Enabled
- ✅ **Auto-confirm users**: ON

## Production Settings

For production:
- ✅ **Email Confirmation**: ON
- ✅ **Email provider**: Configured (SendGrid, AWS SES, etc.)
- ✅ **Email templates**: Customized
