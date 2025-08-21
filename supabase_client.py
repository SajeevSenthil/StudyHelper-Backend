import os
from supabase import create_client, Client
from dotenv import load_dotenv
from typing import Dict, Any, Optional
from datetime import datetime
import io

# Load environment variables
load_dotenv()

# Initialize Supabase client
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def save_document_session(user_id: int, topic: str, original_content: str, 
                         summary: str, resources: list, keywords: str = None) -> Dict[str, Any]:
    """Save a complete document session to Supabase documents table and storage"""
    try:
        # Generate unique filename for the summary
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        summary_filename = f"summary_{user_id}_{timestamp}.txt"
        
        # Save summary as .txt file to Supabase storage bucket
        summary_file_url = None
        if summary:
            try:
                summary_bytes = summary.encode('utf-8')
                storage_response = supabase.storage.from_("summaries").upload(
                    path=summary_filename,
                    file=summary_bytes,
                    file_options={"content-type": "text/plain"}
                )
                
                if storage_response:
                    # Get public URL for the uploaded file
                    summary_file_url = supabase.storage.from_("summaries").get_public_url(summary_filename)
                    print(f"[DEBUG] Summary saved to storage: {summary_filename}")
                else:
                    print(f"[DEBUG] Failed to save summary to storage")
            except Exception as storage_error:
                print(f"[DEBUG] Storage error: {str(storage_error)}")
                # Continue without storage if it fails
        
        # Prepare media JSONB data
        media_data = {
            "original_content": original_content,
            "summary": summary,
            "summary_file_url": summary_file_url,
            "summary_filename": summary_filename,
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
                "summary_file_url": summary_file_url,
                "timestamp": media_data["created_at"]
            }
        else:
            return {"success": False, "message": "Failed to save document", "error": "No data returned"}
            
    except Exception as e:
        return {"success": False, "message": f"Database error: {str(e)}", "error": str(e)}

def get_summary_file_content(filename: str) -> Optional[str]:
    """Download and return the content of a summary .txt file from storage"""
    try:
        # Download file from storage
        storage_response = supabase.storage.from_("summaries").download(filename)
        
        if storage_response:
            # Convert bytes to string
            content = storage_response.decode('utf-8')
            return content
        return None
        
    except Exception as e:
        print(f"Error downloading summary file {filename}: {str(e)}")
        return None

def save_uploaded_file_to_storage(file_content: bytes, filename: str, user_id: int) -> Dict[str, Any]:
    """Save uploaded file to Supabase storage bucket"""
    try:
        # Generate unique filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_extension = filename.split('.')[-1] if '.' in filename else 'txt'
        unique_filename = f"upload_{user_id}_{timestamp}.{file_extension}"
        
        # Determine content type based on file extension
        content_type_map = {
            'pdf': 'application/pdf',
            'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'txt': 'text/plain'
        }
        content_type = content_type_map.get(file_extension.lower(), 'application/octet-stream')
        
        # Upload to storage
        storage_response = supabase.storage.from_("summaries").upload(
            path=unique_filename,
            file=file_content,
            file_options={"content-type": content_type}
        )
        
        if storage_response:
            file_url = supabase.storage.from_("summaries").get_public_url(unique_filename)
            return {
                "success": True,
                "filename": unique_filename,
                "file_url": file_url,
                "original_filename": filename
            }
        else:
            return {"success": False, "error": "Failed to upload file to storage"}
            
    except Exception as e:
        return {"success": False, "error": f"Storage upload error: {str(e)}"}

def get_user_summaries_with_files(user_id: int, limit: int = 50) -> Dict[str, Any]:
    """Get user's saved summaries with file URLs"""
    try:
        # Use filter for JSONB field
        response = supabase.table("documents").select("*").filter("media->>user_id", "eq", str(user_id)).order("doc_id", desc=True).limit(limit).execute()
        
        summaries = []
        if response.data:
            for doc in response.data:
                media = doc.get("media", {})
                summary_data = {
                    "doc_id": doc["doc_id"],
                    "topic": doc["topic"],
                    "created_at": media.get("created_at"),
                    "summary": media.get("summary", ""),
                    "summary_filename": media.get("summary_filename"),
                    "summary_file_url": media.get("summary_file_url"),
                    "download_count": media.get("download_count", 0),
                    "original_length": media.get("original_length", 0),
                    "summary_length": media.get("summary_length", 0),
                    "resources": doc.get("resources", [])
                }
                summaries.append(summary_data)
        
        return {
            "success": True,
            "summaries": summaries,
            "count": len(summaries)
        }
        
    except Exception as e:
        print(f"[DEBUG] Error in get_user_summaries_with_files: {str(e)}")
        return {
            "success": False,
            "error": f"Database error: {str(e)}",
            "summaries": [],
            "count": 0
        }

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
