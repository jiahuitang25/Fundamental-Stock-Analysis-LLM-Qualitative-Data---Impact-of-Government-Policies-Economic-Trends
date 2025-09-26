"""
Refactored Stock Analysis Application
Main application file with clean, organized structure
"""

import logging
import sys
import signal
import os
from datetime import timedelta
from flask import Flask
from flask_login import LoginManager
from flask_cors import CORS
from pymongo import MongoClient
from dotenv import load_dotenv

# Import configuration
from config import Config, config

# Import services
from services.rag_service import RAGService
from services.news_service import NewsService
from services.analysis_service import AnalysisService
from services.conversation_service import ConversationService

# Import route blueprints
from routes.main_routes import main_bp
from routes.analysis_routes import analysis_bp
from routes.watchlist_routes import watchlist_bp
from routes.news_routes import news_bp
from routes.api_routes import api_bp

# Import authentication
from auth import auth_bp
from models import User

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

def create_app(config_name='default'):
    """Application factory pattern"""
    app = Flask(__name__)
    
    # Load configuration
    app.config.from_object(config[config_name])
    
    # Initialize extensions
    CORS(app)
    
    # Initialize login manager
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'info'
    
    @login_manager.user_loader
    def load_user(user_id):
        """Load user from database"""
        try:
            return User.get_by_id(user_id)
        except Exception as e:
            logger.error(f"Error loading user {user_id}: {e}")
            return None
    
    # Initialize database
    try:
        db_client = MongoClient(Config.MONGO_URI)
        db_client.admin.command('ping')  # Test connection
        logger.info("✅ MongoDB connection established")
    except Exception as e:
        logger.error(f"❌ Failed to connect to MongoDB: {e}")
        db_client = None
    
    # Initialize services
    services = {}
    if db_client:
        try:
            services['rag_service'] = RAGService()
            services['news_service'] = NewsService(db_client)
            services['analysis_service'] = AnalysisService(db_client)
            services['conversation_service'] = ConversationService(db_client)
            logger.info("✅ Services initialized successfully")
        except Exception as e:
            logger.error(f"❌ Failed to initialize services: {e}")
    
    # Store services in app context
    app.services = services
    app.db_client = db_client
    
    # Register blueprints
    app.register_blueprint(main_bp)
    app.register_blueprint(analysis_bp)
    app.register_blueprint(watchlist_bp)
    app.register_blueprint(news_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(auth_bp)
    
    # Error handlers
    @app.errorhandler(404)
    def not_found(error):
        return {"error": "Not found"}, 404
    
    @app.errorhandler(500)
    def internal_error(error):
        logger.error(f"Internal server error: {error}")
        return {"error": "Internal server error"}, 500
    
    @app.errorhandler(TimeoutError)
    def handle_timeout(error):
        logger.error(f"Request timeout: {error}")
        return {"error": "Request timeout"}, 408
    
    @app.errorhandler(408)
    def handle_request_timeout(error):
        logger.error(f"Request timeout: {error}")
        return {"error": "Request timeout"}, 408
    
    # Health check endpoint
    @app.route('/health')
    def health():
        """Health check endpoint"""
        try:
            # Check database connection
            db_status = "healthy" if db_client and db_client.admin.command('ping') else "unhealthy"
            
            # Check services
            services_status = "healthy" if services else "unhealthy"
            
            return {
                "status": "healthy" if db_status == "healthy" and services_status == "healthy" else "unhealthy",
                "database": db_status,
                "services": services_status,
                "timestamp": "2024-01-01T00:00:00Z"
            }, 200
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {"status": "unhealthy", "error": str(e)}, 500
    
    return app

def setup_signal_handlers(app):
    """Setup signal handlers for graceful shutdown"""
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        if hasattr(app, 'db_client') and app.db_client:
            app.db_client.close()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

def find_free_port(start_port=5000, max_attempts=100):
    """Find a free port to run the application"""
    import socket
    
    for port in range(start_port, start_port + max_attempts):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('', port))
                return port
        except OSError:
            continue
    
    raise RuntimeError(f"Could not find a free port starting from {start_port}")

def main():
    """Main application entry point"""
    try:
        # Create application
        app = create_app()
        
        # Setup signal handlers
        setup_signal_handlers(app)
        
        # Get configuration
        host = os.getenv('HOST', '0.0.0.0')
        port = int(os.getenv('PORT', 5000))
        debug = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
        
        # Find free port if needed
        if port == 5000:
            try:
                port = find_free_port()
                logger.info(f"Using port {port}")
            except RuntimeError:
                logger.warning("Could not find free port, using default 5000")
        
        logger.info(f"Starting Stock Analysis Application on {host}:{port}")
        logger.info(f"Debug mode: {debug}")
        
        # Run application
        app.run(
            host=host,
            port=port,
            debug=debug,
            threaded=True
        )
        
    except Exception as e:
        logger.error(f"Failed to start application: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
