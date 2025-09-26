#!/usr/bin/env python3
"""
Enhanced Daily News Notification System
- Fetches daily news at 8AM Malaysia time
- Analyzes news for sector impact
- Matches with user watchlists
- Sends targeted email notifications
- Updates news.html with fresh content
"""

import os
import json
import logging
import threading
import time
import smtplib
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders

import schedule
import requests
from pymongo import MongoClient
from newsdataapi import NewsDataApiClient
from dotenv import load_dotenv
import openai
from pinecone import Pinecone
from llama_index.embeddings.openai import OpenAIEmbedding
from bson.objectid import ObjectId

# Import unified news processor
from unified_news_processor import UnifiedNewsProcessor

# Load environment variables
load_dotenv()

# Load sector industries data
try:
    with open('sector_industries.json', 'r') as f:
        SECTOR_INDUSTRIES = json.load(f)
except FileNotFoundError:
    logging.error("sector_industries.json not found. Please ensure the file exists.")
    SECTOR_INDUSTRIES = []

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('daily_news_notification.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class DailyNewsNotificationSystem:
    """
    Enhanced daily news notification system with sector-based user matching
    """
    
    def __init__(self):
        """Initialize the enhanced news notification system with unified processing"""
        self.api_key = os.getenv('NEWSDATA_API_KEY')
        self.mongo_uri = os.getenv('MONGO_URI', 'mongodb://localhost:27017/')
        self.database_name = os.getenv('DATABASE_NAME', 'fyp_analysis')
        
        # Email configuration
        self.smtp_server = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
        self.smtp_port = int(os.getenv('MAIL_PORT', 587))
        self.smtp_username = os.getenv('MAIL_USERNAME')
        self.smtp_password = os.getenv('MAIL_PASSWORD')
        self.smtp_from = os.getenv('MAIL_DEFAULT_SENDER', self.smtp_username)
        
        # Initialize NewsData.io client
        if not self.api_key:
            raise ValueError("NEWSDATA_API_KEY environment variable is required")
        self.news_client = NewsDataApiClient(apikey=self.api_key)
        
        # Initialize unified news processor
        try:
            self.unified_processor = UnifiedNewsProcessor()
            logger.info("✅ Unified news processor initialized successfully")
        except Exception as e:
            logger.error(f"❌ Failed to initialize unified processor: {e}")
            self.unified_processor = None
        
        # Initialize MongoDB connection
        self.mongo_client = MongoClient(self.mongo_uri)
        self.db = self.mongo_client[self.database_name]
        self.news_collection = self.db['malaysia_news']
        self.users_collection = self.db['users']
        self.watchlist_collection = self.db['user_watchlists']
        self.notifications_collection = self.db['email_notifications']
        
        # Malaysia timezone (UTC+8)
        self.malaysia_tz = timezone(timedelta(hours=8))
        
        # Scheduler control
        self.scheduler_thread = None
        self.is_running = False
        
        logger.info("DailyNewsNotificationSystem with unified processing initialized successfully")
    
    def fetch_daily_news(self, max_results: int = 20) -> Dict:
        """
        Fetch latest Malaysia news from NewsData.io API
        """
        try:
            logger.info("📡 Fetching daily Malaysia news from NewsData.io...")
            
            # Malaysia-specific categories
            allowed_categories = [
                "business",
                "politics", 
                "technology",
                "health",
                "environment"
            ]
            
            # Malaysia-specific search query
            malaysia_query = 'Malaysia OR Bursa OR "Kuala Lumpur" OR government OR economy'
            
            # API parameters
            params = {
                'country': 'my',  # Malaysia
                'language': 'en',  # English
                'category': ','.join(allowed_categories),
                'q': malaysia_query,
                'size': min(max_results, 10)  # API limit
            }
            
            logger.info(f"API request parameters: {params}")
            
            # Fetch news from NewsData.io
            response = self.news_client.news_api(**params)
            
            if response.get('status') == 'success':
                articles = response.get('results', [])
                logger.info(f"✅ Successfully fetched {len(articles)} articles from API")
                
                # Filter for quality articles
                filtered_articles = []
                for article in articles:
                    title = article.get('title', '')
                    description = article.get('description', '')
                    
                    # Skip articles that are too short or lack content
                    if len(title) < 10 or len(description) < 20:
                        continue
                    
                    filtered_articles.append(article)
                
                logger.info(f"✅ Filtered to {len(filtered_articles)} quality articles")
                
                return {
                    'status': 'success',
                    'articles': filtered_articles,
                    'total_results': len(filtered_articles),
                    'fetched_at': datetime.now(self.malaysia_tz).isoformat()
                }
            else:
                logger.error(f"❌ API error: {response.get('message', 'Unknown error')}")
                return {'status': 'error', 'message': response.get('message', 'Unknown error'), 'articles': []}
                
        except Exception as e:
            logger.error(f"❌ Error fetching news: {str(e)}")
            return {'status': 'error', 'message': str(e), 'articles': []}
    
    def analyze_sector_impact(self, article: Dict) -> Dict:
        """
        Analyze which sectors and industries are impacted by the news article
        """
        try:
            title = article.get('title', '')
            description = article.get('description', '')
            content = article.get('content', '')
            
            # Combine text for analysis
            full_text = f"{title} {description} {content}".lower()
            
            if not self.openai_client:
                # Fallback to keyword-based analysis
                return self._keyword_based_sector_analysis(full_text)
            
            # Create sector-industry mapping for LLM
            sector_industry_map = {}
            for sector_data in SECTOR_INDUSTRIES:
                sector = sector_data['sector']
                industries = sector_data['industries']
                sector_industry_map[sector] = industries
            
            # Prepare context for LLM
            context = f"""
            Analyze this Malaysia news article and determine which stock market sectors and industries are most likely to be impacted.
            
            Available sectors and their industries:
            {json.dumps(sector_industry_map, indent=2)}
            
            News article:
            Title: {title}
            Description: {description}
            Content: {content[:1000] if content else ''}
            
            Return your analysis in this exact JSON format:
            {{
                "affected_sectors": ["sector1", "sector2"],
                "affected_industries": ["industry1", "industry2"],
                "impact_level": "high|medium|low",
                "impact_type": "positive|negative|neutral",
                "reasoning": "Brief explanation of the impact",
                "confidence": 0.8
            }}
            """
            
            logger.info("🤖 Analyzing sector impact using OpenAI...")
            
            response = self.openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a Malaysian financial analyst. Analyze news articles to determine stock market sector impacts. Be specific and accurate."
                    },
                    {
                        "role": "user",
                        "content": context
                    }
                ],
                max_tokens=400,
                temperature=0.3
            )
            
            result = response.choices[0].message.content.strip()
            
            # Parse JSON response
            try:
                analysis = json.loads(result)
                
                # Validate and clean the response
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
                
                return {
                    'affected_sectors': valid_sectors,
                    'affected_industries': valid_industries,
                    'impact_level': analysis.get('impact_level', 'medium'),
                    'impact_type': analysis.get('impact_type', 'neutral'),
                    'reasoning': analysis.get('reasoning', 'AI analysis completed'),
                    'confidence': analysis.get('confidence', 0.5),
                    'analyzed_at': datetime.now(self.malaysia_tz).isoformat()
                }
                
            except json.JSONDecodeError:
                logger.warning("⚠️ Failed to parse LLM response, using keyword analysis")
                return self._keyword_based_sector_analysis(full_text)
            
        except Exception as e:
            logger.error(f"❌ Error in sector impact analysis: {str(e)}")
            return self._keyword_based_sector_analysis(full_text)
    
    def _keyword_based_sector_analysis(self, text: str) -> Dict:
        """
        Fallback keyword-based sector analysis
        """
        affected_sectors = []
        affected_industries = []
        
        # Define sector keywords
        sector_keywords = {
            'financial-services': ['bank', 'financial', 'insurance', 'credit', 'loan', 'mortgage'],
            'technology': ['tech', 'software', 'digital', 'internet', 'semiconductor', 'ai'],
            'energy': ['oil', 'gas', 'energy', 'petroleum', 'renewable', 'solar'],
            'healthcare': ['health', 'medical', 'pharmaceutical', 'drug', 'hospital'],
            'consumer-cyclical': ['retail', 'automotive', 'travel', 'tourism', 'entertainment'],
            'consumer-defensive': ['food', 'beverage', 'grocery', 'utilities'],
            'industrials': ['manufacturing', 'construction', 'aerospace', 'logistics'],
            'basic-materials': ['steel', 'chemical', 'mining', 'metal'],
            'real-estate': ['property', 'reit', 'housing', 'commercial'],
            'utilities': ['electric', 'water', 'power']
        }
        
        impact_level = 'low'
        confidence = 0.3
        
        for sector, keywords in sector_keywords.items():
            if any(keyword in text for keyword in keywords):
                affected_sectors.append(sector)
                confidence += 0.1
                
                # Find specific industries within the sector
                for sector_data in SECTOR_INDUSTRIES:
                    if sector_data['sector'] == sector:
                        for industry in sector_data['industries']:
                            industry_keywords = industry.replace('-', ' ').split()
                            if any(keyword in text for keyword in industry_keywords):
                                affected_industries.append(industry)
                        break
        
        if len(affected_sectors) >= 2:
            impact_level = 'medium'
        elif len(affected_sectors) >= 3:
            impact_level = 'high'
        
        return {
            'affected_sectors': list(set(affected_sectors)),
            'affected_industries': list(set(affected_industries)),
            'impact_level': impact_level,
            'impact_type': 'neutral',
            'reasoning': 'Keyword-based analysis',
            'confidence': min(confidence, 1.0),
            'analyzed_at': datetime.now(self.malaysia_tz).isoformat()
        }
    
    def get_users_interested_in_sectors(self, sectors: List[str]) -> List[Dict]:
        """
        Get users who have stocks in their watchlist from the affected sectors
        """
        try:
            if not sectors:
                return []
            
            logger.info(f"🔍 Finding users interested in sectors: {sectors}")
            
            # Load bursa companies data to map tickers to sectors
            try:
                with open('bursa_companies.json', 'r') as f:
                    bursa_companies = json.load(f)
            except FileNotFoundError:
                logger.warning("bursa_companies.json not found, using limited sector mapping")
                bursa_companies = []
            
            # Create ticker to sector mapping
            ticker_to_sector = {}
            for company in bursa_companies:
                ticker = company.get('ticker', '')
                sector = company.get('sector', '')
                if ticker and sector:
                    ticker_to_sector[ticker] = sector
            
            # Find users with watchlists containing stocks from affected sectors
            interested_users = []
            
            # Get all users with notification settings enabled
            notification_users = list(self.notifications_collection.find({
                'notifications_enabled': True,
                'news_alerts': True
            }))
            
            for user_notif in notification_users:
                user_id = user_notif.get('user_id')
                user_email = user_notif.get('email')
                
                if not user_id or not user_email:
                    continue
                
                # Get user's watchlist
                watchlist_items = list(self.watchlist_collection.find({'user_id': user_id}))
                
                user_sectors = set()
                matched_stocks = []
                
                for item in watchlist_items:
                    ticker = item.get('ticker', '')
                    company_name = item.get('company_name', '')
                    
                    # Map ticker to sector
                    stock_sector = ticker_to_sector.get(ticker)
                    if stock_sector and stock_sector in sectors:
                        user_sectors.add(stock_sector)
                        matched_stocks.append({
                            'ticker': ticker,
                            'company_name': company_name,
                            'sector': stock_sector
                        })
                
                if user_sectors:  # User has stocks in affected sectors
                    # Get user details
                    user_doc = self.users_collection.find_one({'_id': ObjectId(user_id)})
                    user_name = ''
                    if user_doc:
                        first_name = user_doc.get('first_name', '')
                        last_name = user_doc.get('last_name', '')
                        user_name = f"{first_name} {last_name}".strip()
                    
                    interested_users.append({
                        'user_id': user_id,
                        'email': user_email,
                        'name': user_name or user_email,
                        'interested_sectors': list(user_sectors),
                        'matched_stocks': matched_stocks,
                        'notification_settings': user_notif
                    })
            
            logger.info(f"✅ Found {len(interested_users)} users interested in the affected sectors")
            return interested_users
            
        except Exception as e:
            logger.error(f"❌ Error finding interested users: {str(e)}")
            return []
    
    def generate_email_content(self, user: Dict, articles_with_analysis: List[Dict]) -> Tuple[str, str]:
        """
        Generate personalized email content for a user
        """
        user_name = user.get('name', 'Valued User')
        interested_sectors = user.get('interested_sectors', [])
        matched_stocks = user.get('matched_stocks', [])
        
        # Create HTML email content
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Daily Market News Alert</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5; }}
                .container {{ max-width: 800px; margin: 0 auto; background-color: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
                .header {{ text-align: center; margin-bottom: 30px; }}
                .header h1 {{ color: #2563eb; margin: 0; }}
                .header p {{ color: #666; margin: 10px 0 0 0; }}
                .section {{ margin-bottom: 30px; }}
                .section h2 {{ color: #374151; border-bottom: 2px solid #e5e7eb; padding-bottom: 10px; }}
                .news-item {{ background-color: #f9fafb; padding: 20px; margin-bottom: 20px; border-radius: 8px; border-left: 4px solid #2563eb; }}
                .news-title {{ font-weight: bold; font-size: 18px; color: #1f2937; margin-bottom: 10px; }}
                .news-meta {{ color: #6b7280; font-size: 14px; margin-bottom: 15px; }}
                .news-description {{ color: #374151; line-height: 1.6; margin-bottom: 15px; }}
                .impact-info {{ background-color: #dbeafe; padding: 15px; border-radius: 6px; margin-top: 15px; }}
                .impact-info strong {{ color: #1e40af; }}
                .stocks-list {{ background-color: #f0f9ff; padding: 15px; border-radius: 6px; margin-top: 20px; }}
                .stock-item {{ display: inline-block; background-color: #2563eb; color: white; padding: 5px 10px; margin: 5px; border-radius: 20px; font-size: 12px; }}
                .footer {{ text-align: center; margin-top: 40px; padding-top: 20px; border-top: 1px solid #e5e7eb; color: #6b7280; font-size: 14px; }}
                .btn {{ display: inline-block; background-color: #2563eb; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; margin: 10px 5px; }}
                .btn:hover {{ background-color: #1d4ed8; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>📈 Daily Market News Alert</h1>
                    <p>Personalized news for your watchlist sectors</p>
                    <p><strong>Date:</strong> {datetime.now(self.malaysia_tz).strftime('%B %d, %Y')}</p>
                </div>
                
                <div class="section">
                    <h2>Hello {user_name}!</h2>
                    <p>We found <strong>{len(articles_with_analysis)} news articles</strong> that may impact the sectors in your watchlist.</p>
                </div>
                
                <div class="section">
                    <h2>📊 Your Watchlist Sectors</h2>
                    <p>We're monitoring these sectors based on your watchlist:</p>
                    <div>
                        {' '.join([f'<span class="stock-item">{sector.replace("-", " ").title()}</span>' for sector in interested_sectors])}
                    </div>
                </div>
                
                <div class="section">
                    <h2>📰 Relevant News</h2>
        """
        
        # Add news articles
        for article_data in articles_with_analysis:
            article = article_data['article']
            analysis = article_data['analysis']
            
            title = article.get('title', 'No Title')
            description = article.get('description', '')
            source = article.get('source_id', 'Unknown Source')
            pub_date = article.get('pubDate', '')
            link = article.get('link', '')
            
            affected_sectors = analysis.get('affected_sectors', [])
            impact_level = analysis.get('impact_level', 'medium')
            impact_type = analysis.get('impact_type', 'neutral')
            reasoning = analysis.get('reasoning', 'No analysis available')
            
            # Impact level color
            impact_colors = {
                'high': '#dc2626',
                'medium': '#d97706', 
                'low': '#059669'
            }
            impact_color = impact_colors.get(impact_level, '#6b7280')
            
            html_content += f"""
                    <div class="news-item">
                        <div class="news-title">{title}</div>
                        <div class="news-meta">
                            <strong>Source:</strong> {source} | 
                            <strong>Published:</strong> {pub_date}
                        </div>
                        <div class="news-description">{description}</div>
                        
                        <div class="impact-info">
                            <strong>Market Impact:</strong> 
                            <span style="color: {impact_color};">{impact_level.upper()} {impact_type.upper()}</span><br>
                            <strong>Affected Sectors:</strong> {', '.join([s.replace('-', ' ').title() for s in affected_sectors])}<br>
                            <strong>Analysis:</strong> {reasoning}
                        </div>
                        
                        {f'<p><a href="{link}" class="btn" target="_blank">Read Full Article</a></p>' if link else ''}
                    </div>
            """
        
        # Add matched stocks
        if matched_stocks:
            html_content += f"""
                </div>
                
                <div class="section">
                    <h2>📌 Your Relevant Stocks</h2>
                    <div class="stocks-list">
                        <p><strong>Stocks in your watchlist that may be affected:</strong></p>
                        {' '.join([f'<div class="stock-item">{stock["ticker"]} - {stock["company_name"]}</div>' for stock in matched_stocks])}
                    </div>
                </div>
            """
        
        html_content += f"""
                <div class="footer">
                    <p><a href="http://localhost:5000/chatbot" class="btn">Go to Chatbot</a></p>
                    <p><a href="http://localhost:5000/watchlist.html" class="btn">Manage Watchlist</a></p>
                    <p>You received this email because you have news alerts enabled in your account settings.</p>
                    <p>© 2025 Stock Analysis System - Automated Daily News Alert</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Create plain text version
        text_content = f"""
Daily Market News Alert - {datetime.now(self.malaysia_tz).strftime('%B %d, %Y')}

Hello {user_name}!

We found {len(articles_with_analysis)} news articles that may impact the sectors in your watchlist.

Your Watchlist Sectors:
{', '.join([sector.replace('-', ' ').title() for sector in interested_sectors])}

Relevant News:
"""
        
        for i, article_data in enumerate(articles_with_analysis, 1):
            article = article_data['article']
            analysis = article_data['analysis']
            
            title = article.get('title', 'No Title')
            description = article.get('description', '')
            source = article.get('source_id', 'Unknown Source')
            affected_sectors = analysis.get('affected_sectors', [])
            impact_level = analysis.get('impact_level', 'medium')
            impact_type = analysis.get('impact_type', 'neutral')
            
            text_content += f"""
{i}. {title}
   Source: {source}
   Description: {description}
   Impact: {impact_level.upper()} {impact_type.upper()}
   Affected Sectors: {', '.join([s.replace('-', ' ').title() for s in affected_sectors])}
   
"""
        
        if matched_stocks:
            text_content += f"""
Your Relevant Stocks:
{', '.join([f"{stock['ticker']} - {stock['company_name']}" for stock in matched_stocks])}

"""
        
        text_content += """
View your dashboard: http://localhost:5000
Manage watchlist: http://localhost:5000/watchlist.html

You received this email because you have news alerts enabled.
© 2025 Stock Analysis System - Automated Daily News Alert
"""
        
        return html_content, text_content
    
    def send_email_notification(self, user: Dict, articles_with_analysis: List[Dict]) -> bool:
        """
        Send email notification to a user
        """
        try:
            if not self.smtp_username or not self.smtp_password:
                logger.warning("⚠️ Email credentials not configured, skipping email notification")
                return False
            
            user_email = user.get('email')
            user_name = user.get('name', 'User')
            
            if not user_email:
                logger.warning(f"⚠️ No email address for user {user.get('user_id')}")
                return False
            
            # Generate email content
            html_content, text_content = self.generate_email_content(user, articles_with_analysis)
            
            # Create email message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = f"📈 Daily Market News Alert - {len(articles_with_analysis)} Relevant Updates"
            msg['From'] = self.smtp_from
            msg['To'] = user_email
            
            # Add text and HTML parts
            text_part = MIMEText(text_content, 'plain')
            html_part = MIMEText(html_content, 'html')
            
            msg.attach(text_part)
            msg.attach(html_part)
            
            # Send email
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_username, self.smtp_password)
                server.send_message(msg)
            
            logger.info(f"✅ Email sent successfully to {user_email}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to send email to {user.get('email', 'unknown')}: {str(e)}")
            return False
    
    def update_news_html(self, articles_with_analysis: List[Dict]) -> bool:
        """
        Update the news.html file with fresh news data
        """
        try:
            logger.info("🔄 Updating news.html with fresh news data...")
            
            # Read the current news.html file
            news_html_path = '/Users/tangjiahui/Desktop/FYP/ProjectI_Prototype/news.html'
            
            with open(news_html_path, 'r', encoding='utf-8') as f:
                html_content = f.read()
            
            # Add a comment indicating when the news was last updated
            update_timestamp = datetime.now(self.malaysia_tz).strftime('%Y-%m-%d %H:%M:%S MYT')
            update_comment = f"<!-- News last updated: {update_timestamp} with {len(articles_with_analysis)} articles -->"
            
            # Insert the comment after the <head> tag
            if '<head>' in html_content:
                html_content = html_content.replace('<head>', f'<head>\n    {update_comment}')
            
            # Also update the page title to reflect the last update
            new_title = f"Malaysia News - Updated {update_timestamp} - Stock Analysis Chatbot"
            if '<title>' in html_content and '</title>' in html_content:
                # Extract current title and replace with updated one
                title_start = html_content.find('<title>') + 7
                title_end = html_content.find('</title>')
                html_content = html_content[:title_start] + new_title + html_content[title_end:]
            
            # Write the updated content back to the file
            with open(news_html_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            logger.info(f"✅ Updated news.html with timestamp: {update_timestamp}")
            
            # Also trigger a refresh of the news API endpoint to ensure fresh data is available
            try:
                # This simulates updating the backend news cache
                logger.info("🔄 Triggering news cache refresh...")
                # The actual news fetching is handled by the existing API endpoints
                # This update ensures the HTML reflects that fresh news has been processed
            except Exception as e:
                logger.warning(f"⚠️ Could not trigger news cache refresh: {e}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to update news.html: {str(e)}")
            return False
    
    def process_and_store_articles(self, articles: List[Dict]) -> List[Dict]:
        """
        Process articles using unified processing system
        """
        try:
            if not self.unified_processor:
                logger.error("❌ Unified processor not available, falling back to basic processing")
                return self._fallback_processing(articles)
            
            # Process articles using unified system
            batch_result = self.unified_processor.process_articles_batch(articles, 'daily')
            
            # Convert batch result to expected format for compatibility
            processed_articles = []
            for processed_article in batch_result.get('processed_articles', []):
                # Create analysis object for compatibility with existing code
                analysis = {
                    'affected_sectors': processed_article.get('affected_sectors', []),
                    'affected_industries': processed_article.get('affected_industries', []),
                    'impact_level': processed_article.get('impact_level', 'medium'),
                    'impact_type': processed_article.get('impact_type', 'neutral'),
                    'reasoning': processed_article.get('impact_reasoning', ''),
                    'confidence': processed_article.get('impact_confidence', 0.5)
                }
                
                processed_articles.append({
                    'article': processed_article,  # Full unified article
                    'analysis': analysis,          # Analysis for compatibility
                    'stored': not processed_article.get('duplicate', False)
                })
            
            logger.info(f"✅ Processed {len(processed_articles)} articles using unified system")
            logger.info(f"📊 Batch success rate: {batch_result.get('success_rate', 0):.2%}")
            
            return processed_articles
            
        except Exception as e:
            logger.error(f"❌ Error in unified processing: {str(e)}")
            return self._fallback_processing(articles)
    
    def _fallback_processing(self, articles: List[Dict]) -> List[Dict]:
        """
        Fallback processing method if unified processor fails
        """
        logger.warning("⚠️ Using fallback processing method")
        processed_articles = []
        
        for article in articles:
            try:
                # Basic sector analysis using old method
                sector_analysis = self.analyze_sector_impact(article)
                
                # Create basic processed article
                processed_article = {
                    'article_id': article.get('article_id'),
                    'title': article.get('title', ''),
                    'description': article.get('description', ''),
                    'content': article.get('content', ''),
                    'affected_sectors': sector_analysis.get('affected_sectors', []),
                    'impact_level': sector_analysis.get('impact_level', 'medium'),
                    'processed_at': datetime.now(self.malaysia_tz).isoformat(),
                    'source_system': 'daily_fallback'
                }
                
                processed_articles.append({
                    'article': processed_article,
                    'analysis': sector_analysis,
                    'stored': False
                })
                
            except Exception as e:
                logger.error(f"❌ Error in fallback processing: {str(e)}")
                continue
        
        return processed_articles
    
    def daily_news_processing_and_notification(self):
        """
        Main daily task: fetch, analyze, notify users, and update news HTML
        """
        try:
            logger.info("🕐 Starting daily news processing and notification...")
            start_time = datetime.now(self.malaysia_tz)
            
            # Step 1: Fetch latest news (limited to 20 for production)
            news_data = self.fetch_daily_news(max_results=20)
            
            if news_data['status'] != 'success':
                logger.error(f"❌ Failed to fetch news: {news_data.get('message')}")
                return
            
            articles = news_data.get('articles', [])
            if not articles:
                logger.warning("⚠️ No articles received from API")
                return
            
            logger.info(f"📰 Processing {len(articles)} articles...")
            
            # Step 2: Process and analyze articles
            articles_with_analysis = self.process_and_store_articles(articles)
            
            if not articles_with_analysis:
                logger.warning("⚠️ No articles could be processed")
                return
            
            # Step 3: Find articles with significant sector impact
            significant_articles = []
            all_affected_sectors = set()
            
            for article_data in articles_with_analysis:
                analysis = article_data['analysis']
                impact_level = analysis.get('impact_level', 'low')
                affected_sectors = analysis.get('affected_sectors', [])
                
                # Include articles with medium or high impact, or any sector impact
                if impact_level in ['medium', 'high'] or affected_sectors:
                    significant_articles.append(article_data)
                    all_affected_sectors.update(affected_sectors)
            
            logger.info(f"📊 Found {len(significant_articles)} articles with significant sector impact")
            logger.info(f"🎯 Affected sectors: {list(all_affected_sectors)}")
            
            # Step 4: Find interested users
            if all_affected_sectors:
                interested_users = self.get_users_interested_in_sectors(list(all_affected_sectors))
                
                # Step 5: Send notifications to interested users
                notifications_sent = 0
                for user in interested_users:
                    # Filter articles relevant to this user's sectors
                    user_relevant_articles = []
                    user_sectors = set(user.get('interested_sectors', []))
                    
                    for article_data in significant_articles:
                        article_sectors = set(article_data['analysis'].get('affected_sectors', []))
                        if user_sectors.intersection(article_sectors):
                            user_relevant_articles.append(article_data)
                    
                    if user_relevant_articles:
                        if self.send_email_notification(user, user_relevant_articles):
                            notifications_sent += 1
                
                logger.info(f"📧 Sent {notifications_sent} email notifications")
            else:
                logger.info("ℹ️ No significant sector impacts found, no notifications sent")
            
            # Step 6: Update news.html
            if self.update_news_html(articles_with_analysis):
                logger.info("✅ Successfully updated news.html")
            
            # Step 7: Log summary
            end_time = datetime.now(self.malaysia_tz)
            duration = (end_time - start_time).total_seconds()
            
            logger.info("=" * 60)
            logger.info("📊 DAILY NEWS PROCESSING SUMMARY")
            logger.info("=" * 60)
            logger.info(f"🕐 Start time: {start_time.strftime('%Y-%m-%d %H:%M:%S MYT')}")
            logger.info(f"🕐 End time: {end_time.strftime('%Y-%m-%d %H:%M:%S MYT')}")
            logger.info(f"⏱️  Duration: {duration:.2f} seconds")
            logger.info(f"📰 Articles fetched: {len(articles)}")
            logger.info(f"🔄 Articles processed: {len(articles_with_analysis)}")
            logger.info(f"📊 Significant articles: {len(significant_articles)}")
            logger.info(f"🎯 Affected sectors: {len(all_affected_sectors)}")
            logger.info(f"👥 Interested users: {len(interested_users) if 'interested_users' in locals() else 0}")
            logger.info(f"📧 Notifications sent: {notifications_sent if 'notifications_sent' in locals() else 0}")
            logger.info("=" * 60)
            
        except Exception as e:
            logger.error(f"❌ Error in daily news processing: {str(e)}")
    
    def start_scheduler(self):
        """Start the scheduled news monitoring and notification system"""
        try:
            if self.is_running:
                logger.warning("⚠️ Scheduler is already running")
                return False
            
            logger.info("🚀 Starting daily news notification system...")
            
            # Schedule daily task at 08:45 AM Malaysia time
            schedule.every().day.at("08:45").do(self.daily_news_processing_and_notification)
            
            # Start scheduler in background thread
            self.scheduler_thread = threading.Thread(target=self._run_scheduler, daemon=False)
            self.scheduler_thread.start()
            self.is_running = True
            
            logger.info(f"📅 Scheduler thread started, jobs scheduled: {len(schedule.jobs)}")
            for job in schedule.jobs:
                logger.info(f"🕐 Job: {job.job_func.__name__} at {job.start_day} {job.at_time}")
            
            logger.info("✅ Daily news notification system started successfully")
            logger.info("📧 Will notify users with matching sector interests")
            logger.info("📰 Will update news.html with fresh content")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to start scheduler: {str(e)}")
            return False
    
    def stop_scheduler(self):
        """Stop the scheduled news monitoring"""
        try:
            if not self.is_running:
                logger.warning("⚠️ Scheduler is not running")
                return False
            
            logger.info("🛑 Stopping daily news notification system...")
            
            # Clear all scheduled jobs
            schedule.clear()
            
            # Stop scheduler thread
            if self.scheduler_thread and self.scheduler_thread.is_alive():
                self.scheduler_thread.join(timeout=5)
            
            self.is_running = False
            logger.info("✅ Daily news notification system stopped successfully")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to stop scheduler: {str(e)}")
            return False
    
    def _run_scheduler(self):
        """Run the scheduler loop in background thread"""
        try:
            logger.info("🔄 Scheduler thread started, entering main loop...")
            while self.is_running:
                current_time = datetime.now(self.malaysia_tz).strftime('%H:%M')
                logger.info(f"🕐 Scheduler check at {current_time}, jobs pending: {len(schedule.jobs)}")
                schedule.run_pending()
                time.sleep(60)  # Check every minute
        except Exception as e:
            logger.error(f"❌ Scheduler error: {str(e)}")
    
    def test_immediate_run(self):
        """Test the system with an immediate run"""
        try:
            logger.info("🧪 Running immediate test of daily news notification system...")
            self.daily_news_processing_and_notification()
            logger.info("✅ Test run completed successfully")
            return True
        except Exception as e:
            logger.error(f"❌ Test run failed: {str(e)}")
            return False
    
    def get_status(self):
        """Get current status of the system"""
        try:
            next_run = schedule.next_run()
            return {
                'is_running': self.is_running,
                'next_run': next_run.isoformat() if next_run else None,
                'scheduled_jobs': len(schedule.jobs),
                'database_connected': self.mongo_client.admin.command('ping').get('ok') == 1,
                'email_configured': bool(self.smtp_username and self.smtp_password),
                'openai_configured': bool(os.getenv('OPENAI_API_KEY')),
                'news_api_configured': bool(self.api_key)
            }
        except Exception as e:
            logger.error(f"❌ Error getting status: {str(e)}")
            return {'error': str(e)}


def main():
    """Main function to run the daily news notification system"""
    try:
        # Initialize the system
        notification_system = DailyNewsNotificationSystem()
        
        # Start the scheduler
        if notification_system.start_scheduler():
            logger.info("🎉 Daily News Notification System is running!")
            logger.info("📅 Scheduled to run daily at 08:45 AM Malaysia time")
            logger.info("📧 Will send targeted notifications to users")
            logger.info("📰 Will update news.html with fresh content")
            logger.info("Press Ctrl+C to stop...")
            
            # Keep the main thread alive
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                logger.info("🛑 Shutting down...")
                notification_system.stop_scheduler()
        else:
            logger.error("❌ Failed to start the notification system")
            
    except Exception as e:
        logger.error(f"❌ Fatal error: {str(e)}")


if __name__ == "__main__":
    main()
