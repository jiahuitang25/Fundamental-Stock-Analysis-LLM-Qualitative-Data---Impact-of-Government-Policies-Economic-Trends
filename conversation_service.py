"""
Conversation Service for the Stock Analysis Application
"""

import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional, Tuple
from pymongo import MongoClient
from config import Config

logger = logging.getLogger(__name__)

class ConversationService:
    """Service for conversation management and context handling"""
    
    def __init__(self, db_client: MongoClient):
        self.db_client = db_client
        self.db = db_client[Config.DATABASE_NAME]
        self.conversations_collection = self.db['conversations']
        self.memories_collection = self.db['agent_memories']
        
        # Create indexes
        self.conversations_collection.create_index("session_id")
        self.conversations_collection.create_index("conversation_id")
        self.conversations_collection.create_index("timestamp")
        self.memories_collection.create_index("session_id")
        self.memories_collection.create_index("memory_type")
        self.memories_collection.create_index("timestamp")
    
    def get_conversation_context(self, session_id: str, conversation_id: str = None) -> Dict[str, Any]:
        """Get conversation context for a session"""
        try:
            if not session_id:
                return self._get_default_context(session_id)
            
            # Get recent conversation history
            query = {"session_id": session_id}
            if conversation_id:
                query["conversation_id"] = conversation_id
            
            conversations = list(self.conversations_collection.find(query)
                               .sort("timestamp", -1)
                               .limit(10))
            
            if not conversations:
                return self._get_default_context(session_id)
            
            # Build context from recent conversations
            context = {
                "session_id": session_id,
                "conversation_id": conversation_id or conversations[0].get("conversation_id"),
                "recent_queries": [],
                "recent_responses": [],
                "topics": [],
                "tickers": [],
                "last_analysis": None,
                "conversation_count": len(conversations)
            }
            
            # Extract information from conversations
            for conv in reversed(conversations):  # Process in chronological order
                query_text = conv.get("query", "")
                response_data = conv.get("response_data", {})
                
                if query_text:
                    context["recent_queries"].append(query_text)
                
                if response_data:
                    context["recent_responses"].append(response_data)
                    
                    # Extract ticker if present
                    ticker = response_data.get("ticker")
                    if ticker and ticker not in context["tickers"]:
                        context["tickers"].append(ticker)
                    
                    # Extract topics
                    summary = response_data.get("summary", "")
                    if summary:
                        # Simple topic extraction (first few words)
                        topic_words = summary.split()[:5]
                        topic = " ".join(topic_words)
                        if topic not in context["topics"]:
                            context["topics"].append(topic)
                
                # Set last analysis
                if not context["last_analysis"] and response_data:
                    context["last_analysis"] = response_data
            
            # Limit context size
            context["recent_queries"] = context["recent_queries"][-5:]
            context["recent_responses"] = context["recent_responses"][-3:]
            context["topics"] = context["topics"][-5:]
            context["tickers"] = context["tickers"][-3:]
            
            return context
            
        except Exception as e:
            logger.error(f"Error getting conversation context: {e}")
            return self._get_default_context(session_id)
    
    def update_conversation_context(self, session_id: str, query: str, response_data: Dict, 
                                  analysis_context: Dict = None) -> bool:
        """Update conversation context with new interaction"""
        try:
            if not session_id or not query or not response_data:
                return False
            
            # Generate conversation ID if not provided
            conversation_id = analysis_context.get("conversation_id") if analysis_context else str(uuid.uuid4())
            
            # Create conversation entry
            conversation_entry = {
                "session_id": session_id,
                "conversation_id": conversation_id,
                "query": query,
                "response_data": response_data,
                "analysis_context": analysis_context or {},
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
            # Store conversation
            result = self.conversations_collection.insert_one(conversation_entry)
            
            if result.inserted_id:
                # Store relevant memories
                self._store_conversation_memories(session_id, query, response_data, analysis_context)
                return True
            else:
                logger.error("Failed to store conversation")
                return False
                
        except Exception as e:
            logger.error(f"Error updating conversation context: {e}")
            return False
    
    def retrieve_relevant_memories(self, query: str, session_id: str = None, ticker: str = None) -> List[Dict]:
        """Retrieve relevant memories for a query"""
        try:
            if not query:
                return []
            
            # Build search query
            search_query = {"memory_type": {"$in": ["episodic", "semantic", "conversation"]}}
            
            if session_id:
                search_query["session_id"] = session_id
            
            # Get recent memories
            memories = list(self.memories_collection.find(search_query)
                          .sort("timestamp", -1)
                          .limit(20))
            
            # Filter and rank memories by relevance
            relevant_memories = []
            query_lower = query.lower()
            
            for memory in memories:
                content = memory.get("content", "").lower()
                memory_type = memory.get("memory_type", "")
                
                # Calculate relevance score
                relevance_score = 0
                
                # Direct keyword matching
                query_words = set(query_lower.split())
                content_words = set(content.split())
                overlap = len(query_words.intersection(content_words))
                relevance_score += overlap * 0.3
                
                # Ticker matching
                if ticker and ticker.lower() in content:
                    relevance_score += 0.5
                
                # Memory type weighting
                if memory_type == "episodic":
                    relevance_score += 0.2
                elif memory_type == "semantic":
                    relevance_score += 0.3
                elif memory_type == "conversation":
                    relevance_score += 0.1
                
                # Recency boost
                memory_time = datetime.fromisoformat(memory.get("timestamp", "").replace('Z', '+00:00'))
                days_old = (datetime.now(timezone.utc) - memory_time).days
                if days_old <= 1:
                    relevance_score += 0.2
                elif days_old <= 7:
                    relevance_score += 0.1
                
                if relevance_score > 0.3:  # Threshold for relevance
                    memory["relevance_score"] = relevance_score
                    relevant_memories.append(memory)
            
            # Sort by relevance score
            relevant_memories.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
            
            return relevant_memories[:5]  # Return top 5 relevant memories
            
        except Exception as e:
            logger.error(f"Error retrieving relevant memories: {e}")
            return []
    
    def store_analysis_insights(self, session_id: str, query: str, risk_score: float, 
                              summary: str, insights: List[str], ticker: str = None) -> bool:
        """Store analysis insights as memories"""
        try:
            if not session_id or not query:
                return False
            
            # Create episodic memory
            episodic_memory = {
                "session_id": session_id,
                "memory_type": "episodic",
                "content": f"Analysis of {query}: Risk score {risk_score}, Summary: {summary}",
                "metadata": {
                    "query": query,
                    "risk_score": risk_score,
                    "summary": summary,
                    "insights": insights,
                    "ticker": ticker
                },
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
            # Create semantic memory for insights
            semantic_memory = {
                "session_id": session_id,
                "memory_type": "semantic",
                "content": f"Key insights: {', '.join(insights[:3])}",
                "metadata": {
                    "insights": insights,
                    "ticker": ticker,
                    "risk_score": risk_score
                },
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
            # Store memories
            self.memories_collection.insert_many([episodic_memory, semantic_memory])
            
            return True
            
        except Exception as e:
            logger.error(f"Error storing analysis insights: {e}")
            return False
    
    def is_followup_query(self, query: str, conversation_context: Dict) -> bool:
        """Determine if query is a follow-up to previous conversation"""
        try:
            if not query or not conversation_context:
                return False
            
            query_lower = query.lower()
            
            # Check for follow-up indicators
            followup_indicators = [
                "what about", "how about", "tell me more", "explain", "why", "how",
                "can you", "could you", "what if", "what's", "what is", "it", "this", "that"
            ]
            
            # Check for pronouns that might refer to previous context
            pronouns = ["it", "this", "that", "they", "them", "their", "its"]
            
            # Check for follow-up patterns
            has_followup_indicator = any(indicator in query_lower for indicator in followup_indicators)
            has_pronoun = any(pronoun in query_lower.split() for pronoun in pronouns)
            
            # Check if query is very short (likely a follow-up)
            is_short = len(query.split()) <= 5
            
            # Check if previous context exists
            has_context = bool(conversation_context.get("recent_queries") or 
                             conversation_context.get("recent_responses"))
            
            # Determine if it's a follow-up
            is_followup = (has_followup_indicator or has_pronoun or is_short) and has_context
            
            return is_followup
            
        except Exception as e:
            logger.error(f"Error determining follow-up query: {e}")
            return False
    
    def enhance_followup_query(self, query: str, conversation_context: Dict) -> str:
        """Enhance follow-up query with context"""
        try:
            if not query or not conversation_context:
                return query
            
            enhanced_query = query
            
            # Add context from recent queries
            recent_queries = conversation_context.get("recent_queries", [])
            if recent_queries:
                last_query = recent_queries[-1]
                if "it" in query.lower() or "this" in query.lower() or "that" in query.lower():
                    enhanced_query = f"{query} (referring to: {last_query})"
            
            # Add ticker context
            tickers = conversation_context.get("tickers", [])
            if tickers and not any(ticker.lower() in query.lower() for ticker in tickers):
                enhanced_query = f"{enhanced_query} (for {tickers[0]})"
            
            # Add topic context
            topics = conversation_context.get("topics", [])
            if topics and len(query.split()) <= 3:
                enhanced_query = f"{enhanced_query} (about {topics[0]})"
            
            return enhanced_query
            
        except Exception as e:
            logger.error(f"Error enhancing follow-up query: {e}")
            return query
    
    def _get_default_context(self, session_id: str) -> Dict[str, Any]:
        """Get default context for new session"""
        return {
            "session_id": session_id,
            "conversation_id": str(uuid.uuid4()),
            "recent_queries": [],
            "recent_responses": [],
            "topics": [],
            "tickers": [],
            "last_analysis": None,
            "conversation_count": 0
        }
    
    def _store_conversation_memories(self, session_id: str, query: str, response_data: Dict, 
                                   analysis_context: Dict = None):
        """Store conversation memories"""
        try:
            memories = []
            
            # Store conversation memory
            conversation_memory = {
                "session_id": session_id,
                "memory_type": "conversation",
                "content": f"Q: {query} A: {response_data.get('summary', '')[:100]}...",
                "metadata": {
                    "query": query,
                    "response_summary": response_data.get("summary", ""),
                    "ticker": response_data.get("ticker"),
                    "risk_score": response_data.get("risk_score")
                },
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            memories.append(conversation_memory)
            
            # Store procedural memory if insights are present
            insights = response_data.get("actionable_insights", [])
            if insights:
                procedural_memory = {
                    "session_id": session_id,
                    "memory_type": "procedural",
                    "content": f"Actionable insights: {', '.join(insights[:3])}",
                    "metadata": {
                        "insights": insights,
                        "ticker": response_data.get("ticker"),
                        "query": query
                    },
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
                memories.append(procedural_memory)
            
            # Store memories
            if memories:
                self.memories_collection.insert_many(memories)
                
        except Exception as e:
            logger.error(f"Error storing conversation memories: {e}")
    
    def cleanup_old_conversations(self, days: int = 30):
        """Clean up old conversations and memories"""
        try:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
            cutoff_iso = cutoff_date.isoformat()
            
            # Remove old conversations
            conversations_result = self.conversations_collection.delete_many({
                "timestamp": {"$lt": cutoff_iso}
            })
            
            # Remove old memories
            memories_result = self.memories_collection.delete_many({
                "timestamp": {"$lt": cutoff_iso}
            })
            
            logger.info(f"Cleaned up {conversations_result.deleted_count} conversations and {memories_result.deleted_count} memories")
            return True
            
        except Exception as e:
            logger.error(f"Error cleaning up old conversations: {e}")
            return False
