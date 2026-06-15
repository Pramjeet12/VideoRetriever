from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor
import os
import traceback
import uuid
from datetime import datetime

load_dotenv()


def disable_broken_local_proxy() -> None:
    """Ignore dead local proxy settings like 127.0.0.1:9 for API calls."""
    proxy_keys = [
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    ]
    for key in proxy_keys:
        value = os.environ.get(key, "")
        if "127.0.0.1:9" in value or "localhost:9" in value:
            os.environ.pop(key, None)


disable_broken_local_proxy()

from core.extractor import extract_meeting_insights
from core.rag_engine import ask_question, build_rag_chain
from core.summarizer import generate_title, summarize
from core.transcriber import transcribe_all
from utils.audio_processor import process_input

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'videoretriever-secret-2024')
CORS(app)

# Store sessions in memory
sessions_data = {}


def build_analysis_outputs(transcript: str) -> tuple[str, str, dict[str, str]]:
    """Generate title, summary, and insights with a safe Windows fallback."""
    try:
        with ThreadPoolExecutor(max_workers=3) as executor:
            title_future = executor.submit(generate_title, transcript)
            summary_future = executor.submit(summarize, transcript)
            insights_future = executor.submit(extract_meeting_insights, transcript)
            return (
                title_future.result(),
                summary_future.result(),
                insights_future.result(),
            )
    except OSError as exc:
        # Some Windows environments can raise OSError(22) during concurrent
        # network/file activity; retry sequentially instead of failing analysis.
        print(f"Parallel analysis fallback triggered: {exc}")
        return (
            generate_title(transcript),
            summarize(transcript),
            extract_meeting_insights(transcript),
        )

@app.route('/')
def index():
    """Home page"""
    return render_template('index.html')

@app.route('/api/analyze', methods=['POST'])
def analyze():
    """Analyze media and extract insights"""
    try:
        data = request.json
        source = data.get('source', '').strip()
        language = data.get('language', 'english')
        
        if not source:
            return jsonify({'error': 'Please provide a source URL or file path'}), 400
        
        # Create unique session ID
        session_id = str(uuid.uuid4())
        
        # Process audio
        chunks = process_input(source)
        
        # Transcribe audio
        transcript = transcribe_all(chunks, language)

        title, summary, insights = build_analysis_outputs(transcript)

        action_items = insights["action_items"]
        decisions = insights["key_decisions"]
        questions = insights["open_questions"]
        
        # Store session data
        sessions_data[session_id] = {
            'title': title,
            'transcript': transcript,
            'summary': summary,
            'action_items': action_items,
            'key_decisions': decisions,
            'open_questions': questions,
            'rag_chain': None,
            'chunks': chunks,
            'created_at': datetime.now().isoformat()
        }
        
        return jsonify({
            'success': True,
            'session_id': session_id,
            'data': {
                'title': title,
                'summary': summary,
                'action_items': action_items,
                'key_decisions': decisions,
                'open_questions': questions,
                'transcript_length': len(transcript),
                'chunks_count': len(chunks)
            }
        }), 200
        
    except Exception as e:
        print("Analyze route failed:")
        traceback.print_exc()
        return jsonify({'error': f'Analysis failed: {str(e)}'}), 500

@app.route('/api/get-result/<session_id>')
def get_result(session_id):
    """Retrieve analysis results for a session"""
    if session_id not in sessions_data:
        return jsonify({'error': 'Session not found'}), 404
    
    result = sessions_data[session_id]
    return jsonify({
        'title': result['title'],
        'summary': result['summary'],
        'action_items': result['action_items'],
        'key_decisions': result['key_decisions'],
        'open_questions': result['open_questions'],
        'transcript': result['transcript'],
        'transcript_length': len(result['transcript']),
        'chunks_count': len(result['chunks']),
        'created_at': result['created_at']
    }), 200

@app.route('/api/ask-question', methods=['POST'])
def ask_rag():
    """Ask a question about the transcript using RAG"""
    try:
        data = request.json
        session_id = data.get('session_id')
        question = data.get('question', '').strip()
        
        if not session_id or session_id not in sessions_data:
            return jsonify({'error': 'Invalid session'}), 400
        
        if not question:
            return jsonify({'error': 'Please provide a question'}), 400
        
        # Build the RAG chain only when the user actually asks a question.
        if sessions_data[session_id]['rag_chain'] is None:
            sessions_data[session_id]['rag_chain'] = build_rag_chain(
                sessions_data[session_id]['transcript']
            )

        rag_chain = sessions_data[session_id]['rag_chain']
        answer = ask_question(rag_chain, question)
        
        return jsonify({
            'success': True,
            'question': question,
            'answer': answer
        }), 200
        
    except Exception as e:
        print("Question route failed:")
        traceback.print_exc()
        return jsonify({'error': f'Question failed: {str(e)}'}), 500

@app.route('/results/<session_id>')
def results(session_id):
    """Results page for a specific session"""
    if session_id not in sessions_data:
        return render_template('error.html', message='Session not found'), 404
    return render_template('results.html', session_id=session_id)

@app.errorhandler(404)
def not_found(error):
    return render_template('error.html', message='Page not found'), 404

@app.errorhandler(500)
def server_error(error):
    return render_template('error.html', message='Internal server error'), 500

if __name__ == '__main__':
    debug_mode = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    port = int(os.getenv("PORT", "5000"))
    # Disable the auto-reloader because audio downloads/conversions create files
    # inside the project, which can trigger a restart mid-request on Windows.
    app.run(
        debug=debug_mode,
        host='0.0.0.0',
        port=port,
        use_reloader=False,
    )
