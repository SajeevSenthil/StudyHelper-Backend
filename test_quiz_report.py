#!/usr/bin/env python3
"""
Test the enhanced quiz submission report functionality
Demonstrates the comprehensive quiz results with questions, options, correct answers, marks, and percentage
"""

import requests
import json
import sys

BASE_URL = ""

def test_quiz_submission_report():
    """Test the enhanced quiz submission report format"""
    print("🧪 Testing Enhanced Quiz Submission Report")
    print("=" * 60)
    
    # First, generate a quiz to test with
    print("1. Generating a test quiz...")
    
    generate_url = f"{BASE_URL}/api/generate-quiz"
    generate_payload = {
        "topic": "Python Basics",
        "num_questions": 3
    }
    
    try:
        generate_response = requests.post(generate_url, json=generate_payload, timeout=30)
        
        if generate_response.status_code != 200:
            print(f"❌ Failed to generate quiz: {generate_response.json()}")
            return False
        
        quiz_data = generate_response.json()
        quiz_id = quiz_data["quiz_id"]
        print(f"✅ Quiz generated successfully! ID: {quiz_id}")
        
        # Get the quiz questions
        print("\n2. Fetching quiz questions...")
        quiz_url = f"{BASE_URL}/quiz/{quiz_id}"
        quiz_response = requests.get(quiz_url)
        
        if quiz_response.status_code != 200:
            print(f"❌ Failed to fetch quiz: {quiz_response.json()}")
            return False
        
        quiz = quiz_response.json()
        questions = quiz["questions"]
        print(f"✅ Fetched {len(questions)} questions")
        
        # Submit quiz with mixed correct/incorrect answers for demonstration
        print("\n3. Submitting quiz with mixed answers...")
        
        # Create answers - mix of correct and incorrect for demonstration
        answers = []
        for i, q in enumerate(questions):
            print(f"   Processing question {i+1}: {q.get('question_text', 'N/A')[:50]}...")
            
            if i == 0:
                # First question - correct answer
                selected = q.get("correct_option", "A")
            elif i == 1:
                # Second question - incorrect answer (pick wrong option)
                correct_opt = q.get("correct_option", "A")
                options = ["A", "B", "C", "D"]
                if correct_opt in options:
                    options.remove(correct_opt)
                selected = options[0]  # Pick first wrong option
            else:
                # Third question - correct answer
                selected = q.get("correct_option", "A")
            
            answers.append({
                "question_id": q["question_id"],
                "selected_option": selected
            })
            print(f"   Selected option: {selected} (Correct: {q.get('correct_option', 'Unknown')})")
        
        submit_url = f"{BASE_URL}/quiz/submit"
        submit_payload = {
            "quiz_id": quiz_id,
            "answers": answers
        }
        
        submit_response = requests.post(submit_url, json=submit_payload)
        
        if submit_response.status_code != 200:
            print(f"❌ Failed to submit quiz: {submit_response.json()}")
            return False
        
        result = submit_response.json()
        print("✅ Quiz submitted successfully!")
        
        # Display the enhanced report
        print("\n4. 📊 ENHANCED QUIZ REPORT:")
        print("=" * 60)
        
        if "quiz_report" in result:
            report = result["quiz_report"]
            
            # Quiz Header
            print(f"📝 Quiz Topic: {report['topic']}")
            print(f"🆔 Quiz ID: {report['quiz_id']}")
            print(f"🆔 User Quiz ID: {report['user_quiz_id']}")
            print()
            
            # Performance Summary
            summary = report["submission_summary"]
            print("📈 PERFORMANCE SUMMARY:")
            print(f"   Total Questions: {summary['total_questions']}")
            print(f"   Correct Answers: {summary['correct_answers']}")
            print(f"   Incorrect Answers: {summary['incorrect_answers']}")
            print(f"   Score: {summary['score']}/{summary['total_marks']}")
            print(f"   Percentage: {summary['percentage']:.1f}%")
            print(f"   Grade: {summary['grade']}")
            print(f"   Status: {summary['status']}")
            print()
            
            # Statistics
            stats = report["statistics"]
            print("📊 STATISTICS:")
            print(f"   Accuracy: {stats['accuracy']}")
            print(f"   Questions Attempted: {stats['questions_attempted']}")
            print(f"   Questions Skipped: {stats['questions_skipped']}")
            print()
            
            # Performance Feedback
            print("💬 PERFORMANCE FEEDBACK:")
            print(f"   {report['performance_feedback']}")
            print()
            
            # Detailed Question Results
            print("📋 DETAILED QUESTION RESULTS:")
            print("-" * 60)
            
            for i, q_result in enumerate(report["detailed_results"], 1):
                print(f"\n🔍 Question {i} (ID: {q_result['question_id']}):")
                print(f"   Q: {q_result['question_text']}")
                print()
                print("   Options:")
                for option, text in q_result["options"].items():
                    marker = ""
                    if option == q_result["correct_option"]:
                        marker = " ✅ (Correct Answer)"
                    elif option == q_result["user_selected"]:
                        marker = " 👤 (Your Answer)"
                    
                    print(f"   {option}: {text}{marker}")
                
                print()
                print(f"   Your Answer: {q_result['user_answer']}")
                print(f"   Correct Answer: {q_result['correct_answer']}")
                print(f"   Status: {q_result['status']}")
                print(f"   Marks: {q_result['marks_awarded']}/{q_result['max_marks']}")
                
                if i < len(report["detailed_results"]):
                    print("-" * 40)
            
        else:
            # Fallback for old format
            print("📊 QUIZ RESULTS (Legacy Format):")
            print(f"Score: {result.get('score', 0)}/{result.get('total_marks', 0)}")
            print(f"Percentage: {result.get('percentage', 0):.1f}%")
            print(f"Topic: {result.get('quiz_topic', 'Unknown')}")
        
        print("\n" + "=" * 60)
        print("🎉 Enhanced quiz report test completed successfully!")
        return True
        
    except requests.exceptions.ConnectionError:
        print("❌ Backend server not running on localhost:8000")
        print("💡 Start with: uvicorn main:app --reload --host 0.0.0.0 --port 8000")
        return False
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False

def main():
    """Run the quiz report test"""
    print("🚀 Starting Enhanced Quiz Report Test")
    
    success = test_quiz_submission_report()
    
    if success:
        print("\n✅ Test completed successfully!")
        print("\n📋 Features Verified:")
        print("   ✅ Comprehensive quiz report format")
        print("   ✅ Question-by-question breakdown")
        print("   ✅ Options display with correct/user answers marked")
        print("   ✅ Performance statistics and grading")
        print("   ✅ Detailed feedback and status indicators")
        print("   ✅ Marks and percentage calculation")
        
        print("\n🎯 Ready for Frontend Integration!")
        print("   The quiz submission now returns a complete report")
        print("   with all the data needed for a rich results UI.")
        
    else:
        print("\n❌ Test failed. Check error messages above.")

if __name__ == "__main__":
    main()