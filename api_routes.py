"""
API routes for the Stock Analysis Application
"""

import logging
from flask import Blueprint, request, jsonify
from utils.validation import validate_json_input, validate_request_data

logger = logging.getLogger(__name__)

# Create API blueprint
api_bp = Blueprint('api', __name__, url_prefix='/api')

@api_bp.route('/webhook', methods=['POST'])
def webhook_analysis():
    """Webhook endpoint for external analysis requests"""
    try:
        data = request.json
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400
        
        # Validate JSON input
        validation = validate_json_input(data)
        if not validation["valid"]:
            return jsonify({"error": validation["error"]}), 400
        
        # Extract webhook data
        industry = data.get('industry', '')
        macro_factors = data.get('macro_factors', {})
        policies = data.get('policies', [])
        market_data = data.get('market_data', {})
        news = data.get('news', {})
        
        # Sanitize string inputs
        def sanitize_string(s):
            if isinstance(s, str):
                return s.strip()[:1000]  # Limit length
            return s
        
        industry = sanitize_string(industry)
        macro_factors = {k: sanitize_string(v) for k, v in macro_factors.items()}
        policies = [sanitize_string(p) for p in policies if isinstance(p, str)]
        
        # Process webhook data
        analysis_result = {
            "status": "success",
            "webhook_id": "webhook_123",
            "industry": industry,
            "macro_factors": macro_factors,
            "policies_count": len(policies),
            "market_data_keys": list(market_data.keys()),
            "news_keys": list(news.keys()),
            "processed_at": "2024-01-01T12:00:00Z"
        }
        
        return jsonify(analysis_result), 200
        
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        return jsonify({"error": "Webhook processing failed"}), 500

@api_bp.route('/cache/metrics', methods=['GET'])
def get_cache_metrics():
    """Get cache performance metrics"""
    try:
        # This would integrate with a cache service
        # For now, return mock metrics
        metrics = {
            "cache_hits": 1250,
            "cache_misses": 180,
            "hit_rate": 0.87,
            "total_requests": 1430,
            "average_response_time": 0.15,
            "cache_size": 500,
            "memory_usage": "45MB"
        }
        
        return jsonify({
            "status": "success",
            "metrics": metrics
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting cache metrics: {e}")
        return jsonify({"error": "Failed to get cache metrics"}), 500

@api_bp.route('/cache/analytics', methods=['GET'])
def get_cache_analytics():
    """Get detailed cache analytics"""
    try:
        # This would integrate with a cache service
        # For now, return mock analytics
        analytics = {
            "performance_trends": {
                "hit_rate_trend": [0.85, 0.87, 0.89, 0.87, 0.90],
                "response_time_trend": [0.18, 0.16, 0.15, 0.14, 0.15]
            },
            "top_queries": [
                {"query": "AAPL analysis", "frequency": 45},
                {"query": "market outlook", "frequency": 32},
                {"query": "risk assessment", "frequency": 28}
            ],
            "cache_efficiency": {
                "memory_utilization": 0.75,
                "eviction_rate": 0.12,
                "popularity_score": 0.88
            }
        }
        
        return jsonify({
            "status": "success",
            "analytics": analytics
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting cache analytics: {e}")
        return jsonify({"error": "Failed to get cache analytics"}), 500

@api_bp.route('/cache/optimize', methods=['POST'])
def optimize_cache():
    """Optimize cache performance"""
    try:
        data = request.json or {}
        
        # This would integrate with a cache service
        # For now, return success
        optimization_result = {
            "status": "success",
            "message": "Cache optimization completed",
            "optimizations_applied": [
                "Cleared expired entries",
                "Reorganized LRU structure",
                "Updated popularity scores"
            ],
            "performance_improvement": {
                "hit_rate_improvement": 0.05,
                "response_time_improvement": 0.02
            }
        }
        
        return jsonify(optimization_result), 200
        
    except Exception as e:
        logger.error(f"Error optimizing cache: {e}")
        return jsonify({"error": "Cache optimization failed"}), 500

@api_bp.route('/cache/health', methods=['GET'])
def cache_health_check():
    """Check cache health status"""
    try:
        # This would integrate with a cache service
        # For now, return healthy status
        health_status = {
            "status": "healthy",
            "cache_available": True,
            "memory_usage": "45MB",
            "hit_rate": 0.87,
            "last_cleanup": "2024-01-01T11:30:00Z",
            "issues": []
        }
        
        return jsonify({
            "status": "success",
            "health": health_status
        }), 200
        
    except Exception as e:
        logger.error(f"Error checking cache health: {e}")
        return jsonify({"error": "Cache health check failed"}), 500

@api_bp.route('/cache/clear-expired', methods=['POST'])
def clear_expired_cache():
    """Clear expired cache entries"""
    try:
        # This would integrate with a cache service
        # For now, return success
        result = {
            "status": "success",
            "message": "Expired cache entries cleared",
            "entries_cleared": 25,
            "memory_freed": "5MB",
            "cleared_at": "2024-01-01T12:00:00Z"
        }
        
        return jsonify(result), 200
        
    except Exception as e:
        logger.error(f"Error clearing expired cache: {e}")
        return jsonify({"error": "Failed to clear expired cache"}), 500

@api_bp.route('/search/local', methods=['GET'])
def local_stock_search():
    """Search for local stocks (Malaysia)"""
    try:
        query = request.args.get('q', '').strip()
        limit = int(request.args.get('limit', 10))
        
        if not query:
            return jsonify({"error": "Search query is required"}), 400
        
        # This would integrate with a local stock search service
        # For now, return mock data
        mock_results = [
            {
                "ticker": "1155.KL",
                "company_name": "Malayan Banking Berhad",
                "sector": "Financial Services",
                "industry": "Banks",
                "current_price": 8.50,
                "change_percent": 1.2
            },
            {
                "ticker": "3182.KL",
                "company_name": "Genting Berhad",
                "sector": "Consumer Services",
                "industry": "Gaming",
                "current_price": 4.20,
                "change_percent": -0.5
            }
        ]
        
        return jsonify({
            "status": "success",
            "results": mock_results[:limit],
            "query": query,
            "total": len(mock_results)
        }), 200
        
    except Exception as e:
        logger.error(f"Error in local stock search: {e}")
        return jsonify({"error": "Local stock search failed"}), 500

@api_bp.route('/stock/details', methods=['GET'])
def get_stock_details():
    """Get detailed stock information"""
    try:
        ticker = request.args.get('ticker', '').strip().upper()
        
        if not ticker:
            return jsonify({"error": "Ticker symbol is required"}), 400
        
        # This would integrate with a stock data service
        # For now, return mock data
        stock_details = {
            "ticker": ticker,
            "company_name": "Sample Company",
            "sector": "Technology",
            "industry": "Software",
            "current_price": 100.00,
            "previous_close": 98.50,
            "change": 1.50,
            "change_percent": 1.52,
            "volume": 1500000,
            "market_cap": 1000000000,
            "pe_ratio": 25.5,
            "dividend_yield": 2.1,
            "52_week_high": 120.00,
            "52_week_low": 80.00,
            "description": "A sample technology company",
            "website": "https://example.com",
            "last_updated": "2024-01-01T12:00:00Z"
        }
        
        return jsonify({
            "status": "success",
            "stock": stock_details
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting stock details: {e}")
        return jsonify({"error": "Failed to get stock details"}), 500
