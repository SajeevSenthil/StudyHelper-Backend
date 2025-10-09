# Quiz Generation API Documentation

## Overview
Complete implementation of the StudyHelper Quiz Generation feature using OpenAI GPT-4o Mini, FastAPI, and Supabase PostgreSQL. Supports both document-based and topic-based quiz generation with atomic database transactions.

## API Endpoint

### POST `/api/generate-quiz`

Generates a multiple-choice quiz with specified number of questions either from a document or topic.

#### Request Body
```json
{
  "doc_id": 5,           // Optional: Document ID for document-based quiz
  "topic": "Machine Learning",  // Optional: Topic for topic-based quiz  
  "num_questions": 10    // Required: Number of questions (default: 10)
}
```

#### Response Format
**Success (200):**
```json
{
  "success": true,
  "message": "Quiz generated successfully",
  "quiz_id": 12,
  "topic": "Machine Learning", 
  "total_questions": 10
}
```

**Error (400/401/404/500):**
```json
{
  "detail": "Error message describing the issue"
}
```

## Usage Examples

### 1. Topic-Based Quiz Generation
```bash
curl -X POST "/api/generate-quiz" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your-jwt-token" \
  -d '{
    "topic": "Data Structures and Algorithms",
    "num_questions": 5
  }'
```

### 2. Document-Based Quiz Generation
```bash
curl -X POST "/api/generate-quiz" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your-jwt-token" \
  -d '{
    "doc_id": 3,
    "num_questions": 8
  }'
```

### 3. Frontend JavaScript Example
```javascript
const generateQuiz = async (docId = null, topic = null, numQuestions = 10) => {
  const response = await fetch('/api/generate-quiz', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${authToken}`
    },
    body: JSON.stringify({
      ...(docId && { doc_id: docId }),
      ...(topic && { topic }),
      num_questions: numQuestions
    })
  });
  
  if (response.ok) {
    const quiz = await response.json();
    console.log(`Quiz ${quiz.quiz_id} generated with ${quiz.total_questions} questions`);
    // Redirect to quiz taking page
    window.location.href = `/quiz/${quiz.quiz_id}`;
  } else {
    const error = await response.json();
    console.error('Quiz generation failed:', error.detail);
  }
};
```

## Implementation Details

### Database Schema Support
The implementation follows your exact database schema:

- **quizzes**: `(quiz_id, user_id, topic)`
- **questions**: `(question_id, question_text)`
- **options**: `(question_id, option_a, option_b, option_c, option_d, correct_option)`
- **quiz_questions**: `(quiz_id, question_id, question_order, max_marks)`

### Authentication & Authorization
- Uses Supabase JWT token authentication
- Row-Level Security (RLS) automatically filters by `user_id`
- Demo user fallback for development: `550e8400-e29b-41d4-a716-446655440000`

### AI Generation Process
1. **Document Retrieval**: Fetches content/summary from documents table
2. **Prompt Construction**: Creates educational prompt with specific requirements
3. **OpenAI API Call**: Uses GPT-4o-mini with retry logic (up to 3 attempts)
4. **Response Parsing**: Strips markdown, validates JSON structure
5. **Question Validation**: Ensures all required fields and correct option format

### Database Transaction Flow
```python
# Atomic transaction ensures all-or-nothing
try:
    # 1. Create quiz record
    quiz_id = create_quiz(user_id, topic)
    
    # 2. For each AI-generated question:
    for question in ai_questions:
        question_id = insert_question(question_text)
        insert_options(question_id, options, correct_option)
        link_quiz_question(quiz_id, question_id, order, marks)
    
    # 3. Commit transaction
    return success_response(quiz_id)
    
except Exception:
    # 4. Rollback on any failure
    cleanup_quiz(quiz_id)
    return error_response()
```

### Error Handling
- **401 Unauthorized**: Missing or invalid JWT token
- **400 Bad Request**: Missing required fields or invalid parameters
- **404 Not Found**: Document doesn't exist or user doesn't have access
- **500 Internal Server Error**: AI generation failed, database error, or system error

### Retry Logic
- OpenAI API calls retry up to 2 times on failure
- Automatic cleanup of partial database records on failure
- Detailed error logging for debugging

## Testing

### Run the Test Suite
```bash
cd StudyHelper-Backend
python test_quiz_generation.py
```

### Manual Testing
1. **Start Backend**: `uvicorn main:app --reload --host 0.0.0.0 --port 8000`
2. **Set API Key**: `export OPENAI_API_KEY=your_key_here`
3. **Test Topic Quiz**: 
   ```bash
   curl -X POST localhost:8000/api/generate-quiz \
     -H "Content-Type: application/json" \
     -d '{"topic": "Python", "num_questions": 3}'
   ```

## Frontend Integration

### Quiz Generation Workflow
1. **User Input**: Select document OR enter topic + number of questions
2. **API Call**: POST to `/api/generate-quiz` with appropriate payload
3. **Loading State**: Show progress indicator during AI generation
4. **Success Handling**: Redirect to `/quiz/{quiz_id}` to take quiz
5. **Error Handling**: Display error message with retry option

### UI Components Needed
```javascript
// Quiz generation form
const QuizGenerationForm = () => {
  const [mode, setMode] = useState('topic'); // 'topic' or 'document'
  const [topic, setTopic] = useState('');
  const [docId, setDocId] = useState(null);
  const [numQuestions, setNumQuestions] = useState(10);
  const [loading, setLoading] = useState(false);
  
  const handleGenerate = async () => {
    setLoading(true);
    try {
      const response = await generateQuiz(
        mode === 'document' ? docId : null,
        mode === 'topic' ? topic : null,
        numQuestions
      );
      // Handle success
    } catch (error) {
      // Handle error
    } finally {
      setLoading(false);
    }
  };
};
```

## Performance Considerations

### Optimization Strategies
- **Caching**: Consider caching frequently requested topics
- **Async Processing**: Use background tasks for large quizzes
- **Rate Limiting**: Implement user-based rate limits for API calls
- **Content Chunking**: Split large documents into manageable chunks

### Resource Usage
- **OpenAI API**: ~$0.002 per 1000 tokens (varies by usage)
- **Database**: Minimal impact with proper indexing
- **Memory**: Low footprint with streaming responses

## Production Deployment

### Environment Variables Required
```bash
OPENAI_API_KEY=your_openai_api_key
SUPABASE_URL=your_supabase_url
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key
```

### Monitoring & Logging
- API response times and success rates
- OpenAI API usage and costs
- Database transaction success/failure rates
- User quiz generation patterns

## Next Steps

1. **Frontend Integration**: Implement quiz generation UI components
2. **Enhanced Prompts**: Add difficulty level and subject specialization
3. **Question Bank**: Save questions for reuse across quizzes
4. **Analytics**: Track quiz performance and user engagement
5. **Batch Generation**: Support generating multiple quizzes simultaneously

## Support

The implementation is complete and ready for production use. The API follows RESTful conventions and provides comprehensive error handling for robust operation.