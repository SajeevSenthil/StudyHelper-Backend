import openai
import json
import re
from typing import Dict, List, Any, Optional
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

# Configure APIs - Use OpenAI for quiz generation
client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def clean_quiz_response(text: str) -> str:
    """Clean and format the quiz response text"""
    # Remove extra whitespace and normalize line breaks
    cleaned = re.sub(r'\s+', ' ', text.strip())
    
    # Remove any markdown formatting
    cleaned = re.sub(r'\*\*([^*]+)\*\*', r'\1', cleaned)  # Bold
    cleaned = re.sub(r'\*([^*]+)\*', r'\1', cleaned)      # Italic
    cleaned = re.sub(r'`([^`]+)`', r'\1', cleaned)        # Code
    
    return cleaned

def generate_quiz_questions(content: str, topic: str = None, num_questions: int = 10) -> Dict[str, Any]:
    """
    Generate quiz questions using GPT-4o-mini based on content or topic
    """
    try:
        if topic and not content:
            # Generate quiz from topic
            prompt = f"""
            Generate exactly {num_questions} multiple choice questions about "{topic}".
            
            Requirements:
            - Each question should have exactly 4 options (A, B, C, D)
            - Only one correct answer per question
            - Questions should be challenging but fair
            - Cover different aspects of the topic
            - Include a brief explanation for the correct answer
            
            Format your response as valid JSON:
            {{
                "topic": "{topic}",
                "questions": [
                    {{
                        "question_text": "Question here?",
                        "option_a": "First option",
                        "option_b": "Second option", 
                        "option_c": "Third option",
                        "option_d": "Fourth option",
                        "correct_option": "A",
                        "explanation": "Brief explanation why this is correct"
                    }}
                ]
            }}
            
            Make sure to return exactly {num_questions} questions.
            """
        else:
            # Generate quiz from content
            prompt = f"""
            Based on the following content, generate exactly {num_questions} multiple choice questions.
            
            Content:
            {content[:3000]}  # Limit content to avoid token limits
            
            Requirements:
            - Each question should have exactly 4 options (A, B, C, D)
            - Only one correct answer per question
            - Questions should test understanding of the content
            - Cover different parts of the material
            - Include a brief explanation for the correct answer
            
            Format your response as valid JSON:
            {{
                "topic": "Brief topic name based on content",
                "questions": [
                    {{
                        "question_text": "Question here?",
                        "option_a": "First option",
                        "option_b": "Second option", 
                        "option_c": "Third option",
                        "option_d": "Fourth option",
                        "correct_option": "A",
                        "explanation": "Brief explanation why this is correct"
                    }}
                ]
            }}
            
            Make sure to return exactly {num_questions} questions.
            """
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system", 
                    "content": "You are an expert quiz generator. Always return valid JSON format with exactly the requested number of questions. Ensure questions are educational and test real understanding."
                },
                {"role": "user", "content": prompt}
            ],
            max_tokens=3000,
            temperature=0.7
        )
        
        # Clean the response
        quiz_text = clean_quiz_response(response.choices[0].message.content)
        
        # Parse JSON response
        try:
            quiz_data = json.loads(quiz_text)
        except json.JSONDecodeError:
            # Try to extract JSON from response if wrapped in other text
            json_match = re.search(r'\{.*\}', quiz_text, re.DOTALL)
            if json_match:
                quiz_data = json.loads(json_match.group())
            else:
                raise ValueError("Could not parse JSON from response")
        
        # Validate the structure
        if not isinstance(quiz_data, dict) or 'questions' not in quiz_data:
            raise ValueError("Invalid quiz format")
        
        if len(quiz_data['questions']) != num_questions:
            raise ValueError(f"Expected {num_questions} questions, got {len(quiz_data['questions'])}")
        
        # Validate each question
        for i, q in enumerate(quiz_data['questions']):
            required_fields = ['question_text', 'option_a', 'option_b', 'option_c', 'option_d', 'correct_option', 'explanation']
            for field in required_fields:
                if field not in q:
                    raise ValueError(f"Question {i+1} missing field: {field}")
            
            if q['correct_option'] not in ['A', 'B', 'C', 'D']:
                raise ValueError(f"Question {i+1} has invalid correct_option: {q['correct_option']}")
        
        return {
            "success": True,
            "topic": quiz_data.get('topic', topic or 'Generated Quiz'),
            "questions": quiz_data['questions'],
            "total_questions": len(quiz_data['questions'])
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to generate quiz: {str(e)}",
            "questions": [],
            "total_questions": 0
        }

def generate_performance_feedback(score: int, total_questions: int, topic: str) -> str:
    """
    Generate performance feedback based on quiz results
    """
    percentage = (score / total_questions) * 100
    
    try:
        prompt = f"""
        Generate a brief, encouraging performance feedback for a student who scored {score} out of {total_questions} questions ({percentage:.1f}%) on a quiz about "{topic}".
        
        Requirements:
        - Keep it to exactly 2 lines
        - Be encouraging but honest about performance
        - Include specific suggestions for improvement if needed
        - If score is high (80%+), focus on congratulations and maintaining momentum
        - If score is medium (60-79%), encourage continued effort with specific tips
        - If score is low (<60%), be supportive and suggest focused study areas
        
        Return only the feedback text, no quotes or extra formatting.
        """
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system", 
                    "content": "You are an encouraging tutor providing brief, constructive feedback on quiz performance."
                },
                {"role": "user", "content": prompt}
            ],
            max_tokens=100,
            temperature=0.7
        )
        
        feedback = clean_quiz_response(response.choices[0].message.content)
        
        # Ensure it's exactly 2 lines
        lines = feedback.split('\n')
        if len(lines) > 2:
            feedback = '\n'.join(lines[:2])
        elif len(lines) == 1:
            # Split long line into two
            words = lines[0].split()
            mid = len(words) // 2
            feedback = ' '.join(words[:mid]) + '\n' + ' '.join(words[mid:])
        
        return feedback
        
    except Exception as e:
        # Fallback feedback
        if percentage >= 80:
            return f"Excellent work! You scored {percentage:.1f}% on {topic}.\nKeep up the great momentum and continue exploring advanced concepts."
        elif percentage >= 60:
            return f"Good effort! You scored {percentage:.1f}% on {topic}.\nReview the missed topics and practice more questions to improve further."
        else:
            return f"Keep practicing! You scored {percentage:.1f}% on {topic}.\nFocus on understanding core concepts and try taking more practice quizzes."

if __name__ == "__main__":
    # Test the quiz generation
    test_topic = "Python Programming Basics"
    result = generate_quiz_questions("", test_topic, 5)
    print(json.dumps(result, indent=2))
