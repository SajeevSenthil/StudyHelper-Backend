import os
import re
import json
import base64
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2 import sql
from dotenv import load_dotenv
from datetime import datetime
from typing import Dict, Any
import openai

# Load environment variables
load_dotenv()

# Configure OpenAI API
client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def get_db_connection():
    """
    Create and return a PostgreSQL database connection
    
    Returns:
        psycopg2.connection: Database connection object
    """
    try:
        # Get database connection details from environment
        db_url = os.getenv("SUPABASE_DB_URL")
        if db_url:
            # Parse Supabase URL format
            conn = psycopg2.connect(db_url)
        else:
            # Use individual environment variables
            conn = psycopg2.connect(
                host=os.getenv("DB_HOST", "localhost"),
                database=os.getenv("DB_NAME", "postgres"),
                user=os.getenv("DB_USER", "postgres"),
                password=os.getenv("DB_PASSWORD", ""),
                port=os.getenv("DB_PORT", 5432)
            )
        return conn
    except Exception as e:
        print(f"Database connection error: {e}")
        return None

def save_document_session_sql(user_id: str, topic: str, original_content: str, 
                             summary: str, resources: list, keywords: str = None) -> Dict[str, Any]:
    """
    Save a complete document session to PostgreSQL documents table using direct SQL
    
    Args:
        user_id (str): User ID (UUID string)
        topic (str): Document topic/title
        original_content (str): Original text content
        summary (str): Generated summary
        resources (list): List of study resources
        keywords (str): Extracted keywords
    
    Returns:
        Dict[str, Any]: Save operation result
    """
    conn = None
    cursor = None
    try:
        # Get database connection
        conn = get_db_connection()
        if not conn:
            return {"success": False, "message": "Database connection failed", "doc_id": None}
        
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Use demo user if no user_id provided
        if not user_id:
            user_id = "550e8400-e29b-41d4-a716-446655440000"
        
        # SQL INSERT query using new schema
        insert_query = """
        INSERT INTO documents (user_id, topic, content, summary, keywords)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING doc_id;
        """
        
        # Execute the query
        cursor.execute(insert_query, (
            user_id,
            topic[:255],  # Ensure topic fits in VARCHAR(255)
            original_content,
            summary,
            keywords
        ))
        
        # Get the inserted document ID
        result = cursor.fetchone()
        if result:
            doc_id = result['doc_id']
            conn.commit()
            
            return {
                "success": True,
                "doc_id": doc_id,
                "message": "Document saved successfully",
                "timestamp": datetime.now().isoformat()
            }
        else:
            conn.rollback()
            return {"success": False, "message": "Failed to save document", "doc_id": None}
            
    except psycopg2.Error as e:
        if conn:
            conn.rollback()
        return {
            "success": False, 
            "message": f"Database error: {str(e)}", 
            "doc_id": None,
            "error": str(e)
        }
    except Exception as e:
        if conn:
            conn.rollback()
        return {
            "success": False, 
            "message": f"Unexpected error: {str(e)}", 
            "doc_id": None,
            "error": str(e)
        }
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def get_user_summaries_sql(user_id: str, limit: int = 50) -> Dict[str, Any]:
    """
    Get user's saved summaries using direct SQL queries
    
    Args:
        user_id (str): User ID (UUID string) to filter by
        limit (int): Maximum number of results
    
    Returns:
        Dict[str, Any]: Query results
    """
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        if not conn:
            return {"success": False, "summaries": [], "count": 0}
        
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # SQL query to get user summaries with new schema
        select_query = """
        SELECT doc_id, user_id, topic, content, summary, keywords, created_at
        FROM documents
        WHERE user_id = %s
        ORDER BY doc_id DESC
        LIMIT %s;
        """
        
        cursor.execute(select_query, (str(user_id), limit))
        results = cursor.fetchall()
        
        summaries = []
        for row in results:
            summary_data = {
                "doc_id": row['doc_id'],
                "topic": row['topic'],
                "user_id": row['user_id'],
                "created_at": row['created_at'],
                "summary": row['summary'] or '',
                "keywords": row['keywords'] or '',
                "content_length": len(row['content'] or ''),
                "summary_length": len(row['summary'] or '')
            }
            summaries.append(summary_data)
        
        return {
            "success": True,
            "summaries": summaries,
            "count": len(summaries)
        }
        
    except psycopg2.Error as e:
        return {
            "success": False,
            "error": f"Database error: {str(e)}",
            "summaries": [],
            "count": 0
        }
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def delete_document_sql(doc_id: int, user_id: str = None) -> Dict[str, Any]:
    """
    Delete a document using direct SQL
    
    Args:
        doc_id (int): Document ID to delete
        user_id (str): Optional user ID (UUID string) for ownership verification
    
    Returns:
        Dict[str, Any]: Delete operation result
    """
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        if not conn:
            return {"success": False, "message": "Database connection failed"}
        
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # First check if document exists and verify ownership
        if user_id:
            check_query = """
            SELECT doc_id, user_id
            FROM documents
            WHERE doc_id = %s;
            """
            cursor.execute(check_query, (doc_id,))
            result = cursor.fetchone()
            
            if not result:
                return {"success": False, "message": "Document not found"}
            
            if result['user_id'] != str(user_id):
                return {"success": False, "message": "Access denied: You can only delete your own documents"}
        
        # Delete the document
        delete_query = """
        DELETE FROM documents
        WHERE doc_id = %s
        RETURNING doc_id;
        """
        
        cursor.execute(delete_query, (doc_id,))
        result = cursor.fetchone()
        
        if result:
            conn.commit()
            return {
                "success": True,
                "message": "Document deleted successfully",
                "deleted_doc_id": result['doc_id']
            }
        else:
            conn.rollback()
            return {"success": False, "message": "Failed to delete document"}
            
    except psycopg2.Error as e:
        if conn:
            conn.rollback()
        return {"success": False, "message": f"Database error: {str(e)}"}
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def clean_text_response(text: str) -> str:
    """
    Clean text response using regex patterns
    
    Args:
        text (str): Raw text to clean
    
    Returns:
        str: Cleaned text
    """
    if not text:
        return ""
    
    # Remove markdown formatting
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)  # Remove bold
    text = re.sub(r'\*(.*?)\*', r'\1', text)      # Remove italic
    text = re.sub(r'`(.*?)`', r'\1', text)        # Remove code backticks
    
    # Remove extra asterisks and special characters
    text = re.sub(r'\*+', '', text)
    text = re.sub(r'#+\s*', '', text)  # Remove markdown headers
    
    # Clean up spacing
    text = re.sub(r'\s+', ' ', text)  # Multiple spaces to single
    text = re.sub(r'\n\s*\n', '\n\n', text)  # Clean paragraph breaks
    
    # Remove trailing/leading whitespace
    text = text.strip()
    
    # Ensure proper sentence ending
    if text and not text.endswith(('.', '!', '?')):
        text += '.'
    
    return text

def summarize_text(text: str, max_length: int = 200) -> str:
    """
    Summarize the given text using OpenAI API
    
    Args:
        text (str): The text to summarize
        max_length (int): Maximum length of summary in words (approximate)
    
    Returns:
        str: Summarized text
    """
    try:
        if not text or len(text.strip()) < 50:
            return "Text too short to summarize effectively."
        
        # Use OpenAI for summarization
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful assistant that creates concise, informative summaries. Focus on the main ideas, key concepts, and important details."
                },
                {
                    "role": "user",
                    "content": f"Please provide a concise summary of the following text in approximately {max_length} words or less:\n\n{text}"
                }
            ],
            max_tokens=1500,
            temperature=0.3
        )
        
        if response and response.choices:
            summary = response.choices[0].message.content.strip()
            # Clean the summary response
            summary = clean_text_response(summary)
            return summary
        else:
            return "OpenAI API Error: No response received"
        
    except Exception as e:
        return f"OpenAI API Error: {str(e)}"

def extract_keywords(text: str) -> str:
    """
    Extract key terms and concepts from the text using OpenAI API
    
    Args:
        text (str): The text to analyze
    
    Returns:
        str: Key terms and concepts
    """
    try:
        if not text or len(text.strip()) < 20:
            return "Text too short for keyword extraction."
        
        # Use OpenAI for keyword extraction
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful assistant that extracts key terms and concepts from text. Present them as a comma-separated list focusing on technical terms, main concepts, and subject-specific vocabulary."
                },
                {
                    "role": "user",
                    "content": f"Please extract the key terms, concepts, and important topics from the following text:\n\n{text}"
                }
            ],
            max_tokens=200,
            temperature=0.3
        )
        
        if response and response.choices:
            keywords = response.choices[0].message.content.strip()
            # Clean the keywords response
            keywords = clean_text_response(keywords)
            return keywords
        else:
            return "OpenAI API Error: No response received"
        
    except Exception as e:
        return f"OpenAI API Error: {str(e)}"

def generate_topic_title(text: str) -> str:
    """
    Generate a concise topic title from the text using OpenAI API
    
    Args:
        text (str): The text to analyze
    
    Returns:
        str: Generated topic title
    """
    try:
        if not text or len(text.strip()) < 20:
            return "Short Text Document"
        
        # Use OpenAI for title generation
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful assistant that generates concise, descriptive titles for documents. The title should be 3-8 words and capture the main topic or theme."
                },
                {
                    "role": "user",
                    "content": f"Please generate a concise title for the following text content:\n\n{text[:500]}..."
                }
            ],
            max_tokens=50,
            temperature=0.3
        )
        
        if response and response.choices:
            title = response.choices[0].message.content.strip()
            # Clean and limit the title
            title = clean_text_response(title)
            # Remove quotes if present
            title = title.strip('"\'')
            if len(title) > 60:
                title = title[:57] + "..."
            return title
        else:
            return "Document Summary"
        
    except Exception as e:
        return f"Document Summary - {str(e)[:20]}"

def summarize_and_save(text: str, topic: str = None, user_id: str = None, max_length: int = 200) -> Dict[str, Any]:
    """
    Summarize text using OpenAI and automatically save it to PostgreSQL using direct SQL
    
    Args:
        text (str): The text to summarize
        topic (str): Topic of the content (auto-generated if not provided)
        user_id (str): User ID (UUID string) for saving to database
        max_length (int): Maximum length of summary in words
    
    Returns:
        Dict[str, Any]: Summary data with save status and doc_id
    """
    try:
        # Import here to avoid circular imports
        from resources import get_study_resources
        
        if not text or len(text.strip()) < 50:
            return {
                "success": False,
                "error": "Text too short to summarize effectively.",
                "summary": None,
                "doc_id": None
            }
        
        # Generate summary and keywords using OpenAI
        summary = summarize_text(text, max_length)
        keywords = extract_keywords(text)
        
        # Generate topic if not provided
        if not topic:
            topic = generate_topic_title(text)
        
        # Get study resources
        resources = get_study_resources(text)
        
        # Use demo user if no user_id provided
        if not user_id:
            user_id = "550e8400-e29b-41d4-a716-446655440000"
        
        # Save to PostgreSQL using direct SQL
        save_result = save_document_session_sql(
            user_id=user_id,
            topic=topic,
            original_content=text,
            summary=summary,
            resources=resources,
            keywords=keywords
        )
        
        return {
            "success": save_result["success"],
            "summary": summary,
            "keywords": keywords,
            "topic": topic,
            "resources": resources,
            "doc_id": save_result.get("doc_id"),
            "message": save_result["message"],
            "original_length": len(text),
            "summary_length": len(summary),
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": f"Summarization and save failed: {str(e)}",
            "summary": None,
            "doc_id": None
        }

def update_document_resources_sql(doc_id: int, resources: list) -> Dict[str, Any]:
    """
    Update resources for an existing document using direct SQL
    
    Args:
        doc_id (int): Document ID to update
        resources (list): List of resource URLs/objects
    
    Returns:
        Dict[str, Any]: Update operation result
    """
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        if not conn:
            return {"success": False, "message": "Database connection failed"}
        
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Update the resources field
        update_query = """
        UPDATE documents
        SET resources = %s
        WHERE doc_id = %s
        RETURNING doc_id;
        """
        
        cursor.execute(update_query, (
            json.dumps(resources) if resources else '[]',
            doc_id
        ))
        
        result = cursor.fetchone()
        if result:
            conn.commit()
            return {
                "success": True,
                "message": "Resources updated successfully",
                "doc_id": result['doc_id']
            }
        else:
            conn.rollback()
            return {"success": False, "message": "Document not found"}
            
    except psycopg2.Error as e:
        if conn:
            conn.rollback()
        return {"success": False, "message": f"Database error: {str(e)}"}
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def get_document_by_id_sql(doc_id: int) -> Dict[str, Any]:
    """
    Get a document by ID using direct SQL
    
    Args:
        doc_id (int): Document ID to retrieve
    
    Returns:
        Dict[str, Any]: Document data or None
    """
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        if not conn:
            return {"success": False, "document": None}
        
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        select_query = """
        SELECT doc_id, topic, resources, media
        FROM documents
        WHERE doc_id = %s;
        """
        
        cursor.execute(select_query, (doc_id,))
        result = cursor.fetchone()
        
        if result:
            return {
                "success": True,
                "document": {
                    "doc_id": result['doc_id'],
                    "topic": result['topic'],
                    "resources": result['resources'] if result['resources'] else [],
                    "media": result['media'] if result['media'] else {}
                }
            }
        else:
            return {"success": False, "document": None}
            
    except psycopg2.Error as e:
        return {"success": False, "document": None, "error": str(e)}
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
