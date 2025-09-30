"""
Enhanced main.py endpoints using stored procedures
Add these new endpoints to your existing main.py file
"""

# Add these imports at the top of your main.py
from quiz_database import (
    get_quiz_analytics, 
    get_user_performance_summary,
    search_documents_advanced,
    save_document_with_validation,
    cleanup_old_data
)

# ============================================================================
# ANALYTICS ENDPOINTS USING STORED PROCEDURES
# ============================================================================

@app.get("/api/quiz/{quiz_id}/analytics")
async def get_quiz_analytics_endpoint(quiz_id: int):
    """Get detailed analytics for a specific quiz"""
    try:
        analytics = get_quiz_analytics(quiz_id)
        
        if analytics:
            return {
                "success": True,
                "analytics": analytics
            }
        else:
            raise HTTPException(status_code=404, detail="Quiz not found or no analytics available")
            
    except Exception as e:
        print(f"Error getting quiz analytics: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get quiz analytics: {str(e)}")

@app.get("/api/user/{user_id}/performance")
async def get_user_performance_endpoint(user_id: str):
    """Get comprehensive user performance summary"""
    try:
        performance = get_user_performance_summary(user_id)
        
        if performance:
            return {
                "success": True,
                "performance": performance
            }
        else:
            raise HTTPException(status_code=404, detail="No performance data found for user")
            
    except Exception as e:
        print(f"Error getting user performance: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get user performance: {str(e)}")

@app.get("/api/user/performance")
async def get_current_user_performance(authorization: str = Header(None)):
    """Get performance summary for currently authenticated user"""
    user_id = get_user_from_token(authorization)
    if not user_id:
        # Use demo user for testing
        user_id = "550e8400-e29b-41d4-a716-446655440000"
    
    try:
        performance = get_user_performance_summary(user_id)
        
        if performance:
            return {
                "success": True,
                "performance": performance
            }
        else:
            return {
                "success": True,
                "performance": {
                    "user_id": user_id,
                    "total_quizzes": 0,
                    "average_score": 0,
                    "highest_score": 0,
                    "total_questions_answered": 0,
                    "correct_answers": 0,
                    "accuracy_rate": 0,
                    "recent_performance": [],
                    "topic_performance": []
                }
            }
            
    except Exception as e:
        print(f"Error getting current user performance: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get performance data: {str(e)}")

# ============================================================================
# ADVANCED SEARCH ENDPOINTS
# ============================================================================

class DocumentSearchRequest(BaseModel):
    search_term: str
    limit: Optional[int] = 20
    offset: Optional[int] = 0

@app.post("/api/documents/search")
async def search_documents_endpoint(
    search_request: DocumentSearchRequest,
    authorization: str = Header(None)
):
    """Advanced document search with full-text search capabilities"""
    user_id = get_user_from_token(authorization)
    if not user_id:
        user_id = "550e8400-e29b-41d4-a716-446655440000"
    
    try:
        search_results = search_documents_advanced(
            user_id=user_id,
            search_term=search_request.search_term,
            limit=search_request.limit,
            offset=search_request.offset
        )
        
        if search_results:
            return {
                "success": True,
                "results": search_results
            }
        else:
            return {
                "success": True,
                "results": {
                    "total_count": 0,
                    "documents": []
                }
            }
            
    except Exception as e:
        print(f"Error in document search: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")

# ============================================================================
# ENHANCED DOCUMENT MANAGEMENT
# ============================================================================

class DocumentCreateRequest(BaseModel):
    topic: str
    content: str
    summary: Optional[str] = None
    keywords: Optional[str] = None
    file_url: Optional[str] = None

@app.post("/api/documents/create")
async def create_document_with_validation(
    doc_request: DocumentCreateRequest,
    authorization: str = Header(None)
):
    """Create document with validation using stored procedure"""
    user_id = get_user_from_token(authorization)
    if not user_id:
        user_id = "550e8400-e29b-41d4-a716-446655440000"
    
    try:
        result = save_document_with_validation(
            user_id=user_id,
            topic=doc_request.topic,
            content=doc_request.content,
            summary=doc_request.summary,
            keywords=doc_request.keywords,
            file_url=doc_request.file_url
        )
        
        if result.get('success'):
            return result
        else:
            raise HTTPException(status_code=400, detail=result.get('error', 'Failed to create document'))
            
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error creating document: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to create document: {str(e)}")

# ============================================================================
# SYSTEM MAINTENANCE ENDPOINTS
# ============================================================================

@app.post("/api/admin/cleanup")
async def cleanup_old_data_endpoint(days_old: int = 90):
    """Cleanup old quiz attempts (admin endpoint)"""
    try:
        result = cleanup_old_data(days_old)
        
        if result.get('success'):
            return result
        else:
            raise HTTPException(status_code=500, detail=result.get('error', 'Cleanup failed'))
            
    except Exception as e:
        print(f"Error during cleanup: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Cleanup failed: {str(e)}")

# ============================================================================
# QUIZ MANAGEMENT WITH STORED PROCEDURES
# ============================================================================

@app.get("/api/quizzes/recent")
async def get_recent_quizzes(
    limit: int = 10,
    authorization: str = Header(None)
):
    """Get recent quizzes for the current user"""
    user_id = get_user_from_token(authorization)
    if not user_id:
        user_id = "550e8400-e29b-41d4-a716-446655440000"
    
    try:
        attempts = get_user_quiz_attempts(user_id, limit)
        
        if attempts.get('success'):
            return {
                "success": True,
                "quizzes": attempts.get('attempts', []),
                "count": attempts.get('count', 0)
            }
        else:
            return {
                "success": True,
                "quizzes": [],
                "count": 0
            }
            
    except Exception as e:
        print(f"Error getting recent quizzes: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get recent quizzes: {str(e)}")

@app.get("/api/dashboard/stats")
async def get_dashboard_stats(authorization: str = Header(None)):
    """Get dashboard statistics combining multiple data sources"""
    user_id = get_user_from_token(authorization)
    if not user_id:
        user_id = "550e8400-e29b-41d4-a716-446655440000"
    
    try:
        # Get user performance summary
        performance = get_user_performance_summary(user_id)
        
        # Get recent quiz attempts
        recent_attempts = get_user_quiz_attempts(user_id, 5)
        
        # Get document count (you might need to add this function)
        # For now, we'll use a placeholder
        document_count = 0
        
        dashboard_stats = {
            "user_id": user_id,
            "total_quizzes": performance.get('total_quizzes', 0) if performance else 0,
            "average_score": performance.get('average_score', 0) if performance else 0,
            "total_documents": document_count,
            "recent_activity": recent_attempts.get('attempts', [])[:3] if recent_attempts.get('success') else [],
            "accuracy_rate": performance.get('accuracy_rate', 0) if performance else 0,
            "total_questions_answered": performance.get('total_questions_answered', 0) if performance else 0
        }
        
        return {
            "success": True,
            "stats": dashboard_stats
        }
        
    except Exception as e:
        print(f"Error getting dashboard stats: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get dashboard stats: {str(e)}")

# ============================================================================
# BATCH OPERATIONS USING STORED PROCEDURES
# ============================================================================

class BatchQuizRequest(BaseModel):
    topics: List[str]
    questions_per_quiz: int = 5

@app.post("/api/quizzes/batch-create")
async def create_batch_quizzes(
    batch_request: BatchQuizRequest,
    authorization: str = Header(None)
):
    """Create multiple quizzes using stored procedures for efficiency"""
    user_id = get_user_from_token(authorization)
    if not user_id:
        user_id = "550e8400-e29b-41d4-a716-446655440000"
    
    try:
        results = []
        
        for topic in batch_request.topics:
            # Generate questions for this topic
            questions_data = generate_quiz_questions(topic, batch_request.questions_per_quiz)
            
            if questions_data.get('success'):
                # Save quiz using stored procedure
                save_result = save_quiz_to_database(
                    topic=topic,
                    questions_data=questions_data['questions'],
                    performance_report=f"Batch created quiz for {topic}",
                    user_id=user_id
                )
                
                results.append({
                    "topic": topic,
                    "result": save_result
                })
            else:
                results.append({
                    "topic": topic,
                    "result": {"success": False, "error": "Failed to generate questions"}
                })
        
        # Count successful creations
        successful = sum(1 for r in results if r['result'].get('success'))
        
        return {
            "success": True,
            "total_requested": len(batch_request.topics),
            "successful_creations": successful,
            "results": results
        }
        
    except Exception as e:
        print(f"Error in batch quiz creation: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Batch creation failed: {str(e)}")

# ============================================================================
# HEALTH CHECK FOR STORED PROCEDURES
# ============================================================================

@app.get("/api/health/procedures")
async def check_stored_procedures_health():
    """Health check endpoint to verify stored procedures are working"""
    try:
        # Test a simple stored procedure call
        test_user_id = "550e8400-e29b-41d4-a716-446655440000"
        performance = get_user_performance_summary(test_user_id)
        
        return {
            "success": True,
            "stored_procedures_status": "operational",
            "test_result": "passed",
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        return {
            "success": False,
            "stored_procedures_status": "failed",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }