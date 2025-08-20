import os
import openai
from dotenv import load_dotenv
from datetime import datetime
from typing import Dict, Any
import re


# Load environment variables
load_dotenv()

# Set OpenAI API key
openai.api_key = os.getenv("OPENAI_API_KEY")

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
    Summarize the given text using OpenAI's GPT model
    
    Args:
        text (str): The text to summarize
        max_length (int): Maximum length of summary in tokens
    
    Returns:
        str: Summarized text
    """
    try:
        if not text or len(text.strip()) < 50:
            return "Text too short to summarize effectively."
        
        # Create chat completion for summarization
        response = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system", 
                    "content": "You are a helpful assistant that creates concise, clear summaries of academic and study materials. Focus on key concepts, main ideas, and important details."
                },
                {
                    "role": "user", 
                    "content": f"Please provide a comprehensive summary of the following text, highlighting the main points and key concepts:\n\n{text}"
                }
            ],
            max_tokens=max_length,
            temperature=0.3
        )
        
        summary = response.choices[0].message.content.strip()
        
        # Clean the summary response
        summary = clean_text_response(summary)
        
        return summary
        
    except openai.OpenAIError as e:
        return f"OpenAI API Error: {str(e)}"
    except Exception as e:
        return f"Summarization Error: {str(e)}"

def extract_keywords(text: str) -> str:
    """
    Extract key terms and concepts from the text
    
    Args:
        text (str): The text to analyze
    
    Returns:
        str: Key terms and concepts
    """
    try:
        if not text or len(text.strip()) < 20:
            return "Text too short for keyword extraction."
        
        response = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system", 
                    "content": "You are a helpful assistant that extracts key terms, concepts, and important phrases from academic texts. Return them as a comma-separated list."
                },
                {
                    "role": "user", 
                    "content": f"Extract the most important keywords and concepts from this text:\n\n{text}"
                }
            ],
            max_tokens=100,
            temperature=0.2
        )
        
        keywords = response.choices[0].message.content.strip()
        
        # Clean the keywords response
        keywords = clean_text_response(keywords)
        
        return keywords
        
    except openai.OpenAIError as e:
        return f"OpenAI API Error: {str(e)}"
    except Exception as e:
        return f"Keyword extraction Error: {str(e)}"

def summarize_and_save(text: str, topic: str = None, user_id: int = 1, max_length: int = 200) -> Dict[str, Any]:
    """
    Summarize text and automatically save it to Supabase for download
    
    Args:
        text (str): The text to summarize
        topic (str): Topic of the content (auto-generated if not provided)
        user_id (int): User ID for saving to database
        max_length (int): Maximum length of summary in tokens
    
    Returns:
        Dict[str, Any]: Summary data with save status and doc_id
    """
    try:
        # Import here to avoid circular imports
        from supabase_client import save_document_session
        from resources import get_study_resources
        
        if not text or len(text.strip()) < 50:
            return {
                "success": False,
                "error": "Text too short to summarize effectively.",
                "summary": None,
                "doc_id": None
            }
        
        # Generate summary and keywords
        summary = summarize_text(text, max_length)
        keywords = extract_keywords(text)
        
        # Generate topic if not provided
        if not topic:
            topic_response = openai.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system", 
                        "content": "Extract a concise topic title (max 60 characters) from the given text. Return only the title."
                    },
                    {
                        "role": "user", 
                        "content": f"Generate a topic title for this text:\n\n{text[:300]}"
                    }
                ],
                max_tokens=20,
                temperature=0.2
            )
            topic = topic_response.choices[0].message.content.strip()
        
        # Get study resources
        resources = get_study_resources(text)
        
        # Save to Supabase
        save_result = save_document_session(
            user_id=user_id,
            topic=topic,
            original_content=text,
            summary=summary,
            resources=resources
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
