from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import os
import tempfile
import PyPDF2
import docx
from io import BytesIO
import uuid
from datetime import datetime
import jwt
import jwt
import json
from datetime import datetime

# Import our custom modules
from summarizer import (summarize_text, extract_keywords, summarize_and_save, 
                       get_user_summaries_sql, delete_document_sql,
                       update_document_resources_sql, get_document_by_id_sql)
from resources import get_study_resources
from supabase_client import (save_document_session, get_document, get_user_documents, 
                           get_document_with_download_tracking, increment_download_count,
                           get_saved_summaries, supabase, get_summary_file_content, 
                           save_uploaded_file_to_storage, get_user_summaries_with_files,
                           delete_document)
from quiz_generator import generate_quiz_questions, generate_performance_feedback
from quiz_database import (save_quiz_to_database, get_quiz_by_id, save_user_quiz_attempt,
                          get_user_quiz_attempts, get_quiz_attempt_details)

# Initialize FastAPI app
app = FastAPI(title="StudyHelper Summarization Agent", version="1.0.0")

# Initialize HTTP Bearer for authentication
security = HTTPBearer(auto_error=False)

# Authentication helper functions
def get_user_from_token(authorization: str = Header(None)) -> Optional[str]:
    """Extract user ID from Supabase JWT token"""
    if not authorization:
        return None
    
    try:
        # Remove 'Bearer ' prefix
        token = authorization.replace('Bearer ', '') if authorization.startswith('Bearer ') else authorization
        
        # For development, we'll decode without verification
        # In production, you should verify with your JWT secret
        decoded = jwt.decode(token, options={"verify_signature": False})
        user_id = decoded.get('sub')  # 'sub' contains the user ID in Supabase JWTs
        
        print(f"[DEBUG] Extracted user ID from token: {user_id}")
        return user_id
        
    except Exception as e:
        print(f"[DEBUG] Token decode error: {str(e)}")
        return None

def get_current_user_dev(authorization: str = Header(None)) -> str:
    """Get current user ID, with fallback for development"""
    user_id = get_user_from_token(authorization)
    
    if not user_id:
        print("[DEBUG] No valid token found, using demo user for development")
        # For development/demo purposes, return a demo user ID
        # This should be a valid UUID that exists in your auth.users table
        return "550e8400-e29b-41d4-a716-446655440000"
    
    return user_id

# Authentication utilities
def verify_supabase_token(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    """Verify Supabase JWT token and extract user information"""
    if not credentials:
        return None
    
    try:
        # Get the token from the Authorization header
        token = credentials.credentials
        
        # Use Supabase client to verify the token
        user_response = supabase.auth.get_user(token)
        
        if user_response.user:
            return {
                "user_id": user_response.user.id,
                "email": user_response.user.email,
                "token": token
            }
        else:
            return None
            
    except Exception as e:
        print(f"Token verification error: {str(e)}")
        return None

def get_current_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    """Get current authenticated user or raise HTTPException"""
    user = verify_supabase_token(credentials)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or missing authentication token")
    
    # Ensure user_id is treated as UUID string
    user["user_id"] = str(user["user_id"])
    return user

def get_optional_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    """Get current user if authenticated, otherwise return None"""
    user = verify_supabase_token(credentials)
    if user:
        # Ensure user_id is treated as UUID string
        user["user_id"] = str(user["user_id"])
    return user

# Add CORS middleware for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],  # Next.js default ports
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB in bytes

# Pydantic models for request/response
class TextSummarizeRequest(BaseModel):
    text: str
    max_length: Optional[int] = 200

class ResourceRequest(BaseModel):
    text: str
    doc_id: Optional[int] = None  # Optional document ID to save resources to

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
    resources: List[Dict[str, str]]  # Changed from List[str] to List[Dict[str, str]]
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

# Utility functions for file processing with Document AI
def get_mime_type_from_filename(filename: str) -> str:
    """Get MIME type from filename extension"""
    extension = filename.lower().split('.')[-1]
    mime_types = {
        'pdf': 'application/pdf',
        'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'doc': 'application/msword',
        'txt': 'text/plain',
        'jpg': 'image/jpeg',
        'jpeg': 'image/jpeg',
        'png': 'image/png',
        'webp': 'image/webp',
        'tiff': 'image/tiff',
        'bmp': 'image/bmp',
        'gif': 'image/gif'
    }
    return mime_types.get(extension, 'application/octet-stream')

def validate_file_size(file_content: bytes) -> bool:
    """Validate if file size is within the allowed limit"""
    return len(file_content) <= MAX_FILE_SIZE

def extract_text_with_document_ai(file_content: bytes, filename: str) -> str:
    """
    Extract text from any supported document using Google Document AI
    
    Args:
        file_content (bytes): The file content as bytes
        filename (str): Original filename to determine MIME type
    
    Returns:
        str: Extracted text content
    """
    try:
        # Get MIME type from filename
        mime_type = get_mime_type_from_filename(filename)
        print(f"[DEBUG] Processing file {filename} with MIME type: {mime_type}")
        
        # Document AI is disabled, using legacy methods
        print(f"[DEBUG] Using legacy text extraction methods for {mime_type}")
        return extract_text_legacy(file_content, filename)
            
    except Exception as e:
        print(f"[DEBUG] Document AI extraction exception: {str(e)}")
        # Fallback to legacy methods if any error occurs
        return extract_text_legacy(file_content, filename)

def extract_text_legacy(file_content: bytes, filename: str) -> str:
    """
    Legacy text extraction methods as fallback
    
    Args:
        file_content (bytes): The file content as bytes
        filename (str): Original filename
    
    Returns:
        str: Extracted text content
    """
    try:
        file_extension = filename.lower().split('.')[-1]
        print(f"[DEBUG] Using legacy extraction for {file_extension} file")
        
        if file_extension == 'pdf':
            text = extract_text_from_pdf(file_content)
            print(f"[DEBUG] PDF extraction result length: {len(text) if text else 0}")
            return text
        elif file_extension == 'docx':
            text = extract_text_from_docx(file_content)
            print(f"[DEBUG] DOCX extraction result length: {len(text) if text else 0}")
            return text
        elif file_extension == 'txt':
            text = extract_text_from_txt(file_content)
            print(f"[DEBUG] TXT extraction result length: {len(text) if text else 0}")
            return text
        else:
            print(f"[DEBUG] Unsupported file type: {file_extension}")
            return ""
    except Exception as e:
        print(f"[DEBUG] Legacy extraction failed: {str(e)}")
        return ""

def extract_text_from_pdf(file_content: bytes) -> str:
    """Extract text from PDF file (legacy method)"""
    try:
        pdf_file = BytesIO(file_content)
        pdf_reader = PyPDF2.PdfReader(pdf_file)
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text() + "\n"
        return text.strip()
    except Exception as e:
        print(f"[DEBUG] Error reading PDF: {str(e)}")
        return ""

def extract_text_from_docx(file_content: bytes) -> str:
    """Extract text from DOCX file (legacy method)"""
    try:
        doc = docx.Document(BytesIO(file_content))
        text = ""
        for paragraph in doc.paragraphs:
            text += paragraph.text + "\n"
        return text.strip()
    except Exception as e:
        print(f"[DEBUG] Error reading DOCX: {str(e)}")
        return ""

def extract_text_from_txt(file_content: bytes) -> str:
    """Extract text from TXT file (legacy method)"""
    try:
        return file_content.decode('utf-8').strip()
    except Exception as e:
        print(f"[DEBUG] Error reading TXT: {str(e)}")
        # Try different encodings
        try:
            return file_content.decode('latin-1').strip()
        except:
            return ""

# API Routes
@app.get("/")
def read_root():
    return {"message": "StudyHelper Summarization Agent API", "version": "1.0.0"}

@app.get("/config")
def get_configuration():
    """Get API configuration and supported file types"""
    return {
        "max_file_size_mb": MAX_FILE_SIZE // (1024 * 1024),
        "max_file_size_bytes": MAX_FILE_SIZE,
        "supported_file_types": ["application/pdf", "image/jpeg", "image/png", "image/webp", 
                               "application/msword", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", 
                               "text/plain"],
        "text_extraction": "Legacy text extraction (PyPDF2, python-docx)",
        "summarization": "OpenAI GPT-4o-mini API",
        "quiz_generation": "OpenAI GPT-4o-mini API",
        "features": [
            "Legacy text extraction",
            "OpenAI-powered summarization and quiz generation", 
            "File size validation",
            "Multiple file format support",
            "Legacy fallback methods"
        ]
    }

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
    """Summarize text from uploaded file using Document AI and OpenAI"""
    try:
        # Check file is provided
        if not file.filename:
            raise HTTPException(status_code=400, detail="No file provided")
        
        # Read file content
        file_content = await file.read()
        
        # Validate file size (10MB limit)
        if not validate_file_size(file_content):
            raise HTTPException(
                status_code=413, 
                detail=f"File size exceeds maximum limit of {MAX_FILE_SIZE // (1024 * 1024)}MB"
            )
        
        # Extract text using Document AI with fallback to legacy methods
        text = extract_text_with_document_ai(file_content, file.filename)
        
        # If still no text, provide detailed error
        if not text or not text.strip():
            print(f"[DEBUG] No text extracted from file: {file.filename}")
            # Try to provide more helpful error message
            file_extension = file.filename.lower().split('.')[-1] if '.' in file.filename else 'unknown'
            if file_extension not in ['pdf', 'docx', 'txt']:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Unsupported file type: {file_extension}. Please upload PDF, DOCX, or TXT files only."
                )
            else:
                raise HTTPException(
                    status_code=400, 
                    detail="No text could be extracted from the file. The file may be empty, corrupted, or contain only images/scanned content."
                )
        
        # Get summary and keywords using OpenAI
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
    """Get study resources based on text/summary and optionally save to database"""
    try:
        if not request.text.strip():
            raise HTTPException(status_code=400, detail="Text cannot be empty")
        
        print(f"[DEBUG] Getting resources for text length: {len(request.text)}, doc_id: {request.doc_id}")
        
        # Get study resources using improved web scraping
        resources = get_study_resources(request.text)
        print(f"[DEBUG] Found {len(resources)} resources")
        
        # If doc_id is provided, save resources to database
        if request.doc_id:
            print(f"[DEBUG] Saving resources to document {request.doc_id}")
            # Convert resources to URLs for database storage
            resource_urls = []
            for resource in resources:
                if isinstance(resource, dict):
                    resource_urls.append(resource.get("url", ""))
                else:
                    resource_urls.append(str(resource))
            
            # Update document with resources
            update_result = update_document_resources_sql(request.doc_id, resource_urls)
            print(f"[DEBUG] Database update result: {update_result}")
            
            if not update_result["success"]:
                print(f"[WARNING] Failed to save resources to database: {update_result.get('message', 'Unknown error')}")
        
        # Extract topic for response
        topic_words = request.text.split()[:10]  # First 10 words as topic preview
        topic = " ".join(topic_words) + "..." if len(topic_words) == 10 else " ".join(topic_words)
        
        return ResourceResponse(
            resources=resources,
            topic=topic
        )
        
    except Exception as e:
        print(f"[ERROR] Resource fetching failed: {str(e)}")
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
    """Generate summary from uploaded file using Document AI and OpenAI, then save to Supabase"""
    try:
        # Check file is provided
        if not file.filename:
            raise HTTPException(status_code=400, detail="No file provided")
        
        # Read file content
        file_content = await file.read()
        
        # Validate file size (10MB limit)
        if not validate_file_size(file_content):
            raise HTTPException(
                status_code=413, 
                detail=f"File size exceeds maximum limit of {MAX_FILE_SIZE // (1024 * 1024)}MB"
            )
        
        # Extract text using Document AI with fallback to legacy methods
        text = extract_text_with_document_ai(file_content, file.filename)
        
        if not text.strip():
            raise HTTPException(status_code=400, detail="No text could be extracted from the file")
        
        # Auto-generate topic from filename if not provided
        if not topic:
            topic = file.filename.rsplit('.', 1)[0]  # Remove file extension
        
        # Use the new summarize_and_save function with OpenAI
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

@app.post("/create-demo-user")
async def create_demo_user():
    """Create a demo user for testing - should only be used in development"""
    try:
        demo_user_id = "550e8400-e29b-41d4-a716-446655440000"
        demo_email = "demo@studyhelper.com"
        
        # Check if user already exists
        existing_user = supabase.table("auth.users").select("id").eq("id", demo_user_id).execute()
        
        if existing_user.data:
            return {"success": True, "message": "Demo user already exists", "user_id": demo_user_id}
        
        # Try to create user using admin API
        try:
            auth_result = supabase.auth.admin_create_user({
                "email": demo_email,
                "password": "demo123456",
                "email_confirm": True,
                "user_metadata": {"name": "Demo User", "created_by": "backend"}
            })
            
            if auth_result.user:
                return {
                    "success": True, 
                    "message": "Demo user created successfully",
                    "user_id": auth_result.user.id,
                    "email": auth_result.user.email
                }
            else:
                raise Exception("User creation failed - no user returned")
                
        except Exception as auth_error:
            print(f"[DEBUG] Admin user creation failed: {str(auth_error)}")
            return {
                "success": False,
                "message": "Failed to create demo user",
                "error": str(auth_error),
                "note": "You may need to run the SQL script manually in Supabase"
            }
        
    except Exception as e:
        print(f"[ERROR] Create demo user failed: {str(e)}")
        return {
            "success": False,
            "message": "Failed to create demo user",
            "error": str(e)
        }

@app.post("/save")
async def save_session(request: SaveSessionRequest, current_user: str = Depends(get_current_user_dev)):
    """Save a complete study session to documents table"""
    try:
        if not all([request.topic, request.original_content, request.summary]):
            raise HTTPException(status_code=400, detail="Missing required fields: topic, original_content, or summary")
        
        print(f"[DEBUG] Saving document for user: {current_user}, topic: {request.topic}")
        
        # Save to documents table with the authenticated user ID
        try:
            doc_result = supabase.table("documents").insert({
                "user_id": current_user,
                "topic": request.topic,
                "content": request.original_content,
                "summary": request.summary,
                "file_url": None
            }).execute()
            
            if doc_result.data:
                doc_id = doc_result.data[0]["doc_id"]
                print(f"[DEBUG] Document saved successfully with ID: {doc_id}")
                return {
                    "success": True,
                    "message": "Document saved successfully", 
                    "doc_id": doc_id,
                    "timestamp": datetime.now().isoformat()
                }
            else:
                raise HTTPException(status_code=500, detail="Failed to save document - no data returned")
                
        except Exception as db_error:
            print(f"[ERROR] Database error: {str(db_error)}")
            # If that fails too, let's check what exactly is the constraint
            error_msg = str(db_error)
            if "user_id" in error_msg.lower() and "not null" in error_msg.lower():
                # The user_id column doesn't allow NULL, so we need to provide a value
                print("[DEBUG] user_id column requires a value, will try with NULL UUID")
                try:
                    # Try with a NULL UUID approach - insert a special "anonymous" user ID
                    doc_result = supabase.table("documents").insert({
                        "user_id": None,  # Try explicit NULL first
                        "topic": request.topic,
                        "content": request.original_content,
                        "summary": request.summary,
                        "file_url": None
                    }).execute()
                    
                    if doc_result.data:
                        doc_id = doc_result.data[0]["doc_id"]
                        return {
                            "success": True,
                            "message": "Document saved successfully", 
                            "doc_id": doc_id,
                            "timestamp": datetime.now().isoformat()
                        }
                except Exception as null_error:
                    print(f"[DEBUG] NULL approach failed: {str(null_error)}")
            
            raise HTTPException(status_code=500, detail=f"Database error: {str(db_error)}")
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] Save session failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Save session failed: {str(e)}")
        keywords = extract_keywords(request.summary) if request.summary else ""
        keywords = extract_keywords(request.summary) if request.summary else ""
        
        # Save directly to documents table using your schema
        try:
            doc_result = supabase.table("documents").insert({
                "user_id": user_id,
                "topic": request.topic,
                "content": request.original_content,
                "summary": request.summary,
                "file_url": None  # For text input, no file URL needed
            }).execute()
            
            if doc_result.data:
                doc_id = doc_result.data[0]["doc_id"]
                print(f"[DEBUG] Document saved successfully with ID: {doc_id}")
                return {
                    "success": True,
                    "message": "Document saved successfully", 
                    "doc_id": doc_id,
                    "timestamp": datetime.now().isoformat()
                }
            else:
                raise HTTPException(status_code=500, detail="Failed to save document to database")
                
        except Exception as db_error:
            print(f"[ERROR] Database error: {str(db_error)}")
            raise HTTPException(status_code=500, detail=f"Database error: {str(db_error)}")
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] Save session failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Save session failed: {str(e)}")

@app.get("/my-summaries")
async def get_my_summaries(current_user: str = Depends(get_current_user_dev), limit: Optional[int] = 50):
    """Get user's saved documents using your schema"""
    try:
        print(f"[DEBUG] Getting documents for user: {current_user}")
        
        # Query documents table directly using your schema
        documents_result = supabase.table("documents").select("*").eq("user_id", current_user).order("doc_id", desc=True).limit(limit).execute()
        
        if not documents_result.data:
            return {
                "success": True,
                "summaries": [],
                "message": "No documents found"
            }
        
        # Format the documents for frontend
        summaries = []
        for doc in documents_result.data:
            summaries.append({
                "doc_id": doc["doc_id"],
                "topic": doc["topic"],
                "summary": doc["summary"],
                "content": doc["content"],
                "file_url": doc["file_url"],
                "created_at": doc.get("created_at", ""),
                "summary_length": len(doc["summary"]) if doc["summary"] else 0,
                "content_length": len(doc["content"]) if doc["content"] else 0
            })
        
        return {
            "success": True,
            "summaries": summaries,
            "total_count": len(summaries)
        }
        
    except Exception as e:
        print(f"[ERROR] Get summaries failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve summaries: {str(e)}")

@app.get("/my-documents")
async def get_my_documents():
    """Get user's documents from your schema"""
    try:
        # Use the same demo user ID (service key bypasses RLS)
        user_id = "550e8400-e29b-41d4-a716-446655440000"
            
        print(f"[DEBUG] Getting documents for user: {user_id}")
        
        # Get documents from your schema
        documents_result = supabase.table("documents").select("*").eq("user_id", user_id).order("doc_id", desc=True).execute()
        
        if not documents_result.data:
            return {
                "success": True,
                "documents": [],
                "message": "No documents found"
            }
        
        # Format documents for frontend
        documents = []
        for doc in documents_result.data:
            documents.append({
                "doc_id": doc["doc_id"],
                "topic": doc["topic"],
                "summary": doc["summary"][:200] + "..." if doc["summary"] and len(doc["summary"]) > 200 else doc["summary"],
                "content_preview": doc["content"][:300] + "..." if doc["content"] and len(doc["content"]) > 300 else doc["content"],
                "file_url": doc["file_url"],
                "created_at": doc.get("created_at", ""),
                "summary_length": len(doc["summary"]) if doc["summary"] else 0,
                "content_length": len(doc["content"]) if doc["content"] else 0
            })
        
        return {
            "success": True,
            "documents": documents,
            "total_count": len(documents)
        }
        
    except Exception as e:
        print(f"[ERROR] Get documents failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve documents: {str(e)}")

@app.delete("/documents/{doc_id}")
async def delete_document_endpoint(doc_id: int, current_user: str = Depends(get_current_user_dev)):
    """Delete a document by ID"""
    try:
        print(f"[DEBUG] Deleting document {doc_id} for user: {current_user}")
        
        # First check if document belongs to user
        doc_result = supabase.table("documents").select("*").eq("doc_id", doc_id).eq("user_id", current_user).execute()
        
        if not doc_result.data:
            raise HTTPException(status_code=404, detail="Document not found or access denied")
        
        # Delete the document
        delete_result = supabase.table("documents").delete().eq("doc_id", doc_id).eq("user_id", current_user).execute()
        
        if delete_result.data:
            return {
                "success": True,
                "message": "Document deleted successfully",
                "deleted_doc_id": doc_id
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to delete document")
            
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] Delete document failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to delete document: {str(e)}")

@app.get("/summary-file/{filename}")
async def download_summary_file(filename: str):
    """Download a summary .txt file - get content from database if storage fails"""
    try:
        # First try to get from storage
        content = get_summary_file_content(filename)
        if content:
            return {
                "success": True,
                "content": content,
                "filename": filename
            }
        
        # If storage fails, try to get summary from database using filename
        # Extract doc info from filename (format: summary_userId_timestamp.txt)
        try:
            parts = filename.replace('.txt', '').split('_')
            if len(parts) >= 3:
                user_id = int(parts[1])
                timestamp = parts[2]
                
                # Get summaries for this user and find matching one by timestamp
                summaries_result = get_user_summaries_with_files(user_id, 50)
                if summaries_result.get("success") and summaries_result.get("summaries"):
                    for summary in summaries_result["summaries"]:
                        if summary.get("summary_filename") == filename:
                            return {
                                "success": True,
                                "content": summary.get("summary", ""),
                                "filename": filename
                            }
        except (ValueError, IndexError):
            pass
            
        raise HTTPException(status_code=404, detail="Summary file not found")
            
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error downloading summary file {filename}: {str(e)}")
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
    """Delete a specific document by ID using Supabase client"""
    try:
        result = delete_document(doc_id, user_id)  # Use Supabase version
        
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
async def generate_quiz(request: QuizGenerateRequest, current_user: str = Depends(get_current_user_dev)):
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
        
        # Save quiz to database with user_id
        save_result = save_quiz_to_database(result["topic"], result["questions"], None, current_user)
        
        if not save_result["success"]:
            raise HTTPException(status_code=500, detail=save_result["error"])
        
        return {
            "success": True,
            "quiz_id": save_result["quiz_id"],
            "topic": result["topic"],
            "total_questions": result["total_questions"],
            "message": "Quiz generated successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Quiz generation failed: {str(e)}")

@app.post("/quiz/generate/file")
async def generate_quiz_from_file(
    file: UploadFile = File(...),
    quiz_type: str = Form("document"),
    current_user: str = Depends(get_current_user_dev)
):
    """Generate quiz from uploaded file using Document AI for text extraction"""
    try:
        # Check file is provided
        if not file.filename:
            raise HTTPException(status_code=400, detail="No file provided")
        
        # Read file content
        file_content = await file.read()
        
        # Validate file size (10MB limit)
        if not validate_file_size(file_content):
            raise HTTPException(
                status_code=413, 
                detail=f"File size exceeds maximum limit of {MAX_FILE_SIZE // (1024 * 1024)}MB"
            )
        
        # Extract text using Document AI with fallback to legacy methods
        text = extract_text_with_document_ai(file_content, file.filename)
        
        if not text.strip():
            raise HTTPException(status_code=400, detail="No text could be extracted from the file")
        
        # Generate quiz from content
        result = generate_quiz_questions(text, None, 10)
        
        if not result["success"]:
            raise HTTPException(status_code=500, detail=result["error"])
        
        # Save quiz to database with user_id
        save_result = save_quiz_to_database(result["topic"], result["questions"], None, current_user)
        
        if not save_result["success"]:
            raise HTTPException(status_code=500, detail=save_result["error"])
        
        return {
            "success": True,
            "quiz_id": save_result["quiz_id"],
            "topic": result["topic"],
            "total_questions": result["total_questions"],
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
async def submit_quiz(request: QuizSubmissionRequest, current_user: str = Depends(get_current_user_dev)):
    """Submit quiz answers and get results"""
    try:
        print(f"[DEBUG] Quiz submission request: quiz_id={request.quiz_id}, user_id={current_user}")
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
        
        # Save quiz attempt to database (no doc_id needed in new schema)
        print(f"[DEBUG] Saving quiz attempt: user_id={current_user}, quiz_id={request.quiz_id}")
        save_result = save_user_quiz_attempt(
            current_user, 
            request.quiz_id, 
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
async def get_user_quiz_attempts_endpoint(user_id: str, limit: Optional[int] = 50):
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
    uvicorn.run(app, host="127.0.0.1", port=8002)
