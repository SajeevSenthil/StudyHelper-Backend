import os
from supabase import create_client, Client
from dotenv import load_dotenv
from typing import Dict, Any, Optional
from datetime import datetime

# Load environment variables
load_dotenv()

# Initialize Supabase client
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def save_document_session(user_id: int, topic: str, original_content: str, 
                         summary: str, resources: list, keywords: str = None) -> Dict[str, Any]:
    """Save a complete document session to Supabase documents table"""
    try:
        # Prepare media JSONB data
        media_data = {
            "original_content": original_content,
            "summary": summary,
            "keywords": keywords,
            "user_id": user_id,
            "created_at": datetime.now().isoformat(),
            "download_count": 0,
            "file_type": "text",
            "original_length": len(original_content) if original_content else 0,
            "summary_length": len(summary) if summary else 0
        }
        
        # Save to documents table
        doc_response = supabase.table("documents").insert({
            "topic": topic[:255],  # Ensure topic fits in VARCHAR(255)
            "resources": resources if resources else [],
            "media": media_data
        }).execute()
        
        if doc_response.data:
            doc_id = doc_response.data[0]["doc_id"]
            return {
                "success": True, 
                "doc_id": doc_id, 
                "message": "Document saved successfully",
                "timestamp": media_data["created_at"]
            }
        else:
            return {"success": False, "message": "Failed to save document", "error": "No data returned"}
            
    except Exception as e:
        return {"success": False, "message": f"Database error: {str(e)}", "error": str(e)}

def increment_download_count(doc_id: int) -> Dict[str, Any]:
    """Increment download count for a document"""
    try:
        # Get current document
        current_doc = get_document(doc_id)
        if not current_doc:
            return {"success": False, "message": "Document not found"}
        
        # Update download count
        current_media = current_doc.get("media", {})
        current_count = current_media.get("download_count", 0)
        current_media["download_count"] = current_count + 1
        current_media["last_downloaded"] = datetime.now().isoformat()
        
        # Update document
        update_response = supabase.table("documents").update({
            "media": current_media
        }).eq("doc_id", doc_id).execute()
        
        if update_response.data:
            return {"success": True, "message": "Download count updated", "download_count": current_count + 1}
        else:
            return {"success": False, "message": "Failed to update download count"}
            
    except Exception as e:
        return {"success": False, "message": f"Database error: {str(e)}"}

def get_document_with_download_tracking(doc_id: int) -> Optional[Dict[str, Any]]:
    """Retrieve a document by ID and increment download count"""
    try:
        document = get_document(doc_id)
        if document:
            # Increment download count
            increment_download_count(doc_id)
            return document
        return None
    except Exception as e:
        print(f"Error fetching document with download tracking: {str(e)}")
        return None

def get_document(doc_id: int) -> Optional[Dict[str, Any]]:
    """Retrieve a document by ID"""
    try:
        response = supabase.table("documents").select("*").eq("doc_id", doc_id).execute()
        if response.data:
            return response.data[0]
        return None
    except Exception as e:
        print(f"Error fetching document: {str(e)}")
        return None

def get_user_documents(user_id: int = None) -> list:
    """Get all documents for a specific user or all documents if no user_id specified"""
    try:
        if user_id:
            # Filter by user_id in the media JSONB field
            response = supabase.table("documents").select("*").contains("media", {"user_id": user_id}).execute()
        else:
            # Get all documents
            response = supabase.table("documents").select("*").order("doc_id", desc=True).execute()
        
        # Format the response for easier consumption
        formatted_docs = []
        if response.data:
            for doc in response.data:
                media = doc.get("media", {})
                formatted_doc = {
                    "doc_id": doc["doc_id"],
                    "topic": doc["topic"],
                    "summary": media.get("summary", ""),
                    "keywords": media.get("keywords", ""),
                    "original_content": media.get("original_content", ""),
                    "created_at": media.get("created_at", ""),
                    "download_count": media.get("download_count", 0),
                    "user_id": media.get("user_id"),
                    "resources": doc.get("resources", []),
                    "original_length": media.get("original_length", 0),
                    "summary_length": media.get("summary_length", 0)
                }
                formatted_docs.append(formatted_doc)
        
        return formatted_docs
    except Exception as e:
        print(f"Error fetching user documents: {str(e)}")
        return []

def get_user_summaries_with_files(user_id: int, limit: int = 50) -> Dict[str, Any]:
    """Get user's saved summaries with file URLs for download"""
    try:
        # Use .filter() instead of .eq() for JSONB queries
        response = supabase.table("documents").select("*").filter("media->>user_id", "eq", str(user_id)).order("doc_id", desc=True).limit(limit).execute()
        
        summaries = []
        if response.data:
            for doc in response.data:
                media = doc.get("media", {})
                
                # Generate filename for storage
                topic_safe = "".join(c for c in doc["topic"] if c.isalnum() or c in (' ', '-', '_')).rstrip()
                summary_filename = f"{topic_safe}_{doc['doc_id']}.txt"
                
                # Generate file URL (you might want to check if file actually exists)
                summary_file_url = f"summaries/{summary_filename}"
                
                summary_item = {
                    "doc_id": doc["doc_id"],
                    "topic": doc["topic"],
                    "created_at": media.get("created_at", ""),
                    "summary": media.get("summary", ""),
                    "summary_filename": summary_filename,
                    "summary_file_url": summary_file_url,
                    "download_count": media.get("download_count", 0),
                    "original_length": media.get("original_length", 0),
                    "summary_length": media.get("summary_length", 0),
                    "resources": doc.get("resources", [])
                }
                summaries.append(summary_item)
        
        return {
            "success": True,
            "summaries": summaries,
            "count": len(summaries)
        }
        
    except Exception as e:
        print(f"Error in get_user_summaries_with_files: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "summaries": [],
            "count": 0
        }

def get_saved_summaries(user_id: int = None, limit: int = 50) -> Dict[str, Any]:
    """Get saved summaries with pagination support"""
    try:
        query = supabase.table("documents").select("doc_id, topic, media, resources")
        
        if user_id:
            query = query.contains("media", {"user_id": user_id})
        
        response = query.order("doc_id", desc=True).limit(limit).execute()
        
        summaries = []
        if response.data:
            for doc in response.data:
                media = doc.get("media", {})
                summary_item = {
                    "doc_id": doc["doc_id"],
                    "topic": doc["topic"],
                    "summary": media.get("summary", "")[:200] + "..." if len(media.get("summary", "")) > 200 else media.get("summary", ""),
                    "keywords": media.get("keywords", ""),
                    "created_at": media.get("created_at", ""),
                    "download_count": media.get("download_count", 0),
                    "resources_count": len(doc.get("resources", [])),
                    "original_length": media.get("original_length", 0),
                    "summary_length": media.get("summary_length", 0)
                }
                summaries.append(summary_item)
        
        return {
            "success": True,
            "summaries": summaries,
            "count": len(summaries)
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Error fetching summaries: {str(e)}",
            "summaries": [],
            "count": 0
        }

def delete_document(doc_id: int, user_id: int = None) -> Dict[str, Any]:
    """Delete a specific document by ID with optional user verification"""
    try:
        # First check if document exists
        existing_doc = get_document(doc_id)
        if not existing_doc:
            return {"success": False, "message": "Document not found"}
        
        # Optional: Verify user ownership if user_id is provided
        if user_id:
            media = existing_doc.get("media", {})
            doc_user_id = media.get("user_id")
            if doc_user_id and doc_user_id != user_id:
                return {"success": False, "message": "Access denied: You can only delete your own documents"}
        
        # Delete the document
        delete_response = supabase.table("documents").delete().eq("doc_id", doc_id).execute()
        
        if delete_response.data:
            return {
                "success": True, 
                "message": "Document deleted successfully",
                "deleted_doc_id": doc_id
            }
        else:
            return {"success": False, "message": "Failed to delete document"}
            
    except Exception as e:
        return {"success": False, "message": f"Database error: {str(e)}", "error": str(e)}

# File storage functions
def save_uploaded_file_to_storage(file_content: bytes, filename: str) -> Dict[str, Any]:
    """Save uploaded file content to Supabase storage"""
    try:
        # Upload to the summaries bucket
        response = supabase.storage.from_("summaries").upload(filename, file_content)
        
        if response:
            return {
                "success": True,
                "filename": filename,
                "message": "File uploaded successfully"
            }
        else:
            return {
                "success": False,
                "error": "Failed to upload file to storage"
            }
            
    except Exception as e:
        return {
            "success": False,
            "error": f"Storage upload error: {str(e)}"
        }

def get_summary_file_content(filename: str) -> str:
    """Get summary file content from Supabase storage"""
    try:
        response = supabase.storage.from_("summaries").download(filename)
        if response:
            return response.decode('utf-8')
        return None
        
    except Exception as e:
        print(f"Error downloading file {filename}: {str(e)}")
        return None

def create_txt_file_content(summary: str, topic: str, keywords: str = "", resources: list = None) -> str:
    """Create formatted .txt file content"""
    if resources is None:
        resources = []
    
    content = f"STUDY SUMMARY\n"
    content += f"=" * 50 + "\n\n"
    content += f"Topic: {topic}\n\n"
    
    if keywords:
        content += f"Keywords: {keywords}\n\n"
    
    content += f"Summary:\n"
    content += f"-" * 20 + "\n"
    content += f"{summary}\n\n"
    
    if resources:
        content += f"Additional Resources:\n"
        content += f"-" * 30 + "\n"
        for i, resource in enumerate(resources, 1):
            content += f"{i}. {resource}\n"
        content += "\n"
    
    content += f"Generated by StudyHelper\n"
    content += f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    
    return content
