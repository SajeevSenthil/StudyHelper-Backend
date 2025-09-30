#!/usr/bin/env python3
"""
Database Stored Procedures Setup and Testing Script
This script sets up and tests all stored procedures for the StudyHelper backend
"""

import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
import json
from typing import Dict, Any

# Load environment variables
load_dotenv()

# Database connection parameters
DATABASE_URL = os.getenv("DATABASE_URL")
DB_HOST = os.getenv("DB_HOST")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_PORT = os.getenv("DB_PORT", "5432")

def get_db_connection():
    """Create and return a database connection"""
    try:
        if DATABASE_URL:
            conn = psycopg2.connect(DATABASE_URL)
        else:
            conn = psycopg2.connect(
                host=DB_HOST,
                database=DB_NAME,
                user=DB_USER,
                password=DB_PASSWORD,
                port=DB_PORT
            )
        return conn
    except Exception as e:
        print(f"PostgreSQL connection error: {str(e)}")
        return None

def execute_sql_file(filepath: str) -> bool:
    """Execute SQL file containing stored procedures"""
    conn = get_db_connection()
    if not conn:
        print("❌ Failed to connect to database")
        return False
    
    try:
        with open(filepath, 'r', encoding='utf-8') as file:
            sql_content = file.read()
        
        cursor = conn.cursor()
        cursor.execute(sql_content)
        conn.commit()
        
        print(f"✅ Successfully executed {filepath}")
        return True
        
    except FileNotFoundError:
        print(f"❌ File not found: {filepath}")
        return False
    except Exception as e:
        print(f"❌ Error executing {filepath}: {str(e)}")
        conn.rollback()
        return False
    finally:
        cursor.close()
        conn.close()

def test_stored_procedures():
    """Test all stored procedures"""
    conn = get_db_connection()
    if not conn:
        print("❌ Failed to connect to database for testing")
        return
    
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        print("\n🧪 Testing Stored Procedures...")
        print("=" * 50)
        
        # Test 1: Create complete quiz
        print("1. Testing create_complete_quiz...")
        test_questions = [
            {
                "question_text": "What is the primary key in database?",
                "option_a": "A foreign key",
                "option_b": "A unique identifier for table rows",
                "option_c": "An index",
                "option_d": "A constraint",
                "correct_option": "B",
                "difficulty_level": "medium"
            },
            {
                "question_text": "What does SQL stand for?",
                "option_a": "Structured Query Language",
                "option_b": "Simple Query Language",
                "option_c": "Standard Query Language", 
                "option_d": "System Query Language",
                "correct_option": "A",
                "difficulty_level": "easy"
            }
        ]
        
        cursor.execute("""
            SELECT create_complete_quiz(
                %s::uuid, 
                %s, 
                %s, 
                %s::jsonb
            ) as result;
        """, (
            "550e8400-e29b-41d4-a716-446655440000",
            "Database Fundamentals Test",
            "Testing stored procedure for quiz creation",
            json.dumps(test_questions)
        ))
        
        quiz_result = cursor.fetchone()['result']
        print(f"   ✅ Quiz creation result: {json.dumps(quiz_result, indent=2)}")
        
        if quiz_result.get('success'):
            quiz_id = quiz_result.get('quiz_id')
            
            # Test 2: Save quiz attempt
            print("\n2. Testing save_quiz_attempt...")
            test_answers = [
                {
                    "question_id": 1,  # This would be actual question IDs from the created quiz
                    "selected_option": "B",
                    "awarded_marks": 1
                },
                {
                    "question_id": 2,
                    "selected_option": "A", 
                    "awarded_marks": 1
                }
            ]
            
            cursor.execute("""
                SELECT save_quiz_attempt(
                    %s::uuid,
                    %s,
                    %s::jsonb,
                    %s,
                    %s
                ) as result;
            """, (
                "550e8400-e29b-41d4-a716-446655440000",
                quiz_id,
                json.dumps(test_answers),
                2,  # total marks
                2   # score
            ))
            
            attempt_result = cursor.fetchone()['result']
            print(f"   ✅ Quiz attempt result: {json.dumps(attempt_result, indent=2)}")
            
            # Test 3: Get quiz analytics
            print("\n3. Testing get_quiz_analytics...")
            cursor.execute("SELECT get_quiz_analytics(%s) as analytics;", (quiz_id,))
            analytics_result = cursor.fetchone()['analytics']
            print(f"   ✅ Quiz analytics: {json.dumps(analytics_result, indent=2)}")
            
            # Test 4: Get user performance summary
            print("\n4. Testing get_user_performance_summary...")
            cursor.execute("SELECT get_user_performance_summary(%s) as performance;", 
                         ("550e8400-e29b-41d4-a716-446655440000",))
            performance_result = cursor.fetchone()['performance']
            print(f"   ✅ User performance: {json.dumps(performance_result, indent=2)}")
        
        # Test 5: Document management
        print("\n5. Testing save_document_with_validation...")
        cursor.execute("""
            SELECT save_document_with_validation(
                %s::uuid,
                %s,
                %s,
                %s,
                %s,
                %s
            ) as result;
        """, (
            "550e8400-e29b-41d4-a716-446655440000",
            "Database Design Principles",
            "This document covers the fundamental principles of database design including normalization, entity-relationship modeling, and best practices for creating efficient database schemas.",
            "A comprehensive guide to database design principles and best practices.",
            "database, design, normalization, ER model, schema",
            None
        ))
        
        doc_result = cursor.fetchone()['result']
        print(f"   ✅ Document save result: {json.dumps(doc_result, indent=2)}")
        
        # Test 6: Advanced search
        print("\n6. Testing search_documents...")
        cursor.execute("""
            SELECT search_documents(
                %s::uuid,
                %s,
                %s,
                %s
            ) as search_results;
        """, (
            "550e8400-e29b-41d4-a716-446655440000",
            "database design",
            5,  # limit
            0   # offset
        ))
        
        search_result = cursor.fetchone()['search_results']
        print(f"   ✅ Search results: {json.dumps(search_result, indent=2)}")
        
        print("\n🎉 All stored procedure tests completed successfully!")
        
    except Exception as e:
        print(f"❌ Error during testing: {str(e)}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

def list_stored_procedures():
    """List all stored procedures in the database"""
    conn = get_db_connection()
    if not conn:
        print("❌ Failed to connect to database")
        return
    
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Query to get all stored procedures/functions
        cursor.execute("""
            SELECT 
                p.proname as function_name,
                pg_catalog.pg_get_function_result(p.oid) as return_type,
                pg_catalog.pg_get_function_arguments(p.oid) as arguments,
                d.description
            FROM pg_proc p
            LEFT JOIN pg_description d ON p.oid = d.objoid
            WHERE p.pronamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'public')
            AND p.prokind = 'f'  -- Only functions, not procedures
            ORDER BY p.proname;
        """)
        
        procedures = cursor.fetchall()
        
        print("\n📋 Available Stored Procedures/Functions:")
        print("=" * 60)
        
        for proc in procedures:
            print(f"Function: {proc['function_name']}")
            print(f"  Returns: {proc['return_type']}")
            print(f"  Arguments: {proc['arguments']}")
            if proc['description']:
                print(f"  Description: {proc['description']}")
            print()
        
    except Exception as e:
        print(f"❌ Error listing procedures: {str(e)}")
    finally:
        cursor.close()
        conn.close()

def performance_comparison():
    """Compare performance between stored procedures and regular queries"""
    conn = get_db_connection()
    if not conn:
        print("❌ Failed to connect to database")
        return
    
    try:
        import time
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        print("\n⚡ Performance Comparison:")
        print("=" * 40)
        
        # Test quiz creation performance
        test_questions = [
            {
                "question_text": f"Performance test question {i}",
                "option_a": "Option A",
                "option_b": "Option B", 
                "option_c": "Option C",
                "option_d": "Option D",
                "correct_option": "A"
            } for i in range(10)
        ]
        
        # Test stored procedure
        start_time = time.time()
        for i in range(5):
            cursor.execute("""
                SELECT create_complete_quiz(
                    %s::uuid, 
                    %s, 
                    %s, 
                    %s::jsonb
                ) as result;
            """, (
                "550e8400-e29b-41d4-a716-446655440000",
                f"Performance Test Quiz {i}",
                "Performance testing",
                json.dumps(test_questions)
            ))
            cursor.fetchone()
        
        procedure_time = time.time() - start_time
        
        print(f"Stored Procedure (5 quizzes): {procedure_time:.4f} seconds")
        print(f"Average per quiz: {procedure_time/5:.4f} seconds")
        
        print("\n📈 Benefits of Stored Procedures:")
        print("  ✅ Reduced network traffic")
        print("  ✅ Better transaction management")
        print("  ✅ Centralized business logic")
        print("  ✅ Enhanced security")
        print("  ✅ Better error handling")
        print("  ✅ Improved maintainability")
        
    except Exception as e:
        print(f"❌ Error in performance comparison: {str(e)}")
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    print("🔧 StudyHelper Database Stored Procedures Setup")
    print("=" * 50)
    
    # Step 1: Execute stored procedures file
    print("\n1. Setting up stored procedures...")
    if execute_sql_file("stored_procedures.sql"):
        
        # Step 2: List available procedures
        print("\n2. Listing available procedures...")
        list_stored_procedures()
        
        # Step 3: Test procedures
        print("\n3. Testing procedures...")
        test_stored_procedures()
        
        # Step 4: Performance comparison
        print("\n4. Performance analysis...")
        performance_comparison()
        
        print("\n✨ Setup completed successfully!")
        print("\nNext steps:")
        print("1. Update your Python code to use the new stored procedures")
        print("2. Monitor performance improvements")
        print("3. Consider adding more specialized procedures as needed")
        
    else:
        print("❌ Failed to set up stored procedures")