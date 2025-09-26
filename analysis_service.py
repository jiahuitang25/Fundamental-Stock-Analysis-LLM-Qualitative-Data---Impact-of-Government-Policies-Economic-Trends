"""
Analysis Service for the Stock Analysis Application
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple
from pymongo import MongoClient
from config import Config
from utils.data_processing import (
    fetch_financial_data_for_llm,
    format_financial_data_for_llm,
    calculate_token_usage_and_cost,
    calculate_llamaindex_token_usage
)
from utils.text_processing import (
    filter_high_quality_contexts,
    consolidate_chunked_sources
)
from utils.validation import validate_query, validate_ticker

logger = logging.getLogger(__name__)

class AnalysisService:
    """Service for stock analysis operations"""
    
    def __init__(self, db_client: MongoClient):
        self.db_client = db_client
        self.db = db_client[Config.DATABASE_NAME]
        self.analysis_collection = self.db['analysis_results']
        self.feedback_collection = self.db['user_feedback']
        
        # Create indexes
        self.analysis_collection.create_index("timestamp")
        self.analysis_collection.create_index("user_id")
        self.analysis_collection.create_index("ticker")
        self.feedback_collection.create_index("timestamp")
        self.feedback_collection.create_index("user_id")
    
    def analyze_stock(self, query: str, ticker: str = None, user_id: str = None, 
                     session_id: str = None, conversation_context: Dict = None) -> Dict[str, Any]:
        """Perform comprehensive stock analysis"""
        try:
            # Validate inputs
            query_validation = validate_query(query)
            if not query_validation["valid"]:
                return {"error": query_validation["error"]}
            
            query = query_validation["query"]
            
            if ticker:
                ticker_validation = validate_ticker(ticker)
                if not ticker_validation["valid"]:
                    return {"error": ticker_validation["error"]}
                ticker = ticker_validation["ticker"]
            
            # Generate analysis ID
            analysis_id = str(uuid.uuid4())
            
            # Build analysis context
            analysis_context = {
                "analysis_id": analysis_id,
                "query": query,
                "ticker": ticker,
                "user_id": user_id,
                "session_id": session_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "conversation_context": conversation_context
            }
            
            # Fetch financial data if ticker provided
            financial_data = None
            if ticker:
                financial_data = fetch_financial_data_for_llm(ticker)
                if financial_data:
                    analysis_context["financial_data"] = financial_data
            
            # Perform analysis (this would integrate with RAG service)
            analysis_result = self._perform_analysis(analysis_context)
            
            # Store analysis result
            self._store_analysis_result(analysis_result)
            
            return analysis_result
            
        except Exception as e:
            logger.error(f"Error in stock analysis: {e}")
            return {"error": f"Analysis failed: {str(e)}"}
    
    def get_analysis_history(self, user_id: str = None, limit: int = 20, offset: int = 0) -> List[Dict]:
        """Get analysis history for user"""
        try:
            query = {}
            if user_id:
                query["user_id"] = user_id
            
            analyses = list(self.analysis_collection.find(query)
                          .sort("timestamp", -1)
                          .skip(offset)
                          .limit(limit))
            
            # Convert ObjectId to string and clean up
            for analysis in analyses:
                analysis["_id"] = str(analysis["_id"])
                # Remove large fields for list view
                if "raw_response" in analysis:
                    del analysis["raw_response"]
                if "sources" in analysis and len(str(analysis["sources"])) > 1000:
                    analysis["sources"] = "Large sources data..."
            
            return analyses
            
        except Exception as e:
            logger.error(f"Error getting analysis history: {e}")
            return []
    
    def submit_feedback(self, analysis_id: str, user_id: str, feedback_data: Dict) -> bool:
        """Submit user feedback for analysis"""
        try:
            if not analysis_id or not user_id or not feedback_data:
                return False
            
            feedback_entry = {
                "analysis_id": analysis_id,
                "user_id": user_id,
                "feedback": feedback_data,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
            result = self.feedback_collection.insert_one(feedback_entry)
            return result.inserted_id is not None
            
        except Exception as e:
            logger.error(f"Error submitting feedback: {e}")
            return False
    
    def get_feedback_stats(self, user_id: str = None) -> Dict[str, Any]:
        """Get feedback statistics"""
        try:
            query = {}
            if user_id:
                query["user_id"] = user_id
            
            total_feedback = self.feedback_collection.count_documents(query)
            
            # Get feedback by type
            feedback_types = {}
            for feedback in self.feedback_collection.find(query):
                feedback_type = feedback.get("feedback", {}).get("type", "unknown")
                feedback_types[feedback_type] = feedback_types.get(feedback_type, 0) + 1
            
            return {
                "total_feedback": total_feedback,
                "feedback_by_type": feedback_types,
                "user_id": user_id
            }
            
        except Exception as e:
            logger.error(f"Error getting feedback stats: {e}")
            return {"error": str(e)}
    
    def get_learning_progress(self, user_id: str = None) -> Dict[str, Any]:
        """Get learning progress based on analysis history and feedback"""
        try:
            if not user_id:
                return {"error": "User ID required"}
            
            # Get user's analysis history
            analyses = self.get_analysis_history(user_id, limit=100)
            
            # Get user's feedback
            feedback_stats = self.get_feedback_stats(user_id)
            
            # Calculate progress metrics
            total_analyses = len(analyses)
            recent_analyses = [a for a in analyses if self._is_recent(a.get("timestamp", ""), days=7)]
            
            # Analyze query complexity over time
            complexity_trend = self._analyze_complexity_trend(analyses)
            
            # Analyze ticker diversity
            ticker_diversity = self._analyze_ticker_diversity(analyses)
            
            return {
                "total_analyses": total_analyses,
                "recent_analyses": len(recent_analyses),
                "complexity_trend": complexity_trend,
                "ticker_diversity": ticker_diversity,
                "feedback_stats": feedback_stats,
                "learning_score": self._calculate_learning_score(analyses, feedback_stats)
            }
            
        except Exception as e:
            logger.error(f"Error getting learning progress: {e}")
            return {"error": str(e)}
    
    def _perform_analysis(self, analysis_context: Dict) -> Dict[str, Any]:
        """Perform the actual analysis (placeholder for RAG integration)"""
        try:
            # This would integrate with the RAG service
            # For now, return a basic analysis structure
            
            query = analysis_context["query"]
            ticker = analysis_context.get("ticker")
            financial_data = analysis_context.get("financial_data")
            
            # Basic analysis result
            analysis_result = {
                "analysis_id": analysis_context["analysis_id"],
                "query": query,
                "ticker": ticker,
                "user_id": analysis_context.get("user_id"),
                "session_id": analysis_context.get("session_id"),
                "timestamp": analysis_context["timestamp"],
                "status": "success",
                "risk_score": 3.0,  # Placeholder
                "risk_explanation": "Analysis completed successfully",
                "summary": f"Analysis of {query} completed",
                "actionable_insights": [
                    "Consider market conditions",
                    "Review financial metrics",
                    "Monitor news updates"
                ],
                "sources": [],
                "financial_data": financial_data,
                "processing_time": 1.5,
                "token_usage": {"tokens": 100, "cost": 0.001},
                "conversation_context": analysis_context.get("conversation_context")
            }
            
            return analysis_result
            
        except Exception as e:
            logger.error(f"Error performing analysis: {e}")
            return {
                "analysis_id": analysis_context.get("analysis_id"),
                "error": str(e),
                "status": "error",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
    
    def _store_analysis_result(self, analysis_result: Dict) -> bool:
        """Store analysis result in database"""
        try:
            if not analysis_result:
                return False
            
            result = self.analysis_collection.insert_one(analysis_result)
            return result.inserted_id is not None
            
        except Exception as e:
            logger.error(f"Error storing analysis result: {e}")
            return False
    
    def _is_recent(self, timestamp: str, days: int = 7) -> bool:
        """Check if timestamp is within recent days"""
        try:
            if not timestamp:
                return False
            
            analysis_time = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            cutoff_time = datetime.now(timezone.utc) - timedelta(days=days)
            return analysis_time > cutoff_time
            
        except Exception as e:
            logger.error(f"Error checking timestamp: {e}")
            return False
    
    def _analyze_complexity_trend(self, analyses: List[Dict]) -> Dict[str, Any]:
        """Analyze query complexity trend over time"""
        try:
            if not analyses:
                return {"trend": "stable", "complexity_score": 0}
            
            # Simple complexity scoring based on query length and keywords
            complexity_scores = []
            for analysis in analyses:
                query = analysis.get("query", "")
                # Basic complexity: length + number of financial terms
                financial_terms = ["risk", "analysis", "investment", "portfolio", "market", "stock", "price"]
                complexity = len(query) + sum(1 for term in financial_terms if term.lower() in query.lower())
                complexity_scores.append(complexity)
            
            if len(complexity_scores) < 2:
                return {"trend": "stable", "complexity_score": complexity_scores[0] if complexity_scores else 0}
            
            # Calculate trend
            recent_avg = sum(complexity_scores[:len(complexity_scores)//2]) / (len(complexity_scores)//2)
            older_avg = sum(complexity_scores[len(complexity_scores)//2:]) / (len(complexity_scores) - len(complexity_scores)//2)
            
            if recent_avg > older_avg * 1.1:
                trend = "increasing"
            elif recent_avg < older_avg * 0.9:
                trend = "decreasing"
            else:
                trend = "stable"
            
            return {
                "trend": trend,
                "complexity_score": sum(complexity_scores) / len(complexity_scores),
                "recent_avg": recent_avg,
                "older_avg": older_avg
            }
            
        except Exception as e:
            logger.error(f"Error analyzing complexity trend: {e}")
            return {"trend": "stable", "complexity_score": 0}
    
    def _analyze_ticker_diversity(self, analyses: List[Dict]) -> Dict[str, Any]:
        """Analyze ticker diversity in analyses"""
        try:
            if not analyses:
                return {"diversity_score": 0, "unique_tickers": 0}
            
            tickers = [analysis.get("ticker") for analysis in analyses if analysis.get("ticker")]
            unique_tickers = len(set(tickers))
            total_analyses = len(analyses)
            
            diversity_score = unique_tickers / total_analyses if total_analyses > 0 else 0
            
            return {
                "diversity_score": diversity_score,
                "unique_tickers": unique_tickers,
                "total_analyses": total_analyses,
                "most_analyzed": max(set(tickers), key=tickers.count) if tickers else None
            }
            
        except Exception as e:
            logger.error(f"Error analyzing ticker diversity: {e}")
            return {"diversity_score": 0, "unique_tickers": 0}
    
    def _calculate_learning_score(self, analyses: List[Dict], feedback_stats: Dict) -> float:
        """Calculate overall learning score"""
        try:
            if not analyses:
                return 0.0
            
            # Base score from number of analyses
            base_score = min(len(analyses) * 0.1, 5.0)
            
            # Bonus for feedback engagement
            feedback_bonus = min(feedback_stats.get("total_feedback", 0) * 0.2, 2.0)
            
            # Bonus for complexity trend
            complexity_trend = self._analyze_complexity_trend(analyses)
            if complexity_trend.get("trend") == "increasing":
                complexity_bonus = 1.0
            elif complexity_trend.get("trend") == "stable":
                complexity_bonus = 0.5
            else:
                complexity_bonus = 0.0
            
            # Bonus for ticker diversity
            ticker_diversity = self._analyze_ticker_diversity(analyses)
            diversity_bonus = ticker_diversity.get("diversity_score", 0) * 2.0
            
            total_score = base_score + feedback_bonus + complexity_bonus + diversity_bonus
            return min(total_score, 10.0)  # Cap at 10
            
        except Exception as e:
            logger.error(f"Error calculating learning score: {e}")
            return 0.0
