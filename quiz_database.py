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
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None
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

def save_quiz_to_database(topic: str, questions_data: List[Dict], performance_report: str = None) -> Dict[str, Any]:
    """
    Save a complete quiz to the database with all questions and options using raw SQL
    """
    conn = get_db_connection()
    if not conn:
        # Fallback to Supabase client
        if supabase:
            print("Using Supabase client fallback for save_quiz_to_database")
            return save_quiz_to_database_supabase(topic, questions_data, performance_report)
        else:
            return {"success": False, "error": "Database connection failed and no Supabase fallback available"}
    
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Begin transaction
        cursor.execute("BEGIN;")
        
        # 1. Create quiz record
        quiz_insert_sql = """
            INSERT INTO quizzes (topic, performance_report) 
            VALUES (%s, %s) 
            RETURNING quiz_id;
        """
        cursor.execute(quiz_insert_sql, (topic[:255], performance_report))
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
        conn.close()

def save_quiz_to_database_supabase(topic: str, questions_data: List[Dict], performance_report: str = None) -> Dict[str, Any]:
    """
    Fallback function to save quiz using Supabase client
    """
    try:
        # Create quiz record
        quiz_result = supabase.table("quizzes").insert({
            "topic": topic[:255],
            "performance_report": performance_report
        }).execute()
        
        if not quiz_result.data:
            return {"success": False, "error": "Failed to create quiz record"}
        
        quiz_id = quiz_result.data[0]["quiz_id"]
        
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
        return {"success": False, "error": f"Supabase error: {str(e)}"}

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
            SELECT quiz_id, topic, performance_report 
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

def save_user_quiz_attempt(user_id: int, quiz_id: int, doc_id: int, user_answers: List[Dict], 
                          total_marks: int, score: int) -> Dict[str, Any]:
    """
    Save user's quiz attempt and answers using raw SQL
    """
    conn = get_db_connection()
    if not conn:
        # Fallback to Supabase client
        if supabase:
            print("Using Supabase client fallback for save_user_quiz_attempt")
            return save_user_quiz_attempt_supabase(user_id, quiz_id, doc_id, user_answers, total_marks, score)
        else:
            return {"success": False, "error": "Database connection failed"}
    
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Begin transaction
        cursor.execute("BEGIN;")
        
        # Calculate percentage
        percentage = (score / total_marks) * 100 if total_marks > 0 else 0
        
        # Check if this user has already taken this quiz
        existing_attempt_sql = """
            SELECT user_quiz_id FROM user_quizzes 
            WHERE user_id = %s AND quiz_id = %s AND doc_id = %s;
        """
        cursor.execute(existing_attempt_sql, (user_id, quiz_id, doc_id))
        existing = cursor.fetchone()
        
        if existing:
            # Update existing attempt
            user_quiz_id = existing['user_quiz_id']
            
            update_attempt_sql = """
                UPDATE user_quizzes 
                SET taken_date = %s, total_marks = %s, score = %s, percentage = %s
                WHERE user_quiz_id = %s;
            """
            cursor.execute(update_attempt_sql, (
                date.today().isoformat(), total_marks, score, round(percentage, 2), user_quiz_id
            ))
            
            # Delete old answers
            delete_answers_sql = "DELETE FROM user_answers WHERE user_quiz_id = %s;"
            cursor.execute(delete_answers_sql, (user_quiz_id,))
            
        else:
            # Create new attempt
            insert_attempt_sql = """
                INSERT INTO user_quizzes (user_id, quiz_id, doc_id, taken_date, total_marks, score, percentage)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING user_quiz_id;
            """
            cursor.execute(insert_attempt_sql, (
                user_id, quiz_id, doc_id, date.today().isoformat(), 
                total_marks, score, round(percentage, 2)
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
        conn.close()

def save_user_quiz_attempt_supabase(user_id: int, quiz_id: int, doc_id: int, user_answers: List[Dict], 
                                   total_marks: int, score: int) -> Dict[str, Any]:
    """
    Fallback function to save user's quiz attempt using Supabase client
    """
    try:
        # Calculate percentage
        percentage = (score / total_marks) * 100 if total_marks > 0 else 0
        
        # Check if this user has already taken this quiz
        existing_attempt = supabase.table("user_quizzes").select("user_quiz_id").eq("user_id", user_id).eq("quiz_id", quiz_id).eq("doc_id", doc_id).execute()
        
        if existing_attempt.data:
            # Update existing attempt
            user_quiz_id = existing_attempt.data[0]["user_quiz_id"]
            
            update_result = supabase.table("user_quizzes").update({
                "taken_date": date.today().isoformat(),
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
                "doc_id": doc_id,
                "taken_date": date.today().isoformat(),
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

def get_user_quiz_attempts(user_id: int, limit: int = 50) -> Dict[str, Any]:
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
                uq.taken_date,
                uq.total_marks,
                uq.score,
                uq.percentage,
                q.quiz_id,
                q.topic,
                q.performance_report
            FROM user_quizzes uq
            JOIN quizzes q ON uq.quiz_id = q.quiz_id
            WHERE uq.user_id = %s
            ORDER BY uq.taken_date DESC
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
                "taken_date": attempt['taken_date'],
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

def get_user_quiz_attempts_supabase(user_id: int, limit: int = 50) -> Dict[str, Any]:
    """
    Fallback function to get user's quiz attempts using Supabase client
    """
    try:
        # Get user quiz attempts first
        attempts_result = supabase.table("user_quizzes").select("""
            user_quiz_id,
            taken_date,
            total_marks,
            score,
            percentage,
            quiz_id
        """).eq("user_id", user_id).order("taken_date", desc=True).limit(limit).execute()
        
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
                    "taken_date": attempt['taken_date'],
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

def create_dummy_document(title: str, content_type: str = "quiz_generated") -> int:
    """
    Create a dummy document record for quiz generation using raw SQL
    """
    conn = get_db_connection()
    if not conn:
        # Fallback to Supabase client
        if supabase:
            print("Using Supabase client fallback for create_dummy_document")
            return create_dummy_document_supabase(title, content_type)
        else:
            return None
    
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Create dummy document
        doc_insert_sql = """
            INSERT INTO documents (topic, resources, media)
            VALUES (%s, %s, %s)
            RETURNING doc_id;
        """
        
        media_data = {
            "content_type": content_type,
            "generated_for": "quiz",
            "created_at": datetime.now().isoformat()
        }
        
        cursor.execute(doc_insert_sql, (
            title[:255],
            json.dumps([]),  # Empty resources array
            json.dumps(media_data)  # Media as JSON
        ))
        
        result = cursor.fetchone()
        doc_id = result['doc_id'] if result else None
        
        return doc_id
        
    except Exception as e:
        print(f"Error creating dummy document: {str(e)}")
        return None
    finally:
        cursor.close()
        conn.close()

def create_dummy_document_supabase(title: str, content_type: str = "quiz_generated") -> int:
    """
    Fallback function to create dummy document using Supabase client
    """
    try:
        media_data = {
            "content_type": content_type,
            "generated_for": "quiz",
            "created_at": datetime.now().isoformat()
        }
        
        result = supabase.table("documents").insert({
            "topic": title[:255],
            "resources": [],  # Empty resources array
            "media": media_data  # Media as JSON
        }).execute()
        
        if result.data:
            return result.data[0]["doc_id"]
        else:
            return None
        
    except Exception as e:
        print(f"Error creating dummy document with Supabase: {str(e)}")
        return None

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
