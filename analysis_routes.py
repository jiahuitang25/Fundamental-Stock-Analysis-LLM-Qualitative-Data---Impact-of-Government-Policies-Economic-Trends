"""
Analysis routes for the Stock Analysis Application
"""

import logging
import uuid
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from services.analysis_service import AnalysisService
from services.rag_service import RAGService
from services.conversation_service import ConversationService
from utils.validation import validate_query, validate_ticker
from config import Config

logger = logging.getLogger(__name__)

# Create analysis blueprint
analysis_bp = Blueprint('analysis', __name__, url_prefix='/analyze')

# Initialize services (these would be injected in a real application)
# For now, we'll initialize them here
from pymongo import MongoClient
db_client = MongoClient(Config.MONGO_URI)
analysis_service = AnalysisService(db_client)
rag_service = RAGService()
conversation_service = ConversationService(db_client)

@analysis_bp.route('/', methods=['POST'])
@login_required
def analyze_stock():
    """Main stock analysis endpoint"""
    try:
        # Start timing the request
        start_time = datetime.now(timezone.utc)
        
        # Get request data
        data = request.json
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400
        
        # Validate required fields
        if "query" not in data:
            return jsonify({"error": "Missing 'query' field"}), 400
        
        query = data["query"].strip()
        if not query:
            return jsonify({"error": "Query cannot be empty"}), 400
        
        # Validate query
        query_validation = validate_query(query)
        if not query_validation["valid"]:
            return jsonify({"error": query_validation["error"]}), 400
        
        query = query_validation["query"]
        
        # Get optional parameters
        ticker = data.get("ticker", "").strip().upper() if data.get("ticker") else None
        session_id = data.get("session_id", str(uuid.uuid4()))
        conversation_id = data.get("conversation_id")
        
        # Validate ticker if provided
        if ticker:
            ticker_validation = validate_ticker(ticker)
            if not ticker_validation["valid"]:
                return jsonify({"error": ticker_validation["error"]}), 400
            ticker = ticker_validation["ticker"]
        
        # Get conversation context
        conversation_context = conversation_service.get_conversation_context(
            session_id, conversation_id
        )
        
        # Check if this is a follow-up query
        is_followup = conversation_service.is_followup_query(query, conversation_context)
        if is_followup:
            query = conversation_service.enhance_followup_query(query, conversation_context)
        
        # Perform analysis
        analysis_result = analysis_service.analyze_stock(
            query=query,
            ticker=ticker,
            user_id=current_user.id,
            session_id=session_id,
            conversation_context=conversation_context
        )
        
        if "error" in analysis_result:
            return jsonify(analysis_result), 500
        
        # Calculate processing time
        processing_time = (datetime.now(timezone.utc) - start_time).total_seconds()
        analysis_result["processing_time"] = processing_time
        
        # Update conversation context
        conversation_service.update_conversation_context(
            session_id, query, analysis_result, {
                "conversation_id": conversation_id,
                "analysis_id": analysis_result.get("analysis_id")
            }
        )
        
        # Store analysis insights as memories
        if analysis_result.get("risk_score") and analysis_result.get("summary"):
            conversation_service.store_analysis_insights(
                session_id, query, analysis_result["risk_score"],
                analysis_result["summary"], analysis_result.get("actionable_insights", []),
                ticker
            )
        
        return jsonify(analysis_result), 200
        
    except Exception as e:
        logger.error(f"Error in stock analysis: {e}", exc_info=True)
        return jsonify({"error": f"Analysis failed: {str(e)}"}), 500

@analysis_bp.route('/history', methods=['GET'])
@login_required
def get_analysis_history():
    """Get analysis history for the current user"""
    try:
        # Get pagination parameters
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 20))
        
        # Validate pagination
        if page < 1 or limit < 1 or limit > 100:
            return jsonify({"error": "Invalid pagination parameters"}), 400
        
        offset = (page - 1) * limit
        
        # Get analysis history
        analyses = analysis_service.get_analysis_history(
            user_id=current_user.id,
            limit=limit,
            offset=offset
        )
        
        return jsonify({
            "status": "success",
            "analyses": analyses,
            "page": page,
            "limit": limit,
            "total": len(analyses)
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting analysis history: {e}")
        return jsonify({"error": "Failed to get analysis history"}), 500

@analysis_bp.route('/feedback', methods=['POST'])
@login_required
def submit_feedback():
    """Submit feedback for an analysis"""
    try:
        data = request.json
        if not data:
            return jsonify({"error": "No data provided"}), 400
        
        # Validate required fields
        required_fields = ["analysis_id", "feedback"]
        for field in required_fields:
            if field not in data:
                return jsonify({"error": f"Missing required field: {field}"}), 400
        
        analysis_id = data["analysis_id"]
        feedback_data = data["feedback"]
        
        # Submit feedback
        success = analysis_service.submit_feedback(
            analysis_id=analysis_id,
            user_id=current_user.id,
            feedback_data=feedback_data
        )
        
        if success:
            return jsonify({"status": "success", "message": "Feedback submitted successfully"}), 200
        else:
            return jsonify({"error": "Failed to submit feedback"}), 500
        
    except Exception as e:
        logger.error(f"Error submitting feedback: {e}")
        return jsonify({"error": "Failed to submit feedback"}), 500

@analysis_bp.route('/feedback/stats', methods=['GET'])
@login_required
def get_feedback_stats():
    """Get feedback statistics for the current user"""
    try:
        stats = analysis_service.get_feedback_stats(user_id=current_user.id)
        
        if "error" in stats:
            return jsonify(stats), 500
        
        return jsonify({
            "status": "success",
            "stats": stats
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting feedback stats: {e}")
        return jsonify({"error": "Failed to get feedback stats"}), 500

@analysis_bp.route('/learning/progress', methods=['GET'])
@login_required
def get_learning_progress():
    """Get learning progress for the current user"""
    try:
        progress = analysis_service.get_learning_progress(user_id=current_user.id)
        
        if "error" in progress:
            return jsonify(progress), 500
        
        return jsonify({
            "status": "success",
            "progress": progress
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting learning progress: {e}")
        return jsonify({"error": "Failed to get learning progress"}), 500

@analysis_bp.route('/context', methods=['GET'])
@login_required
def get_conversation_context():
    """Get conversation context for a session"""
    try:
        session_id = request.args.get('session_id')
        conversation_id = request.args.get('conversation_id')
        
        if not session_id:
            return jsonify({"error": "session_id is required"}), 400
        
        context = conversation_service.get_conversation_context(session_id, conversation_id)
        
        return jsonify({
            "status": "success",
            "context": context
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting conversation context: {e}")
        return jsonify({"error": "Failed to get conversation context"}), 500

@analysis_bp.route('/memories', methods=['GET'])
@login_required
def get_relevant_memories():
    """Get relevant memories for a query"""
    try:
        query = request.args.get('query')
        session_id = request.args.get('session_id')
        ticker = request.args.get('ticker')
        
        if not query:
            return jsonify({"error": "query is required"}), 400
        
        memories = conversation_service.retrieve_relevant_memories(
            query=query,
            session_id=session_id,
            ticker=ticker
        )
        
        return jsonify({
            "status": "success",
            "memories": memories
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting relevant memories: {e}")
        return jsonify({"error": "Failed to get relevant memories"}), 500
