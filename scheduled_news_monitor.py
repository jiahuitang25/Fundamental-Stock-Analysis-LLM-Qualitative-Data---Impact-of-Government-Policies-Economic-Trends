#!/usr/bin/env python3
"""
Scheduled Malaysia News Monitor
Fetches daily news from NewsData.io API, classifies impact, and stores in MongoDB
"""

import os
import json
import logging
import threading
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple
import schedule
import requests
from pymongo import MongoClient
from newsdataapi import NewsDataApiClient
from dotenv import load_dotenv
import openai
from pinecone import Pinecone
from llama_index.embeddings.openai import OpenAIEmbedding
from bson.objectid import ObjectId

# Load environment variables from .env file
load_dotenv()

# Load sector industries data
with open('sector_industries.json', 'r') as f:
    SECTOR_INDUSTRIES = json.load(f)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('scheduled_news_monitor.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class ScheduledNewsMonitor:
    """
    Scheduled news monitoring system for Malaysia news
    Fetches daily at 08:00 AM Malaysia time, classifies impact, and stores in MongoDB
    """
    
    def __init__(self):
        """Initialize the news monitor with API and database connections"""
        self.api_key = os.getenv('NEWSDATA_API_KEY')
        self.openai_api_key = os.getenv('OPENAI_API_KEY')
        self.pinecone_api_key = os.getenv('PINECONE_API_KEY')
        self.mongo_uri = os.getenv('MONGO_URI', 'mongodb://localhost:27017/')
        self.database_name = os.getenv('DATABASE_NAME', 'fyp_analysis')
        
        # Initialize NewsData.io client
        if not self.api_key:
            raise ValueError("NEWSDATA_API_KEY environment variable is required")
        self.news_client = NewsDataApiClient(apikey=self.api_key)
        
        # Initialize OpenAI client
        if self.openai_api_key:
            self.openai_client = openai.OpenAI(api_key=self.openai_api_key)
        else:
            logger.warning("OPENAI_API_KEY not found - AI summary generation will be disabled")
            self.openai_client = None
        
        # Initialize MongoDB connection
        self.mongo_client = MongoClient(self.mongo_uri)
        self.db = self.mongo_client[self.database_name]
        self.news_collection = self.db['malaysia_news']
        
        # Initialize Pinecone for vector embeddings
        if self.pinecone_api_key:
            try:
                self.pc = Pinecone(api_key=self.pinecone_api_key)
                self.pinecone_index = self.pc.Index("stock-analysis")
                self.embed_model = OpenAIEmbedding(model='text-embedding-3-small', api_key=self.openai_api_key)
                logger.info("✅ Pinecone and embedding model initialized successfully")
            except Exception as e:
                logger.error(f"❌ Failed to initialize Pinecone: {e}")
                self.pinecone_index = None
                self.embed_model = None
        else:
            logger.warning("⚠️  PINECONE_API_KEY not found - vector embeddings will be disabled")
            self.pinecone_index = None
            self.embed_model = None
        
        # Malaysia timezone (UTC+8)
        self.malaysia_tz = timezone(timedelta(hours=8))
        
        # Scheduler control
        self.scheduler_thread = None
        self.is_running = False
        
        logger.info("ScheduledNewsMonitor initialized successfully")
    
    def generate_ai_summary(self, content: str, description: str = "") -> str:
        """
        Generate AI summary using OpenAI API
        
        Args:
            content (str): Article content
            description (str): Article description (fallback)
            
        Returns:
            str: AI-generated summary (2 sentences)
        """
        try:
            if not self.openai_client:
                logger.warning("OpenAI client not available - using description as summary")
                return description[:200] + "..." if len(description) > 200 else description
            
            # Use content if available, otherwise use description
            text_to_summarize = content if content and content.strip() else description
            
            if not text_to_summarize or not text_to_summarize.strip():
                return "No content available for summary generation."
            
            # Truncate if too long (OpenAI has token limits)
            if len(text_to_summarize) > 3000:
                text_to_summarize = text_to_summarize[:3000] + "..."
            
            logger.info("🤖 Generating AI summary using OpenAI...")
            
            response = self.openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {
                        "role": "system", 
                        "content": "You are a news summarizer. Summarize the following news article in exactly 2 sentences. Focus on the key facts and main points. Write in clear, concise English."
                    },
                    {
                        "role": "user", 
                        "content": f"Summarize this news article in 2 sentences:\n\n{text_to_summarize}"
                    }
                ],
                max_tokens=150,
                temperature=0.3
            )
            
            summary = response.choices[0].message.content.strip()
            logger.info(f"✅ AI summary generated: {summary[:100]}...")
            return summary
            
        except Exception as e:
            logger.error(f"❌ Error generating AI summary: {str(e)}")
            # Fallback to description or truncated content
            fallback = description if description and description.strip() else content
            if fallback and len(fallback) > 200:
                return fallback[:200] + "..."
            return fallback or "Summary generation failed."
    
    def determine_stock_market_relevance(self, article: Dict) -> Dict:
        """
        Determine if news article is relevant to stock market
        
        Args:
            article (Dict): News article data
            
        Returns:
            Dict: Relevance analysis with impact_relevance and affected sectors/industries
        """
        try:
            # Extract article content for analysis
            title = article.get('title', '')
            description = article.get('description', '')
            content = article.get('content', '')
            
            # Combine text for analysis
            full_text = f"{title} {description} {content}".lower()
            
            # Define keywords for high relevance
            high_relevance_keywords = [
                # Economy & Finance
                'economy', 'economic', 'gdp', 'inflation', 'interest rate', 'monetary policy',
                'fiscal policy', 'budget', 'revenue', 'profit', 'earnings', 'quarterly',
                'annual report', 'financial', 'banking', 'investment', 'trading', 'market',
                'stock', 'share', 'dividend', 'ipo', 'merger', 'acquisition',
                
                # Government & Policy
                'government', 'policy', 'regulation', 'tax', 'subsidy', 'incentive',
                'ministry', 'minister', 'parliament', 'bill', 'law', 'legislation',
                
                # Companies & Industries
                'company', 'corporation', 'business', 'industry', 'sector', 'manufacturing',
                'production', 'export', 'import', 'trade', 'commerce', 'retail',
                
                # Market Indicators
                'growth', 'decline', 'increase', 'decrease', 'rise', 'fall', 'surge',
                'crash', 'boom', 'recession', 'expansion', 'contraction'
            ]
            
            # Count high relevance keyword occurrences
            relevance_count = sum(1 for keyword in high_relevance_keywords if keyword in full_text)
            
            # Determine relevance level
            if relevance_count >= 3:
                impact_relevance = "high"
            elif relevance_count >= 1:
                impact_relevance = "medium"
            else:
                impact_relevance = "low"
            
            # If high or medium relevance, analyze affected sectors and industries
            affected_sectors = []
            affected_industries = []
            
            if impact_relevance in ["high", "medium"]:
                affected_sectors, affected_industries = self.analyze_sector_industry_impact(full_text)
            
            return {
                'impact_relevance': impact_relevance,
                'relevance_score': relevance_count,
                'affected_sectors': affected_sectors,
                'affected_industries': affected_industries,
                'analyzed_at': datetime.now(self.malaysia_tz).isoformat()
            }
            
        except Exception as e:
            logger.error(f"❌ Error determining stock market relevance: {str(e)}")
            return {
                'impact_relevance': 'low',
                'relevance_score': 0,
                'affected_sectors': [],
                'affected_industries': [],
                'error': str(e)
            }
    
    def analyze_sector_industry_impact(self, text: str) -> Tuple[List[str], List[str]]:
        """
        Analyze which sectors and industries are impacted by the news
        
        Args:
            text (str): Article text to analyze
            
        Returns:
            Tuple[List[str], List[str]]: (affected_sectors, affected_industries)
        """
        try:
            if not self.openai_client:
                # Fallback to keyword matching if OpenAI not available
                return self._keyword_based_sector_analysis(text)
            
            # Create sector-industry mapping for LLM
            sector_industry_map = {}
            for sector_data in SECTOR_INDUSTRIES:
                sector = sector_data['sector']
                industries = sector_data['industries']
                sector_industry_map[sector] = industries
            
            # Prepare context for LLM
            context = f"""
            Analyze this news article and determine which stock market sectors and industries are most likely to be impacted.
            
            Available sectors and their industries:
            {json.dumps(sector_industry_map, indent=2)}
            
            News article text:
            {text[:2000]}  # Limit text length for API
            
            Return your analysis in this exact JSON format:
            {{
                "affected_sectors": ["sector1", "sector2"],
                "affected_industries": ["industry1", "industry2", "industry3"],
                "reasoning": "Brief explanation of why these sectors/industries are affected"
            }}
            """
            
            logger.info("🤖 Analyzing sector/industry impact using OpenAI...")
            
            response = self.openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a financial analyst. Analyze news articles to determine which stock market sectors and industries are most likely to be impacted. Be specific and accurate in your analysis."
                    },
                    {
                        "role": "user",
                        "content": context
                    }
                ],
                max_tokens=300,
                temperature=0.3
            )
            
            result = response.choices[0].message.content.strip()
            
            # Parse JSON response
            try:
                analysis = json.loads(result)
                affected_sectors = analysis.get('affected_sectors', [])
                affected_industries = analysis.get('affected_industries', [])
                
                # Validate sectors and industries against our data
                valid_sectors = []
                valid_industries = []
                
                for sector in affected_sectors:
                    if any(s['sector'] == sector for s in SECTOR_INDUSTRIES):
                        valid_sectors.append(sector)
                
                for industry in affected_industries:
                    for sector_data in SECTOR_INDUSTRIES:
                        if industry in sector_data['industries']:
                            valid_industries.append(industry)
                            break
                
                logger.info(f"✅ Sector analysis: {len(valid_sectors)} sectors, {len(valid_industries)} industries")
                return valid_sectors, valid_industries
                
            except json.JSONDecodeError:
                logger.warning("⚠️ Failed to parse LLM response, using keyword analysis")
                return self._keyword_based_sector_analysis(text)
            
        except Exception as e:
            logger.error(f"❌ Error in sector analysis: {str(e)}")
            return self._keyword_based_sector_analysis(text)
    
    def _keyword_based_sector_analysis(self, text: str) -> Tuple[List[str], List[str]]:
        """
        Fallback keyword-based sector analysis
        
        Args:
            text (str): Article text to analyze
            
        Returns:
            Tuple[List[str], List[str]]: (affected_sectors, affected_industries)
        """
        affected_sectors = []
        affected_industries = []
        
        # Define sector keywords
        sector_keywords = {
            'financial-services': ['bank', 'financial', 'insurance', 'credit', 'loan', 'mortgage', 'investment'],
            'technology': ['tech', 'software', 'hardware', 'digital', 'internet', 'semiconductor', 'ai', 'data'],
            'energy': ['oil', 'gas', 'energy', 'petroleum', 'renewable', 'solar', 'wind'],
            'healthcare': ['health', 'medical', 'pharmaceutical', 'drug', 'hospital', 'biotech'],
            'consumer-cyclical': ['retail', 'automotive', 'travel', 'tourism', 'entertainment', 'gaming'],
            'consumer-defensive': ['food', 'beverage', 'grocery', 'tobacco', 'utilities'],
            'industrials': ['manufacturing', 'construction', 'aerospace', 'defense', 'logistics'],
            'basic-materials': ['steel', 'chemical', 'mining', 'metal', 'lumber', 'paper'],
            'real-estate': ['real estate', 'property', 'reit', 'housing', 'commercial'],
            'utilities': ['utility', 'electric', 'water', 'gas', 'power']
        }
        
        for sector, keywords in sector_keywords.items():
            if any(keyword in text for keyword in keywords):
                affected_sectors.append(sector)
                
                # Find specific industries within the sector
                for sector_data in SECTOR_INDUSTRIES:
                    if sector_data['sector'] == sector:
                        for industry in sector_data['industries']:
                            industry_keywords = industry.replace('-', ' ').split()
                            if any(keyword in text for keyword in industry_keywords):
                                affected_industries.append(industry)
                        break
        
        return list(set(affected_sectors)), list(set(affected_industries))
    
    def create_news_embeddings(self, article: Dict) -> Optional[List[float]]:
        """
        Create vector embeddings for a news article (LEGACY - kept for backward compatibility)
        
        Args:
            article (Dict): News article data
            
        Returns:
            Optional[List[float]]: Vector embedding or None if failed
        """
        try:
            if not self.embed_model:
                logger.warning("⚠️  Embedding model not available - skipping vector embedding")
                return None
            
            # Combine title, description, and content for embedding
            title = article.get('title', '')
            description = article.get('description', '')
            content = article.get('content', '')
            
            # Create text for embedding (prioritize title and description for better relevance)
            text_for_embedding = f"{title} {description}"
            if content and len(text_for_embedding) < 200:
                # Add content if title+description is too short
                text_for_embedding += f" {content[:500]}"  # Limit content length
            
            if not text_for_embedding.strip():
                logger.warning("⚠️  No text content for embedding")
                return None
            
            # Generate embedding
            logger.info(f"🔢 Generating vector embedding for: {title[:50]}...")
            embedding = self.embed_model.get_text_embedding(text_for_embedding)
            
            logger.info(f"✅ Vector embedding generated (dimension: {len(embedding)})")
            return embedding
            
        except Exception as e:
            logger.error(f"❌ Error creating news embedding: {str(e)}")
            return None
    
    def create_chunked_embeddings(self, article: Dict, mongo_id: str) -> Optional[List[Dict]]:
        """
        Create chunked embeddings for a news article following RAG best practices
        
        Args:
            article (Dict): News article data
            mongo_id (str): MongoDB document ID
            
        Returns:
            Optional[List[Dict]]: List of chunk data with embeddings or None if failed
        """
        try:
            if not self.embed_model:
                logger.warning("⚠️  Embedding model not available - skipping chunked embeddings")
                return None
            
            # Combine title, description, and content for chunking
            title = article.get('title', '')
            description = article.get('description', '')
            content = article.get('content', '')
            
            # Create comprehensive text for chunking
            full_text = f"{title}\n\n{description}\n\n{content}" if content else f"{title}\n\n{description}"
            
            if not full_text.strip():
                logger.warning("⚠️  No text content for chunking")
                return None
            
            # Chunk the text using semantic chunking
            chunks = self._chunk_text_semantic(full_text, chunk_size=512)
            
            if not chunks:
                logger.warning("⚠️  No chunks created from text")
                return None
            
            chunk_embeddings = []
            
            for i, chunk in enumerate(chunks):
                try:
                    # Generate embedding for this chunk
                    embedding = self.embed_model.get_text_embedding(chunk)
                    
                    # Create chunk data structure
                    chunk_data = {
                        'chunk_id': f"{mongo_id}_chunk_{i}",
                        'chunk_index': i,
                        'chunk_text': chunk,
                        'embedding': embedding,
                        'chunk_size': len(chunk),
                        'mongo_id': mongo_id,
                        'article_title': title,
                        'source_name': article.get('source_name', ''),
                        'category': article.get('category', []),
                        'affected_sectors': article.get('affected_sectors', []),
                        'processed_at': article.get('processed_at', '')
                    }
                    
                    chunk_embeddings.append(chunk_data)
                    
                except Exception as e:
                    logger.error(f"❌ Error creating embedding for chunk {i}: {str(e)}")
                    continue
            
            logger.info(f"✅ Created {len(chunk_embeddings)} chunk embeddings for: {title[:50]}...")
            return chunk_embeddings if chunk_embeddings else None
            
        except Exception as e:
            logger.error(f"❌ Error creating chunked embeddings: {str(e)}")
            return None
    
    def _chunk_text_semantic(self, text: str, chunk_size: int = 512) -> List[str]:
        """
        Chunk text using semantic chunking with LlamaIndex SemanticSplitterNodeParser
        
        Args:
            text (str): Text to chunk
            chunk_size (int): Target chunk size in characters
            
        Returns:
            List[str]: List of semantically coherent text chunks
        """
        if not text.strip():
            return []
        
        try:
            from llama_index.core.node_parser import SemanticSplitterNodeParser
            from llama_index.core.schema import Document
            from llama_index.embeddings.openai import OpenAIEmbedding
            
            # Create a document from the text
            doc = Document(text=text)
            
            # Initialize semantic splitter with embedding model
            embed_model = OpenAIEmbedding(model='text-embedding-3-small', api_key=os.getenv('OPENAI_API_KEY'))
            
            # Create semantic splitter with buffer size (overlap)
            buffer_size = 50  # Characters of overlap between chunks
            semantic_splitter = SemanticSplitterNodeParser(
                buffer_size=buffer_size,
                embed_model=embed_model,
                breakpoint_percentile_threshold=95,  # Threshold for semantic similarity
                include_metadata=True,
                include_prev_next_rel=True
            )
            
            # Split the document semantically
            nodes = semantic_splitter.get_nodes_from_documents([doc])
            
            # Extract text from nodes and ensure they don't exceed chunk_size
            chunks = []
            for node in nodes:
                chunk_text = node.text.strip()
                
                # If chunk is too large, split it further using sentence boundaries
                if len(chunk_text) > chunk_size:
                    sub_chunks = self._split_large_chunk(chunk_text, chunk_size)
                    chunks.extend(sub_chunks)
                else:
                    chunks.append(chunk_text)
            
            # Filter out empty chunks
            chunks = [chunk for chunk in chunks if chunk.strip()]
            
            logger.info(f"✅ Created {len(chunks)} semantic chunks (avg size: {sum(len(c) for c in chunks) // len(chunks) if chunks else 0} chars)")
            
            return chunks
            
        except ImportError as e:
            logger.warning(f"⚠️  SemanticSplitterNodeParser not available, falling back to sentence-based chunking: {e}")
            return self._chunk_text_fallback(text, chunk_size)
        except Exception as e:
            logger.error(f"❌ Error in semantic chunking, falling back to sentence-based: {e}")
            return self._chunk_text_fallback(text, chunk_size)
    
    def _split_large_chunk(self, text: str, max_size: int) -> List[str]:
        """
        Split large chunks using sentence boundaries as fallback
        
        Args:
            text (str): Text to split
            max_size (int): Maximum size per chunk
            
        Returns:
            List[str]: List of smaller chunks
        """
        sentences = text.split('. ')
        chunks = []
        current_chunk = ""
        
        for sentence in sentences:
            # Add period back if it's not the last sentence
            if sentence != sentences[-1]:
                sentence += '. '
            
            # Check if adding this sentence would exceed max size
            if len(current_chunk) + len(sentence) <= max_size:
                current_chunk += sentence
            else:
                # Save current chunk if it has content
                if current_chunk.strip():
                    chunks.append(current_chunk.strip())
                current_chunk = sentence
        
        # Add the last chunk if it has content
        if current_chunk.strip():
            chunks.append(current_chunk.strip())
        
        return chunks
    
    def _chunk_text_fallback(self, text: str, chunk_size: int = 512, chunk_overlap: int = 50) -> List[str]:
        """
        Fallback chunking using sentence-based splitting with overlap
        
        Args:
            text (str): Text to chunk
            chunk_size (int): Target chunk size in characters
            chunk_overlap (int): Overlap between chunks in characters
            
        Returns:
            List[str]: List of text chunks
        """
        if not text.strip():
            return []
        
        # Split by sentences first, then by paragraphs
        sentences = text.split('. ')
        chunks = []
        current_chunk = ""
        
        for sentence in sentences:
            # Add period back if it's not the last sentence
            if sentence != sentences[-1]:
                sentence += '. '
            
            # Check if adding this sentence would exceed chunk size
            if len(current_chunk) + len(sentence) <= chunk_size:
                current_chunk += sentence
            else:
                # Save current chunk if it has content
                if current_chunk.strip():
                    chunks.append(current_chunk.strip())
                
                # Start new chunk with overlap
                if chunk_overlap > 0 and len(current_chunk) > chunk_overlap:
                    # Take last part of previous chunk for overlap
                    overlap_text = current_chunk[-chunk_overlap:]
                    current_chunk = overlap_text + sentence
                else:
                    current_chunk = sentence
        
        # Add the last chunk if it has content
        if current_chunk.strip():
            chunks.append(current_chunk.strip())
        
        logger.info(f"✅ Created {len(chunks)} fallback chunks (avg size: {sum(len(c) for c in chunks) // len(chunks) if chunks else 0} chars)")
        
        return chunks
    
    def store_news_embedding(self, article: Dict, embedding: List[float]) -> Optional[str]:
        """
        Store news article embedding in Pinecone
        
        Args:
            article (Dict): News article data
            embedding (List[float]): Pre-computed embedding vector
            
        Returns:
            Optional[str]: Vector ID if successful, None otherwise
        """
        try:
            if not self.pinecone_index:
                logger.warning("⚠️  Pinecone not available - skipping vector storage")
                return None
            
            if not embedding:
                logger.warning("⚠️  No embedding provided")
                return None
            
            # Create unique vector ID for news article  
            mongo_id = str(article['_id'])
            article_id = article.get('article_id', mongo_id)
            vector_id = f"news_{article_id}"
            
            # Prepare metadata for Pinecone (ensure all values are strings, numbers, or booleans)
            metadata = {
                'mongo_id': str(mongo_id),
                'article_id': article_id,
                'source': 'malaysia_news',
                'type': 'news_article',
                'title': article.get('title', '')[:100],  # Limit title length
                'source_name': article.get('source_name', ''),
                'category': ','.join(article.get('category', [])),
                'impact_relevance': article.get('impact_relevance', 'low'),
                'affected_sectors': ','.join(article.get('affected_sectors', [])),
                'processed_at': article.get('processed_at', '')
            }
            
            # Store in Pinecone
            logger.info(f"📊 Storing vector embedding in Pinecone: {vector_id}")
            self.pinecone_index.upsert([(vector_id, embedding, metadata)])
            
            logger.info(f"✅ News embedding stored successfully: {vector_id}")
            return vector_id
            
        except Exception as e:
            logger.error(f"❌ Error storing news embedding: {str(e)}")
            return None
    
    def store_chunked_embeddings(self, article: Dict, chunk_embeddings: List[Dict], mongo_id: str) -> Optional[List[str]]:
        """
        Store chunked embeddings in Pinecone following RAG best practices
        
        Args:
            article (Dict): News article data
            chunk_embeddings (List[Dict]): List of chunk data with embeddings
            mongo_id (str): MongoDB document ID
            
        Returns:
            Optional[List[str]]: List of vector IDs if successful, None otherwise
        """
        try:
            if not self.pinecone_index:
                logger.warning("⚠️  Pinecone not available - skipping chunked vector storage")
                return None
            
            if not chunk_embeddings:
                logger.warning("⚠️  No chunk embeddings provided")
                return None
            
            vector_ids = []
            upsert_data = []
            
            for chunk_data in chunk_embeddings:
                try:
                    vector_id = chunk_data['chunk_id']
                    embedding = chunk_data['embedding']
                    
                    # Prepare metadata for Pinecone (ensure all values are strings, numbers, or booleans)
                    metadata = {
                        'mongo_id': str(mongo_id),
                        'chunk_id': chunk_data['chunk_id'],
                        'chunk_index': chunk_data['chunk_index'],
                        'source': 'malaysia_news_chunk',
                        'type': 'news_chunk',
                        'chunk_text': chunk_data['chunk_text'][:1000],  # Limit text length for metadata
                        'article_title': chunk_data['article_title'][:100],
                        'source_name': chunk_data['source_name'],
                        'category': ','.join(chunk_data['category']) if chunk_data['category'] else '',
                        'affected_sectors': ','.join(chunk_data['affected_sectors']) if chunk_data['affected_sectors'] else '',
                        'chunk_size': chunk_data['chunk_size'],
                        'processed_at': chunk_data['processed_at']
                    }
                    
                    upsert_data.append((vector_id, embedding, metadata))
                    vector_ids.append(vector_id)
                    
                except Exception as e:
                    logger.error(f"❌ Error preparing chunk {chunk_data.get('chunk_id', 'unknown')} for storage: {str(e)}")
                    continue
            
            if upsert_data:
                # Batch upsert to Pinecone
                logger.info(f"📊 Storing {len(upsert_data)} chunk embeddings in Pinecone...")
                self.pinecone_index.upsert(upsert_data)
                
                logger.info(f"✅ {len(vector_ids)} chunk embeddings stored successfully")
                return vector_ids
            else:
                logger.warning("⚠️  No valid chunks to store")
                return None
            
        except Exception as e:
            logger.error(f"❌ Error storing chunked embeddings: {str(e)}")
            return None
    
    def fetch_malaysia_news(self, max_results: int = 50) -> Dict:
        """
        Fetch latest Malaysia news from NewsData.io API with specific categories and regions
        
        Args:
            max_results (int): Maximum number of articles to fetch
            
        Returns:
            Dict: News data with articles and metadata
        """
        try:
            logger.info("📡 Fetching Malaysia news from NewsData.io...")
            
            # Define allowed categories (limited to 5 per API call)
            allowed_categories = [
                "business",
                "politics", 
                "technology",
                "health",
                "environment"
            ]
            
            # Malaysia-specific search query (limited to 100 characters)
            malaysia_query = 'Malaysia OR Bursa OR "Kuala Lumpur" OR government OR Petaling OR Johor OR Sabah'
            
            # API parameters
            params = {
                'country': 'my',  # Malaysia
                'language': 'en',  # English
                'category': ','.join(allowed_categories),  # Filter by specific categories
                'q': malaysia_query  # Malaysia-specific search terms
            }
            
            # Add size parameter only if it's within valid range (1-10 for free tier)
            if max_results and 1 <= max_results <= 10:
                params['size'] = max_results
            elif max_results and max_results > 10:
                params['size'] = 10  # Limit to 10 for free tier
            
            logger.info(f"API request parameters: {params}")
            
            # Fetch news from NewsData.io
            response = self.news_client.news_api(**params)
            
            if response.get('status') == 'success':
                articles = response.get('results', [])
                logger.info(f"✅ Successfully fetched {len(articles)} articles from API")
                
                # Filter for Malaysian news articles (accept all sources but prioritize quality)
                filtered_articles = []
                
                for article in articles:
                    # Basic filtering for quality and relevance
                    title = article.get('title', '')
                    description = article.get('description', '')
                    
                    # Skip articles that are too short or lack content
                    if len(title) < 10 or len(description) < 20:
                        continue
                    
                    # Add all quality articles from Malaysia
                    filtered_articles.append(article)
                
                logger.info(f"✅ Filtered to {len(filtered_articles)} quality Malaysian news articles")
                
                return {
                    'status': 'success',
                    'articles': filtered_articles,
                    'total_results': len(filtered_articles),
                    'original_count': len(articles),
                    'fetched_at': datetime.now(self.malaysia_tz).isoformat()
                }
            else:
                logger.error(f"❌ API error: {response.get('message', 'Unknown error')}")
                return {
                    'status': 'error',
                    'message': response.get('message', 'Unknown error'),
                    'articles': []
                }
                
        except Exception as e:
            logger.error(f"❌ Error fetching news: {str(e)}")
            return {
                'status': 'error',
                'message': str(e),
                'articles': []
            }
    
    def classify_news_impact(self, article: Dict) -> Dict:
        """
        Classify the potential stock/economic impact of a news article
        
        Args:
            article (Dict): News article data
            
        Returns:
            Dict: Classification result with impact, confidence, and reasoning
        """
        try:
            # Extract article content for analysis
            title = article.get('title', '')
            description = article.get('description', '')
            content = article.get('content', '')
            
            # Combine text for analysis
            full_text = f"{title} {description} {content}".lower()
            
            # Define keywords for impact classification
            positive_keywords = [
                'profit', 'growth', 'increase', 'rise', 'gain', 'surge', 'boom',
                'expansion', 'success', 'achievement', 'breakthrough', 'milestone',
                'positive', 'strong', 'robust', 'healthy', 'improvement', 'upgrade',
                'investment', 'funding', 'acquisition', 'merger', 'partnership',
                'award', 'recognition', 'innovation', 'development', 'launch'
            ]
            
            negative_keywords = [
                'loss', 'decline', 'decrease', 'fall', 'drop', 'crash', 'recession',
                'crisis', 'problem', 'issue', 'concern', 'risk', 'threat', 'warning',
                'negative', 'weak', 'poor', 'struggle', 'difficulty', 'challenge',
                'layoff', 'cut', 'reduction', 'closure', 'bankruptcy', 'debt',
                'scandal', 'investigation', 'lawsuit', 'penalty', 'fine'
            ]
            
            # Count keyword occurrences
            positive_count = sum(1 for keyword in positive_keywords if keyword in full_text)
            negative_count = sum(1 for keyword in negative_keywords if keyword in full_text)
            
            # Calculate confidence score
            total_keywords = positive_count + negative_count
            confidence = min(total_keywords / 10, 1.0) if total_keywords > 0 else 0.0
            
            # Determine impact classification
            if positive_count > negative_count:
                impact = 'positive'
                reasoning = f"Article contains {positive_count} positive indicators vs {negative_count} negative"
            elif negative_count > positive_count:
                impact = 'negative'
                reasoning = f"Article contains {negative_count} negative indicators vs {positive_count} positive"
            else:
                impact = 'neutral'
                reasoning = f"Article has balanced indicators: {positive_count} positive, {negative_count} negative"
            
            # Additional analysis for economic/financial relevance
            economic_terms = [
                'stock', 'market', 'economy', 'financial', 'revenue', 'earnings',
                'quarterly', 'annual', 'dividend', 'share', 'trading', 'investment',
                'banking', 'finance', 'monetary', 'fiscal', 'budget', 'gdp'
            ]
            
            economic_relevance = sum(1 for term in economic_terms if term in full_text)
            is_economically_relevant = economic_relevance > 0
            
            return {
                'impact': impact,
                'confidence': round(confidence, 2),
                'reasoning': reasoning,
                'positive_indicators': positive_count,
                'negative_indicators': negative_count,
                'economic_relevance': is_economically_relevant,
                'economic_terms_found': economic_relevance,
                'analyzed_at': datetime.now(self.malaysia_tz).isoformat()
            }
            
        except Exception as e:
            logger.error(f"❌ Error classifying article impact: {str(e)}")
            return {
                'impact': 'neutral',
                'confidence': 0.0,
                'reasoning': f"Classification error: {str(e)}",
                'error': str(e)
            }
    
    def process_news_article(self, article: Dict) -> Dict:
        """
        Process a single news article: collect all fields, classify impact, and prepare for storage
        
        Args:
            article (Dict): Raw article data from API
            
        Returns:
            Dict: Processed article with all fields and classification
        """
        try:
            # Classify the article impact
            classification = self.classify_news_impact(article)
            
            # Determine stock market relevance
            relevance_analysis = self.determine_stock_market_relevance(article)
            
            # Extract all required fields from the article
            article_id = article.get('article_id')
            title = article.get('title', '')
            link = article.get('link', '')
            keywords = article.get('keywords', [])
            description = article.get('description', '')
            content = article.get('content', '')
            pub_date = article.get('pubDate', '')
            pub_date_tz = article.get('pubDateTZ', '')
            image_url = article.get('image_url', '')
            video_url = article.get('video_url', '')
            source_id = article.get('source_id', '')
            source_name = article.get('source_name', '')
            source_url = article.get('source_url', '')
            source_icon = article.get('source_icon', '')
            language = article.get('language', '')
            country = article.get('country', [])
            category = article.get('category', [])
            ai_summary = article.get('ai_summary', '')
            duplicate = article.get('duplicate', False)
            
            # Handle AI summary generation
            if ai_summary and ai_summary.strip():
                # Use existing AI summary from API
                logger.info(f"📝 Using existing AI summary for article: {title[:50]}...")
                final_ai_summary = ai_summary
            else:
                # Generate AI summary using OpenAI
                logger.info(f"🤖 Generating AI summary for article: {title[:50]}...")
                final_ai_summary = self.generate_ai_summary(content, description)
            
            # Create comprehensive processed article document
            processed_article = {
                # Core article fields
                'article_id': article_id,
                'title': title,
                'link': link,
                'keywords': keywords,
                'description': description,
                'content': content,
                'pubDate': pub_date,
                'pubDateTZ': pub_date_tz,
                'image_url': image_url,
                'video_url': video_url,
                
                # Source information
                'source_id': source_id,
                'source_name': source_name,
                'source_url': source_url,
                'source_icon': source_icon,
                
                # Metadata
                'language': language,
                'country': country,
                'category': category,
                'ai_summary': final_ai_summary,
                'duplicate': duplicate,
                
                # Stock market analysis
                'impact_relevance': relevance_analysis.get('impact_relevance', 'low'),
                'relevance_score': relevance_analysis.get('relevance_score', 0),
                'affected_sectors': relevance_analysis.get('affected_sectors', []),
                'affected_industries': relevance_analysis.get('affected_industries', []),
                
                # Impact analysis
                'impact_classification': classification,
                
                # Processing metadata
                'processed_at': datetime.now(self.malaysia_tz).isoformat(),
                'source': 'newsdata_io',
                'type': 'malaysia_news',
                'ai_summary_generated': not bool(ai_summary and ai_summary.strip())  # Track if we generated it
            }
            
            return processed_article
            
        except Exception as e:
            logger.error(f"❌ Error processing article: {str(e)}")
            return None
    
    def store_news_articles(self, articles: List[Dict]) -> Tuple[int, int]:
        """
        Store processed news articles in MongoDB with chunked vector embeddings
        
        Args:
            articles (List[Dict]): List of processed articles
            
        Returns:
            Tuple[int, int]: (successful_stores, failed_stores)
        """
        successful = 0
        failed = 0
        
        try:
            logger.info(f"💾 Storing {len(articles)} articles in MongoDB with chunked vector embeddings...")
            
            for article in articles:
                if article is None:
                    failed += 1
                    continue
                    
                try:
                    # Check if article already exists
                    existing = self.news_collection.find_one({
                        'article_id': article.get('article_id')
                    })
                    
                    if existing:
                        logger.info(f"⏭️  Article already exists: {article.get('title', '')[:50]}...")
                        continue
                    
                    # Insert new article into MongoDB
                    result = self.news_collection.insert_one(article)
                    if result.inserted_id:
                        mongo_id = str(result.inserted_id)
                        successful += 1
                        logger.info(f"✅ Stored article in MongoDB: {article.get('title', '')[:50]}...")
                        
                        # Create and store chunked embeddings
                        if self.pinecone_index and self.embed_model:
                            chunk_embeddings = self.create_chunked_embeddings(article, mongo_id)
                            if chunk_embeddings:
                                embedding_ids = self.store_chunked_embeddings(article, chunk_embeddings, mongo_id)
                                if embedding_ids:
                                    # Update MongoDB document with chunk embedding info
                                    self.news_collection.update_one(
                                        {'_id': result.inserted_id},
                                        {'$set': {
                                            'chunk_embeddings': embedding_ids,
                                            'chunk_count': len(embedding_ids)
                                        }}
                                    )
                                    logger.info(f"✅ {len(embedding_ids)} chunk embeddings stored for: {article.get('title', '')[:50]}...")
                                else:
                                    logger.warning(f"⚠️  Chunk embedding storage failed for: {article.get('title', '')[:50]}...")
                            else:
                                logger.warning(f"⚠️  Could not create chunk embeddings for: {article.get('title', '')[:50]}...")
                        else:
                            logger.warning(f"⚠️  Skipping chunk embeddings (Pinecone not available): {article.get('title', '')[:50]}...")
                    else:
                        failed += 1
                        logger.warning(f"⚠️  Failed to store article: {article.get('title', '')[:50]}...")
                        
                except Exception as e:
                    failed += 1
                    logger.error(f"❌ Error storing individual article: {str(e)}")
            
            logger.info(f"📊 Storage complete: {successful} successful, {failed} failed")
            return successful, failed
            
        except Exception as e:
            logger.error(f"❌ Error in bulk storage: {str(e)}")
            return successful, failed
    
    def search_news_by_embedding(self, query: str, top_k: int = 5) -> List[Dict]:
        """
        Search news articles using vector embeddings (supports both chunked and legacy articles)
        
        Args:
            query (str): Search query
            top_k (int): Number of results to return
            
        Returns:
            List[Dict]: List of relevant news chunks/articles
        """
        try:
            if not self.pinecone_index or not self.embed_model:
                logger.warning("⚠️  Pinecone not available - cannot perform vector search")
                return []
            
            # Generate query embedding
            logger.info(f"🔍 Searching news with query: {query[:50]}...")
            query_embedding = self.embed_model.get_text_embedding(query)
            
            # Search Pinecone for similar vectors (prioritize chunks, fallback to articles)
            search_results = self.pinecone_index.query(
                vector=query_embedding,
                top_k=top_k,
                include_metadata=True,
                filter={"type": "news_chunk"}  # Search for chunked news first
            )
            
            # If no chunks found, search for legacy articles
            if not search_results['matches']:
                search_results = self.pinecone_index.query(
                    vector=query_embedding,
                    top_k=top_k,
                    include_metadata=True,
                    filter={"type": "news_article"}  # Fallback to legacy articles
                )
            
            # Process results based on type
            relevant_results = []
            for match in search_results['matches']:
                metadata = match['metadata']
                similarity_score = match['score']
                
                if metadata.get('type') == 'news_chunk':
                    # This is a chunked result - return chunk data directly
                    chunk_result = {
                        'chunk_id': metadata.get('chunk_id'),
                        'chunk_text': metadata.get('chunk_text', ''),
                        'article_title': metadata.get('article_title', ''),
                        'source_name': metadata.get('source_name', ''),
                        'category': metadata.get('category', '').split(',') if metadata.get('category') else [],
                        'affected_sectors': metadata.get('affected_sectors', '').split(',') if metadata.get('affected_sectors') else [],
                        'mongo_id': metadata.get('mongo_id'),
                        'chunk_index': metadata.get('chunk_index', 0),
                        'similarity_score': similarity_score,
                        'type': 'news_chunk'
                    }
                    relevant_results.append(chunk_result)
                else:
                    # Legacy article - get full article from MongoDB
                    mongo_id = metadata.get('mongo_id')
                    if mongo_id:
                        article = self.news_collection.find_one({"_id": ObjectId(mongo_id)})
                        if article:
                            article['similarity_score'] = similarity_score
                            article['vector_id'] = match['id']
                            article['type'] = 'news_article'
                            relevant_results.append(article)
            
            logger.info(f"✅ Found {len(relevant_results)} relevant news chunks/articles")
            return relevant_results
            
        except Exception as e:
            logger.error(f"❌ Error searching news by embedding: {str(e)}")
            return []
    
    def get_news_embedding_stats(self) -> Dict:
        """
        Get statistics about news embeddings in Pinecone
        
        Returns:
            Dict: Statistics about news embeddings
        """
        try:
            if not self.pinecone_index:
                return {"error": "Pinecone not available"}
            
            # Get index stats
            stats = self.pinecone_index.describe_index_stats()
            
            # Count news vectors specifically
            news_vectors = 0
            try:
                # Query for news vectors to count them
                news_results = self.pinecone_index.query(
                    vector=[0.0] * 1536,  # Dummy vector for counting
                    top_k=10000,  # Large number to get all
                    include_metadata=True,
                    filter={"source": "malaysia_news"}
                )
                news_vectors = len(news_results['matches'])
            except:
                news_vectors = "Unknown"
            
            return {
                "total_vectors": stats.get('total_vector_count', 0),
                "news_vectors": news_vectors,
                "dimension": stats.get('dimension', 0),
                "index_fullness": stats.get('index_fullness', 0)
            }
            
        except Exception as e:
            logger.error(f"❌ Error getting embedding stats: {str(e)}")
            return {"error": str(e)}
    
    def daily_news_fetch_and_process(self):
        """
        Main scheduled task: fetch, process, and store Malaysia news
        Runs daily at 08:00 AM Malaysia time
        """
        try:
            logger.info("🕐 Starting daily Malaysia news fetch and process...")
            start_time = datetime.now(self.malaysia_tz)
            
            # Step 1: Fetch latest news
            news_data = self.fetch_malaysia_news(max_results=10)
            
            if news_data['status'] != 'success':
                logger.error(f"❌ Failed to fetch news: {news_data.get('message')}")
                return
            
            articles = news_data.get('articles', [])
            if not articles:
                logger.warning("⚠️  No articles received from API")
                return
            
            logger.info(f"📰 Processing {len(articles)} articles...")
            
            # Step 2: Process each article
            processed_articles = []
            for i, article in enumerate(articles, 1):
                logger.info(f"🔄 Processing article {i}/{len(articles)}: {article.get('title', '')[:50]}...")
                processed = self.process_news_article(article)
                if processed:
                    processed_articles.append(processed)
            
            # Step 3: Store processed articles
            successful, failed = self.store_news_articles(processed_articles)
            
            # Step 4: Log summary
            end_time = datetime.now(self.malaysia_tz)
            duration = (end_time - start_time).total_seconds()
            
            logger.info("=" * 60)
            logger.info("📊 DAILY NEWS PROCESSING SUMMARY")
            logger.info("=" * 60)
            logger.info(f"🕐 Start time: {start_time.strftime('%Y-%m-%d %H:%M:%S MYT')}")
            logger.info(f"🕐 End time: {end_time.strftime('%Y-%m-%d %H:%M:%S MYT')}")
            logger.info(f"⏱️  Duration: {duration:.2f} seconds")
            logger.info(f"📰 Articles fetched: {len(articles)}")
            logger.info(f"🔄 Articles processed: {len(processed_articles)}")
            logger.info(f"✅ Successfully stored: {successful}")
            logger.info(f"❌ Failed to store: {failed}")
            
            # Impact classification summary
            impact_counts = {'positive': 0, 'negative': 0, 'neutral': 0}
            for article in processed_articles:
                impact = article.get('impact_classification', {}).get('impact', 'neutral')
                impact_counts[impact] += 1
            
            logger.info(f"📈 Impact classification: {impact_counts}")
            logger.info("=" * 60)
            
        except Exception as e:
            logger.error(f"❌ Error in daily news processing: {str(e)}")
    
    def start_scheduler(self):
        """Start the scheduled news monitoring"""
        try:
            if self.is_running:
                logger.warning("⚠️  Scheduler is already running")
                return False
            
            logger.info("🚀 Starting scheduled news monitoring...")
            
            # Schedule daily task at 08:00 AM Malaysia time
            schedule.every().day.at("08:00").do(self.daily_news_fetch_and_process)
            
            # Start scheduler in background thread
            self.scheduler_thread = threading.Thread(target=self._run_scheduler, daemon=True)
            self.scheduler_thread.start()
            self.is_running = True
            
            logger.info("✅ Scheduled news monitoring started successfully")
            logger.info("📅 Next run: Daily at 08:00 AM Malaysia time")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to start scheduler: {str(e)}")
            return False
    
    def stop_scheduler(self):
        """Stop the scheduled news monitoring"""
        try:
            if not self.is_running:
                logger.warning("⚠️  Scheduler is not running")
                return False
            
            logger.info("🛑 Stopping scheduled news monitoring...")
            
            # Clear all scheduled jobs
            schedule.clear()
            
            # Stop scheduler thread
            if self.scheduler_thread and self.scheduler_thread.is_alive():
                self.scheduler_thread.join(timeout=5)
            
            self.is_running = False
            logger.info("✅ Scheduled news monitoring stopped successfully")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to stop scheduler: {str(e)}")
            return False
    
    def _run_scheduler(self):
        """Run the scheduler loop in background thread"""
        try:
            while self.is_running:
                schedule.run_pending()
                time.sleep(60)  # Check every minute
        except Exception as e:
            logger.error(f"❌ Scheduler error: {str(e)}")
    
    def test_immediate_run(self):
        """Test the system with an immediate run"""
        try:
            logger.info("🧪 Running immediate test of news processing...")
            self.daily_news_fetch_and_process()
            logger.info("✅ Test run completed successfully")
            return True
        except Exception as e:
            logger.error(f"❌ Test run failed: {str(e)}")
            return False
    
    def get_status(self):
        """Get current status of the scheduler"""
        try:
            next_run = schedule.next_run()
            return {
                'is_running': self.is_running,
                'next_run': next_run.isoformat() if next_run else None,
                'scheduled_jobs': len(schedule.jobs),
                'database_connected': self.mongo_client.admin.command('ping').get('ok') == 1
            }
        except Exception as e:
            logger.error(f"❌ Error getting status: {str(e)}")
            return {'error': str(e)}


def main():
    """Main function to run the scheduled news monitor"""
    try:
        # Initialize the monitor
        monitor = ScheduledNewsMonitor()
        
        # Start the scheduler
        if monitor.start_scheduler():
            logger.info("🎉 Scheduled Malaysia News Monitor is running!")
            logger.info("Press Ctrl+C to stop...")
            
            # Keep the main thread alive
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                logger.info("🛑 Shutting down...")
                monitor.stop_scheduler()
        else:
            logger.error("❌ Failed to start the monitor")
            
    except Exception as e:
        logger.error(f"❌ Fatal error: {str(e)}")


if __name__ == "__main__":
    main()
