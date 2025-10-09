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
            # Generate quiz from topic only
            prompt = f"""You are an expert educational content creator specializing in generating high-quality multiple-choice questions for student assessments.

Generate {num_questions} multiple-choice questions based on the following topic:

TOPIC: {topic}

REQUIREMENTS:
1. Each question must have exactly 4 options (A, B, C, D)
2. Only ONE option should be correct
3. The other 3 options should be plausible distractors (not obviously wrong)
4. Questions should test understanding, not just memorization
5. Vary difficulty across easy, medium, and hard levels
6. Cover different aspects of the topic
7. Make questions clear and unambiguous
8. Each question is worth 1 mark

IMPORTANT: Return the output ONLY as a valid JSON array with this exact structure:
[
  {{
    "question_text": "What is the primary concept in {topic}?",
    "option_a": "First option",
    "option_b": "Second option",
    "option_c": "Third option", 
    "option_d": "Fourth option",
    "correct_option": "A"
  }}
]

Do not include any additional text, explanations, or markdown formatting. Output must be valid JSON only."""
        else:
            # Generate quiz from content
            topic_name = topic or "Content-based Quiz"
            content_snippet = content[:2500] if content else "No content provided"
            
            prompt = f"""You are an expert educational content creator specializing in generating high-quality multiple-choice questions for student assessments.

Generate {num_questions} multiple-choice questions based on the following study material:

TOPIC: {topic_name}

STUDY MATERIAL:
{content_snippet}

REQUIREMENTS:
1. Each question must have exactly 4 options (A, B, C, D)
2. Only ONE option should be correct
3. The other 3 options should be plausible distractors (not obviously wrong)
4. Questions should test understanding, not just memorization
5. Vary difficulty across easy, medium, and hard levels
6. Cover different aspects of the material
7. Make questions clear and unambiguous
8. Each question is worth 1 mark

IMPORTANT: Return the output ONLY as a valid JSON array with this exact structure:
[
  {{
    "question_text": "Based on the material, what is...?",
    "option_a": "First option",
    "option_b": "Second option",
    "option_c": "Third option",
    "option_d": "Fourth option", 
    "correct_option": "A"
  }}
]

Do not include any additional text, explanations, or markdown formatting. Output must be valid JSON only."""
        
        # Make API call with explicit instructions
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system", 
                    "content": "You are a quiz generator. You MUST return only a valid JSON array with exactly the requested number of questions. Each question must have all 5 required fields: question_text, option_a, option_b, option_c, option_d, correct_option. No additional text outside JSON."
                },
                {"role": "user", "content": prompt}
            ],
            max_tokens=4000,
            temperature=0.3  # Lower temperature for more consistent output
        )
        
        # Get and clean the response
        quiz_text = response.choices[0].message.content.strip()
        
        # Remove any markdown code blocks if present
        if quiz_text.startswith("```json"):
            quiz_text = quiz_text[7:]
        if quiz_text.startswith("```"):
            quiz_text = quiz_text[3:]
        if quiz_text.endswith("```"):
            quiz_text = quiz_text[:-3]
        quiz_text = quiz_text.strip()
        
        # Parse JSON response
        try:
            quiz_data = json.loads(quiz_text)
        except json.JSONDecodeError as e:
            print(f"JSON Parse Error: {e}")
            print(f"Response text: {quiz_text[:500]}...")
            # Try to extract JSON array from response
            json_match = re.search(r'\[.*\]', quiz_text, re.DOTALL)
            if json_match:
                try:
                    quiz_data = json.loads(json_match.group())
                except json.JSONDecodeError:
                    raise ValueError(f"Could not parse JSON from response. Raw response: {quiz_text[:200]}...")
            else:
                raise ValueError(f"No JSON array found in response. Raw response: {quiz_text[:200]}...")
        
        # Validate the structure
        if not isinstance(quiz_data, list):
            raise ValueError("Response is not a JSON array")
        
        if len(quiz_data) != num_questions:
            print(f"Warning: Expected {num_questions} questions, got {len(quiz_data)}")
            # Don't fail, just use what we got if it's reasonable
            if len(quiz_data) == 0:
                raise ValueError(f"No questions generated")
        
        # Validate and fix each question
        validated_questions = []
        for i, q in enumerate(quiz_data):
            if not isinstance(q, dict):
                raise ValueError(f"Question {i+1} is not an object")
            
            # Check required fields
            required_fields = ['question_text', 'option_a', 'option_b', 'option_c', 'option_d', 'correct_option']
            missing_fields = [field for field in required_fields if field not in q or not q[field]]
            
            if missing_fields:
                print(f"Question {i+1} missing/empty fields: {missing_fields}")
                raise ValueError(f"Question {i+1} missing field: {missing_fields[0]}")
            
            # Validate correct_option
            if q['correct_option'].upper() not in ['A', 'B', 'C', 'D']:
                print(f"Question {i+1} has invalid correct_option: {q['correct_option']}")
                raise ValueError(f"Question {i+1} has invalid correct_option: {q['correct_option']}")
            
            # Normalize correct_option to uppercase
            q['correct_option'] = q['correct_option'].upper()
            
            # Ensure all fields are strings and non-empty
            for field in required_fields:
                if not isinstance(q[field], str) or not q[field].strip():
                    raise ValueError(f"Question {i+1} field '{field}' is empty or not a string")
                q[field] = q[field].strip()
            
            validated_questions.append(q)
        
        return {
            "success": True,
            "topic": topic or "Generated Quiz",
            "questions": validated_questions,
            "total_questions": len(validated_questions)
        }
        
    except Exception as e:
        error_msg = str(e)
        print(f"Quiz generation error: {error_msg}")
        return {
            "success": False,
            "error": f"Failed to generate quiz: {error_msg}",
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
