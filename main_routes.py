"""
Main routes for the Stock Analysis Application
"""

import logging
from flask import Blueprint, send_from_directory, request, jsonify
from flask_login import login_required, current_user

logger = logging.getLogger(__name__)

# Create main blueprint
main_bp = Blueprint('main', __name__)

@main_bp.route('/')
@login_required
def index():
    """Serve the main application page"""
    try:
        return send_from_directory('.', 'index.html')
    except Exception as e:
        logger.error(f"Error serving index page: {e}")
        return jsonify({"error": "Page not found"}), 404

@main_bp.route('/chatbot')
@login_required
def chatbot():
    """Alternative route for the chatbot interface"""
    try:
        return send_from_directory('.', 'index.html')
    except Exception as e:
        logger.error(f"Error serving chatbot page: {e}")
        return jsonify({"error": "Page not found"}), 404

@main_bp.route('/index.html')
@login_required
def index_html():
    """Alternative route for index.html"""
    try:
        return send_from_directory('.', 'index.html')
    except Exception as e:
        logger.error(f"Error serving index.html: {e}")
        return jsonify({"error": "Page not found"}), 404

@main_bp.route('/watchlist.html')
@login_required
def watchlist_html():
    """Serve the watchlist.html page"""
    try:
        return send_from_directory('.', 'watchlist.html')
    except Exception as e:
        logger.error(f"Error serving watchlist page: {e}")
        return jsonify({"error": "Page not found"}), 404

@main_bp.route('/news.html')
@login_required
def news_html():
    """Route for news.html"""
    try:
        return send_from_directory('.', 'news.html')
    except Exception as e:
        logger.error(f"Error serving news page: {e}")
        return jsonify({"error": "Page not found"}), 404

@main_bp.route('/clear_storage.html')
def clear_storage_html():
    """Route for clearing localStorage - debugging utility"""
    try:
        return send_from_directory('.', 'clear_storage.html')
    except Exception as e:
        logger.error(f"Error serving clear storage page: {e}")
        return jsonify({"error": "Page not found"}), 404

@main_bp.route('/test_news_api.html')
def test_news_api_html():
    """Route for testing news API - debugging utility"""
    try:
        return send_from_directory('.', 'test_news_api.html')
    except Exception as e:
        logger.error(f"Error serving test news API page: {e}")
        return jsonify({"error": "Page not found"}), 404

@main_bp.route('/debug_conversation_transfer.html')
def debug_conversation_transfer_html():
    """Route for debugging conversation transfer - debugging utility"""
    try:
        return send_from_directory('.', 'debug_conversation_transfer.html')
    except Exception as e:
        logger.error(f"Error serving debug conversation transfer page: {e}")
        return jsonify({"error": "Page not found"}), 404

@main_bp.route('/test_auto_refresh.html')
def test_auto_refresh_html():
    """Route for testing auto refresh - debugging utility"""
    try:
        return send_from_directory('.', 'test_auto_refresh.html')
    except Exception as e:
        logger.error(f"Error serving test auto refresh page: {e}")
        return jsonify({"error": "Page not found"}), 404

@main_bp.route('/debug-watchlist.html')
def debug_watchlist_html():
    """Serve the debug watchlist page"""
    try:
        return send_from_directory('.', 'debug-watchlist.html')
    except Exception as e:
        logger.error(f"Error serving debug watchlist page: {e}")
        return jsonify({"error": "Page not found"}), 404

@main_bp.route('/test-auth.html')
def test_auth_html():
    """Serve the authentication test page"""
    try:
        return send_from_directory('.', 'test-auth.html')
    except Exception as e:
        logger.error(f"Error serving test auth page: {e}")
        return jsonify({"error": "Page not found"}), 404

@main_bp.route('/favicon.ico')
def favicon():
    """Serve favicon"""
    try:
        return send_from_directory('.', 'favicon.ico')
    except Exception as e:
        logger.error(f"Error serving favicon: {e}")
        return jsonify({"error": "Favicon not found"}), 404

@main_bp.route('/static/<path:filename>')
def static_files(filename):
    """Serve static files from current directory"""
    try:
        return send_from_directory('.', filename)
    except Exception as e:
        logger.error(f"Error serving static file {filename}: {e}")
        return jsonify({"error": "File not found"}), 404

@main_bp.route('/status', methods=['GET'])
def status():
    """Get application status"""
    try:
        return jsonify({
            "status": "healthy",
            "version": "2.0.0",
            "user": current_user.email if current_user.is_authenticated else None,
            "timestamp": "2024-01-01T00:00:00Z"
        }), 200
    except Exception as e:
        logger.error(f"Error getting status: {e}")
        return jsonify({"error": "Status check failed"}), 500

@main_bp.route('/health', methods=['GET'])
def health_check():
    """Simple health check for load balancers"""
    try:
        return "OK", 200
    except Exception as e:
        logger.error(f"Error in health check: {e}")
        return "ERROR", 500

@main_bp.route('/keep-alive', methods=['GET'])
def keep_alive():
    """Keep alive endpoint"""
    try:
        return jsonify({"status": "alive", "timestamp": "2024-01-01T00:00:00Z"}), 200
    except Exception as e:
        logger.error(f"Error in keep alive: {e}")
        return jsonify({"error": "Keep alive failed"}), 500
