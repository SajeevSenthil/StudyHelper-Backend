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

# Configure OpenAI API
client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def get_study_resources(topic_text: str) -> List[Dict[str, str]]:
    """
    Get study resources and links based on the topic/summary using context-aware web scraping
    
    Args:
        topic_text (str): The text or summary to find resources for
    
    Returns:
        List[Dict[str, str]]: List of relevant study resources with title, url, description
    """
    try:
        # Extract specific topics and concepts from the summary using OpenAI analysis
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system", 
                    "content": """Analyze the given text and extract specific topics, concepts, and keywords that should be used for finding educational resources. 
                    Return a JSON object with:
                    - "main_subject": The general academic field (e.g., "Computer Science", "Biology")
                    - "specific_topics": Array of 3-5 specific concepts/topics mentioned (e.g., ["neural networks", "backpropagation", "deep learning"])
                    - "search_terms": Array of 2-3 best search terms for finding relevant educational content
                    
                    Example: {"main_subject": "Computer Science", "specific_topics": ["binary trees", "traversal algorithms", "data structures"], "search_terms": ["binary tree traversal", "data structures algorithms"]}"""
                },
                {
                    "role": "user", 
                    "content": f"Extract topics and concepts from this text for finding educational resources:\n\n{topic_text[:1000]}"
                }
            ],
            max_tokens=150,
            temperature=0.2
        )
        
        # Parse the OpenAI response to get context-aware topics
        import json
        try:
            ai_response = response.choices[0].message.content.strip() if response and response.choices else ""
            print(f"[DEBUG] Raw OpenAI response: {ai_response[:100]}...")
            
            # Remove markdown code blocks if present
            if ai_response.startswith('```json'):
                ai_response = ai_response.replace('```json', '').replace('```', '').strip()
            elif ai_response.startswith('```'):
                ai_response = ai_response.replace('```', '').strip()
            
            print(f"[DEBUG] Cleaned OpenAI response: {ai_response[:100]}...")
            
            topic_analysis = json.loads(ai_response)
            main_subject = topic_analysis.get("main_subject", "General Studies")
            specific_topics = topic_analysis.get("specific_topics", [])
            search_terms = topic_analysis.get("search_terms", [main_subject])
        except (json.JSONDecodeError, KeyError, AttributeError) as e:
            print(f"[DEBUG] JSON parsing failed: {e}, using fallback")
            # Fallback to simple extraction if JSON parsing fails
            # Extract keywords from the original text
            words = topic_text.lower().split()
            # Take first few meaningful words as search terms
            meaningful_words = [w for w in words if len(w) > 3 and w.isalpha()][:3]
            main_subject = "General Studies"
            specific_topics = meaningful_words
            search_terms = meaningful_words if meaningful_words else ["study materials"]
        
        print(f"[DEBUG] Context-aware analysis: Subject='{main_subject}', Topics={specific_topics}, Search terms={search_terms}")
        
        # Get context-specific resources using the extracted topics
        all_resources = []
        
        # Scrape resources for each specific search term
        for search_term in search_terms[:3]:  # Limit to 3 search terms
            scraped_resources = scrape_educational_resources_contextual(search_term, main_subject)
            all_resources.extend(scraped_resources)
        
        # Get base resources for the main subject
        base_resources = get_topic_specific_resources(main_subject)
        all_resources.extend(base_resources)
        
        # Format and deduplicate resources
        formatted_resources = format_resources(all_resources)
        
        # Remove duplicates based on URL
        seen_urls = set()
        unique_resources = []
        for resource in formatted_resources:
            if resource.get('url') not in seen_urls:
                seen_urls.add(resource.get('url'))
                unique_resources.append(resource)
        
        return unique_resources[:8]  # Return top 8 unique resources
        
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

def scrape_educational_resources_contextual(search_term: str, main_subject: str) -> List[Dict[str, str]]:
    """
    Context-aware scraping that searches for specific topics within educational websites
    
    Args:
        search_term (str): Specific topic/concept to search for
        main_subject (str): General subject area for context
    
    Returns:
        List[Dict[str, str]]: Contextually relevant resources
    """
    scraped_resources = []
    
    try:
        print(f"[DEBUG] Context-aware scraping for: '{search_term}' in subject '{main_subject}'")
        
        # Enhanced Khan Academy search with specific terms
        khan_resources = scrape_khan_academy_contextual(search_term, main_subject)
        scraped_resources.extend(khan_resources)
        
        # Enhanced Coursera search with specific terms
        coursera_resources = scrape_coursera_contextual(search_term, main_subject)
        scraped_resources.extend(coursera_resources)
        
        # Enhanced Wikipedia search with specific terms
        wikipedia_resources = scrape_wikipedia_contextual(search_term)
        scraped_resources.extend(wikipedia_resources)
        
        print(f"[DEBUG] Found {len(scraped_resources)} contextual resources for '{search_term}'")
        
    except Exception as e:
        print(f"Error in contextual web scraping: {str(e)}")
    
    return scraped_resources

def scrape_khan_academy(topic: str) -> List[Dict[str, str]]:
    """Scrape relevant courses from Khan Academy using BeautifulSoup"""
    try:
        # Use Khan Academy's search functionality
        search_url = f"https://www.khanacademy.org/search?page_search_query={topic.replace(' ', '%20')}"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        response = requests.get(search_url, headers=headers, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Look for course links and titles
            resources = []
            course_links = soup.find_all('a', class_=['_1f4zp9x9', '_1f4zp9x9 _14hvi6g8'])[:3]  # Get first 3 results
            
            for link in course_links:
                title_elem = link.find(['h3', 'h4', 'span'])
                if title_elem and link.get('href'):
                    title = clean_text(title_elem.get_text())
                    url = urljoin('https://www.khanacademy.org', link.get('href'))
                    
                    resources.append({
                        "title": f"Khan Academy - {title}",
                        "url": url,
                        "description": f"Interactive course on {title} from Khan Academy"
                    })
            
            # Fallback if no specific courses found
            if not resources:
                resources.append({
                    "title": f"Khan Academy - {topic} Search",
                    "url": search_url,
                    "description": f"Search results for {topic} courses on Khan Academy"
                })
            
            return resources
            
    except Exception as e:
        print(f"Khan Academy scraping error: {str(e)}")
    
    return []

def scrape_coursera(topic: str) -> List[Dict[str, str]]:
    """Scrape relevant courses from Coursera using BeautifulSoup"""
    try:
        search_url = f"https://www.coursera.org/search?query={topic.replace(' ', '%20')}"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        response = requests.get(search_url, headers=headers, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')
            
            resources = []
            # Look for course cards
            course_cards = soup.find_all('div', class_=['css-1pa0qml', 'css-bbd009'])[:2]  # Get first 2 results
            
            for card in course_cards:
                title_elem = card.find(['h3', 'h2', 'span'], class_=['css-e7lgfl', 'css-14d8ngk'])
                link_elem = card.find('a')
                
                if title_elem and link_elem:
                    title = clean_text(title_elem.get_text())
                    url = urljoin('https://www.coursera.org', link_elem.get('href'))
                    
                    resources.append({
                        "title": f"Coursera - {title}",
                        "url": url,
                        "description": f"University-level course: {title}"
                    })
            
            # Fallback if no specific courses found
            if not resources:
                resources.append({
                    "title": f"Coursera - {topic} Courses",
                    "url": search_url,
                    "description": f"Search results for {topic} specializations on Coursera"
                })
            
            return resources
            
    except Exception as e:
        print(f"Coursera scraping error: {str(e)}")
    
    return []

def scrape_wikipedia(topic: str) -> List[Dict[str, str]]:
    """Scrape Wikipedia articles related to the topic using BeautifulSoup"""
    try:
        # First try the Wikipedia API for the main article
        search_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{topic.replace(' ', '_')}"
        
        headers = {
            'User-Agent': 'StudyHelper/1.0 (Educational Tool)'
        }
        
        response = requests.get(search_url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            main_article = {
                "title": f"Wikipedia - {data.get('title', topic)}",
                "url": data.get('content_urls', {}).get('desktop', {}).get('page', f"https://en.wikipedia.org/wiki/{topic.replace(' ', '_')}"),
                "description": clean_text(data.get('extract', f"Wikipedia article about {topic}"))[:200] + "..."
            }
            
            resources = [main_article]
            
            # Try to get related topics using search
            try:
                search_api_url = f"https://en.wikipedia.org/w/api.php?action=opensearch&search={topic}&limit=3&format=json"
                search_response = requests.get(search_api_url, headers=headers, timeout=5)
                
                if search_response.status_code == 200:
                    search_data = search_response.json()
                    if len(search_data) >= 4 and len(search_data[1]) > 1:  # Skip first result (main topic)
                        for i in range(1, min(3, len(search_data[1]))):  # Get 2 related topics
                            title = search_data[1][i]
                            url = search_data[3][i] if i < len(search_data[3]) else f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}"
                            description = search_data[2][i] if i < len(search_data[2]) else f"Related Wikipedia article: {title}"
                            
                            resources.append({
                                "title": f"Wikipedia - {title}",
                                "url": url,
                                "description": clean_text(description)[:200] + "..."
                            })
            except:
                pass  # If search fails, just return main article
            
            return resources
            
    except Exception as e:
        print(f"Wikipedia scraping error: {str(e)}")
    
    return []

# ===== CONTEXTUAL SCRAPING FUNCTIONS =====

def scrape_khan_academy_contextual(search_term: str, main_subject: str) -> List[Dict[str, str]]:
    """Enhanced Khan Academy scraping with context awareness"""
    try:
        # Create more specific search query combining the search term with subject context
        enhanced_query = f"{search_term} {main_subject}".strip()
        search_url = f"https://www.khanacademy.org/search?page_search_query={enhanced_query.replace(' ', '%20')}"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        response = requests.get(search_url, headers=headers, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')
            
            resources = []
            # Look for more specific content matching our search terms
            course_links = soup.find_all('a', class_=['_1f4zp9x9'])[:2]  # Get top 2 results
            
            for link in course_links:
                title_elem = link.find(['h3', 'h4', 'span'])
                if title_elem and link.get('href'):
                    title = clean_text(title_elem.get_text())
                    # Only include if it's relevant to our search term
                    if any(term.lower() in title.lower() for term in search_term.split()):
                        url = urljoin('https://www.khanacademy.org', link.get('href'))
                        resources.append({
                            "title": f"Khan Academy - {title}",
                            "url": url,
                            "description": f"Interactive course on {search_term} from Khan Academy"
                        })
            
            # Fallback with specific search
            if not resources:
                resources.append({
                    "title": f"Khan Academy - {search_term}",
                    "url": search_url,
                    "description": f"Educational content on {search_term} from Khan Academy"
                })
            
            return resources
            
    except Exception as e:
        print(f"Khan Academy contextual scraping error: {str(e)}")
    
    return []

def scrape_coursera_contextual(search_term: str, main_subject: str) -> List[Dict[str, str]]:
    """Enhanced Coursera scraping with context awareness"""
    try:
        # Create more targeted search
        enhanced_query = f"{search_term} {main_subject}".strip()
        search_url = f"https://www.coursera.org/search?query={enhanced_query.replace(' ', '%20')}"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        response = requests.get(search_url, headers=headers, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')
            
            resources = []
            # Look for course cards with relevant content
            course_cards = soup.find_all(['div', 'a'], class_=['css-1pa0myx', 'css-1f83b1j'])[:2]
            
            for card in course_cards:
                title_elem = card.find(['h3', 'h2', 'span'])
                if title_elem:
                    title = clean_text(title_elem.get_text())
                    # Check relevance to search term
                    if any(term.lower() in title.lower() for term in search_term.split()):
                        url = search_url  # Use search URL as fallback
                        resources.append({
                            "title": f"Coursera - {title}",
                            "url": url,
                            "description": f"Professional course on {search_term} from top universities"
                        })
            
            # Fallback
            if not resources:
                resources.append({
                    "title": f"Coursera - {search_term} Courses",
                    "url": search_url,
                    "description": f"Professional courses and specializations on {search_term}"
                })
            
            return resources
            
    except Exception as e:
        print(f"Coursera contextual scraping error: {str(e)}")
    
    return []

def scrape_wikipedia_contextual(search_term: str) -> List[Dict[str, str]]:
    """Enhanced Wikipedia scraping with context awareness"""
    try:
        # Use Wikipedia's API for more accurate search
        search_api_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{search_term.replace(' ', '_')}"
        
        headers = {
            'User-Agent': 'StudyHelper/1.0 (Educational Resource Finder)'
        }
        
        response = requests.get(search_api_url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            
            resources = []
            if 'title' in data and 'extract' in data:
                title = data['title']
                description = data['extract'][:150] + "..." if data['extract'] else f"Wikipedia article about {search_term}"
                url = data.get('content_urls', {}).get('desktop', {}).get('page', f"https://en.wikipedia.org/wiki/{search_term.replace(' ', '_')}")
                
                resources.append({
                    "title": f"Wikipedia - {title}",
                    "url": url,
                    "description": clean_text(description)
                })
            
            # Also try a search for related articles
            search_url = f"https://en.wikipedia.org/w/api.php?action=opensearch&search={search_term}&limit=2&format=json"
            search_response = requests.get(search_url, headers=headers, timeout=10)
            
            if search_response.status_code == 200:
                search_data = search_response.json()
                if len(search_data) >= 3:
                    titles = search_data[1][:1]  # Get top 1 additional result
                    urls = search_data[3][:1]
                    
                    for i, title in enumerate(titles):
                        if i < len(urls) and title.lower() != search_term.lower():
                            resources.append({
                                "title": f"Wikipedia - {title}",
                                "url": urls[i],
                                "description": f"Related Wikipedia article about {title} and {search_term}"
                            })
            
            return resources
            
    except Exception as e:
        print(f"Wikipedia contextual scraping error: {str(e)}")
    
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
