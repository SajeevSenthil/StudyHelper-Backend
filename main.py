from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import os
import tempfile
import PyPDF2
import docx
from io import BytesIO
import uuid

# Import our custom modules
from summarizer import summarize_text, extract_keywords, summarize_and_save
from resources import get_study_resources
from supabase_client import (save_document_session, get_document, get_user_documents, 
                           get_document_with_download_tracking, increment_download_count,
                           get_saved_summaries, get_user_summaries_with_files, 
                           get_summary_file_content, supabase)
from quiz_generator import generate_quiz_questions, generate_performance_feedback
from quiz_database import (save_quiz_to_database, get_quiz_by_id, save_user_quiz_attempt,
                          get_user_quiz_attempts, get_quiz_attempt_details, create_dummy_document)

# Initialize FastAPI app
app = FastAPI(title="StudyHelper Summarization Agent", version="1.0.0")

# Add CORS middleware for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],  # Next.js default ports
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic models for request/response
class TextSummarizeRequest(BaseModel):
    text: str
    max_length: Optional[int] = 200

class ResourceRequest(BaseModel):
    text: str

class SaveSessionRequest(BaseModel):
    user_id: Optional[int] = 1  # Default user for now
    topic: str
    original_content: str
    summary: str
    resources: List[str]

class QuizGenerateRequest(BaseModel):
    topic: Optional[str] = None
    content: Optional[str] = None
    quiz_type: str  # "topic" or "document"

class QuizSubmissionRequest(BaseModel):
    quiz_id: int
    user_id: Optional[int] = 1
    answers: List[Dict[str, Any]]  # [{"question_id": 1, "selected_option": "A"}, ...]
    doc_id: Optional[int] = None
    quiz_title: Optional[str] = None

class SummarizeResponse(BaseModel):
    summary: str
    keywords: str
    original_length: int
    summary_length: int

class ResourceResponse(BaseModel):
    resources: List[str]
    topic: str

class DownloadSummaryRequest(BaseModel):
    text: str
    topic: Optional[str] = None
    user_id: Optional[int] = 1
    max_length: Optional[int] = 200

class DownloadSummaryResponse(BaseModel):
    success: bool
    summary: Optional[str] = None
    keywords: Optional[str] = None
    topic: Optional[str] = None
    resources: Optional[List[str]] = None
    doc_id: Optional[int] = None
    message: str
    original_length: Optional[int] = None
    summary_length: Optional[int] = None
    timestamp: Optional[str] = None
    error: Optional[str] = None

# Utility functions for file processing
def extract_text_from_pdf(file_content: bytes) -> str:
    """Extract text from PDF file"""
    try:
        pdf_file = BytesIO(file_content)
        pdf_reader = PyPDF2.PdfReader(pdf_file)
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text() + "\n"
        return text.strip()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error reading PDF: {str(e)}")

def extract_text_from_docx(file_content: bytes) -> str:
    """Extract text from DOCX file"""
    try:
        doc = docx.Document(BytesIO(file_content))
        text = ""
        for paragraph in doc.paragraphs:
            text += paragraph.text + "\n"
        return text.strip()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error reading DOCX: {str(e)}")

def extract_text_from_txt(file_content: bytes) -> str:
    """Extract text from TXT file"""
    try:
        return file_content.decode('utf-8').strip()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error reading TXT: {str(e)}")

# API Routes
@app.get("/")
def read_root():
    return {"message": "StudyHelper Summarization Agent API", "version": "1.0.0"}

@app.post("/summarize/text", response_model=SummarizeResponse)
async def summarize_from_text(request: TextSummarizeRequest):
    """Summarize text directly from input"""
    try:
        if not request.text.strip():
            raise HTTPException(status_code=400, detail="Text cannot be empty")
        
        # Get summary and keywords
        summary = summarize_text(request.text, request.max_length)
        keywords = extract_keywords(request.text)
        
        return SummarizeResponse(
            summary=summary,
            keywords=keywords,
            original_length=len(request.text),
            summary_length=len(summary)
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Summarization failed: {str(e)}")

@app.post("/summarize/file", response_model=SummarizeResponse)
async def summarize_from_file(
    file: UploadFile = File(...),
    max_length: Optional[int] = Form(200)
):
    """Summarize text from uploaded file (PDF, DOCX, TXT)"""
    try:
        # Check file type
        if not file.filename:
            raise HTTPException(status_code=400, detail="No file provided")
        
        file_extension = file.filename.lower().split('.')[-1]
        if file_extension not in ['pdf', 'docx', 'txt']:
            raise HTTPException(status_code=400, detail="Unsupported file type. Use PDF, DOCX, or TXT")
        
        # Read file content
        file_content = await file.read()
        
        # Extract text based on file type
        if file_extension == 'pdf':
            text = extract_text_from_pdf(file_content)
        elif file_extension == 'docx':
            text = extract_text_from_docx(file_content)
        elif file_extension == 'txt':
            text = extract_text_from_txt(file_content)
        
        if not text.strip():
            raise HTTPException(status_code=400, detail="No text could be extracted from the file")
        
        # Get summary and keywords
        summary = summarize_text(text, max_length)
        keywords = extract_keywords(text)
        
        return SummarizeResponse(
            summary=summary,
            keywords=keywords,
            original_length=len(text),
            summary_length=len(summary)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"File processing failed: {str(e)}")

@app.post("/resources", response_model=ResourceResponse)
async def get_resources(request: ResourceRequest):
    """Get study resources based on text/summary"""
    try:
        if not request.text.strip():
            raise HTTPException(status_code=400, detail="Text cannot be empty")
        
        resources = get_study_resources(request.text)
        
        # Extract topic for response
        topic_words = request.text.split()[:10]  # First 10 words as topic preview
        topic = " ".join(topic_words) + "..." if len(topic_words) == 10 else " ".join(topic_words)
        
        return ResourceResponse(
            resources=resources,
            topic=topic
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Resource fetching failed: {str(e)}")

@app.post("/download/summary", response_model=DownloadSummaryResponse)
async def download_summary(request: DownloadSummaryRequest):
    """Generate summary and automatically save it to Supabase for download"""
    try:
        if not request.text.strip():
            raise HTTPException(status_code=400, detail="Text cannot be empty")
        
        # Use the new summarize_and_save function
        result = summarize_and_save(
            text=request.text,
            topic=request.topic,
            user_id=request.user_id,
            max_length=request.max_length
        )
        
        if result["success"]:
            return DownloadSummaryResponse(
                success=True,
                summary=result["summary"],
                keywords=result["keywords"],
                topic=result["topic"],
                resources=result["resources"],
                doc_id=result["doc_id"],
                message=result["message"],
                original_length=result["original_length"],
                summary_length=result["summary_length"],
                timestamp=result["timestamp"]
            )
        else:
            return DownloadSummaryResponse(
                success=False,
                message="Failed to save summary",
                error=result.get("error", "Unknown error occurred")
            )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Download summary failed: {str(e)}")

@app.post("/download/file-summary")
async def download_file_summary(
    file: UploadFile = File(...),
    topic: Optional[str] = Form(None),
    user_id: Optional[int] = Form(1),
    max_length: Optional[int] = Form(200)
):
    """Generate summary from uploaded file and automatically save it to Supabase for download"""
    try:
        # Check file type
        if not file.filename:
            raise HTTPException(status_code=400, detail="No file provided")
        
        file_extension = file.filename.lower().split('.')[-1]
        if file_extension not in ['pdf', 'docx', 'txt']:
            raise HTTPException(status_code=400, detail="Unsupported file type. Use PDF, DOCX, or TXT")
        
        # Read file content
        file_content = await file.read()
        
        # Extract text based on file type
        if file_extension == 'pdf':
            text = extract_text_from_pdf(file_content)
        elif file_extension == 'docx':
            text = extract_text_from_docx(file_content)
        elif file_extension == 'txt':
            text = extract_text_from_txt(file_content)
        
        if not text.strip():
            raise HTTPException(status_code=400, detail="No text could be extracted from the file")
        
        # Auto-generate topic from filename if not provided
        if not topic:
            topic = file.filename.rsplit('.', 1)[0]  # Remove file extension
        
        # Use the new summarize_and_save function
        result = summarize_and_save(
            text=text,
            topic=topic,
            user_id=user_id,
            max_length=max_length
        )
        
        if result["success"]:
            return DownloadSummaryResponse(
                success=True,
                summary=result["summary"],
                keywords=result["keywords"],
                topic=result["topic"],
                resources=result["resources"],
                doc_id=result["doc_id"],
                message=result["message"],
                original_length=result["original_length"],
                summary_length=result["summary_length"],
                timestamp=result["timestamp"]
            )
        else:
            return DownloadSummaryResponse(
                success=False,
                message="Failed to save summary",
                error=result.get("error", "Unknown error occurred")
            )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"File download summary failed: {str(e)}")

@app.post("/save")
async def save_session(request: SaveSessionRequest):
    """Save a complete study session to Supabase"""
    try:
        if not all([request.topic, request.original_content, request.summary]):
            raise HTTPException(status_code=400, detail="Missing required fields: topic, original_content, or summary")
        
        # Extract keywords from the summary if not provided
        keywords = extract_keywords(request.summary) if request.summary else ""
        
        result = save_document_session(
            user_id=request.user_id,
            topic=request.topic,
            original_content=request.original_content,
            summary=request.summary,
            resources=request.resources,
            keywords=keywords
        )
        
        if result["success"]:
            return {
                "success": True,
                "message": result["message"], 
                "doc_id": result["doc_id"],
                "timestamp": result.get("timestamp")
            }
        else:
            raise HTTPException(status_code=500, detail=result["message"])
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Save session failed: {str(e)}")

@app.get("/summaries/{user_id}")
async def get_user_summaries_endpoint(user_id: int, limit: Optional[int] = 50):
    """Get user's saved summaries with file URLs"""
    try:
        print(f"[DEBUG] Getting summaries for user_id: {user_id}, limit: {limit}")
        result = get_user_summaries_with_files(user_id, limit)
        print(f"[DEBUG] Result: {result}")
        
        if result["success"]:
            return result
        else:
            raise HTTPException(status_code=500, detail=result.get("error", "Unknown error"))
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[DEBUG] Exception in summaries endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve summaries: {str(e)}")

@app.get("/summary-file/{filename}")
async def download_summary_file(filename: str):
    """Download a summary .txt file from storage"""
    try:
        content = get_summary_file_content(filename)
        if content:
            return {
                "success": True,
                "content": content,
                "filename": filename
            }
        else:
            raise HTTPException(status_code=404, detail="Summary file not found")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to download summary file: {str(e)}")

@app.get("/documents/{doc_id}")
async def get_document_by_id(doc_id: int):
    """Retrieve a saved document by ID"""
    try:
        document = get_document(doc_id)
        if document:
            return document
        else:
            raise HTTPException(status_code=404, detail="Document not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve document: {str(e)}")

@app.get("/download/document/{doc_id}")
async def download_document(doc_id: int):
    """Download a saved document by ID (with download tracking)"""
    try:
        document = get_document_with_download_tracking(doc_id)
        if document:
            return {
                "doc_id": doc_id,
                "topic": document.get("topic"),
                "summary": document.get("media", {}).get("summary"),
                "keywords": document.get("media", {}).get("keywords"),
                "resources": document.get("resources"),
                "original_content": document.get("media", {}).get("original_content"),
                "created_at": document.get("media", {}).get("created_at"),
                "download_count": document.get("media", {}).get("download_count", 0),
                "message": "Document downloaded successfully"
            }
        else:
            raise HTTPException(status_code=404, detail="Document not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to download document: {str(e)}")

@app.get("/documents")
async def list_documents(user_id: Optional[int] = 1):
    """List all documents for a user"""
    try:
        documents = get_user_documents(user_id)
        return {"documents": documents, "count": len(documents)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve documents: {str(e)}")

@app.get("/saved-summaries")
async def get_saved_summaries_endpoint(user_id: Optional[int] = None, limit: Optional[int] = 50):
    """Get saved summaries for the saved summaries page"""
    try:
        result = get_saved_summaries(user_id, limit)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve saved summaries: {str(e)}")

@app.get("/saved-summaries/{doc_id}")
async def get_saved_summary_detail(doc_id: int):
    """Get detailed view of a specific saved summary"""
    try:
        document = get_document(doc_id)
        if document:
            media = document.get("media", {})
            return {
                "success": True,
                "doc_id": doc_id,
                "topic": document["topic"],
                "summary": media.get("summary", ""),
                "keywords": media.get("keywords", ""),
                "original_content": media.get("original_content", ""),
                "resources": document.get("resources", []),
                "created_at": media.get("created_at", ""),
                "download_count": media.get("download_count", 0),
                "original_length": media.get("original_length", 0),
                "summary_length": media.get("summary_length", 0),
                "user_id": media.get("user_id")
            }
        else:
            raise HTTPException(status_code=404, detail="Summary not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve summary: {str(e)}")

@app.delete("/documents/{doc_id}")
async def delete_document_endpoint(doc_id: int, user_id: Optional[int] = None):
    """Delete a specific document by ID"""
    try:
        from supabase_client import delete_document
        result = delete_document(doc_id, user_id)
        
        if result["success"]:
            return {
                "success": True,
                "message": result["message"],
                "deleted_doc_id": doc_id
            }
        else:
            raise HTTPException(status_code=400, detail=result["message"])
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete document: {str(e)}")

# QUIZ ENDPOINTS

@app.post("/quiz/generate")
async def generate_quiz(request: QuizGenerateRequest):
    """Generate a quiz from topic or content"""
    try:
        if request.quiz_type == "topic":
            if not request.topic:
                raise HTTPException(status_code=400, detail="Topic is required for topic-based quiz")
            
            # Generate quiz from topic
            result = generate_quiz_questions("", request.topic, 10)
            
        elif request.quiz_type == "document":
            if not request.content:
                raise HTTPException(status_code=400, detail="Content is required for document-based quiz")
            
            # Generate quiz from content
            result = generate_quiz_questions(request.content, None, 10)
            
        else:
            raise HTTPException(status_code=400, detail="Invalid quiz_type. Use 'topic' or 'document'")
        
        if not result["success"]:
            raise HTTPException(status_code=500, detail=result["error"])
        
        # Save quiz to database
        save_result = save_quiz_to_database(result["topic"], result["questions"])
        
        if not save_result["success"]:
            raise HTTPException(status_code=500, detail=save_result["error"])
        
        # Create dummy document for this quiz
        doc_id = create_dummy_document(result["topic"], "quiz_generated")
        
        return {
            "success": True,
            "quiz_id": save_result["quiz_id"],
            "topic": result["topic"],
            "total_questions": result["total_questions"],
            "doc_id": doc_id,
            "message": "Quiz generated successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Quiz generation failed: {str(e)}")

@app.post("/quiz/generate/file")
async def generate_quiz_from_file(
    file: UploadFile = File(...),
    quiz_type: str = Form("document")
):
    """Generate quiz from uploaded file"""
    try:
        # Check file type
        if not file.filename:
            raise HTTPException(status_code=400, detail="No file provided")
        
        file_extension = file.filename.lower().split('.')[-1]
        if file_extension not in ['pdf', 'docx', 'txt']:
            raise HTTPException(status_code=400, detail="Unsupported file type. Use PDF, DOCX, or TXT")
        
        # Read file content
        file_content = await file.read()
        
        # Extract text based on file type
        if file_extension == 'pdf':
            text = extract_text_from_pdf(file_content)
        elif file_extension == 'docx':
            text = extract_text_from_docx(file_content)
        elif file_extension == 'txt':
            text = extract_text_from_txt(file_content)
        
        if not text.strip():
            raise HTTPException(status_code=400, detail="No text could be extracted from the file")
        
        # Generate quiz from content
        result = generate_quiz_questions(text, None, 10)
        
        if not result["success"]:
            raise HTTPException(status_code=500, detail=result["error"])
        
        # Save quiz to database
        save_result = save_quiz_to_database(result["topic"], result["questions"])
        
        if not save_result["success"]:
            raise HTTPException(status_code=500, detail=save_result["error"])
        
        # Create dummy document for this quiz
        doc_id = create_dummy_document(result["topic"], "quiz_from_file")
        
        return {
            "success": True,
            "quiz_id": save_result["quiz_id"],
            "topic": result["topic"],
            "total_questions": result["total_questions"],
            "doc_id": doc_id,
            "message": "Quiz generated from file successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"File quiz generation failed: {str(e)}")

@app.get("/quiz/{quiz_id}")
async def get_quiz(quiz_id: int):
    """Get quiz questions and options (without correct answers for taking quiz)"""
    try:
        quiz_data = get_quiz_by_id(quiz_id)
        if not quiz_data:
            raise HTTPException(status_code=404, detail="Quiz not found")
        
        # Remove correct answers for quiz taking
        questions_for_quiz = []
        for q in quiz_data["questions"]:
            questions_for_quiz.append({
                "question_id": q["question_id"],
                "question_text": q["question_text"],
                "option_a": q["option_a"],
                "option_b": q["option_b"],
                "option_c": q["option_c"],
                "option_d": q["option_d"],
                "question_order": q["question_order"],
                "max_marks": q["max_marks"]
            })
        
        return {
            "quiz_id": quiz_data["quiz_id"],
            "topic": quiz_data["topic"],
            "questions": questions_for_quiz,
            "total_questions": quiz_data["total_questions"]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve quiz: {str(e)}")

@app.post("/quiz/submit")
async def submit_quiz(request: QuizSubmissionRequest):
    """Submit quiz answers and get results"""
    try:
        print(f"[DEBUG] Quiz submission request: quiz_id={request.quiz_id}, user_id={request.user_id}")
        print(f"[DEBUG] Answers: {request.answers}")
        
        # Get quiz with correct answers
        quiz_data = get_quiz_by_id(request.quiz_id)
        if not quiz_data:
            raise HTTPException(status_code=404, detail="Quiz not found")
        
        # Calculate score
        score = 0
        total_marks = len(quiz_data["questions"])
        user_answers = []
        
        # Create a map of question_id to correct answer
        correct_answers = {q["question_id"]: q["correct_option"] for q in quiz_data["questions"]}
        
        for answer in request.answers:
            question_id = answer["question_id"]
            selected_option = answer["selected_option"]
            
            # Check if answer is correct
            is_correct = selected_option == correct_answers.get(question_id)
            awarded_marks = 1 if is_correct else 0
            
            if is_correct:
                score += 1
            
            user_answers.append({
                "question_id": question_id,
                "selected_option": selected_option,
                "awarded_marks": awarded_marks
            })
        
        # Generate performance feedback
        feedback = generate_performance_feedback(score, total_marks, quiz_data["topic"])
        
        # Use provided doc_id or create a dummy one
        doc_id = request.doc_id
        if not doc_id:
            print(f"[DEBUG] Creating dummy document for topic: {quiz_data['topic']}")
            doc_id = create_dummy_document(quiz_data["topic"], "quiz_submission")
            print(f"[DEBUG] Created dummy document with ID: {doc_id}")
            if not doc_id:
                print("[DEBUG] Failed to create dummy document, using default doc_id=1")
                doc_id = 1  # Use a default doc_id if creation fails
        
        # Save quiz attempt to database
        print(f"[DEBUG] Saving quiz attempt: user_id={request.user_id}, quiz_id={request.quiz_id}, doc_id={doc_id}")
        save_result = save_user_quiz_attempt(
            request.user_id, 
            request.quiz_id, 
            doc_id,
            user_answers, 
            total_marks, 
            score
        )
        print(f"[DEBUG] Save result: {save_result}")

        if not save_result["success"]:
            print(f"[DEBUG] Save failed: {save_result['error']}")
            raise HTTPException(status_code=500, detail=save_result["error"])        # Return results with correct answers for analytics
        detailed_results = []
        for q in quiz_data["questions"]:
            user_answer = next((a for a in request.answers if a["question_id"] == q["question_id"]), None)
            user_selected = user_answer["selected_option"] if user_answer else None
            
            detailed_results.append({
                "question_id": q["question_id"],
                "question_text": q["question_text"],
                "option_a": q["option_a"],
                "option_b": q["option_b"],
                "option_c": q["option_c"],
                "option_d": q["option_d"],
                "correct_option": q["correct_option"],
                "user_selected": user_selected,
                "is_correct": user_selected == q["correct_option"] if user_selected else False
            })
        
        return {
            "success": True,
            "user_quiz_id": save_result["user_quiz_id"],
            "score": score,
            "total_marks": total_marks,
            "percentage": save_result["percentage"],
            "feedback": feedback,
            "quiz_topic": quiz_data["topic"],
            "detailed_results": detailed_results,
            "message": "Quiz submitted successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Quiz submission failed: {str(e)}")

@app.post("/quiz/save")
async def save_quiz_with_title(request: dict):
    """Save quiz with custom title by creating a new quiz entry with all questions"""
    try:
        user_quiz_id = request.get("user_quiz_id")
        custom_title = request.get("custom_title", "").strip()
        
        if not user_quiz_id or not custom_title:
            raise HTTPException(status_code=400, detail="user_quiz_id and custom_title are required")
        
        # Get the original quiz attempt details including the quiz info
        quiz_attempt_response = supabase.table("user_quizzes").select("*").eq("user_quiz_id", user_quiz_id).execute()
        
        if not quiz_attempt_response.data:
            raise HTTPException(status_code=404, detail="Quiz attempt not found")
        
        attempt_data = quiz_attempt_response.data[0]
        original_quiz_id = attempt_data["quiz_id"]
        
        # Get original quiz info
        original_quiz_response = supabase.table("quizzes").select("*").eq("quiz_id", original_quiz_id).execute()
        if not original_quiz_response.data:
            raise HTTPException(status_code=404, detail="Original quiz not found")
        
        original_quiz = original_quiz_response.data[0]
        
        # Create new quiz entry with custom title
        new_quiz_response = supabase.table("quizzes").insert({
            "topic": custom_title,
            "performance_report": original_quiz.get("performance_report")
        }).execute()
        
        if not new_quiz_response.data:
            raise HTTPException(status_code=500, detail="Failed to create new quiz entry")
        
        new_quiz_id = new_quiz_response.data[0]["quiz_id"]
        
        # Get all questions from the original quiz with their order
        quiz_questions_response = supabase.table("quiz_questions").select("*").eq("quiz_id", original_quiz_id).order("question_order").execute()
        
        # Copy quiz questions to the new quiz
        if quiz_questions_response.data:
            new_quiz_questions = []
            for qq in quiz_questions_response.data:
                new_quiz_questions.append({
                    "quiz_id": new_quiz_id,
                    "question_id": qq["question_id"],
                    "question_order": qq["question_order"],
                    "max_marks": qq["max_marks"]
                })
            
            # Insert all quiz question mappings
            quiz_questions_insert_response = supabase.table("quiz_questions").insert(new_quiz_questions).execute()
            if not quiz_questions_insert_response.data:
                raise HTTPException(status_code=500, detail="Failed to copy quiz questions")
        
        # Update the user_quiz record to point to the new quiz
        update_response = supabase.table("user_quizzes").update({
            "quiz_id": new_quiz_id
        }).eq("user_quiz_id", user_quiz_id).execute()
        
        if not update_response.data:
            raise HTTPException(status_code=500, detail="Failed to update quiz attempt")
        
        return {
            "success": True,
            "message": "Quiz saved successfully",
            "new_quiz_id": new_quiz_id,
            "custom_title": custom_title
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[DEBUG] Save quiz error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to save quiz: {str(e)}")

@app.get("/quiz/attempts/{user_id}")
async def get_user_quiz_attempts_endpoint(user_id: int, limit: Optional[int] = 50):
    """Get user's quiz attempts and performance"""
    try:
        result = get_user_quiz_attempts(user_id, limit)
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve quiz attempts: {str(e)}")

@app.get("/quiz/attempt/{user_quiz_id}")
async def get_quiz_attempt_detail(user_quiz_id: int):
    """Get detailed analytics for a specific quiz attempt with all questions and answers"""
    try:
        # Get user quiz info
        user_quiz_response = supabase.table("user_quizzes").select("*").eq("user_quiz_id", user_quiz_id).execute()
        
        if not user_quiz_response.data:
            raise HTTPException(status_code=404, detail="Quiz attempt not found")
        
        user_quiz = user_quiz_response.data[0]
        quiz_id = user_quiz["quiz_id"]
        
        # Get quiz info
        quiz_response = supabase.table("quizzes").select("*").eq("quiz_id", quiz_id).execute()
        if not quiz_response.data:
            raise HTTPException(status_code=404, detail="Quiz not found")
        
        quiz_info = quiz_response.data[0]
        
        # Get all questions for this quiz in order
        quiz_questions_response = supabase.table("quiz_questions").select("*").eq("quiz_id", quiz_id).order("question_order").execute()
        
        if not quiz_questions_response.data:
            raise HTTPException(status_code=404, detail="No questions found for this quiz")
        
        # Get user answers for this attempt
        user_answers_response = supabase.table("user_answers").select("*").eq("user_quiz_id", user_quiz_id).execute()
        user_answers_map = {ua["question_id"]: ua["selected_option"] for ua in user_answers_response.data}
        
        detailed_results = []
        for idx, qq in enumerate(quiz_questions_response.data, 1):
            question_id = qq["question_id"]
            
            # Get question text
            question_response = supabase.table("questions").select("*").eq("question_id", question_id).execute()
            if not question_response.data:
                continue
            
            question = question_response.data[0]
            
            # Get options for this question
            options_response = supabase.table("options").select("*").eq("question_id", question_id).execute()
            if not options_response.data:
                continue
            
            options = options_response.data[0]
            user_selected = user_answers_map.get(question_id)
            correct_option = options["correct_option"]
            is_correct = user_selected == correct_option
            
            detailed_results.append({
                "question_number": idx,
                "question_id": question_id,
                "question_text": question["question_text"],
                "option_a": options["option_a"],
                "option_b": options["option_b"],
                "option_c": options["option_c"],
                "option_d": options["option_d"],
                "correct_option": correct_option,
                "user_selected": user_selected,
                "is_correct": is_correct,
                "status": "Correct" if is_correct else "Incorrect"
            })
        
        return {
            "user_quiz_id": user_quiz_id,
            "quiz_id": quiz_id,
            "topic": quiz_info["topic"],
            "taken_date": user_quiz["taken_date"],
            "total_marks": user_quiz["total_marks"],
            "score": user_quiz["score"],
            "percentage": user_quiz["percentage"],
            "detailed_results": detailed_results
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[DEBUG] Get quiz attempt error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve quiz attempt details: {str(e)}")

# Health check endpoint
@app.get("/health")
def health_check():
    return {"status": "healthy", "service": "StudyHelper Summarization Agent"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001)
