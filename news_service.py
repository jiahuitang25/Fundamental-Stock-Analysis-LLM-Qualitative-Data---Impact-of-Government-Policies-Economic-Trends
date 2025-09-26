"""
News Service for the Stock Analysis Application
"""

import logging
import time
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
from pymongo import MongoClient
from config import Config
from utils.api_utils import (
    fetch_malaysia_news, 
    fetch_malaysia_stock_news, 
    get_malaysia_market_overview,
    search_malaysia_news_by_keywords
)

logger = logging.getLogger(__name__)

class NewsService:
    """Service for news operations and management"""
    
    def __init__(self, db_client: MongoClient):
        self.db_client = db_client
        self.db = db_client[Config.DATABASE_NAME]
        self.news_collection = self.db['news_articles']
        self.knowledge_base_collection = self.db['knowledge_base']
        
        # Create indexes
        self.news_collection.create_index("timestamp", expireAfterSeconds=2592000)  # 30 days
        self.news_collection.create_index("category")
        self.news_collection.create_index("source")
        self.knowledge_base_collection.create_index("timestamp")
        self.knowledge_base_collection.create_index("category")
    
    def fetch_historical_malaysia_news(self, from_date=None, to_date=None, query=None, 
                                     category=None, max_results=None, use_semantic_chunking=True):
        """Fetch historical Malaysia news"""
        try:
            # Set default date range if not provided
            if not from_date:
                from_date = (datetime.now(timezone.utc) - timedelta(days=30)).strftime('%Y-%m-%d')
            if not to_date:
                to_date = datetime.now(timezone.utc).strftime('%Y-%m-%d')
            
            # Fetch news from API
            articles = fetch_malaysia_news(
                query=query,
                category=category,
                max_results=max_results or 50
            )
            
            if not articles:
                logger.warning("No articles fetched from API")
                return []
            
            # Process and store articles
            processed_articles = []
            for article in articles:
                try:
                    # Process article
                    processed_article = self._process_article(article, use_semantic_chunking)
                    if processed_article:
                        processed_articles.append(processed_article)
                        
                        # Store in database
                        self._store_article(processed_article)
                        
                except Exception as e:
                    logger.error(f"Error processing article: {e}")
                    continue
            
            logger.info(f"Processed and stored {len(processed_articles)} articles")
            return processed_articles
            
        except Exception as e:
            logger.error(f"Error fetching historical Malaysia news: {e}")
            return []
    
    def fetch_malaysia_stock_news(self, ticker=None, company_name=None, sector=None):
        """Fetch Malaysia stock-specific news"""
        try:
            articles = fetch_malaysia_stock_news(ticker, company_name, sector)
            
            # Process and store articles
            processed_articles = []
            for article in articles:
                try:
                    processed_article = self._process_article(article)
                    if processed_article:
                        processed_articles.append(processed_article)
                        self._store_article(processed_article)
                except Exception as e:
                    logger.error(f"Error processing stock article: {e}")
                    continue
            
            return processed_articles
            
        except Exception as e:
            logger.error(f"Error fetching Malaysia stock news: {e}")
            return []
    
    def get_malaysia_market_overview(self):
        """Get Malaysia market overview"""
        try:
            overview = get_malaysia_market_overview()
            return overview
        except Exception as e:
            logger.error(f"Error getting Malaysia market overview: {e}")
            return {'error': str(e)}
    
    def search_malaysia_news_by_keywords(self, keywords, max_results=20):
        """Search Malaysia news by keywords"""
        try:
            articles = search_malaysia_news_by_keywords(keywords, max_results)
            
            # Process articles
            processed_articles = []
            for article in articles:
                try:
                    processed_article = self._process_article(article)
                    if processed_article:
                        processed_articles.append(processed_article)
                except Exception as e:
                    logger.error(f"Error processing search article: {e}")
                    continue
            
            return processed_articles
            
        except Exception as e:
            logger.error(f"Error searching Malaysia news: {e}")
            return []
    
    def store_news_in_knowledge_base(self, article):
        """Store news article in knowledge base"""
        try:
            if not article or not isinstance(article, dict):
                return False
            
            # Extract content
            content = self._extract_article_content(article)
            if not content or len(content.strip()) < 100:
                logger.warning("Article content too short, skipping")
                return False
            
            # Create knowledge base entry
            kb_entry = {
                'type': 'news_article',
                'content': content,
                'metadata': {
                    'title': article.get('title', ''),
                    'source': article.get('source_id', 'unknown'),
                    'url': article.get('link', ''),
                    'published_date': article.get('pubDate', ''),
                    'category': article.get('category', []),
                    'country': article.get('country', []),
                    'language': article.get('language', 'en'),
                    'description': article.get('description', ''),
                    'image_url': article.get('image_url', ''),
                    'keywords': article.get('keywords', [])
                },
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'processed': True,
                'chunked': False
            }
            
            # Store in knowledge base
            result = self.knowledge_base_collection.insert_one(kb_entry)
            
            if result.inserted_id:
                logger.info(f"Stored article in knowledge base: {article.get('title', 'Unknown')}")
                return True
            else:
                logger.error("Failed to store article in knowledge base")
                return False
                
        except Exception as e:
            logger.error(f"Error storing article in knowledge base: {e}")
            return False
    
    def get_news_articles(self, limit=20, offset=0, category=None, source=None):
        """Get news articles from database"""
        try:
            query = {}
            if category:
                query['category'] = category
            if source:
                query['source'] = source
            
            articles = list(self.news_collection.find(query)
                          .sort('timestamp', -1)
                          .skip(offset)
                          .limit(limit))
            
            # Convert ObjectId to string
            for article in articles:
                article['_id'] = str(article['_id'])
            
            return articles
            
        except Exception as e:
            logger.error(f"Error getting news articles: {e}")
            return []
    
    def get_watchlist_news(self, user_watchlist, limit=20):
        """Get news relevant to user's watchlist"""
        try:
            if not user_watchlist:
                return []
            
            # Extract tickers and company names from watchlist
            tickers = [item.get('ticker', '') for item in user_watchlist if item.get('ticker')]
            company_names = [item.get('company_name', '') for item in user_watchlist if item.get('company_name')]
            
            # Search for relevant news
            relevant_articles = []
            
            # Search by tickers
            for ticker in tickers:
                if ticker:
                    articles = self.search_malaysia_news_by_keywords([ticker], max_results=5)
                    relevant_articles.extend(articles)
            
            # Search by company names
            for company_name in company_names:
                if company_name:
                    articles = self.search_malaysia_news_by_keywords([company_name], max_results=5)
                    relevant_articles.extend(articles)
            
            # Remove duplicates and limit results
            seen_titles = set()
            unique_articles = []
            for article in relevant_articles:
                title = article.get('title', '')
                if title not in seen_titles:
                    seen_titles.add(title)
                    unique_articles.append(article)
                    if len(unique_articles) >= limit:
                        break
            
            return unique_articles
            
        except Exception as e:
            logger.error(f"Error getting watchlist news: {e}")
            return []
    
    def _process_article(self, article, use_semantic_chunking=True):
        """Process raw article data"""
        try:
            if not article or not isinstance(article, dict):
                return None
            
            # Extract and clean content
            content = self._extract_article_content(article)
            if not content or len(content.strip()) < 50:
                return None
            
            # Create processed article
            processed_article = {
                'title': article.get('title', '').strip(),
                'content': content,
                'description': article.get('description', '').strip(),
                'source': article.get('source_id', 'unknown'),
                'url': article.get('link', ''),
                'published_date': article.get('pubDate', ''),
                'category': article.get('category', []),
                'country': article.get('country', []),
                'language': article.get('language', 'en'),
                'image_url': article.get('image_url', ''),
                'keywords': article.get('keywords', []),
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'processed': True,
                'semantic_chunked': use_semantic_chunking
            }
            
            return processed_article
            
        except Exception as e:
            logger.error(f"Error processing article: {e}")
            return None
    
    def _extract_article_content(self, article):
        """Extract content from article"""
        try:
            # Try different content fields
            content_fields = ['content', 'description', 'summary', 'text']
            
            for field in content_fields:
                if field in article and article[field]:
                    content = str(article[field]).strip()
                    if len(content) > 50:
                        return content
            
            # If no content field found, use title and description
            title = article.get('title', '')
            description = article.get('description', '')
            
            if title and description:
                return f"{title}\n\n{description}"
            elif title:
                return title
            elif description:
                return description
            
            return ""
            
        except Exception as e:
            logger.error(f"Error extracting article content: {e}")
            return ""
    
    def _store_article(self, article):
        """Store processed article in database"""
        try:
            if not article:
                return False
            
            # Check if article already exists
            existing = self.news_collection.find_one({
                'title': article['title'],
                'source': article['source']
            })
            
            if existing:
                logger.debug(f"Article already exists: {article['title']}")
                return True
            
            # Insert new article
            result = self.news_collection.insert_one(article)
            
            if result.inserted_id:
                logger.debug(f"Stored article: {article['title']}")
                return True
            else:
                logger.error("Failed to store article")
                return False
                
        except Exception as e:
            logger.error(f"Error storing article: {e}")
            return False
