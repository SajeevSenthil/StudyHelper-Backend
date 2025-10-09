# Fix Quiz Generation Issues

## Issues Found:
1. ✅ GPT-4o-mini already configured in `quiz_generator.py`
2. ❌ Missing `create_complete_quiz` stored procedure in database
3. ❌ Database transaction error

## Solution Steps:

### Step 1: Run SQL Setup
Run the file `complete_setup.sql` in your Supabase SQL Editor:

1. Go to: https://ayleiamfxchlqyaxklnq.supabase.co
2. Navigate to **SQL Editor**
3. Click **New Query**
4. Copy and paste the contents of `complete_setup.sql`
5. Click **Run**

This will create all necessary functions:
- `create_complete_quiz()` - Creates quiz with questions
- `save_quiz_attempt()` - Saves quiz results
- `get_quiz_with_questions()` - Retrieves quiz data
- `get_user_performance_summary()` - Gets user stats

### Step 2: Verify Functions Created
Run this in SQL Editor to verify:

```sql
SELECT routine_name, routine_type
FROM information_schema.routines
WHERE routine_schema = 'public'
AND routine_name LIKE '%quiz%'
ORDER BY routine_name;
```

You should see at least:
- create_complete_quiz
- save_quiz_attempt
- get_quiz_with_questions
- get_user_performance_summary

### Step 3: Restart Backend
The backend server will auto-reload, or manually restart:

```bash
cd StudyHelper-Backend
# Kill existing process
taskkill //F //IM python.exe

# Restart
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Step 4: Test Quiz Generation
1. Go to your frontend
2. Try generating a quiz from a topic or document
3. Should now work with GPT-4o-mini

## Quiz Generation Features:
- ✅ Uses GPT-4o-mini for cost-effective generation
- ✅ Generates 10 questions by default
- ✅ Multiple choice with 4 options
- ✅ Includes explanations
- ✅ Saves to Supabase with proper user association

## Troubleshooting:
If you still get errors:
1. Check OpenAI API key is valid in `.env`
2. Verify stored procedures exist in database
3. Check backend logs for specific errors
