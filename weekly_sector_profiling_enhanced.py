"""
Enhanced Weekly Sector Profiling System with MongoDB Storage

This module generates weekly sector profiles by analyzing news documents
from the malaysia_news collection using vector similarity search and LLM summarization.
Enhanced version includes MongoDB storage for sector profiles.

Features:
- Retrieves top-k documents for each sector using similarity search
- Generates sector profiles with risk scores, sentiment, and key drivers
- Outputs structured JSON profiles for each sector
- Stores profiles in MongoDB collection for historical tracking
- Integrates with existing Pinecone/MongoDB infrastructure
"""

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
import numpy as np
from dataclasses import dataclass

# Fix OpenAI compatibility issue with llama-index
try:
    from openai.types.responses import ResponseTextAnnotationDeltaEvent
except ImportError:
    # Use ResponseTextDeltaEvent as fallback since ResponseTextAnnotationDeltaEvent doesn't exist
    from openai.types.responses import ResponseTextDeltaEvent
    ResponseTextAnnotationDeltaEvent = ResponseTextDeltaEvent
    
    # Add it to the openai module for compatibility
    import openai
    if not hasattr(openai.types.responses, 'ResponseTextAnnotationDeltaEvent'):
        openai.types.responses.ResponseTextAnnotationDeltaEvent = ResponseTextAnnotationDeltaEvent

# Import existing system components
from pymongo import MongoClient
from bson.objectid import ObjectId
from pinecone import Pinecone
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.llms.openai import OpenAI
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@dataclass
class SectorProfile:
    """Data class for sector profile structure"""
    sector: str
    week: str
    risk_score: float
    sentiment: str
    drivers: List[str]
    sources: List[str]

class WeeklySectorProfiler:
    """
    Enhanced Weekly Sector Profiling System with MongoDB Storage
    
    Generates comprehensive sector profiles by analyzing news documents
    using vector similarity search and LLM-based summarization.
    Stores profiles in MongoDB for historical tracking and analysis.
    """
    
    def __init__(self):
        """Initialize the sector profiler with database connections and models"""
        self.setup_connections()
        self.setup_models()
        self.load_sector_data()
        
    def setup_connections(self):
        """Setup MongoDB and Pinecone connections"""
        try:
            # MongoDB connection
            self.mongo_client = MongoClient(os.getenv('MONGODB_URI'))
            self.db = self.mongo_client[os.getenv('MONGODB_DB_NAME', 'fyp_analysis')]
            self.collection = self.db['malaysia_news']
            
            # Pinecone connection
            pc = Pinecone(api_key=os.getenv('PINECONE_API_KEY'))
            self.pinecone_index = pc.Index(os.getenv('PINECONE_INDEX_NAME', 'stock-analysis'))
            
            logger.info("Database connections established successfully")
            
        except Exception as e:
            logger.error(f"Error setting up database connections: {e}")
            raise
    
    def setup_models(self):
        """Setup OpenAI embedding and LLM models"""
        try:
            self.embed_model = OpenAIEmbedding(
                model='text-embedding-3-small',
                api_key=os.getenv('OPENAI_API_KEY')
            )
            
            self.llm = OpenAI(
                model='gpt-4o-mini',
                api_key=os.getenv('OPENAI_API_KEY'),
                temperature=0.1,
                max_tokens=2000
            )
            
            logger.info("AI models initialized successfully")
            
        except Exception as e:
            logger.error(f"Error setting up AI models: {e}")
            raise
    
    def load_sector_data(self):
        """Load sector and industry data from JSON file"""
        try:
            with open('sector_industries.json', 'r') as f:
                self.sectors_data = json.load(f)
            
            # Create sector mapping for easy lookup
            self.sector_mapping = {}
            for sector_info in self.sectors_data:
                sector_name = sector_info['sector']
                industries = sector_info['industries']
                self.sector_mapping[sector_name] = industries
                
            logger.info(f"Loaded {len(self.sector_mapping)} sectors with industries")
            
        except Exception as e:
            logger.error(f"Error loading sector data: {e}")
            raise
    
    def generate_sector_queries(self, sector: str, industries: List[str]) -> List[str]:
        """
        Generate search queries for a specific sector based on its industries
        
        Args:
            sector: Sector name (e.g., 'financial-services')
            industries: List of industries in the sector
            
        Returns:
            List of search queries for the sector
        """
        # Convert sector name to readable format
        sector_readable = sector.replace('-', ' ').title()
        
        # Base sector queries
        base_queries = [
            f"{sector_readable} sector news Malaysia",
            f"{sector_readable} industry developments Malaysia",
            f"{sector_readable} market trends Malaysia",
            f"{sector_readable} policy impact Malaysia"
        ]
        
        # Industry-specific queries (sample top industries to avoid too many queries)
        industry_queries = []
        for industry in industries[:3]:  # Limit to top 3 industries per sector
            industry_readable = industry.replace('-', ' ').title()
            industry_queries.extend([
                f"{industry_readable} Malaysia news",
                f"{industry_readable} market update Malaysia"
            ])
        
        return base_queries + industry_queries
    
    def search_documents_for_sector(self, sector: str, industries: List[str], 
                                  top_k: int = 20, days_back: int = 7) -> List[Dict[str, Any]]:
        """
        Search for relevant documents for a specific sector
        
        Args:
            sector: Sector name
            industries: List of industries in the sector
            top_k: Number of top documents to retrieve per query
            days_back: Number of days to look back for recent news
            
        Returns:
            List of relevant documents with metadata
        """
        try:
            # Generate search queries for the sector
            queries = self.generate_sector_queries(sector, industries)
            
            all_documents = []
            seen_doc_ids = set()
            
            # Calculate date filter for recent news
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_back)
            
            for query in queries:
                try:
                    # Get query embedding
                    query_embedding = self.embed_model.get_text_embedding(query)
                    
                    # Search Pinecone
                    search_results = self.pinecone_index.query(
                        vector=query_embedding,
                        top_k=top_k,
                        include_metadata=True,
                        filter={"type": "news_article"}  # Filter for news articles
                    )
                    
                    # Extract MongoDB IDs
                    mongo_ids = []
                    for match in search_results.get('matches', []):
                        mongo_id = match.get('metadata', {}).get('mongo_id')
                        if mongo_id and mongo_id not in seen_doc_ids:
                            mongo_ids.append(ObjectId(mongo_id))
                            seen_doc_ids.add(mongo_id)
                    
                    if mongo_ids:
                        # Fetch documents from MongoDB
                        docs = list(self.collection.find({
                            "_id": {"$in": mongo_ids}
                        }))
                        
                        # Filter by date if published_time is available
                        for doc in docs:
                            # Add similarity score from Pinecone
                            for match in search_results.get('matches', []):
                                if match.get('metadata', {}).get('mongo_id') == str(doc['_id']):
                                    doc['similarity_score'] = match.get('score', 0.0)
                                    break
                            
                            # Check if document is recent enough
                            if 'published_time' in doc.get('raw_data', {}):
                                try:
                                    pub_time = datetime.fromisoformat(
                                        doc['raw_data']['published_time'].replace('Z', '+00:00')
                                    )
                                    if pub_time >= cutoff_date:
                                        all_documents.append(doc)
                                except:
                                    # If date parsing fails, include the document
                                    all_documents.append(doc)
                            else:
                                # If no date info, include the document
                                all_documents.append(doc)
                    
                except Exception as e:
                    logger.warning(f"Error searching for query '{query}': {e}")
                    continue
            
            # Sort by similarity score and remove duplicates
            unique_docs = {}
            for doc in all_documents:
                doc_id = str(doc['_id'])
                if doc_id not in unique_docs or doc.get('similarity_score', 0) > unique_docs[doc_id].get('similarity_score', 0):
                    unique_docs[doc_id] = doc
            
            sorted_docs = sorted(
                unique_docs.values(),
                key=lambda x: x.get('similarity_score', 0),
                reverse=True
            )
            
            logger.info(f"Found {len(sorted_docs)} relevant documents for sector '{sector}'")
            return sorted_docs[:top_k]  # Return top documents
            
        except Exception as e:
            logger.error(f"Error searching documents for sector '{sector}': {e}")
            return []
    
    def extract_document_content(self, doc: Dict[str, Any]) -> str:
        """
        Extract readable content from a document
        
        Args:
            doc: Document from MongoDB
            
        Returns:
            Extracted content string
        """
        content_parts = []
        
        # Try different content fields
        if 'chunk_text' in doc:
            content_parts.append(doc['chunk_text'])
        elif 'ai_summary' in doc:
            content_parts.append(doc['ai_summary'])
        elif 'content' in doc:
            content_parts.append(doc['content'])
        
        # Add raw data content if available
        raw_data = doc.get('raw_data', {})
        if isinstance(raw_data, dict):
            if 'title' in raw_data:
                content_parts.append(f"Title: {raw_data['title']}")
            if 'content' in raw_data:
                content_parts.append(f"Content: {raw_data['content']}")
            if 'summary' in raw_data:
                content_parts.append(f"Summary: {raw_data['summary']}")
        
        return "\n\n".join(content_parts) if content_parts else "No content available"
    
    def generate_sector_profile(self, sector: str, documents: List[Dict[str, Any]]) -> SectorProfile:
        """
        Generate a sector profile using LLM analysis
        
        Args:
            sector: Sector name
            documents: List of relevant documents
            
        Returns:
            SectorProfile object with analysis results
        """
        try:
            if not documents:
                logger.warning(f"No documents available for sector '{sector}'")
                return SectorProfile(
                    sector=sector.replace('-', ' ').title(),
                    week=datetime.now().strftime("%Y-%m-%d"),
                    risk_score=0.5,
                    sentiment="Neutral",
                    drivers=["No recent news available"],
                    sources=[]
                )
            
            # Prepare document content for analysis
            doc_contents = []
            source_ids = []
            
            for i, doc in enumerate(documents[:10]):  # Limit to top 10 documents
                content = self.extract_document_content(doc)
                if content and content != "No content available":
                    doc_contents.append(f"Document {i+1}:\n{content}")
                    source_ids.append(f"doc_{str(doc['_id'])}_chunk_{i+1}")
            
            if not doc_contents:
                logger.warning(f"No valid content found for sector '{sector}'")
                return SectorProfile(
                    sector=sector.replace('-', ' ').title(),
                    week=datetime.now().strftime("%Y-%m-%d"),
                    risk_score=0.5,
                    sentiment="Neutral",
                    drivers=["No analyzable content available"],
                    sources=[]
                )
            
            # Combine all document content
            combined_content = "\n\n---\n\n".join(doc_contents)
            
            # Create analysis prompt
            sector_readable = sector.replace('-', ' ').title()
            analysis_prompt = f"""
You are a financial analyst specializing in sector analysis. Analyze the following news documents related to the {sector_readable} sector in Malaysia and provide a comprehensive sector profile.

NEWS DOCUMENTS:
{combined_content}

Please provide your analysis in the following JSON format:
{{
    "risk_score": <float between 0.0 and 1.0, where 0.0 is very low risk and 1.0 is very high risk>,
    "sentiment": "<Overall sentiment: Very Positive, Positive, Mixed (slightly positive), Neutral, Mixed (slightly negative), Negative, or Very Negative>",
    "drivers": [
        "<Key driver 1 - specific event, policy, or trend affecting the sector>",
        "<Key driver 2 - specific event, policy, or trend affecting the sector>",
        "<Key driver 3 - specific event, policy, or trend affecting the sector>"
    ]
}}

ANALYSIS GUIDELINES:
1. Risk Score: Consider regulatory changes, market volatility, economic indicators, and sector-specific challenges
2. Sentiment: Assess overall market sentiment based on news tone, market reactions, and future outlook
3. Drivers: Identify 3-5 specific, actionable factors currently influencing the sector (policies, market trends, economic events, etc.)

Focus on Malaysian market context and recent developments. Be specific and avoid generic statements.
"""
            
            # Get LLM analysis
            response = self.llm.complete(analysis_prompt)
            response_text = response.text.strip()
            
            # Parse JSON response
            try:
                # Extract JSON from response (handle cases where LLM adds extra text)
                json_start = response_text.find('{')
                json_end = response_text.rfind('}') + 1
                if json_start >= 0 and json_end > json_start:
                    json_str = response_text[json_start:json_end]
                    analysis_result = json.loads(json_str)
                else:
                    raise ValueError("No valid JSON found in response")
                
                # Create sector profile
                profile = SectorProfile(
                    sector=sector_readable,
                    week=datetime.now().strftime("%Y-%m-%d"),
                    risk_score=float(analysis_result.get('risk_score', 0.5)),
                    sentiment=analysis_result.get('sentiment', 'Neutral'),
                    drivers=analysis_result.get('drivers', ['Analysis unavailable']),
                    sources=source_ids
                )
                
                logger.info(f"Generated profile for sector '{sector}' with risk score {profile.risk_score}")
                return profile
                
            except (json.JSONDecodeError, ValueError, KeyError) as e:
                logger.error(f"Error parsing LLM response for sector '{sector}': {e}")
                logger.debug(f"Raw LLM response: {response_text}")
                
                # Fallback profile
                return SectorProfile(
                    sector=sector_readable,
                    week=datetime.now().strftime("%Y-%m-%d"),
                    risk_score=0.5,
                    sentiment="Analysis Error",
                    drivers=["Unable to analyze due to parsing error"],
                    sources=source_ids
                )
                
        except Exception as e:
            logger.error(f"Error generating sector profile for '{sector}': {e}")
            return SectorProfile(
                sector=sector.replace('-', ' ').title(),
                week=datetime.now().strftime("%Y-%m-%d"),
                risk_score=0.5,
                sentiment="Error",
                drivers=[f"Analysis failed: {str(e)}"],
                sources=[]
            )
    
    def generate_weekly_profiles(self, sectors: Optional[List[str]] = None, 
                               top_k_docs: int = 15, days_back: int = 7) -> Dict[str, Dict[str, Any]]:
        """
        Generate weekly profiles for all sectors or specified sectors
        
        Args:
            sectors: List of specific sectors to analyze (None for all sectors)
            top_k_docs: Number of top documents to retrieve per sector
            days_back: Number of days to look back for recent news
            
        Returns:
            Dictionary of sector profiles
        """
        try:
            # Use all sectors if none specified
            if sectors is None:
                sectors = list(self.sector_mapping.keys())
            
            profiles = {}
            
            logger.info(f"Starting weekly sector profiling for {len(sectors)} sectors")
            
            for sector in sectors:
                logger.info(f"Processing sector: {sector}")
                
                # Get industries for this sector
                industries = self.sector_mapping.get(sector, [])
                
                # Search for relevant documents
                documents = self.search_documents_for_sector(
                    sector, industries, top_k_docs, days_back
                )
                
                # Generate sector profile
                profile = self.generate_sector_profile(sector, documents)
                
                # Convert to dictionary format
                profiles[sector] = {
                    "sector": profile.sector,
                    "week": profile.week,
                    "risk_score": profile.risk_score,
                    "sentiment": profile.sentiment,
                    "drivers": profile.drivers,
                    "sources": profile.sources,
                    "document_count": len(documents),
                    "generated_at": datetime.now(timezone.utc).isoformat()
                }
                
                logger.info(f"Completed profile for sector '{sector}': Risk={profile.risk_score:.2f}, Sentiment={profile.sentiment}")
            
            logger.info(f"Weekly sector profiling completed for {len(profiles)} sectors")
            return profiles
            
        except Exception as e:
            logger.error(f"Error generating weekly profiles: {e}")
            return {}
    
    def save_profiles_to_mongodb(self, profiles: Dict[str, Dict[str, Any]]) -> str:
        """
        Save sector profiles to MongoDB collection
        
        Args:
            profiles: Dictionary of sector profiles
            
        Returns:
            MongoDB document ID of the saved weekly report
        """
        try:
            # Prepare document for MongoDB
            weekly_report = {
                "type": "weekly_sector_profiles",
                "generated_at": datetime.now(timezone.utc),
                "week_ending": datetime.now().strftime("%Y-%m-%d"),
                "total_sectors": len(profiles),
                "system_version": "1.0",
                "profiles": profiles,
                "created_at": datetime.now(timezone.utc)
            }
            
            # Insert into MongoDB collection: weekly_sector_profiles
            result = self.db['weekly_sector_profiles'].insert_one(weekly_report)
            document_id = str(result.inserted_id)
            
            logger.info(f"Weekly sector profiles saved to MongoDB collection 'weekly_sector_profiles' with ID: {document_id}")
            return document_id
            
        except Exception as e:
            logger.error(f"Error saving profiles to MongoDB: {e}")
            raise
    
    def save_profiles_to_file(self, profiles: Dict[str, Dict[str, Any]], 
                            filename: Optional[str] = None) -> str:
        """
        Save sector profiles to JSON file
        
        Args:
            profiles: Dictionary of sector profiles
            filename: Output filename (auto-generated if None)
            
        Returns:
            Path to saved file
        """
        try:
            if filename is None:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"weekly_sector_profiles_{timestamp}.json"
            
            # Add metadata
            output_data = {
                "metadata": {
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "total_sectors": len(profiles),
                    "week_ending": datetime.now().strftime("%Y-%m-%d"),
                    "system_version": "1.0"
                },
                "profiles": profiles
            }
            
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(output_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Sector profiles saved to: {filename}")
            return filename
            
        except Exception as e:
            logger.error(f"Error saving profiles to file: {e}")
            raise
    
    def save_profiles(self, profiles: Dict[str, Dict[str, Any]], 
                     save_to_mongodb: bool = True, 
                     save_to_file: bool = True,
                     filename: Optional[str] = None) -> Dict[str, str]:
        """
        Save sector profiles to both MongoDB and file (optional)
        
        Args:
            profiles: Dictionary of sector profiles
            save_to_mongodb: Whether to save to MongoDB
            save_to_file: Whether to save to file
            filename: Output filename (auto-generated if None)
            
        Returns:
            Dictionary with 'mongodb_id' and/or 'filename' keys
        """
        results = {}
        
        try:
            if save_to_mongodb:
                mongodb_id = self.save_profiles_to_mongodb(profiles)
                results['mongodb_id'] = mongodb_id
            
            if save_to_file:
                filename = self.save_profiles_to_file(profiles, filename)
                results['filename'] = filename
            
            return results
            
        except Exception as e:
            logger.error(f"Error saving profiles: {e}")
            raise
    
    def get_historical_profiles(self, weeks_back: int = 4) -> List[Dict[str, Any]]:
        """
        Retrieve historical sector profiles from MongoDB
        
        Args:
            weeks_back: Number of weeks to look back
            
        Returns:
            List of historical weekly reports
        """
        try:
            # Calculate cutoff date
            cutoff_date = datetime.now(timezone.utc) - timedelta(weeks=weeks_back)
            
            # Query MongoDB for historical profiles
            historical_profiles = list(self.db['weekly_sector_profiles'].find({
                "type": "weekly_sector_profiles",
                "generated_at": {"$gte": cutoff_date}
            }).sort("generated_at", -1))
            
            logger.info(f"Retrieved {len(historical_profiles)} historical profiles from MongoDB")
            return historical_profiles
            
        except Exception as e:
            logger.error(f"Error retrieving historical profiles: {e}")
            return []
    
    def get_sector_trends(self, sector: str, weeks_back: int = 8) -> Dict[str, Any]:
        """
        Analyze trends for a specific sector over time
        
        Args:
            sector: Sector name to analyze
            weeks_back: Number of weeks to analyze
            
        Returns:
            Dictionary with trend analysis
        """
        try:
            # Get historical profiles
            historical_profiles = self.get_historical_profiles(weeks_back)
            
            if not historical_profiles:
                return {"error": "No historical data available"}
            
            # Extract sector data over time
            sector_data = []
            for report in historical_profiles:
                if sector in report.get('profiles', {}):
                    profile = report['profiles'][sector]
                    sector_data.append({
                        "week": profile.get('week'),
                        "risk_score": profile.get('risk_score'),
                        "sentiment": profile.get('sentiment'),
                        "generated_at": report.get('generated_at')
                    })
            
            if not sector_data:
                return {"error": f"No data found for sector '{sector}'"}
            
            # Calculate trends
            risk_scores = [d['risk_score'] for d in sector_data if d['risk_score'] is not None]
            
            trends = {
                "sector": sector,
                "period_weeks": len(sector_data),
                "current_risk_score": risk_scores[0] if risk_scores else None,
                "average_risk_score": sum(risk_scores) / len(risk_scores) if risk_scores else None,
                "risk_trend": "increasing" if len(risk_scores) > 1 and risk_scores[0] > risk_scores[-1] else "decreasing" if len(risk_scores) > 1 else "stable",
                "recent_sentiment": sector_data[0]['sentiment'] if sector_data else None,
                "data_points": sector_data
            }
            
            logger.info(f"Generated trend analysis for sector '{sector}' over {len(sector_data)} weeks")
            return trends
            
        except Exception as e:
            logger.error(f"Error analyzing trends for sector '{sector}': {e}")
            return {"error": str(e)}

def main():
    """Main function to run weekly sector profiling with MongoDB storage"""
    try:
        # Initialize profiler
        profiler = WeeklySectorProfiler()
        
        # Generate profiles for all sectors
        logger.info("Starting weekly sector profiling...")
        profiles = profiler.generate_weekly_profiles()
        
        if profiles:
            # Save to both MongoDB and file
            results = profiler.save_profiles(profiles, save_to_mongodb=True, save_to_file=True)
            
            # Print summary
            print(f"\n=== Weekly Sector Profiling Complete ===")
            print(f"Profiles generated: {len(profiles)}")
            print(f"MongoDB ID: {results.get('mongodb_id', 'Not saved')}")
            print(f"Output file: {results.get('filename', 'Not saved')}")
            print(f"\nSector Summary:")
            
            for sector, profile in profiles.items():
                print(f"  {profile['sector']}: Risk={profile['risk_score']:.2f}, "
                      f"Sentiment={profile['sentiment']}, Docs={profile['document_count']}")
        else:
            print("No profiles generated. Check logs for errors.")
            
    except Exception as e:
        logger.error(f"Error in main execution: {e}")
        raise

if __name__ == "__main__":
    main()
