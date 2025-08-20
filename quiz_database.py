import os
from supabase import create_client, Client
from dotenv import load_dotenv
from typing import Dict, Any, Optional, List
from datetime import datetime, date
import json

# Load environment variables
load_dotenv()

# Initialize Supabase client
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def save_quiz_to_database(topic: str, questions_data: List[Dict], performance_report: str = None) -> Dict[str, Any]:
    """
    Save a complete quiz to the database with all questions and options
    """
    try:
        # 1. Create quiz record
        quiz_response = supabase.table("quizzes").insert({
            "topic": topic[:255],  # Ensure it fits in VARCHAR(255)
            "performance_report": performance_report
        }).execute()
        
        if not quiz_response.data:
            return {"success": False, "error": "Failed to create quiz record"}
        
        quiz_id = quiz_response.data[0]["quiz_id"]
        
        # 2. Save each question and its options
        for order, question_data in enumerate(questions_data, 1):
            # Insert question
            question_response = supabase.table("questions").insert({
                "question_text": question_data["question_text"]
            }).execute()
            
            if not question_response.data:
                return {"success": False, "error": f"Failed to save question {order}"}
            
            question_id = question_response.data[0]["question_id"]
            
            # Insert options for this question
            options_response = supabase.table("options").insert({
                "question_id": question_id,
                "option_a": question_data["option_a"],
                "option_b": question_data["option_b"],
                "option_c": question_data["option_c"],
                "option_d": question_data["option_d"],
                "correct_option": question_data["correct_option"]
            }).execute()
            
            if not options_response.data:
                return {"success": False, "error": f"Failed to save options for question {order}"}
            
            # Link question to quiz
            quiz_question_response = supabase.table("quiz_questions").insert({
                "quiz_id": quiz_id,
                "question_id": question_id,
                "question_order": order,
                "max_marks": 1  # Each question worth 1 mark
            }).execute()
            
            if not quiz_question_response.data:
                return {"success": False, "error": f"Failed to link question {order} to quiz"}
        
        return {
            "success": True,
            "quiz_id": quiz_id,
            "message": "Quiz saved successfully",
            "total_questions": len(questions_data)
        }
        
    except Exception as e:
        return {"success": False, "error": f"Database error: {str(e)}"}

def get_quiz_by_id(quiz_id: int) -> Optional[Dict[str, Any]]:
    """
    Retrieve a complete quiz with all questions and options
    """
    try:
        print(f"[DEBUG] Fetching quiz with ID: {quiz_id}")
        # Get quiz info
        quiz_response = supabase.table("quizzes").select("*").eq("quiz_id", quiz_id).execute()
        print(f"[DEBUG] Quiz response: {quiz_response.data}")
        if not quiz_response.data:
            print(f"No quiz found with ID: {quiz_id}")
            return None
        
        quiz = quiz_response.data[0]
        
        # Get question IDs for this quiz in order
        quiz_questions_response = supabase.table("quiz_questions").select("question_id, question_order, max_marks").eq("quiz_id", quiz_id).order("question_order").execute()
        
        if not quiz_questions_response.data:
            print(f"No questions found for quiz ID: {quiz_id}")
            return None
        
        questions = []
        for q_data in quiz_questions_response.data:
            question_id = q_data["question_id"]
            
            # Get question text
            question_response = supabase.table("questions").select("*").eq("question_id", question_id).execute()
            if not question_response.data:
                print(f"Question not found for ID: {question_id}")
                continue
                
            question = question_response.data[0]
            
            # Get options for this question
            options_response = supabase.table("options").select("*").eq("question_id", question_id).execute()
            if not options_response.data:
                print(f"Options not found for question ID: {question_id}")
                continue
                
            options = options_response.data[0]
            questions.append({
                "question_id": question_id,
                "question_text": question["question_text"],
                "option_a": options["option_a"],
                "option_b": options["option_b"],
                "option_c": options["option_c"],
                "option_d": options["option_d"],
                "correct_option": options["correct_option"],
                "question_order": q_data["question_order"],
                "max_marks": q_data["max_marks"]
            })
        
        return {
            "quiz_id": quiz["quiz_id"],
            "topic": quiz["topic"],
            "performance_report": quiz["performance_report"],
            "questions": questions,
            "total_questions": len(questions)
        }
        
    except Exception as e:
        print(f"Error fetching quiz: {str(e)}")
        return None

def save_user_quiz_attempt(user_id: int, quiz_id: int, doc_id: int, user_answers: List[Dict], 
                          total_marks: int, score: int) -> Dict[str, Any]:
    """
    Save user's quiz attempt and answers
    """
    try:
        # Calculate percentage
        percentage = (score / total_marks) * 100 if total_marks > 0 else 0
        
        # Check if this user has already taken this quiz
        existing_attempt = supabase.table("user_quizzes").select("*").eq("user_id", user_id).eq("quiz_id", quiz_id).eq("doc_id", doc_id).execute()
        
        if existing_attempt.data:
            # Update existing attempt instead of creating new one
            user_quiz_id = existing_attempt.data[0]["user_quiz_id"]
            
            # Update the existing attempt
            update_data = {
                "taken_date": date.today().isoformat(),
                "total_marks": total_marks,
                "score": score,
                "percentage": round(percentage, 2)
            }
            
            update_response = supabase.table("user_quizzes").update(update_data).eq("user_quiz_id", user_quiz_id).execute()
            
            if not update_response.data:
                return {"success": False, "error": "Failed to update existing quiz attempt"}
            
            # Delete old answers
            supabase.table("user_answers").delete().eq("user_quiz_id", user_quiz_id).execute()
            
        else:
            # Create new attempt
            quiz_attempt_data = {
                "user_id": user_id,
                "quiz_id": quiz_id,
                "doc_id": doc_id,
                "taken_date": date.today().isoformat(),
                "total_marks": total_marks,
                "score": score,
                "percentage": round(percentage, 2)
            }
            
            # Save user quiz attempt
            user_quiz_response = supabase.table("user_quizzes").insert(quiz_attempt_data).execute()
            
            if not user_quiz_response.data:
                return {"success": False, "error": "Failed to save quiz attempt"}
            
            user_quiz_id = user_quiz_response.data[0]["user_quiz_id"]
        
        # Save each answer
        for answer_data in user_answers:
            answer_response = supabase.table("user_answers").insert({
                "user_quiz_id": user_quiz_id,
                "question_id": answer_data["question_id"],
                "selected_option": answer_data["selected_option"],
                "awarded_marks": answer_data["awarded_marks"]
            }).execute()
            
            if not answer_response.data:
                return {"success": False, "error": f"Failed to save answer for question {answer_data['question_id']}"}
        
        return {
            "success": True,
            "user_quiz_id": user_quiz_id,
            "percentage": percentage,
            "message": "Quiz attempt saved successfully"
        }
        
    except Exception as e:
        return {"success": False, "error": f"Database error: {str(e)}"}

def get_user_quiz_attempts(user_id: int, limit: int = 50) -> Dict[str, Any]:
    """
    Get user's quiz attempts with performance data
    """
    try:
        response = supabase.table("user_quizzes").select("""
            user_quiz_id,
            taken_date,
            total_marks,
            score,
            percentage,
            quizzes (
                quiz_id,
                topic,
                performance_report
            )
        """).eq("user_id", user_id).order("taken_date", desc=True).limit(limit).execute()
        
        attempts = []
        if response.data:
            for attempt in response.data:
                attempts.append({
                    "user_quiz_id": attempt["user_quiz_id"],
                    "quiz_id": attempt["quizzes"]["quiz_id"],
                    "topic": attempt["quizzes"]["topic"],
                    "taken_date": attempt["taken_date"],
                    "total_marks": attempt["total_marks"],
                    "score": attempt["score"],
                    "percentage": attempt["percentage"],
                    "performance_report": attempt["quizzes"]["performance_report"]
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

def get_quiz_attempt_details(user_quiz_id: int) -> Optional[Dict[str, Any]]:
    """
    Get detailed information about a specific quiz attempt
    """
    try:
        # Get user quiz info
        user_quiz_response = supabase.table("user_quizzes").select("""
            *,
            quizzes (
                quiz_id,
                topic,
                performance_report
            )
        """).eq("user_quiz_id", user_quiz_id).execute()
        
        if not user_quiz_response.data:
            return None
        
        user_quiz = user_quiz_response.data[0]
        quiz_id = user_quiz["quizzes"]["quiz_id"]
        
        # Get user answers
        answers_response = supabase.table("user_answers").select("""
            question_id,
            selected_option,
            awarded_marks,
            questions (
                question_text
            )
        """).eq("user_quiz_id", user_quiz_id).execute()
        
        # Get correct answers
        quiz_data = get_quiz_by_id(quiz_id)
        if not quiz_data:
            return None
        
        # Match user answers with questions and correct answers
        detailed_answers = []
        for user_answer in answers_response.data:
            question_id = user_answer["question_id"]
            question_data = next((q for q in quiz_data["questions"] if q["question_id"] == question_id), None)
            
            if question_data:
                detailed_answers.append({
                    "question_id": question_id,
                    "question_text": question_data["question_text"],
                    "option_a": question_data["option_a"],
                    "option_b": question_data["option_b"],
                    "option_c": question_data["option_c"],
                    "option_d": question_data["option_d"],
                    "correct_option": question_data["correct_option"],
                    "user_selected": user_answer["selected_option"],
                    "awarded_marks": user_answer["awarded_marks"],
                    "is_correct": user_answer["selected_option"] == question_data["correct_option"]
                })
        
        return {
            "user_quiz_id": user_quiz_id,
            "quiz_id": quiz_id,
            "topic": user_quiz["quizzes"]["topic"],
            "taken_date": user_quiz["taken_date"],
            "total_marks": user_quiz["total_marks"],
            "score": user_quiz["score"],
            "percentage": user_quiz["percentage"],
            "performance_report": user_quiz["quizzes"]["performance_report"],
            "detailed_answers": detailed_answers
        }
        
    except Exception as e:
        print(f"Error fetching quiz attempt details: {str(e)}")
        return None

def create_dummy_document(title: str, content_type: str = "quiz_generated") -> int:
    """
    Create a dummy document record for quiz generation (since user_quizzes requires doc_id)
    """
    try:
        doc_response = supabase.table("documents").insert({
            "topic": title[:255],
            "resources": [],
            "media": {
                "content_type": content_type,
                "generated_for": "quiz",
                "created_at": datetime.now().isoformat()
            }
        }).execute()
        
        if doc_response.data:
            return doc_response.data[0]["doc_id"]
        return None
        
    except Exception as e:
        print(f"Error creating dummy document: {str(e)}")
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
