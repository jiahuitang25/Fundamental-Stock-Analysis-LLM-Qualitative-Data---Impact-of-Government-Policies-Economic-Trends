"""
Cache Manager for Enhanced LRU Cache System
Provides a unified interface for managing different types of caches with LRU and popularity-based retention
"""

import logging
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Union
import pymongo
from pymongo import MongoClient
from enhanced_lru_cache import EnhancedLRUCache, create_enhanced_cache


class CacheManager:
    """
    Unified cache manager that handles multiple cache types with enhanced LRU functionality
    """
    
    def __init__(self, db_client: MongoClient, max_cache_size: int = 1000):
        """
        Initialize Cache Manager
        
        Args:
            db_client: MongoDB client instance
            max_cache_size: Maximum size for each cache type
        """
        self.db_client = db_client
        self.max_cache_size = max_cache_size
        
        # Initialize different cache types
        self.query_cache = create_enhanced_cache(db_client, 'query', max_cache_size)
        self.financial_cache = create_enhanced_cache(db_client, 'financial', max_cache_size)
        self.ticker_cache = create_enhanced_cache(db_client, 'ticker', max_cache_size)
        
        # Cache type mapping for easy access
        self.caches = {
            'query': self.query_cache,
            'financial': self.financial_cache,
            'ticker': self.ticker_cache
        }
        
        logging.info(f"Cache Manager initialized with max_size={max_cache_size}")
    
    def get_query_cache(self, query: str, 
                       is_first_message: bool = False,
                       embedding: Optional[List[float]] = None,
                       similarity_threshold: float = 0.9) -> Optional[Dict[str, Any]]:
        """
        Get cached query result with enhanced LRU and similarity search
        
        Args:
            query: Query string
            is_first_message: Whether this is the first message in conversation
            embedding: Query embedding for similarity search
            similarity_threshold: Threshold for similarity-based cache hits
            
        Returns:
            Cached result if found, None otherwise
        """
        cache_key = {
            "query": query,
            "is_first_message": is_first_message
        }
        
        if embedding:
            cache_key["embedding"] = embedding
        
        result = self.query_cache.get(cache_key, similarity_threshold)
        
        if result:
            logging.info(f"Query cache hit for: {query[:50]}...")
        else:
            logging.debug(f"Query cache miss for: {query[:50]}...")
        
        return result
    
    def put_query_cache(self, query: str,
                       result: Dict[str, Any],
                       is_first_message: bool = False,
                       embedding: Optional[List[float]] = None):
        """
        Cache query result with enhanced metadata
        
        Args:
            query: Query string
            result: Analysis result to cache
            is_first_message: Whether this is the first message in conversation
            embedding: Query embedding for similarity search
        """
        cache_key = {
            "query": query,
            "is_first_message": is_first_message
        }
        
        self.query_cache.put(cache_key, result, embedding)
        logging.debug(f"Cached query result for: {query[:50]}...")
    
    def get_financial_cache(self, ticker: str, 
                          data_type: str = "llm_data") -> Optional[Dict[str, Any]]:
        """
        Get cached financial data
        
        Args:
            ticker: Stock ticker symbol
            data_type: Type of financial data (e.g., 'llm_data', 'detailed')
            
        Returns:
            Cached financial data if found, None otherwise
        """
        cache_key = {
            "ticker": ticker,
            "data_type": data_type
        }
        
        result = self.financial_cache.get(cache_key)
        
        if result:
            logging.info(f"Financial cache hit for: {ticker}")
        else:
            logging.debug(f"Financial cache miss for: {ticker}")
        
        return result
    
    def put_financial_cache(self, ticker: str,
                          data: Dict[str, Any],
                          data_type: str = "llm_data"):
        """
        Cache financial data
        
        Args:
            ticker: Stock ticker symbol
            data: Financial data to cache
            data_type: Type of financial data
        """
        cache_key = {
            "ticker": ticker,
            "data_type": data_type
        }
        
        self.financial_cache.put(cache_key, data)
        logging.debug(f"Cached financial data for: {ticker}")
    
    def get_ticker_cache(self, company_name: str) -> Optional[Dict[str, Any]]:
        """
        Get cached ticker information
        
        Args:
            company_name: Company name to look up
            
        Returns:
            Cached ticker info if found, None otherwise
        """
        cache_key = {"company_name": company_name}
        
        result = self.ticker_cache.get(cache_key)
        
        if result:
            logging.info(f"Ticker cache hit for: {company_name}")
        else:
            logging.debug(f"Ticker cache miss for: {company_name}")
        
        return result
    
    def put_ticker_cache(self, company_name: str, 
                        ticker_data: Dict[str, Any]):
        """
        Cache ticker information
        
        Args:
            company_name: Company name
            ticker_data: Ticker information to cache
        """
        cache_key = {"company_name": company_name}
        
        self.ticker_cache.put(cache_key, ticker_data)
        logging.debug(f"Cached ticker data for: {company_name}")
    
    def clear_expired_entries(self, max_age_days: int = 30):
        """
        Clear expired entries from all caches
        
        Args:
            max_age_days: Maximum age in days before entry is considered expired
        """
        logging.info(f"Clearing expired entries older than {max_age_days} days from all caches")
        
        for cache_name, cache_instance in self.caches.items():
            try:
                cache_instance.clear_expired_entries(max_age_days)
                logging.info(f"Cleared expired entries from {cache_name} cache")
            except Exception as e:
                logging.error(f"Error clearing expired entries from {cache_name} cache: {e}")
    
    def get_cache_metrics(self) -> Dict[str, Any]:
        """
        Get metrics for all cache types
        
        Returns:
            Combined metrics for all caches
        """
        combined_metrics = {}
        
        for cache_name, cache_instance in self.caches.items():
            try:
                metrics = cache_instance.get_metrics()
                combined_metrics[cache_name] = metrics
            except Exception as e:
                logging.error(f"Error getting metrics for {cache_name} cache: {e}")
                combined_metrics[cache_name] = {"error": str(e)}
        
        # Calculate overall metrics
        total_hits = sum(m.get("hits", 0) for m in combined_metrics.values() if isinstance(m, dict) and "hits" in m)
        total_misses = sum(m.get("misses", 0) for m in combined_metrics.values() if isinstance(m, dict) and "misses" in m)
        total_requests = sum(m.get("total_requests", 0) for m in combined_metrics.values() if isinstance(m, dict) and "total_requests" in m)
        total_evictions = sum(m.get("evictions", 0) for m in combined_metrics.values() if isinstance(m, dict) and "evictions" in m)
        total_cache_size = sum(m.get("cache_size", 0) for m in combined_metrics.values() if isinstance(m, dict) and "cache_size" in m)
        
        combined_metrics["overall"] = {
            "total_hits": total_hits,
            "total_misses": total_misses,
            "total_requests": total_requests,
            "total_evictions": total_evictions,
            "total_cache_size": total_cache_size,
            "overall_hit_rate": (total_hits / max(1, total_requests)) * 100,
            "overall_eviction_rate": (total_evictions / max(1, total_requests)) * 100
        }
        
        return combined_metrics
    
    def get_cache_analytics(self) -> Dict[str, Any]:
        """
        Get detailed analytics for all cache types
        
        Returns:
            Combined analytics for all caches
        """
        analytics = {}
        
        for cache_name, cache_instance in self.caches.items():
            try:
                cache_analytics = cache_instance.get_analytics()
                analytics[cache_name] = cache_analytics
            except Exception as e:
                logging.error(f"Error getting analytics for {cache_name} cache: {e}")
                analytics[cache_name] = {"error": str(e)}
        
        return analytics
    
    def optimize_caches(self):
        """
        Perform optimization on all caches (evict old entries, update popularity scores)
        """
        logging.info("Starting cache optimization process")
        
        for cache_name, cache_instance in self.caches.items():
            try:
                # Force eviction check if cache is getting full
                current_metrics = cache_instance.get_metrics()
                current_size = current_metrics.get("cache_size", 0)
                max_size = cache_instance.max_size
                
                if current_size > max_size * 0.8:  # If cache is 80% full
                    logging.info(f"Cache {cache_name} is {(current_size/max_size)*100:.1f}% full, triggering eviction")
                    cache_instance._evict_entries()
                
                # Clear very old expired entries (older than 30 days)
                cache_instance.clear_expired_entries(max_age_days=30)
                
            except Exception as e:
                logging.error(f"Error optimizing {cache_name} cache: {e}")
        
        logging.info("Cache optimization completed")
    
    def warm_up_cache(self, queries: List[str]):
        """
        Warm up cache with common queries (for production deployment)
        
        Args:
            queries: List of common queries to pre-cache
        """
        logging.info(f"Warming up cache with {len(queries)} common queries")
        
        # This would be used in production to pre-populate cache with common queries
        # For now, we just log the intent
        for query in queries:
            logging.debug(f"Would warm up cache for query: {query[:50]}...")
    
    def health_check(self) -> Dict[str, Any]:
        """
        Perform health check on all caches
        
        Returns:
            Health status for all caches
        """
        health_status = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "overall_status": "healthy",
            "caches": {}
        }
        
        for cache_name, cache_instance in self.caches.items():
            try:
                # Test basic cache operations
                test_key = {"test": f"health_check_{int(time.time())}"}
                test_data = {"status": "ok", "timestamp": time.time()}
                
                # Test write
                cache_instance.put(test_key, test_data)
                
                # Test read
                result = cache_instance.get(test_key)
                
                # Test cleanup
                cache_instance.collection.delete_one({"cache_key": test_key})
                
                if result and result.get("status") == "ok":
                    health_status["caches"][cache_name] = {
                        "status": "healthy",
                        "metrics": cache_instance.get_metrics()
                    }
                else:
                    health_status["caches"][cache_name] = {
                        "status": "degraded",
                        "error": "Cache read/write test failed"
                    }
                    health_status["overall_status"] = "degraded"
                
            except Exception as e:
                health_status["caches"][cache_name] = {
                    "status": "unhealthy",
                    "error": str(e)
                }
                health_status["overall_status"] = "unhealthy"
                logging.error(f"Health check failed for {cache_name} cache: {e}")
        
        return health_status


# Global cache manager instance (will be initialized in main application)
cache_manager: Optional[CacheManager] = None


def initialize_cache_manager(db_client: MongoClient, max_cache_size: int = 1000) -> CacheManager:
    """
    Initialize global cache manager instance
    
    Args:
        db_client: MongoDB client
        max_cache_size: Maximum cache size for each cache type
        
    Returns:
        Initialized CacheManager instance
    """
    global cache_manager
    cache_manager = CacheManager(db_client, max_cache_size)
    logging.info("Global cache manager initialized")
    return cache_manager


def get_cache_manager() -> Optional[CacheManager]:
    """
    Get the global cache manager instance
    
    Returns:
        CacheManager instance if initialized, None otherwise
    """
    return cache_manager
