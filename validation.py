"""
Validation utilities for the Stock Analysis Application
"""

import re
import logging
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

def validate_query(query: str) -> Dict[str, Any]:
    """Validate user query"""
    if not query or not isinstance(query, str):
        return {"valid": False, "error": "Query must be a non-empty string"}
    
    query = query.strip()
    
    if len(query) < 3:
        return {"valid": False, "error": "Query must be at least 3 characters long"}
    
    if len(query) > 200:
        return {"valid": False, "error": "Query must be less than 200 characters"}
    
    # Check for potentially harmful content
    harmful_patterns = [
        r'<script.*?>.*?</script>',  # Script tags
        r'javascript:',  # JavaScript URLs
        r'on\w+\s*=',  # Event handlers
    ]
    
    for pattern in harmful_patterns:
        if re.search(pattern, query, re.IGNORECASE):
            return {"valid": False, "error": "Query contains potentially harmful content"}
    
    return {"valid": True, "query": query}

def validate_ticker(ticker: str) -> Dict[str, Any]:
    """Validate ticker symbol"""
    if not ticker or not isinstance(ticker, str):
        return {"valid": False, "error": "Ticker must be a non-empty string"}
    
    ticker = ticker.strip().upper()
    
    # Basic ticker format validation
    if not re.match(r'^[A-Z0-9\.\-]+$', ticker):
        return {"valid": False, "error": "Invalid ticker format"}
    
    if len(ticker) < 1 or len(ticker) > 10:
        return {"valid": False, "error": "Ticker must be 1-10 characters long"}
    
    return {"valid": True, "ticker": ticker}

def validate_email(email: str) -> Dict[str, Any]:
    """Validate email address"""
    if not email or not isinstance(email, str):
        return {"valid": False, "error": "Email must be a non-empty string"}
    
    email = email.strip().lower()
    
    # Basic email format validation
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(email_pattern, email):
        return {"valid": False, "error": "Invalid email format"}
    
    if len(email) > 254:
        return {"valid": False, "error": "Email address too long"}
    
    return {"valid": True, "email": email}

def validate_watchlist_item(item: Dict[str, Any]) -> Dict[str, Any]:
    """Validate watchlist item"""
    if not isinstance(item, dict):
        return {"valid": False, "error": "Watchlist item must be a dictionary"}
    
    # Required fields
    required_fields = ["ticker", "user_id"]
    for field in required_fields:
        if field not in item:
            return {"valid": False, "error": f"Missing required field: {field}"}
    
    # Validate ticker
    ticker_validation = validate_ticker(item["ticker"])
    if not ticker_validation["valid"]:
        return ticker_validation
    
    # Validate user_id
    user_id = item.get("user_id", "").strip()
    if not user_id:
        return {"valid": False, "error": "User ID cannot be empty"}
    
    # Validate optional fields
    if "notes" in item and item["notes"] and len(item["notes"]) > 500:
        return {"valid": False, "error": "Notes must be less than 500 characters"}
    
    if "price_alerts" in item and not isinstance(item["price_alerts"], dict):
        return {"valid": False, "error": "Price alerts must be a dictionary"}
    
    return {"valid": True, "item": item}

def validate_pagination_params(page: int, limit: int) -> Dict[str, Any]:
    """Validate pagination parameters"""
    if not isinstance(page, int) or page < 1:
        return {"valid": False, "error": "Page must be a positive integer"}
    
    if not isinstance(limit, int) or limit < 1 or limit > 100:
        return {"valid": False, "error": "Limit must be between 1 and 100"}
    
    return {"valid": True, "page": page, "limit": limit}

def sanitize_string(s: str) -> str:
    """Sanitize string input"""
    if not isinstance(s, str):
        return ""
    
    # Remove potentially harmful characters
    s = re.sub(r'[<>"\']', '', s)
    
    # Limit length
    s = s[:1000]
    
    return s.strip()

def validate_request_data(data: Dict[str, Any], required_fields: List[str]) -> Dict[str, Any]:
    """Validate request data"""
    if not isinstance(data, dict):
        return {"valid": False, "error": "Request data must be a dictionary"}
    
    # Check required fields
    for field in required_fields:
        if field not in data:
            return {"valid": False, "error": f"Missing required field: {field}"}
        
        if not data[field] or (isinstance(data[field], str) and not data[field].strip()):
            return {"valid": False, "error": f"Field '{field}' cannot be empty"}
    
    return {"valid": True, "data": data}

def validate_json_input(json_data: Any) -> Dict[str, Any]:
    """Validate JSON input"""
    if json_data is None:
        return {"valid": False, "error": "JSON data cannot be null"}
    
    if isinstance(json_data, (str, int, float, bool)):
        return {"valid": True, "data": json_data}
    
    if isinstance(json_data, (list, dict)):
        # Check for reasonable size limits
        if len(str(json_data)) > 1000000:  # 1MB limit
            return {"valid": False, "error": "JSON data too large"}
        
        return {"valid": True, "data": json_data}
    
    return {"valid": False, "error": "Invalid JSON data type"}

def validate_api_key(api_key: str) -> Dict[str, Any]:
    """Validate API key format"""
    if not api_key or not isinstance(api_key, str):
        return {"valid": False, "error": "API key must be a non-empty string"}
    
    api_key = api_key.strip()
    
    if len(api_key) < 10:
        return {"valid": False, "error": "API key too short"}
    
    if len(api_key) > 200:
        return {"valid": False, "error": "API key too long"}
    
    # Check for valid characters (alphanumeric, hyphens, underscores)
    if not re.match(r'^[a-zA-Z0-9\-_]+$', api_key):
        return {"valid": False, "error": "API key contains invalid characters"}
    
    return {"valid": True, "api_key": api_key}

def validate_session_id(session_id: str) -> Dict[str, Any]:
    """Validate session ID"""
    if not session_id or not isinstance(session_id, str):
        return {"valid": False, "error": "Session ID must be a non-empty string"}
    
    session_id = session_id.strip()
    
    # UUID format validation
    uuid_pattern = r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
    if not re.match(uuid_pattern, session_id, re.IGNORECASE):
        return {"valid": False, "error": "Invalid session ID format"}
    
    return {"valid": True, "session_id": session_id}

def validate_conversation_context(context: Dict[str, Any]) -> Dict[str, Any]:
    """Validate conversation context"""
    if not isinstance(context, dict):
        return {"valid": False, "error": "Conversation context must be a dictionary"}
    
    # Check for reasonable size
    if len(str(context)) > 50000:  # 50KB limit
        return {"valid": False, "error": "Conversation context too large"}
    
    # Validate timestamp if present
    if "timestamp" in context:
        try:
            from datetime import datetime
            datetime.fromisoformat(context["timestamp"].replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            return {"valid": False, "error": "Invalid timestamp format"}
    
    return {"valid": True, "context": context}
