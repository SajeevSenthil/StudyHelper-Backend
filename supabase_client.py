import io
import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from supabase import Client, create_client

# Load environment variables
load_dotenv()

# Environment configuration
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

# Local storage configuration
BASE_DIR = Path(__file__).resolve().parent
LOCAL_DB_PATH = BASE_DIR / "local_documents.db"
LOCAL_STORAGE_DIR = BASE_DIR / "local_storage"
LOCAL_SUMMARIES_DIR = LOCAL_STORAGE_DIR / "summaries"

SUPABASE_AVAILABLE = False
SUPABASE_FAILURE_REASON: Optional[str] = None
_supabase: Optional[Client] = None


def _init_supabase() -> None:
    """Initialise the Supabase client if credentials are available."""
    global _supabase, SUPABASE_AVAILABLE, SUPABASE_FAILURE_REASON

    key = SUPABASE_SERVICE_KEY or SUPABASE_KEY
    if SUPABASE_URL and key:
        try:
            client = create_client(SUPABASE_URL, key)

            # Run a lightweight query to ensure connectivity. This will raise
            # if the project URL is invalid or the network is unavailable.
            client.table("documents").select("doc_id").limit(1).execute()

            key_type = "service" if SUPABASE_SERVICE_KEY else "anon"
            print(f"[DEBUG] Supabase connection established using {key_type} key")
            _supabase = client
            SUPABASE_AVAILABLE = True
            SUPABASE_FAILURE_REASON = None
            return
        except Exception as exc:  # noqa: BLE001 - propagate fallback
            SUPABASE_FAILURE_REASON = str(exc)
            print(f"[WARNING] Supabase connectivity failed: {SUPABASE_FAILURE_REASON}")

    _supabase = None
    SUPABASE_AVAILABLE = False
    if not SUPABASE_FAILURE_REASON:
        SUPABASE_FAILURE_REASON = "Missing Supabase configuration"
    print("[INFO] Falling back to local SQLite storage for documents")


def _init_local_storage() -> None:
    LOCAL_STORAGE_DIR.mkdir(exist_ok=True)
    LOCAL_SUMMARIES_DIR.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(LOCAL_DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS documents (
                doc_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                topic TEXT,
                content TEXT,
                summary TEXT,
                keywords TEXT,
                resources TEXT,
                file_url TEXT,
                created_at TEXT,
                download_count INTEGER DEFAULT 0,
                last_downloaded TEXT
            )
            """
        )
        conn.commit()


def _serialize_resources(resources: Optional[List[Any]]) -> str:
    try:
        return json.dumps(resources or [])
    except TypeError:
        return json.dumps([])


def _deserialize_resources(value: Optional[str]) -> List[Any]:
    if not value:
        return []
    try:
        payload = json.loads(value)
        return payload if isinstance(payload, list) else []
    except json.JSONDecodeError:
        return []


def _ensure_local_mode() -> None:
    if not LOCAL_DB_PATH.exists():
        _init_local_storage()
    else:
        LOCAL_STORAGE_DIR.mkdir(exist_ok=True)
        LOCAL_SUMMARIES_DIR.mkdir(parents=True, exist_ok=True)


def _sqlite_connection() -> sqlite3.Connection:
    _ensure_local_mode()
    conn = sqlite3.connect(LOCAL_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _save_document_session_sqlite(
    user_id: str,
    topic: str,
    original_content: str,
    summary: str,
    resources: List[Any],
    keywords: Optional[str] = None,
) -> Dict[str, Any]:
    timestamp = datetime.utcnow().isoformat()
    with _sqlite_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO documents (user_id, topic, content, summary, keywords, resources, file_url, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                topic[:255],
                original_content,
                summary,
                keywords,
                _serialize_resources(resources),
                None,
                timestamp,
            ),
        )
        doc_id = cursor.lastrowid
        conn.commit()

    return {
        "success": True,
        "message": "Document saved successfully",
        "doc_id": doc_id,
        "timestamp": timestamp,
        "storage": "sqlite",
    }


def _row_to_document(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "doc_id": row["doc_id"],
        "user_id": row["user_id"],
        "topic": row["topic"],
        "content": row["content"],
        "summary": row["summary"],
        "keywords": row["keywords"],
        "resources": _deserialize_resources(row["resources"]),
        "file_url": row["file_url"],
        "created_at": row["created_at"],
        "download_count": row["download_count"],
        "last_downloaded": row["last_downloaded"],
    }


def _handle_supabase_failure(exc: Exception) -> None:
    global SUPABASE_AVAILABLE, SUPABASE_FAILURE_REASON
    SUPABASE_AVAILABLE = False
    SUPABASE_FAILURE_REASON = str(exc)
    print(f"[WARNING] Supabase operation failed: {SUPABASE_FAILURE_REASON}. Falling back to SQLite.")


_init_supabase()
if not SUPABASE_AVAILABLE:
    _init_local_storage()


def _build_media_payload(
    *,
    user_id: str,
    summary: str,
    keywords: Optional[str],
    original_content: str,
    created_at: str,
    resources: Optional[List[Any]] = None,
) -> Dict[str, Any]:
    return {
        "summary": summary,
        "keywords": keywords or "",
        "original_content": original_content,
        "created_at": created_at,
        "download_count": 0,
        "last_downloaded": None,
        "original_length": len(original_content or ""),
        "summary_length": len(summary or ""),
        "user_id": user_id,
        "resources": resources or [],
    }


def _normalize_supabase_document(record: Dict[str, Any]) -> Dict[str, Any]:
    """Normalise Supabase document rows to the internal structure."""
    
    # Schema has: doc_id, user_id, topic, content, summary, file_url
    # No keywords, no created_at, no updated_at
    
    original_content = record.get("content") or ""
    summary_text = record.get("summary") or ""
    resources = record.get("resources") or []
    created_at = datetime.utcnow().isoformat()  # Generate timestamp for compatibility
    
    media = {
        "summary": summary_text,
        "keywords": "",  # Not in schema but keep for compatibility
        "original_content": original_content,
        "created_at": created_at,
        "download_count": 0,
        "last_downloaded": None,
        "original_length": len(original_content),
        "summary_length": len(summary_text),
        "user_id": str(record.get("user_id")),
        "resources": resources,
    }

    return {
        "doc_id": record.get("doc_id"),
        "topic": record.get("topic"),
        "summary": summary_text,
        "keywords": "",  # Not in schema but keep for compatibility
        "original_content": original_content,
        "content": original_content,  # Backwards compatibility
        "created_at": created_at,
        "user_id": str(record.get("user_id")) if record.get("user_id") else None,
        "file_url": record.get("file_url"),
        "resources": resources,
        "media": media,
        "original_length": len(original_content),
        "summary_length": len(summary_text),
    }

def save_document_session(user_id: str, topic: str, original_content: str,
                         summary: str, resources: List[Any], keywords: str = None) -> Dict[str, Any]:
    """Save a complete document session to Supabase documents table."""

    try:
        if not user_id:
            user_id = "550e8400-e29b-41d4-a716-446655440000"

        timestamp = datetime.utcnow().isoformat()

        if SUPABASE_AVAILABLE and _supabase:
            try:
                # Direct table insert - schema has: doc_id, user_id, topic, content, summary, file_url
                insert_data = {
                    "user_id": user_id,
                    "topic": topic[:255],
                    "content": original_content,
                    "summary": summary,
                    "file_url": None
                }
                
                response = _supabase.table("documents").insert(insert_data).execute()
                data = getattr(response, "data", None) if response else None

                if data:
                    row = data[0] if isinstance(data, list) else data
                    doc_id = row.get("doc_id")

                    return {
                        "success": True,
                        "doc_id": doc_id,
                        "message": "Document saved successfully",
                        "timestamp": timestamp,
                        "storage": "supabase",
                    }

                return {
                    "success": False,
                    "message": "Failed to save document",
                    "error": "No data returned",
                }

            except Exception as exc:  # noqa: BLE001
                _handle_supabase_failure(exc)

        # Fallback to SQLite storage
        return _save_document_session_sqlite(user_id, topic, original_content, summary, resources, keywords)

    except Exception as e:  # noqa: BLE001
        return {"success": False, "message": f"Database error: {str(e)}", "error": str(e)}

def get_summary_file_content(filename: str) -> Optional[str]:
    """Download and return the content of a summary .txt file from storage"""
    try:
        if SUPABASE_AVAILABLE and _supabase:
            storage_response = _supabase.storage.from_("summaries").download(filename)
            if storage_response:
                return storage_response.decode("utf-8")
            return None

        file_path = LOCAL_SUMMARIES_DIR / filename
        if file_path.exists():
            return file_path.read_text(encoding="utf-8")
        return None

    except Exception as e:
        print(f"Error downloading summary file {filename}: {str(e)}")
        return None

def save_uploaded_file_to_storage(file_content: bytes, filename: str, user_id: int) -> Dict[str, Any]:
    """Save uploaded file to Supabase storage bucket"""
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_extension = filename.split(".")[-1] if "." in filename else "txt"
        unique_filename = f"upload_{user_id}_{timestamp}.{file_extension}"

        if SUPABASE_AVAILABLE and _supabase:
            content_type_map = {
                "pdf": "application/pdf",
                "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "txt": "text/plain",
            }
            content_type = content_type_map.get(file_extension.lower(), "application/octet-stream")

            storage_response = _supabase.storage.from_("summaries").upload(
                path=unique_filename,
                file=file_content,
                file_options={"content-type": content_type},
            )

            if storage_response:
                file_url = _supabase.storage.from_("summaries").get_public_url(unique_filename)
                return {
                    "success": True,
                    "filename": unique_filename,
                    "file_url": file_url,
                    "original_filename": filename,
                }

        # Local fallback storage
        LOCAL_SUMMARIES_DIR.mkdir(parents=True, exist_ok=True)
        local_path = LOCAL_SUMMARIES_DIR / unique_filename
        local_path.write_bytes(file_content)
        return {
            "success": True,
            "filename": unique_filename,
            "file_url": str(local_path),
            "original_filename": filename,
            "storage": "sqlite",
        }

    except Exception as e:
        return {"success": False, "error": f"Storage upload error: {str(e)}"}

def get_user_summaries_with_files(user_id: int, limit: int = 50) -> Dict[str, Any]:
    """Get user's saved summaries with file URLs"""
    try:
        documents = get_user_documents(str(user_id), limit)

        summaries: List[Dict[str, Any]] = []
        for doc in documents[:limit]:
            media = doc.get("media", {})
            summaries.append({
                "doc_id": doc.get("doc_id"),
                "topic": doc.get("topic"),
                "created_at": doc.get("created_at"),
                "summary": doc.get("summary"),
                "summary_filename": media.get("summary_filename"),
                "summary_file_url": media.get("summary_file_url"),
                "download_count": media.get("download_count", 0),
                "original_length": doc.get("original_length", 0),
                "summary_length": doc.get("summary_length", 0),
                "resources": doc.get("resources", []),
            })

        return {
            "success": True,
            "summaries": summaries,
            "count": len(summaries),
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
        current_doc = get_document(doc_id)
        if not current_doc:
            return {"success": False, "message": "Document not found"}

        if SUPABASE_AVAILABLE and _supabase:
            current_media = current_doc.get("media") or _build_media_payload(
                user_id=str(current_doc.get("user_id")),
                summary=current_doc.get("summary", ""),
                keywords=current_doc.get("keywords"),
                original_content=current_doc.get("original_content", ""),
                created_at=current_doc.get("created_at", datetime.utcnow().isoformat()),
                resources=current_doc.get("resources"),
            )
            current_count = current_media.get("download_count", 0)
            current_media["download_count"] = current_count + 1
            current_media["last_downloaded"] = datetime.utcnow().isoformat()

            update_response = _supabase.table("documents").update({"media": current_media}).eq("doc_id", doc_id).execute()
            if update_response.data:
                return {
                    "success": True,
                    "message": "Download count updated",
                    "download_count": current_count + 1,
                }
            return {"success": False, "message": "Failed to update download count"}

        with _sqlite_connection() as conn:
            conn.execute(
                """
                UPDATE documents
                SET download_count = download_count + 1, last_downloaded = ?
                WHERE doc_id = ?
                """,
                (datetime.utcnow().isoformat(), doc_id),
            )
            conn.commit()

        return {
            "success": True,
            "message": "Download count updated",
        }
        
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
    """Retrieve a document by ID."""

    try:
        if SUPABASE_AVAILABLE and _supabase:
            try:
                # Direct table query - schema has: doc_id, user_id, topic, content, summary, file_url
                response = _supabase.table("documents").select("doc_id, user_id, topic, content, summary, file_url").eq("doc_id", doc_id).execute()

                data = getattr(response, "data", None) if response else None
                if data and len(data) > 0:
                    record = data[0]
                    return _normalize_supabase_document(record)
            except Exception as exc:  # noqa: BLE001
                _handle_supabase_failure(exc)

        with _sqlite_connection() as conn:
            row = conn.execute("SELECT * FROM documents WHERE doc_id = ?", (doc_id,)).fetchone()
            if row:
                document = _row_to_document(row)
                media_payload = _build_media_payload(
                    user_id=document["user_id"],
                    summary=document["summary"],
                    keywords=document["keywords"],
                    original_content=document["content"],
                    created_at=document["created_at"],
                    resources=document.get("resources", []),
                )
                media_payload.update(
                    {
                        "download_count": document["download_count"],
                        "last_downloaded": document["last_downloaded"],
                    }
                )

                record = {
                    "doc_id": document["doc_id"],
                    "topic": document["topic"],
                    "summary": document["summary"],
                    "keywords": document["keywords"],
                    "content": document["content"],
                    "created_at": document["created_at"],
                    "resources": document.get("resources", []),
                    "media": media_payload,
                    "user_id": document["user_id"],
                    "file_url": document["file_url"],
                }

                return _normalize_supabase_document(record)
        return None
    except Exception as e:  # noqa: BLE001
        print(f"Error fetching document: {str(e)}")
        return None


def get_user_documents(user_id: Optional[str] = None, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """Get documents for a specific user (or all documents when user_id is None)."""

    try:
        if SUPABASE_AVAILABLE and _supabase:
            try:
                # Use direct table query - schema has: doc_id, user_id, topic, content, summary, file_url
                query = _supabase.table("documents").select("doc_id, user_id, topic, content, summary, file_url").order("doc_id", desc=True)
                
                if user_id:
                    query = query.eq("user_id", str(user_id))
                if limit:
                    query = query.limit(limit)
                    
                response = query.execute()
                records = getattr(response, "data", None) if response else None

                if not records:
                    return []

                return [_normalize_supabase_document(record) for record in records]

            except Exception as exc:  # noqa: BLE001
                _handle_supabase_failure(exc)

        query = "SELECT * FROM documents"
        params: List[Any] = []
        if user_id:
            query += " WHERE user_id = ?"
            params.append(str(user_id))
        query += " ORDER BY doc_id DESC"
        if limit:
            query += " LIMIT ?"
            params.append(limit)

        with _sqlite_connection() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()

        formatted_docs: List[Dict[str, Any]] = []
        for row in rows:
            doc = _row_to_document(row)
            formatted_docs.append({
                "doc_id": doc["doc_id"],
                "topic": doc["topic"],
                "summary": doc["summary"],
                "keywords": doc["keywords"],
                "original_content": doc["content"],
                "content": doc["content"],
                "created_at": doc["created_at"],
                "user_id": doc["user_id"],
                "file_url": doc["file_url"],
                "resources": doc.get("resources", []),
                "media": {
                    "summary": doc["summary"],
                    "keywords": doc["keywords"],
                    "original_content": doc["content"],
                    "created_at": doc["created_at"],
                    "download_count": doc["download_count"],
                    "last_downloaded": doc["last_downloaded"],
                    "original_length": len(doc["content"] or ""),
                    "summary_length": len(doc["summary"] or ""),
                    "user_id": doc["user_id"],
                    "resources": doc.get("resources", []),
                },
                "original_length": len(doc["content"] or ""),
                "summary_length": len(doc["summary"] or ""),
            })

        return formatted_docs
    except Exception as e:  # noqa: BLE001
        print(f"Error fetching user documents: {str(e)}")
        return []

def get_saved_summaries(user_id: str = None, limit: int = 50) -> Dict[str, Any]:
    """Get saved summaries with pagination support"""
    try:
        documents = get_user_documents(user_id, limit)

        summaries: List[Dict[str, Any]] = []
        for doc in documents[:limit]:
            summary_text = doc.get("summary", "")
            summaries.append({
                "doc_id": doc.get("doc_id"),
                "topic": doc.get("topic"),
                "summary": summary_text[:200] + "..." if len(summary_text) > 200 else summary_text,
                "keywords": doc.get("keywords", ""),
                "created_at": doc.get("created_at"),
                "original_length": doc.get("original_length", 0),
                "summary_length": doc.get("summary_length", 0),
            })

        return {
            "success": True,
            "summaries": summaries,
            "count": len(summaries),
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Error fetching summaries: {str(e)}",
            "summaries": [],
            "count": 0
        }

def delete_document(doc_id: int, user_id: str = None) -> Dict[str, Any]:
    """Delete a specific document by ID with optional user verification"""
    try:
        existing_doc = get_document(doc_id)
        if not existing_doc:
            return {"success": False, "message": "Document not found"}

        if user_id:
            doc_user_id = existing_doc.get("user_id") or existing_doc.get("media", {}).get("user_id")
            if doc_user_id and str(doc_user_id) != str(user_id):
                return {"success": False, "message": "Access denied: You can only delete your own documents"}

        if SUPABASE_AVAILABLE and _supabase:
            try:
                # Direct table delete with RLS policy
                delete_response = _supabase.table("documents").delete().eq("doc_id", doc_id).execute()
                data = getattr(delete_response, "data", None) if delete_response else None

                if data:
                    return {
                        "success": True,
                        "message": "Document deleted successfully",
                        "deleted_doc_id": doc_id,
                    }
                return {"success": False, "message": "Failed to delete document"}
            except Exception as exc:  # noqa: BLE001
                _handle_supabase_failure(exc)

        with _sqlite_connection() as conn:
            conn.execute("DELETE FROM documents WHERE doc_id = ?", (doc_id,))
            conn.commit()

        return {
            "success": True,
            "message": "Document deleted successfully",
            "deleted_doc_id": doc_id,
        }
            
    except Exception as e:
        return {"success": False, "message": f"Database error: {str(e)}", "error": str(e)}


# Expose Supabase client (may be None when running in local mode)
supabase = _supabase
