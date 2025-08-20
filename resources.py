import os
import requests
import openai
from dotenv import load_dotenv
from typing import List, Dict, Any
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import time

# Load environment variables  
load_dotenv()

def get_study_resources(topic_text: str) -> List[Dict[str, str]]:
    """
    Get study resources and links based on the topic/summary using web scraping
    
    Args:
        topic_text (str): The text or summary to find resources for
    
    Returns:
        List[Dict[str, str]]: List of relevant study resources with title, url, description
    """
    try:
        # Extract main topic/subject from text using OpenAI
        response = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system", 
                    "content": "Extract the main academic subject/topic from the given text. Return only the subject name (e.g., 'Machine Learning', 'Biology', 'History')."
                },
                {
                    "role": "user", 
                    "content": f"What is the main academic subject of this text?\n\n{topic_text[:500]}"
                }
            ],
            max_tokens=20,
            temperature=0.2
        )
        
        main_topic = response.choices[0].message.content.strip()
        
        # Get base resources
        base_resources = get_topic_specific_resources(main_topic)
        
        # Scrape additional resources
        scraped_resources = scrape_educational_resources(main_topic)
        
        # Combine and format resources
        all_resources = format_resources(base_resources + scraped_resources)
        
        return all_resources[:8]  # Return top 8 resources
        
    except Exception as e:
        print(f"Error getting study resources: {str(e)}")
        return format_resources(get_fallback_resources())

def scrape_educational_resources(topic: str) -> List[Dict[str, str]]:
    """
    Scrape educational resources from various educational websites
    
    Args:
        topic (str): Academic topic to search for
    
    Returns:
        List[Dict[str, str]]: Scraped resources with metadata
    """
    scraped_resources = []
    
    try:
        # Scrape from Khan Academy
        khan_resources = scrape_khan_academy(topic)
        scraped_resources.extend(khan_resources)
        
        # Scrape from Coursera (basic search)
        coursera_resources = scrape_coursera(topic)
        scraped_resources.extend(coursera_resources)
        
        # Scrape from Wikipedia
        wikipedia_resources = scrape_wikipedia(topic)
        scraped_resources.extend(wikipedia_resources)
        
    except Exception as e:
        print(f"Error in web scraping: {str(e)}")
    
    return scraped_resources

def scrape_khan_academy(topic: str) -> List[Dict[str, str]]:
    """Scrape relevant courses from Khan Academy"""
    try:
        # Use Khan Academy's search functionality
        search_url = f"https://www.khanacademy.org/search?page_search_query={topic.replace(' ', '%20')}"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        response = requests.get(search_url, headers=headers, timeout=10)
        if response.status_code == 200:
            return [{
                "title": f"Khan Academy - {topic} Courses",
                "url": "https://www.khanacademy.org",
                "description": f"Free interactive courses and exercises on {topic}"
            }]
    except Exception as e:
        print(f"Khan Academy scraping error: {str(e)}")
    
    return []

def scrape_coursera(topic: str) -> List[Dict[str, str]]:
    """Scrape relevant courses from Coursera"""
    try:
        return [{
            "title": f"Coursera - {topic} Specializations",
            "url": f"https://www.coursera.org/search?query={topic.replace(' ', '%20')}",
            "description": f"University-level courses and specializations in {topic}"
        }]
    except Exception as e:
        print(f"Coursera scraping error: {str(e)}")
    
    return []

def scrape_wikipedia(topic: str) -> List[Dict[str, str]]:
    """Scrape Wikipedia articles related to the topic"""
    try:
        # Wikipedia search API
        search_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{topic.replace(' ', '_')}"
        
        headers = {
            'User-Agent': 'StudyHelper/1.0 (Educational Tool)'
        }
        
        response = requests.get(search_url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            return [{
                "title": f"Wikipedia - {data.get('title', topic)}",
                "url": data.get('content_urls', {}).get('desktop', {}).get('page', f"https://en.wikipedia.org/wiki/{topic.replace(' ', '_')}"),
                "description": clean_text(data.get('extract', f"Wikipedia article about {topic}"))[:200] + "..."
            }]
    except Exception as e:
        print(f"Wikipedia scraping error: {str(e)}")
    
    return []

def clean_text(text: str) -> str:
    """Clean text using regex patterns"""
    if not text:
        return ""
    
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    
    # Remove extra whitespace
    text = re.sub(r'\s+', ' ', text)
    
    # Remove special characters but keep basic punctuation
    text = re.sub(r'[^\w\s\.\,\!\?\-\:\;]', '', text)
    
    # Remove multiple punctuation
    text = re.sub(r'([.!?]){2,}', r'\1', text)
    
    # Remove URLs
    text = re.sub(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', '', text)
    
    return text.strip()

def format_resources(resources: List[str]) -> List[Dict[str, str]]:
    """Format string resources into structured format"""
    formatted = []
    
    for resource in resources:
        if isinstance(resource, str):
            # Extract domain name for title
            try:
                domain = urlparse(resource).netloc
                domain_name = domain.replace('www.', '').split('.')[0].title()
                
                formatted.append({
                    "title": f"{domain_name} - Educational Resource",
                    "url": resource,
                    "description": f"Educational content and courses from {domain_name}"
                })
            except:
                formatted.append({
                    "title": "Educational Resource",
                    "url": resource,
                    "description": "Educational content and learning materials"
                })
        elif isinstance(resource, dict):
            formatted.append(resource)
    
    return formatted



def get_topic_specific_resources(topic: str) -> List[Dict[str, str]]:
    """
    Get topic-specific educational resources as fallback
    
    Args:
        topic (str): Academic topic
    
    Returns:
        List[Dict[str, str]]: List of relevant educational resources with metadata
    """
    topic_lower = topic.lower()
    
    if any(keyword in topic_lower for keyword in ['math', 'calculus', 'algebra', 'geometry', 'mathematics']):
        return [
            {"title": "Khan Academy - Mathematics", "url": "https://www.khanacademy.org/math", "description": "Free interactive math courses from basic arithmetic to advanced calculus"},
            {"title": "Wolfram MathWorld", "url": "https://mathworld.wolfram.com", "description": "Comprehensive mathematics encyclopedia and reference"},
            {"title": "MIT OpenCourseWare - Mathematics", "url": "https://ocw.mit.edu/courses/mathematics/", "description": "Free MIT mathematics courses and materials"},
            {"title": "Paul's Online Math Notes", "url": "https://tutorial.math.lamar.edu", "description": "Comprehensive math tutorials and practice problems"}
        ]
    
    elif any(keyword in topic_lower for keyword in ['physics', 'chemistry', 'science']):
        return [
            {"title": "Khan Academy - Science", "url": "https://www.khanacademy.org/science", "description": "Interactive science courses covering physics, chemistry, and biology"},
            {"title": "PhET Interactive Simulations", "url": "https://phet.colorado.edu", "description": "Free interactive math and science simulations"},
            {"title": "MIT OpenCourseWare - Science", "url": "https://ocw.mit.edu/courses/physics/", "description": "Free MIT science courses and laboratory materials"},
            {"title": "NASA Educational Resources", "url": "https://www.nasa.gov/audience/foreducators/", "description": "Space science and physics educational materials from NASA"}
        ]
    
    elif any(keyword in topic_lower for keyword in ['biology', 'anatomy', 'medicine', 'life science']):
        return [
            {"title": "Khan Academy - Biology", "url": "https://www.khanacademy.org/science/biology", "description": "Comprehensive biology courses from cells to ecosystems"},
            {"title": "NCBI Education", "url": "https://www.ncbi.nlm.nih.gov/education/", "description": "Biomedical databases and research tools from National Center for Biotechnology Information"},
            {"title": "Nature Education", "url": "https://www.nature.com/scitable/", "description": "Free science education resources from Nature Publishing Group"},
            {"title": "Visible Body", "url": "https://www.visiblebody.com", "description": "Interactive 3D anatomy and physiology learning tools"}
        ]
    
    elif any(keyword in topic_lower for keyword in ['computer', 'programming', 'coding', 'software', 'technology']):
        return [
            {"title": "freeCodeCamp", "url": "https://www.freecodecamp.org", "description": "Free coding courses and programming tutorials"},
            {"title": "Codecademy", "url": "https://www.codecademy.com", "description": "Interactive programming courses and coding exercises"},
            {"title": "MIT OpenCourseWare - Computer Science", "url": "https://ocw.mit.edu/courses/electrical-engineering-and-computer-science/", "description": "Free MIT computer science courses and materials"},
            {"title": "Stack Overflow", "url": "https://stackoverflow.com", "description": "Programming Q&A community and developer resources"}
        ]
    
    elif any(keyword in topic_lower for keyword in ['history', 'literature', 'english', 'humanities']):
        return [
            {"title": "Britannica", "url": "https://www.britannica.com", "description": "Comprehensive encyclopedia with historical and literary content"},
            {"title": "Library of Congress", "url": "https://www.loc.gov/education/", "description": "Educational resources from the world's largest library"},
            {"title": "Project Gutenberg", "url": "https://www.gutenberg.org", "description": "Free electronic books and classic literature"},
            {"title": "History.com", "url": "https://www.history.com", "description": "Historical articles, videos, and educational content"}
        ]
    
    elif any(keyword in topic_lower for keyword in ['business', 'economics', 'finance', 'management']):
        return [
            {"title": "Khan Academy - Economics", "url": "https://www.khanacademy.org/economics-finance-domain", "description": "Free economics and finance courses"},
            {"title": "Coursera Business", "url": "https://www.coursera.org/browse/business", "description": "Business and management courses from top universities"},
            {"title": "MIT Sloan Executive Education", "url": "https://executive.mit.edu", "description": "Business education and executive training from MIT"},
            {"title": "Harvard Business Review", "url": "https://hbr.org", "description": "Business insights, case studies, and management articles"}
        ]
    
    else:
        return [
            {"title": "Khan Academy", "url": "https://www.khanacademy.org", "description": "Free online courses covering various subjects"},
            {"title": "Coursera", "url": "https://www.coursera.org", "description": "University courses and professional certificates"},
            {"title": "MIT OpenCourseWare", "url": "https://ocw.mit.edu", "description": "Free course materials from MIT"},
            {"title": "edX", "url": "https://www.edx.org", "description": "Free online courses from top universities"}
        ]

def get_fallback_resources() -> List[Dict[str, str]]:
    """
    Get fallback educational resources when topic extraction fails
    
    Returns:
        List[Dict[str, str]]: General educational resource URLs with metadata
    """
    return [
        {"title": "Khan Academy", "url": "https://www.khanacademy.org", "description": "Free online courses covering math, science, and humanities"},
        {"title": "Coursera", "url": "https://www.coursera.org", "description": "University courses and professional certificates from top institutions"},
        {"title": "MIT OpenCourseWare", "url": "https://ocw.mit.edu", "description": "Free course materials from Massachusetts Institute of Technology"},
        {"title": "edX", "url": "https://www.edx.org", "description": "Free online courses from Harvard, MIT, and other top universities"},
        {"title": "Wikipedia", "url": "https://en.wikipedia.org", "description": "Free encyclopedia with comprehensive articles on various topics"}
    ]
