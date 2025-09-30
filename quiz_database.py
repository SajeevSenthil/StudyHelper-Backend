import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
from typing import Dict, Any, Optional, List
from datetime import datetime, date
import json

# Load environment variables
load_dotenv()

# Import Supabase as fallback
try:
    from supabase import create_client, Client
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY")
    SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
    
    # Use service key if available to bypass RLS, otherwise use anon key
    if SUPABASE_SERVICE_KEY and SUPABASE_URL:
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
        print("[DEBUG] Quiz database using Supabase service key (bypasses RLS)")
    elif SUPABASE_URL and SUPABASE_KEY:
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        print("[DEBUG] Quiz database using Supabase anon key")
    else:
        supabase = None
except ImportError:
    supabase = None

# Database connection parameters
DATABASE_URL = os.getenv("DATABASE_URL")  # Full PostgreSQL connection string
# Or individual parameters:
DB_HOST = os.getenv("DB_HOST")
DB_NAME = os.getenv("DB_NAME") 
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_PORT = os.getenv("DB_PORT", "5432")

def get_db_connection():
    """Create and return a database connection"""
    try:
        if DATABASE_URL:
            conn = psycopg2.connect(DATABASE_URL)
        else:
            conn = psycopg2.connect(
                host=DB_HOST,
                database=DB_NAME,
                user=DB_USER,
                password=DB_PASSWORD,
                port=DB_PORT
            )
        return conn
    except Exception as e:
        print(f"PostgreSQL connection error: {str(e)}")
        print("Falling back to Supabase client for database operations...")
        return None

def save_quiz_to_database(topic: str, questions_data: List[Dict], performance_report: str = None, user_id: str = None) -> Dict[str, Any]:
    """
    Save a complete quiz to the database using stored procedure for better performance
    """
    conn = get_db_connection()
    if not conn:
        # Fallback to Supabase client
        if supabase:
            print("Using Supabase client fallback for save_quiz_to_database")
            return save_quiz_to_database_supabase(topic, questions_data, performance_report, user_id)
        else:
            return {"success": False, "error": "Database connection failed and no Supabase fallback available"}
    
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Use demo user if no user_id provided
        if not user_id:
            user_id = "550e8400-e29b-41d4-a716-446655440000"
        
        # Convert questions data to JSONB format
        questions_json = json.dumps(questions_data)
        
        # Call stored procedure for creating complete quiz
        cursor.execute("""
            SELECT create_complete_quiz(%s, %s, %s, %s::jsonb) as result;
        """, (user_id, topic[:255], performance_report, questions_json))
        
        result = cursor.fetchone()['result']
        
        # Return the result from stored procedure
        return result
        
    except Exception as e:
        print(f"Error calling stored procedure: {str(e)}")
        # Fallback to original manual method if stored procedure fails
        return save_quiz_to_database_manual(topic, questions_data, performance_report, user_id, conn)
    finally:
        cursor.close()
        conn.close()

def save_quiz_to_database_manual(topic: str, questions_data: List[Dict], performance_report: str = None, user_id: str = None, conn=None) -> Dict[str, Any]:
    """
    Fallback manual method for saving quiz (original implementation)
    """
    should_close_conn = False
    if not conn:
        conn = get_db_connection()
        should_close_conn = True
        if not conn:
            return {"success": False, "error": "Database connection failed"}
    
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Begin transaction
        cursor.execute("BEGIN;")
        
        # Use demo user if no user_id provided
        if not user_id:
            user_id = "550e8400-e29b-41d4-a716-446655440000"
        
        # 1. Create quiz record
        quiz_insert_sql = """
            INSERT INTO quizzes (user_id, topic, performance_report, total_questions) 
            VALUES (%s, %s, %s, %s) 
            RETURNING quiz_id;
        """
        cursor.execute(quiz_insert_sql, (user_id, topic[:255], performance_report, len(questions_data)))
        quiz_result = cursor.fetchone()
        quiz_id = quiz_result['quiz_id']
        
        # 2. Save each question and its options
        for order, question_data in enumerate(questions_data, 1):
            # Insert question
            question_insert_sql = """
                INSERT INTO questions (question_text) 
                VALUES (%s) 
                RETURNING question_id;
            """
            cursor.execute(question_insert_sql, (question_data["question_text"],))
            question_result = cursor.fetchone()
            question_id = question_result['question_id']
            
            # Insert options for this question
            options_insert_sql = """
                INSERT INTO options (question_id, option_a, option_b, option_c, option_d, correct_option)
                VALUES (%s, %s, %s, %s, %s, %s);
            """
            cursor.execute(options_insert_sql, (
                question_id,
                question_data["option_a"],
                question_data["option_b"],
                question_data["option_c"],
                question_data["option_d"],
                question_data["correct_option"]
            ))
            
            # Link question to quiz
            quiz_question_insert_sql = """
                INSERT INTO quiz_questions (quiz_id, question_id, question_order, max_marks)
                VALUES (%s, %s, %s, %s);
            """
            cursor.execute(quiz_question_insert_sql, (quiz_id, question_id, order, 1))
        
        # Commit transaction
        cursor.execute("COMMIT;")
        
        return {
            "success": True,
            "quiz_id": quiz_id,
            "message": "Quiz saved successfully",
            "total_questions": len(questions_data)
        }
        
    except Exception as e:
        cursor.execute("ROLLBACK;")
        return {"success": False, "error": f"Database error: {str(e)}"}
    finally:
        cursor.close()
        if should_close_conn:
            conn.close()

def save_quiz_to_database_supabase(topic: str, questions_data: List[Dict], performance_report: str = None, user_id: str = None) -> Dict[str, Any]:
    """
    Fallback function to save quiz using Supabase client
    """
    try:
        # Use demo user if no user_id provided
        if not user_id:
            user_id = "550e8400-e29b-41d4-a716-446655440000"
        
        print(f"[DEBUG] Attempting to save quiz for user_id: {user_id}")
        
        # Create quiz record directly (service key should bypass RLS)
        print(f"[DEBUG] Creating quiz with topic: {topic[:50]}...")
        quiz_result = supabase.table("quizzes").insert({
            "user_id": user_id,
            "topic": topic[:255],
            "performance_report": performance_report,
            "total_questions": len(questions_data)
        }).execute()
        
        if not quiz_result.data:
            return {"success": False, "error": "Failed to create quiz record - no data returned"}
        
        quiz_id = quiz_result.data[0]["quiz_id"]
        print(f"[DEBUG] Quiz created with ID: {quiz_id}")
        
        # Save each question and its options
        for order, question_data in enumerate(questions_data, 1):
            # Insert question
            question_result = supabase.table("questions").insert({
                "question_text": question_data["question_text"]
            }).execute()
            
            if not question_result.data:
                return {"success": False, "error": f"Failed to save question {order}"}
            
            question_id = question_result.data[0]["question_id"]
            
            # Insert options for this question
            options_result = supabase.table("options").insert({
                "question_id": question_id,
                "option_a": question_data["option_a"],
                "option_b": question_data["option_b"],
                "option_c": question_data["option_c"],
                "option_d": question_data["option_d"],
                "correct_option": question_data["correct_option"]
            }).execute()
            
            if not options_result.data:
                return {"success": False, "error": f"Failed to save options for question {order}"}
            
            # Link question to quiz
            quiz_question_result = supabase.table("quiz_questions").insert({
                "quiz_id": quiz_id,
                "question_id": question_id,
                "question_order": order,
                "max_marks": 1
            }).execute()
            
            if not quiz_question_result.data:
                return {"success": False, "error": f"Failed to link question {order} to quiz"}
        
        return {
            "success": True,
            "quiz_id": quiz_id,
            "message": "Quiz saved successfully using Supabase fallback",
            "total_questions": len(questions_data)
        }
        
    except Exception as e:
        error_details = str(e)
        print(f"[ERROR] Supabase quiz save error: {error_details}")
        
        # Provide more specific error messages
        if "violates foreign key constraint" in error_details and "user_id" in error_details:
            return {"success": False, "error": f"Demo user does not exist in auth.users table. Please run fix_demo_user.sql script. Details: {error_details}"}
        elif "violates row-level security policy" in error_details:
            return {"success": False, "error": f"Row-level security policy violation. Please check RLS policies. Details: {error_details}"}
        else:
            return {"success": False, "error": f"Supabase error: {error_details}"}

def get_quiz_by_id(quiz_id: int) -> Optional[Dict[str, Any]]:
    """
    Retrieve a complete quiz with all questions and options using raw SQL
    """
    conn = get_db_connection()
    if not conn:
        # Fallback to Supabase client
        if supabase:
            print("Using Supabase client fallback for get_quiz_by_id")
            return get_quiz_by_id_supabase(quiz_id)
        else:
            return None
    
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        print(f"[DEBUG] Fetching quiz with ID: {quiz_id}")
        
        # Get quiz basic info
        quiz_select_sql = """
            SELECT quiz_id, user_id, topic, performance_report, total_questions, created_at 
            FROM quizzes 
            WHERE quiz_id = %s;
        """
        cursor.execute(quiz_select_sql, (quiz_id,))
        quiz_result = cursor.fetchone()
        
        if not quiz_result:
            print(f"No quiz found with ID: {quiz_id}")
            return None
        
        print(f"[DEBUG] Quiz response: {dict(quiz_result)}")
        
        # Get questions with options in proper order
        questions_select_sql = """
            SELECT 
                q.question_id,
                q.question_text,
                o.option_a,
                o.option_b, 
                o.option_c,
                o.option_d,
                o.correct_option,
                qq.question_order,
                qq.max_marks
            FROM questions q
            JOIN quiz_questions qq ON q.question_id = qq.question_id
            JOIN options o ON q.question_id = o.question_id
            WHERE qq.quiz_id = %s
            ORDER BY qq.question_order;
        """
        cursor.execute(questions_select_sql, (quiz_id,))
        questions_results = cursor.fetchall()
        
        if not questions_results:
            print(f"No questions found for quiz ID: {quiz_id}")
            return None
        
        # Format questions data
        questions = []
        for q in questions_results:
            questions.append({
                "question_id": q['question_id'],
                "question_text": q['question_text'],
                "option_a": q['option_a'],
                "option_b": q['option_b'],
                "option_c": q['option_c'],
                "option_d": q['option_d'],
                "correct_option": q['correct_option'],
                "question_order": q['question_order'],
                "max_marks": q['max_marks']
            })
        
        return {
            "quiz_id": quiz_result['quiz_id'],
            "topic": quiz_result['topic'],
            "performance_report": quiz_result['performance_report'],
            "questions": questions,
            "total_questions": len(questions)
        }
        
    except Exception as e:
        print(f"Error fetching quiz: {str(e)}")
        return None
    finally:
        cursor.close()
        conn.close()

def get_quiz_by_id_supabase(quiz_id: int) -> Optional[Dict[str, Any]]:
    """
    Fallback function to retrieve quiz using Supabase client
    """
    try:
        print(f"[DEBUG] Fetching quiz with ID: {quiz_id} using Supabase")
        
        # Get quiz basic info
        quiz_result = supabase.table("quizzes").select("quiz_id, topic, performance_report").eq("quiz_id", quiz_id).execute()
        
        if not quiz_result.data:
            print(f"No quiz found with ID: {quiz_id}")
            return None
        
        quiz_info = quiz_result.data[0]
        print(f"[DEBUG] Quiz response: {quiz_info}")
        
        # Get questions with options - Fix the complex join query
        # First get quiz_questions for this quiz
        quiz_questions_result = supabase.table("quiz_questions").select(
            "question_id, question_order, max_marks"
        ).eq("quiz_id", quiz_id).order("question_order").execute()
        
        if not quiz_questions_result.data:
            print(f"No questions found for quiz ID: {quiz_id}")
            return None
        
        questions = []
        for qq in quiz_questions_result.data:
            question_id = qq['question_id']
            
            # Get question text
            question_result = supabase.table("questions").select("question_text").eq("question_id", question_id).execute()
            if not question_result.data:
                continue
                
            # Get options for this question
            options_result = supabase.table("options").select(
                "option_a, option_b, option_c, option_d, correct_option"
            ).eq("question_id", question_id).execute()
            if not options_result.data:
                continue
            
            question_data = question_result.data[0]
            options_data = options_result.data[0]
            
            questions.append({
                "question_id": question_id,
                "question_text": question_data['question_text'],
                "option_a": options_data['option_a'],
                "option_b": options_data['option_b'],
                "option_c": options_data['option_c'],
                "option_d": options_data['option_d'],
                "correct_option": options_data['correct_option'],
                "question_order": qq['question_order'],
                "max_marks": qq['max_marks']
            })
        
        # Sort questions by order (just to be safe)
        questions.sort(key=lambda x: x['question_order'])
        
        return {
            "quiz_id": quiz_info['quiz_id'],
            "topic": quiz_info['topic'],
            "performance_report": quiz_info['performance_report'],
            "questions": questions,
            "total_questions": len(questions)
        }
        
    except Exception as e:
        print(f"Error fetching quiz with Supabase: {str(e)}")
        return None

def save_user_quiz_attempt(user_id: str, quiz_id: int, user_answers: List[Dict], 
                          total_marks: int, score: int) -> Dict[str, Any]:
    """
    Save user's quiz attempt and answers using stored procedure for better performance
    """
    conn = get_db_connection()
    if not conn:
        # Fallback to Supabase client
        if supabase:
            print("Using Supabase client fallback for save_user_quiz_attempt")
            return save_user_quiz_attempt_supabase(user_id, quiz_id, user_answers, total_marks, score)
        else:
            return {"success": False, "error": "Database connection failed"}
    
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Use demo user if no user_id provided
        if not user_id:
            user_id = "550e8400-e29b-41d4-a716-446655440000"
        
        # Convert answers to JSONB format
        answers_json = json.dumps(user_answers)
        
        # Call stored procedure for saving quiz attempt
        cursor.execute("""
            SELECT save_quiz_attempt(%s, %s, %s::jsonb, %s, %s) as result;
        """, (user_id, quiz_id, answers_json, total_marks, score))
        
        result = cursor.fetchone()['result']
        
        # Return the result from stored procedure
        return result
        
    except Exception as e:
        print(f"Error calling stored procedure for quiz attempt: {str(e)}")
        # Fallback to original manual method if stored procedure fails
        return save_user_quiz_attempt_manual(user_id, quiz_id, user_answers, total_marks, score, conn)
    finally:
        cursor.close()
        conn.close()

def save_user_quiz_attempt_manual(user_id: str, quiz_id: int, user_answers: List[Dict], 
                                 total_marks: int, score: int, conn=None) -> Dict[str, Any]:
    """
    Fallback manual method for saving quiz attempt (original implementation)
    """
    should_close_conn = False
    if not conn:
        conn = get_db_connection()
        should_close_conn = True
        if not conn:
            return {"success": False, "error": "Database connection failed"}
    
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Begin transaction
        cursor.execute("BEGIN;")
        
        # Use demo user if no user_id provided
        if not user_id:
            user_id = "550e8400-e29b-41d4-a716-446655440000"
        
        # Calculate percentage
        percentage = (score / total_marks) * 100 if total_marks > 0 else 0
        
        # Check if this user has already taken this quiz
        existing_attempt_sql = """
            SELECT user_quiz_id FROM user_quizzes 
            WHERE user_id = %s AND quiz_id = %s;
        """
        cursor.execute(existing_attempt_sql, (user_id, quiz_id))
        existing = cursor.fetchone()
        
        if existing:
            # Update existing attempt
            user_quiz_id = existing['user_quiz_id']
            
            update_attempt_sql = """
                UPDATE user_quizzes 
                SET total_marks = %s, score = %s, percentage = %s, completed_at = NOW()
                WHERE user_quiz_id = %s;
            """
            cursor.execute(update_attempt_sql, (
                total_marks, score, round(percentage, 2), user_quiz_id
            ))
            
            # Delete old answers
            delete_answers_sql = "DELETE FROM user_answers WHERE user_quiz_id = %s;"
            cursor.execute(delete_answers_sql, (user_quiz_id,))
            
        else:
            # Create new attempt
            insert_attempt_sql = """
                INSERT INTO user_quizzes (user_id, quiz_id, total_marks, score, percentage)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING user_quiz_id;
            """
            cursor.execute(insert_attempt_sql, (
                user_id, quiz_id, total_marks, score, round(percentage, 2)
            ))
            result = cursor.fetchone()
            user_quiz_id = result['user_quiz_id']
        
        # Save each answer
        for answer_data in user_answers:
            insert_answer_sql = """
                INSERT INTO user_answers (user_quiz_id, question_id, selected_option, awarded_marks)
                VALUES (%s, %s, %s, %s);
            """
            cursor.execute(insert_answer_sql, (
                user_quiz_id,
                answer_data["question_id"],
                answer_data["selected_option"],
                answer_data["awarded_marks"]
            ))
        
        # Commit transaction
        cursor.execute("COMMIT;")
        
        return {
            "success": True,
            "user_quiz_id": user_quiz_id,
            "percentage": percentage,
            "message": "Quiz attempt saved successfully"
        }
        
    except Exception as e:
        cursor.execute("ROLLBACK;")
        return {"success": False, "error": f"Database error: {str(e)}"}
    finally:
        cursor.close()
        if should_close_conn:
            conn.close()

def save_user_quiz_attempt_supabase(user_id: str, quiz_id: int, user_answers: List[Dict], 
                                   total_marks: int, score: int) -> Dict[str, Any]:
    """
    Fallback function to save user's quiz attempt using Supabase client
    """
    try:
        # Use demo user if no user_id provided
        if not user_id:
            user_id = "550e8400-e29b-41d4-a716-446655440000"
        
        # Calculate percentage
        percentage = (score / total_marks) * 100 if total_marks > 0 else 0
        
        # Check if this user has already taken this quiz
        existing_attempt = supabase.table("user_quizzes").select("user_quiz_id").eq("user_id", user_id).eq("quiz_id", quiz_id).execute()
        
        if existing_attempt.data:
            # Update existing attempt
            user_quiz_id = existing_attempt.data[0]["user_quiz_id"]
            
            update_result = supabase.table("user_quizzes").update({
                "total_marks": total_marks,
                "score": score,
                "percentage": round(percentage, 2)
            }).eq("user_quiz_id", user_quiz_id).execute()
            
            if not update_result.data:
                return {"success": False, "error": "Failed to update quiz attempt"}
            
            # Delete old answers
            supabase.table("user_answers").delete().eq("user_quiz_id", user_quiz_id).execute()
            
        else:
            # Create new attempt
            insert_result = supabase.table("user_quizzes").insert({
                "user_id": user_id,
                "quiz_id": quiz_id,
                "total_marks": total_marks,
                "score": score,
                "percentage": round(percentage, 2)
            }).execute()
            
            if not insert_result.data:
                return {"success": False, "error": "Failed to create quiz attempt"}
            
            user_quiz_id = insert_result.data[0]["user_quiz_id"]
        
        # Save each answer
        for answer_data in user_answers:
            answer_result = supabase.table("user_answers").insert({
                "user_quiz_id": user_quiz_id,
                "question_id": answer_data["question_id"],
                "selected_option": answer_data["selected_option"],
                "awarded_marks": answer_data["awarded_marks"]
            }).execute()
            
            if not answer_result.data:
                return {"success": False, "error": f"Failed to save answer for question {answer_data['question_id']}"}
        
        return {
            "success": True,
            "user_quiz_id": user_quiz_id,
            "percentage": percentage,
            "message": "Quiz attempt saved successfully using Supabase fallback"
        }
        
    except Exception as e:
        return {"success": False, "error": f"Supabase error: {str(e)}"}

def get_user_quiz_attempts(user_id: str, limit: int = 50) -> Dict[str, Any]:
    """
    Get user's quiz attempts with performance data using raw SQL
    """
    conn = get_db_connection()
    if not conn:
        # Fallback to Supabase client
        if supabase:
            print("Using Supabase client fallback for get_user_quiz_attempts")
            return get_user_quiz_attempts_supabase(user_id, limit)
        else:
            return {"success": False, "error": "Database connection failed", "attempts": [], "count": 0}
    
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        attempts_select_sql = """
            SELECT 
                uq.user_quiz_id,
                uq.completed_at,
                uq.total_marks,
                uq.score,
                uq.percentage,
                q.quiz_id,
                q.topic,
                q.performance_report
            FROM user_quizzes uq
            JOIN quizzes q ON uq.quiz_id = q.quiz_id
            WHERE uq.user_id = %s
            ORDER BY uq.completed_at DESC
            LIMIT %s;
        """
        cursor.execute(attempts_select_sql, (user_id, limit))
        attempts_data = cursor.fetchall()
        
        attempts = []
        for attempt in attempts_data:
            attempts.append({
                "user_quiz_id": attempt['user_quiz_id'],
                "quiz_id": attempt['quiz_id'],
                "topic": attempt['topic'],
                "completed_at": attempt['completed_at'],
                "total_marks": attempt['total_marks'],
                "score": attempt['score'],
                "percentage": float(attempt['percentage']) if attempt['percentage'] else 0.0,
                "performance_report": attempt['performance_report']
            })
        
        return {
            "success": True,
            "attempts": attempts,
            "count": len(attempts)
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": f"Database error: {str(e)}",
            "attempts": [],
            "count": 0
        }
    finally:
        cursor.close()
        conn.close()

def get_user_quiz_attempts_supabase(user_id: str, limit: int = 50) -> Dict[str, Any]:
    """
    Fallback function to get user's quiz attempts using Supabase client
    """
    try:
        # Get user quiz attempts first
        attempts_result = supabase.table("user_quizzes").select("""
            user_quiz_id,
            completed_at,
            total_marks,
            score,
            percentage,
            quiz_id
        """).eq("user_id", user_id).order("completed_at", desc=True).limit(limit).execute()
        
        if not attempts_result.data:
            return {
                "success": True,
                "attempts": [],
                "count": 0
            }
        
        attempts = []
        for attempt in attempts_result.data:
            # Get quiz information for each attempt
            quiz_result = supabase.table("quizzes").select(
                "topic, performance_report"
            ).eq("quiz_id", attempt['quiz_id']).execute()
            
            if quiz_result.data:
                quiz_info = quiz_result.data[0]
                attempts.append({
                    "user_quiz_id": attempt['user_quiz_id'],
                    "quiz_id": attempt['quiz_id'],
                    "topic": quiz_info['topic'],
                    "completed_at": attempt['completed_at'],
                    "total_marks": attempt['total_marks'],
                    "score": attempt['score'],
                    "percentage": float(attempt['percentage']) if attempt['percentage'] else 0.0,
                    "performance_report": quiz_info['performance_report']
                })
        
        return {
            "success": True,
            "attempts": attempts,
            "count": len(attempts)
        }
        
    except Exception as e:
        print(f"Error fetching user quiz attempts with Supabase: {str(e)}")
        return {
            "success": False,
            "error": f"Supabase error: {str(e)}",
            "attempts": [],
            "count": 0
        }

def get_quiz_attempt_details(user_quiz_id: int) -> Optional[Dict[str, Any]]:
    """
    Get detailed information about a specific quiz attempt using raw SQL
    """
    conn = get_db_connection()
    if not conn:
        # Fallback to Supabase client
        if supabase:
            print("Using Supabase client fallback for get_quiz_attempt_details")
            return get_quiz_attempt_details_supabase(user_quiz_id)
        else:
            return None
    
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Get user quiz info with quiz details
        attempt_info_sql = """
            SELECT 
                uq.user_quiz_id,
                uq.taken_date,
                uq.total_marks,
                uq.score,
                uq.percentage,
                q.quiz_id,
                q.topic,
                q.performance_report
            FROM user_quizzes uq
            JOIN quizzes q ON uq.quiz_id = q.quiz_id
            WHERE uq.user_quiz_id = %s;
        """
        cursor.execute(attempt_info_sql, (user_quiz_id,))
        attempt_info = cursor.fetchone()
        
        if not attempt_info:
            return None
        
        quiz_id = attempt_info['quiz_id']
        
        # Get detailed question results with user answers
        details_sql = """
            SELECT 
                quest.question_id,
                quest.question_text,
                opt.option_a,
                opt.option_b,
                opt.option_c,
                opt.option_d,
                opt.correct_option,
                ua.selected_option,
                ua.awarded_marks
            FROM user_answers ua
            JOIN questions quest ON ua.question_id = quest.question_id
            JOIN options opt ON quest.question_id = opt.question_id
            WHERE ua.user_quiz_id = %s;
        """
        cursor.execute(details_sql, (user_quiz_id,))
        answer_details = cursor.fetchall()
        
        # Format detailed answers
        detailed_answers = []
        for detail in answer_details:
            detailed_answers.append({
                "question_id": detail['question_id'],
                "question_text": detail['question_text'],
                "option_a": detail['option_a'],
                "option_b": detail['option_b'],
                "option_c": detail['option_c'],
                "option_d": detail['option_d'],
                "correct_option": detail['correct_option'],
                "user_selected": detail['selected_option'],
                "awarded_marks": detail['awarded_marks'],
                "is_correct": detail['selected_option'] == detail['correct_option']
            })
        
        return {
            "user_quiz_id": user_quiz_id,
            "quiz_id": quiz_id,
            "topic": attempt_info['topic'],
            "taken_date": attempt_info['taken_date'],
            "total_marks": attempt_info['total_marks'],
            "score": attempt_info['score'],
            "percentage": float(attempt_info['percentage']) if attempt_info['percentage'] else 0.0,
            "performance_report": attempt_info['performance_report'],
            "detailed_answers": detailed_answers
        }
        
    except Exception as e:
        print(f"Error fetching quiz attempt details: {str(e)}")
        return None
    finally:
        cursor.close()
        conn.close()

def get_quiz_attempt_details_supabase(user_quiz_id: int) -> Optional[Dict[str, Any]]:
    """
    Fallback function to get detailed quiz attempt information using Supabase client
    """
    try:
        # Get user quiz info first
        attempt_result = supabase.table("user_quizzes").select("""
            user_quiz_id,
            taken_date,
            total_marks,
            score,
            percentage,
            quiz_id
        """).eq("user_quiz_id", user_quiz_id).execute()
        
        if not attempt_result.data:
            return None
        
        attempt_info = attempt_result.data[0]
        quiz_id = attempt_info['quiz_id']
        
        # Get quiz information
        quiz_result = supabase.table("quizzes").select(
            "topic, performance_report"
        ).eq("quiz_id", quiz_id).execute()
        
        if not quiz_result.data:
            return None
        
        quiz_info = quiz_result.data[0]
        
        # Get detailed question results with user answers
        answers_result = supabase.table("user_answers").select("""
            question_id,
            selected_option,
            awarded_marks
        """).eq("user_quiz_id", user_quiz_id).execute()
        
        # Format detailed answers
        detailed_answers = []
        for detail in answers_result.data:
            question_id = detail['question_id']
            
            # Get question text
            question_result = supabase.table("questions").select("question_text").eq("question_id", question_id).execute()
            if not question_result.data:
                continue
                
            # Get options for this question
            options_result = supabase.table("options").select(
                "option_a, option_b, option_c, option_d, correct_option"
            ).eq("question_id", question_id).execute()
            if not options_result.data:
                continue
            
            question_data = question_result.data[0]
            options_data = options_result.data[0]
            
            detailed_answers.append({
                "question_id": question_id,
                "question_text": question_data['question_text'],
                "option_a": options_data['option_a'],
                "option_b": options_data['option_b'],
                "option_c": options_data['option_c'],
                "option_d": options_data['option_d'],
                "correct_option": options_data['correct_option'],
                "user_selected": detail['selected_option'],
                "awarded_marks": detail['awarded_marks'],
                "is_correct": detail['selected_option'] == options_data['correct_option']
            })
        
        return {
            "user_quiz_id": user_quiz_id,
            "quiz_id": quiz_id,
            "topic": quiz_info['topic'],
            "taken_date": attempt_info['taken_date'],
            "total_marks": attempt_info['total_marks'],
            "score": attempt_info['score'],
            "percentage": float(attempt_info['percentage']) if attempt_info['percentage'] else 0.0,
            "performance_report": quiz_info['performance_report'],
            "detailed_answers": detailed_answers
        }
        
    except Exception as e:
        print(f"Error fetching quiz attempt details with Supabase: {str(e)}")
        return None

# ============================================================================
# ANALYTICS FUNCTIONS USING STORED PROCEDURES
# ============================================================================

def get_quiz_analytics(quiz_id: int) -> Optional[Dict[str, Any]]:
    """
    Get detailed analytics for a quiz using stored procedure
    """
    conn = get_db_connection()
    if not conn:
        # Fallback to Supabase client
        if supabase:
            print("Using Supabase client fallback for get_quiz_analytics")
            return get_quiz_analytics_supabase(quiz_id)
        else:
            return None
    
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Call stored procedure for quiz analytics
        cursor.execute("SELECT get_quiz_analytics(%s) as analytics;", (quiz_id,))
        result = cursor.fetchone()
        
        if result and result['analytics']:
            return result['analytics']
        
        return None
        
    except Exception as e:
        print(f"Error getting quiz analytics: {str(e)}")
        return None
    finally:
        cursor.close()
        conn.close()

def get_quiz_analytics_supabase(quiz_id: int) -> Optional[Dict[str, Any]]:
    """
    Fallback function to get quiz analytics using Supabase client
    """
    try:
        # Get basic quiz info
        quiz_result = supabase.table("quizzes").select("quiz_id, topic").eq("quiz_id", quiz_id).execute()
        if not quiz_result.data:
            return None
        
        # Get user attempts for this quiz
        attempts_result = supabase.table("user_quizzes").select(
            "user_quiz_id, score, total_marks, percentage, user_id"
        ).eq("quiz_id", quiz_id).execute()
        
        attempts = attempts_result.data
        total_attempts = len(attempts)
        
        if total_attempts == 0:
            return {
                "quiz_id": quiz_id,
                "total_attempts": 0,
                "average_score": 0,
                "highest_score": 0,
                "lowest_score": 0
            }
        
        # Calculate statistics
        percentages = [float(attempt['percentage']) for attempt in attempts]
        
        return {
            "quiz_id": quiz_id,
            "total_attempts": total_attempts,
            "average_score": round(sum(percentages) / len(percentages), 2),
            "highest_score": max(percentages),
            "lowest_score": min(percentages),
            "unique_users": len(set(attempt['user_id'] for attempt in attempts))
        }
        
    except Exception as e:
        print(f"Error getting quiz analytics with Supabase: {str(e)}")
        return None

def get_user_performance_summary(user_id: str) -> Optional[Dict[str, Any]]:
    """
    Get comprehensive user performance summary using stored procedure
    """
    conn = get_db_connection()
    if not conn:
        # Fallback to Supabase client
        if supabase:
            print("Using Supabase client fallback for get_user_performance_summary")
            return get_user_performance_summary_supabase(user_id)
        else:
            return None
    
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Call stored procedure for user performance summary
        cursor.execute("SELECT get_user_performance_summary(%s) as performance;", (user_id,))
        result = cursor.fetchone()
        
        if result and result['performance']:
            return result['performance']
        
        return None
        
    except Exception as e:
        print(f"Error getting user performance summary: {str(e)}")
        return None
    finally:
        cursor.close()
        conn.close()

def get_user_performance_summary_supabase(user_id: str) -> Optional[Dict[str, Any]]:
    """
    Fallback function to get user performance summary using Supabase client
    """
    try:
        # Get all user quiz attempts
        attempts_result = supabase.table("user_quizzes").select(
            "user_quiz_id, quiz_id, score, total_marks, percentage, completed_at"
        ).eq("user_id", user_id).order("completed_at", desc=True).execute()
        
        attempts = attempts_result.data
        
        if not attempts:
            return {
                "user_id": user_id,
                "total_quizzes": 0,
                "average_score": 0,
                "highest_score": 0,
                "total_questions_answered": 0,
                "correct_answers": 0,
                "accuracy_rate": 0
            }
        
        # Calculate statistics
        total_quizzes = len(attempts)
        percentages = [float(attempt['percentage']) for attempt in attempts]
        total_questions = sum(attempt['total_marks'] for attempt in attempts)
        correct_answers = sum(attempt['score'] for attempt in attempts)
        
        return {
            "user_id": user_id,
            "total_quizzes": total_quizzes,
            "average_score": round(sum(percentages) / len(percentages), 2),
            "highest_score": max(percentages),
            "total_questions_answered": total_questions,
            "correct_answers": correct_answers,
            "accuracy_rate": round((correct_answers / total_questions) * 100, 2) if total_questions > 0 else 0,
            "recent_attempts": attempts[:5]  # Last 5 attempts
        }
        
    except Exception as e:
        print(f"Error getting user performance summary with Supabase: {str(e)}")
        return None

def search_documents_advanced(user_id: str, search_term: str, limit: int = 20, offset: int = 0) -> Optional[Dict[str, Any]]:
    """
    Advanced document search using stored procedure with full-text search
    """
    conn = get_db_connection()
    if not conn:
        # Fallback to basic search
        if supabase:
            print("Using Supabase client fallback for search_documents_advanced")
            return search_documents_basic_supabase(user_id, search_term, limit, offset)
        else:
            return None
    
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Call stored procedure for advanced search
        cursor.execute("""
            SELECT search_documents(%s, %s, %s, %s) as search_results;
        """, (user_id, search_term, limit, offset))
        
        result = cursor.fetchone()
        
        if result and result['search_results']:
            return result['search_results']
        
        return {"total_count": 0, "documents": []}
        
    except Exception as e:
        print(f"Error in advanced document search: {str(e)}")
        return None
    finally:
        cursor.close()
        conn.close()

def search_documents_basic_supabase(user_id: str, search_term: str, limit: int = 20, offset: int = 0) -> Optional[Dict[str, Any]]:
    """
    Basic document search using Supabase client (fallback)
    """
    try:
        # Simple text search in topic and summary
        documents_result = supabase.table("documents").select(
            "doc_id, topic, summary, keywords, created_at"
        ).eq("user_id", user_id).or_(
            f"topic.ilike.%{search_term}%,summary.ilike.%{search_term}%,keywords.ilike.%{search_term}%"
        ).range(offset, offset + limit - 1).execute()
        
        documents = documents_result.data
        
        return {
            "total_count": len(documents),
            "documents": documents
        }
        
    except Exception as e:
        print(f"Error in basic document search with Supabase: {str(e)}")
        return None

def cleanup_old_data(days_old: int = 90) -> Dict[str, Any]:
    """
    Cleanup old quiz attempts using stored procedure
    """
    conn = get_db_connection()
    if not conn:
        return {"success": False, "error": "Database connection failed"}
    
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Call stored procedure for cleanup
        cursor.execute("SELECT cleanup_old_quiz_attempts(%s) as cleanup_result;", (days_old,))
        result = cursor.fetchone()
        
        if result and result['cleanup_result']:
            return result['cleanup_result']
        
        return {"success": False, "error": "No result from cleanup procedure"}
        
    except Exception as e:
        return {"success": False, "error": f"Cleanup error: {str(e)}"}
    finally:
        cursor.close()
        conn.close()

# ============================================================================
# DOCUMENT MANAGEMENT WITH STORED PROCEDURES
# ============================================================================

def save_document_with_validation(user_id: str, topic: str, content: str, 
                                 summary: str = None, keywords: str = None, 
                                 file_url: str = None) -> Dict[str, Any]:
    """
    Save document with validation using stored procedure
    """
    conn = get_db_connection()
    if not conn:
        return {"success": False, "error": "Database connection failed"}
    
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Call stored procedure for document validation and saving
        cursor.execute("""
            SELECT save_document_with_validation(%s, %s, %s, %s, %s, %s) as save_result;
        """, (user_id, topic, content, summary, keywords, file_url))
        
        result = cursor.fetchone()
        
        if result and result['save_result']:
            return result['save_result']
        
        return {"success": False, "error": "No result from save procedure"}
        
    except Exception as e:
        return {"success": False, "error": f"Document save error: {str(e)}"}
    finally:
        cursor.close()
        conn.close()

# Note: create_dummy_document functions removed as they're not needed with new schema

if __name__ == "__main__":
    # Test the functions
    print("Testing quiz database functions...")
    
    # Test saving a quiz
    test_questions = [
        {
            "question_text": "What is Python?",
            "option_a": "A snake",
            "option_b": "A programming language",
            "option_c": "A movie",
            "option_d": "A car",
            "correct_option": "B"
        }
    ]
    
    result = save_quiz_to_database("Test Quiz", test_questions)
    print("Save result:", result)
