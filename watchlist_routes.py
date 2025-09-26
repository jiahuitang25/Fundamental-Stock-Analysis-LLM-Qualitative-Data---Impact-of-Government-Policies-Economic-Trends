"""
Watchlist routes for the Stock Analysis Application
"""

import logging
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from utils.validation import validate_watchlist_item, validate_pagination_params
from config import Config

logger = logging.getLogger(__name__)

# Create watchlist blueprint
watchlist_bp = Blueprint('watchlist', __name__, url_prefix='/watchlist')

@watchlist_bp.route('/search', methods=['GET'])
@login_required
def search_stocks():
    """Search for stocks to add to watchlist"""
    try:
        query = request.args.get('q', '').strip()
        if not query:
            return jsonify({"error": "Search query is required"}), 400
        
        # This would integrate with a stock search service
        # For now, return mock data
        mock_results = [
            {
                "ticker": "AAPL",
                "company_name": "Apple Inc.",
                "sector": "Technology",
                "industry": "Consumer Electronics",
                "current_price": 150.00,
                "change_percent": 2.5
            },
            {
                "ticker": "MSFT",
                "company_name": "Microsoft Corporation",
                "sector": "Technology",
                "industry": "Software",
                "current_price": 300.00,
                "change_percent": 1.8
            }
        ]
        
        return jsonify({
            "status": "success",
            "results": mock_results,
            "query": query
        }), 200
        
    except Exception as e:
        logger.error(f"Error searching stocks: {e}")
        return jsonify({"error": "Search failed"}), 500

@watchlist_bp.route('/add', methods=['POST'])
@login_required
def add_to_watchlist():
    """Add stock to user's watchlist"""
    try:
        data = request.json
        if not data:
            return jsonify({"error": "No data provided"}), 400
        
        # Validate watchlist item
        validation = validate_watchlist_item(data)
        if not validation["valid"]:
            return jsonify({"error": validation["error"]}), 400
        
        item = validation["item"]
        
        # Ensure user_id matches current user
        if item["user_id"] != current_user.id:
            return jsonify({"error": "Unauthorized"}), 403
        
        # This would integrate with a watchlist service
        # For now, return success
        return jsonify({
            "status": "success",
            "message": "Stock added to watchlist",
            "item": item
        }), 200
        
    except Exception as e:
        logger.error(f"Error adding to watchlist: {e}")
        return jsonify({"error": "Failed to add to watchlist"}), 500

@watchlist_bp.route('/remove', methods=['DELETE'])
@login_required
def remove_from_watchlist():
    """Remove stock from user's watchlist"""
    try:
        data = request.json
        if not data:
            return jsonify({"error": "No data provided"}), 400
        
        ticker = data.get("ticker", "").strip().upper()
        user_id = data.get("user_id", "").strip()
        
        if not ticker or not user_id:
            return jsonify({"error": "Ticker and user_id are required"}), 400
        
        # Ensure user_id matches current user
        if user_id != current_user.id:
            return jsonify({"error": "Unauthorized"}), 403
        
        # This would integrate with a watchlist service
        # For now, return success
        return jsonify({
            "status": "success",
            "message": "Stock removed from watchlist",
            "ticker": ticker
        }), 200
        
    except Exception as e:
        logger.error(f"Error removing from watchlist: {e}")
        return jsonify({"error": "Failed to remove from watchlist"}), 500

@watchlist_bp.route('/list', methods=['GET'])
@login_required
def get_watchlist():
    """Get user's watchlist"""
    try:
        # Get pagination parameters
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 20))
        
        # Validate pagination
        pagination_validation = validate_pagination_params(page, limit)
        if not pagination_validation["valid"]:
            return jsonify({"error": pagination_validation["error"]}), 400
        
        # This would integrate with a watchlist service
        # For now, return mock data
        mock_watchlist = [
            {
                "ticker": "AAPL",
                "company_name": "Apple Inc.",
                "sector": "Technology",
                "industry": "Consumer Electronics",
                "current_price": 150.00,
                "change_percent": 2.5,
                "notes": "Tech giant with strong fundamentals",
                "email_notifications": True,
                "price_alerts": {
                    "high": 160.00,
                    "low": 140.00
                }
            }
        ]
        
        return jsonify({
            "status": "success",
            "watchlist": mock_watchlist,
            "total_items": len(mock_watchlist),
            "page": page,
            "limit": limit
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting watchlist: {e}")
        return jsonify({"error": "Failed to get watchlist"}), 500

@watchlist_bp.route('/update', methods=['PUT'])
@login_required
def update_watchlist_item():
    """Update watchlist item settings"""
    try:
        data = request.json
        if not data:
            return jsonify({"error": "No data provided"}), 400
        
        required_fields = ["ticker", "user_id"]
        for field in required_fields:
            if field not in data:
                return jsonify({"error": f"Missing required field: {field}"}), 400
        
        ticker = data["ticker"].strip().upper()
        user_id = data["user_id"].strip()
        
        # Ensure user_id matches current user
        if user_id != current_user.id:
            return jsonify({"error": "Unauthorized"}), 403
        
        # This would integrate with a watchlist service
        # For now, return success
        return jsonify({
            "status": "success",
            "message": "Watchlist item updated",
            "ticker": ticker
        }), 200
        
    except Exception as e:
        logger.error(f"Error updating watchlist item: {e}")
        return jsonify({"error": "Failed to update watchlist item"}), 500

@watchlist_bp.route('/notifications/setup', methods=['POST'])
@login_required
def setup_email_notifications():
    """Setup email notifications for watchlist"""
    try:
        data = request.json
        if not data:
            return jsonify({"error": "No data provided"}), 400
        
        user_id = data.get("user_id", "").strip()
        
        # Ensure user_id matches current user
        if user_id != current_user.id:
            return jsonify({"error": "Unauthorized"}), 403
        
        # This would integrate with a notification service
        # For now, return success
        return jsonify({
            "status": "success",
            "message": "Email notifications configured"
        }), 200
        
    except Exception as e:
        logger.error(f"Error setting up email notifications: {e}")
        return jsonify({"error": "Failed to setup email notifications"}), 500

@watchlist_bp.route('/alerts/check', methods=['POST'])
@login_required
def trigger_price_alerts():
    """Trigger price alerts for watchlist"""
    try:
        data = request.json
        if not data:
            return jsonify({"error": "No data provided"}), 400
        
        user_id = data.get("user_id", "").strip()
        
        # Ensure user_id matches current user
        if user_id != current_user.id:
            return jsonify({"error": "Unauthorized"}), 403
        
        # This would integrate with a price alert service
        # For now, return success
        return jsonify({
            "status": "success",
            "message": "Price alerts checked",
            "alerts_triggered": 0
        }), 200
        
    except Exception as e:
        logger.error(f"Error triggering price alerts: {e}")
        return jsonify({"error": "Failed to trigger price alerts"}), 500
