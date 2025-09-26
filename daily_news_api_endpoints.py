#!/usr/bin/env python3
"""
Daily News API Endpoints
Flask endpoints to manage the daily news notification system
"""

import os
import json
import logging
from datetime import datetime, timezone
from flask import Flask, request, jsonify, Blueprint
from flask_login import login_required, current_user
from daily_news_notification_system import DailyNewsNotificationSystem
from watchlist_sector_mapping import WatchlistSectorMapping

# Create Blueprint for news notifications
news_notification_bp = Blueprint('news_notification', __name__, url_prefix='/news-notifications')

# Configure logging
logger = logging.getLogger(__name__)

# Global instances (will be initialized when blueprint is registered)
notification_system = None
sector_mapper = None

def init_news_notification_system():
    """Initialize the notification system and sector mapper"""
    global notification_system, sector_mapper
    try:
        notification_system = DailyNewsNotificationSystem()
        sector_mapper = WatchlistSectorMapping()
        logger.info("✅ News notification system initialized")
    except Exception as e:
        logger.error(f"❌ Failed to initialize news notification system: {e}")

@news_notification_bp.route('/status', methods=['GET'])
def get_system_status():
    """Get the status of the daily news notification system"""
    try:
        if not notification_system:
            init_news_notification_system()
        
        status = notification_system.get_status() if notification_system else {'error': 'System not initialized'}
        
        # Add sector mapping statistics
        if sector_mapper:
            sector_stats = sector_mapper.get_sector_statistics()
            status['sector_mapping'] = {
                'total_users': sector_stats.get('total_users', 0),
                'total_stocks': sector_stats.get('total_stocks', 0),
                'unique_sectors': sector_stats.get('unique_sectors', 0)
            }
        
        return jsonify({
            'status': 'success',
            'system_status': status,
            'timestamp': datetime.now(timezone.utc).isoformat()
        })
    
    except Exception as e:
        logger.error(f"❌ Error getting system status: {str(e)}")
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500

@news_notification_bp.route('/start', methods=['POST'])
@login_required
def start_notification_system():
    """Start the daily news notification system"""
    try:
        # Check if user has admin privileges (optional security check)
        # if not current_user.is_admin:  # Uncomment if you have admin role checking
        #     return jsonify({'status': 'error', 'error': 'Admin privileges required'}), 403
        
        if not notification_system:
            init_news_notification_system()
        
        if notification_system.start_scheduler():
            return jsonify({
                'status': 'success',
                'message': 'Daily news notification system started successfully',
                'scheduled_time': '08:00 AM Malaysia time',
                'timestamp': datetime.now(timezone.utc).isoformat()
            })
        else:
            return jsonify({
                'status': 'error',
                'error': 'Failed to start the notification system'
            }), 500
    
    except Exception as e:
        logger.error(f"❌ Error starting notification system: {str(e)}")
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500

@news_notification_bp.route('/stop', methods=['POST'])
@login_required
def stop_notification_system():
    """Stop the daily news notification system"""
    try:
        if not notification_system:
            return jsonify({
                'status': 'error',
                'error': 'Notification system not initialized'
            }), 400
        
        if notification_system.stop_scheduler():
            return jsonify({
                'status': 'success',
                'message': 'Daily news notification system stopped successfully',
                'timestamp': datetime.now(timezone.utc).isoformat()
            })
        else:
            return jsonify({
                'status': 'error',
                'error': 'Failed to stop the notification system'
            }), 500
    
    except Exception as e:
        logger.error(f"❌ Error stopping notification system: {str(e)}")
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500

@news_notification_bp.route('/test-run', methods=['POST'])
@login_required
def test_notification_system():
    """Run an immediate test of the notification system"""
    try:
        if not notification_system:
            init_news_notification_system()
        
        if notification_system.test_immediate_run():
            return jsonify({
                'status': 'success',
                'message': 'Test run completed successfully',
                'timestamp': datetime.now(timezone.utc).isoformat()
            })
        else:
            return jsonify({
                'status': 'error',
                'error': 'Test run failed'
            }), 500
    
    except Exception as e:
        logger.error(f"❌ Error in test run: {str(e)}")
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500

@news_notification_bp.route('/user-sectors', methods=['GET'])
@login_required
def get_user_sector_interests():
    """Get the current user's sector interests based on their watchlist"""
    try:
        if not sector_mapper:
            init_news_notification_system()
        
        user_id = str(current_user.id)
        user_interests = sector_mapper.get_user_sector_interests(user_id)
        
        return jsonify({
            'status': 'success',
            'user_interests': user_interests,
            'timestamp': datetime.now(timezone.utc).isoformat()
        })
    
    except Exception as e:
        logger.error(f"❌ Error getting user sector interests: {str(e)}")
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500

@news_notification_bp.route('/user-sectors/<user_id>', methods=['GET'])
@login_required
def get_specific_user_sector_interests(user_id):
    """Get sector interests for a specific user (admin only)"""
    try:
        # Check if current user can access other user's data
        if str(current_user.id) != user_id:
            # Add admin check here if needed
            pass  # For now, allow access
        
        if not sector_mapper:
            init_news_notification_system()
        
        user_interests = sector_mapper.get_user_sector_interests(user_id)
        
        return jsonify({
            'status': 'success',
            'user_interests': user_interests,
            'timestamp': datetime.now(timezone.utc).isoformat()
        })
    
    except Exception as e:
        logger.error(f"❌ Error getting user sector interests: {str(e)}")
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500

@news_notification_bp.route('/sector-statistics', methods=['GET'])
def get_sector_statistics():
    """Get statistics about sector distribution across all watchlists"""
    try:
        if not sector_mapper:
            init_news_notification_system()
        
        stats = sector_mapper.get_sector_statistics()
        
        return jsonify({
            'status': 'success',
            'statistics': stats,
            'timestamp': datetime.now(timezone.utc).isoformat()
        })
    
    except Exception as e:
        logger.error(f"❌ Error getting sector statistics: {str(e)}")
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500

@news_notification_bp.route('/find-interested-users', methods=['POST'])
@login_required
def find_users_interested_in_sectors():
    """Find users interested in specific sectors"""
    try:
        data = request.get_json()
        if not data or 'sectors' not in data:
            return jsonify({
                'status': 'error',
                'error': 'Sectors list is required'
            }), 400
        
        sectors = data['sectors']
        if not isinstance(sectors, list):
            return jsonify({
                'status': 'error',
                'error': 'Sectors must be a list'
            }), 400
        
        if not sector_mapper:
            init_news_notification_system()
        
        interested_users = sector_mapper.find_users_interested_in_sectors(sectors)
        
        return jsonify({
            'status': 'success',
            'sectors': sectors,
            'interested_users': interested_users,
            'user_count': len(interested_users),
            'timestamp': datetime.now(timezone.utc).isoformat()
        })
    
    except Exception as e:
        logger.error(f"❌ Error finding interested users: {str(e)}")
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500

@news_notification_bp.route('/update-sectors', methods=['POST'])
@login_required
def update_all_sectors():
    """Update sector information for all stocks in watchlists"""
    try:
        if not sector_mapper:
            init_news_notification_system()
        
        update_result = sector_mapper.update_all_watchlist_sectors()
        
        return jsonify({
            'status': 'success',
            'update_result': update_result,
            'timestamp': datetime.now(timezone.utc).isoformat()
        })
    
    except Exception as e:
        logger.error(f"❌ Error updating sectors: {str(e)}")
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500

@news_notification_bp.route('/analyze-news', methods=['POST'])
@login_required
def analyze_news_for_sectors():
    """Analyze a news article for sector impact"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'status': 'error',
                'error': 'Request data is required'
            }), 400
        
        required_fields = ['title']
        for field in required_fields:
            if field not in data:
                return jsonify({
                    'status': 'error',
                    'error': f'Field {field} is required'
                }), 400
        
        if not notification_system:
            init_news_notification_system()
        
        # Create article object from request data
        article = {
            'title': data.get('title', ''),
            'description': data.get('description', ''),
            'content': data.get('content', ''),
            'source_id': data.get('source', 'Manual Input'),
            'pubDate': data.get('date', datetime.now().isoformat())
        }
        
        # Analyze sector impact
        sector_analysis = notification_system.analyze_sector_impact(article)
        
        # Find interested users if sectors are affected
        interested_users = []
        if sector_analysis.get('affected_sectors'):
            interested_users = sector_mapper.find_users_interested_in_sectors(
                sector_analysis['affected_sectors']
            )
        
        return jsonify({
            'status': 'success',
            'article': {
                'title': article['title'],
                'source': article['source_id']
            },
            'sector_analysis': sector_analysis,
            'interested_users': interested_users,
            'notification_potential': len(interested_users),
            'timestamp': datetime.now(timezone.utc).isoformat()
        })
    
    except Exception as e:
        logger.error(f"❌ Error analyzing news: {str(e)}")
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500

@news_notification_bp.route('/send-test-notification', methods=['POST'])
@login_required
def send_test_notification():
    """Send a test notification to the current user"""
    try:
        data = request.get_json()
        if not data or 'article' not in data:
            return jsonify({
                'status': 'error',
                'error': 'Article data is required'
            }), 400
        
        if not notification_system:
            init_news_notification_system()
        
        # Get current user's sector interests
        user_id = str(current_user.id)
        user_interests = sector_mapper.get_user_sector_interests(user_id)
        
        if not user_interests.get('sectors'):
            return jsonify({
                'status': 'error',
                'error': 'User has no sector interests (empty watchlist)'
            }), 400
        
        # Create test article with analysis
        article = data['article']
        test_analysis = {
            'affected_sectors': user_interests['sectors'][:2],  # Use user's first 2 sectors
            'affected_industries': user_interests.get('industries', [])[:2],
            'impact_level': 'medium',
            'impact_type': 'neutral',
            'reasoning': 'Test notification for demonstration purposes',
            'confidence': 0.8
        }
        
        # Create user object for notification
        test_user = {
            'user_id': user_id,
            'email': current_user.email,
            'name': f"{current_user.first_name} {current_user.last_name}".strip() or current_user.email,
            'interested_sectors': user_interests['sectors'],
            'matched_stocks': user_interests.get('stocks', [])
        }
        
        # Send test notification
        articles_with_analysis = [{
            'article': article,
            'analysis': test_analysis
        }]
        
        success = notification_system.send_email_notification(test_user, articles_with_analysis)
        
        if success:
            return jsonify({
                'status': 'success',
                'message': f'Test notification sent to {current_user.email}',
                'user_sectors': user_interests['sectors'],
                'timestamp': datetime.now(timezone.utc).isoformat()
            })
        else:
            return jsonify({
                'status': 'error',
                'error': 'Failed to send test notification'
            }), 500
    
    except Exception as e:
        logger.error(f"❌ Error sending test notification: {str(e)}")
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500

@news_notification_bp.route('/export-mapping', methods=['GET'])
@login_required
def export_sector_mapping():
    """Export user sector mapping to JSON"""
    try:
        if not sector_mapper:
            init_news_notification_system()
        
        # Generate filename with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'user_sector_mapping_{timestamp}.json'
        
        if sector_mapper.export_user_sector_mapping(filename):
            return jsonify({
                'status': 'success',
                'message': f'Sector mapping exported to {filename}',
                'filename': filename,
                'timestamp': datetime.now(timezone.utc).isoformat()
            })
        else:
            return jsonify({
                'status': 'error',
                'error': 'Failed to export sector mapping'
            }), 500
    
    except Exception as e:
        logger.error(f"❌ Error exporting sector mapping: {str(e)}")
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500

# Error handlers for the blueprint
@news_notification_bp.errorhandler(404)
def not_found(error):
    return jsonify({
        'status': 'error',
        'error': 'Endpoint not found',
        'available_endpoints': [
            '/news-notifications/status',
            '/news-notifications/start',
            '/news-notifications/stop',
            '/news-notifications/test-run',
            '/news-notifications/user-sectors',
            '/news-notifications/sector-statistics',
            '/news-notifications/find-interested-users',
            '/news-notifications/update-sectors',
            '/news-notifications/analyze-news',
            '/news-notifications/send-test-notification',
            '/news-notifications/export-mapping'
        ]
    }), 404

@news_notification_bp.errorhandler(500)
def internal_error(error):
    return jsonify({
        'status': 'error',
        'error': 'Internal server error',
        'message': 'An unexpected error occurred'
    }), 500

# Function to register the blueprint with the main Flask app
def register_news_notification_blueprint(app):
    """Register the news notification blueprint with the Flask app"""
    app.register_blueprint(news_notification_bp)
    
    # Initialize the system when the blueprint is registered
    with app.app_context():
        init_news_notification_system()
    
    logger.info("✅ News notification blueprint registered successfully")

# Standalone Flask app for testing
if __name__ == "__main__":
    from flask import Flask
    from flask_login import LoginManager, UserMixin, login_user
    
    # Create test Flask app
    app = Flask(__name__)
    app.secret_key = 'test-secret-key'
    
    # Simple user class for testing
    class TestUser(UserMixin):
        def __init__(self, id, email, first_name="Test", last_name="User"):
            self.id = id
            self.email = email
            self.first_name = first_name
            self.last_name = last_name
    
    # Setup login manager
    login_manager = LoginManager()
    login_manager.init_app(app)
    
    @login_manager.user_loader
    def load_user(user_id):
        return TestUser(user_id, "test@example.com")
    
    # Test login route
    @app.route('/test-login')
    def test_login():
        user = TestUser("test_user_123", "test@example.com")
        login_user(user)
        return "Logged in as test user"
    
    # Register the blueprint
    register_news_notification_blueprint(app)
    
    # Run the test server
    print("🚀 Starting test server for news notification API...")
    print("📍 Available endpoints:")
    print("   GET  /test-login                                    - Login as test user")
    print("   GET  /news-notifications/status                     - Get system status")
    print("   POST /news-notifications/start                      - Start scheduler")
    print("   POST /news-notifications/test-run                   - Run immediate test")
    print("   GET  /news-notifications/user-sectors               - Get user sectors")
    print("   GET  /news-notifications/sector-statistics          - Get sector stats")
    print("   POST /news-notifications/analyze-news               - Analyze news article")
    app.run(debug=True, port=5001)
