"""
API utilities for the Stock Analysis Application
"""

import logging
import requests
import time
from typing import Dict, List, Any, Optional
from newsdataapi import NewsDataApiClient
from googleapiclient.discovery import build
from youtube_transcript_api import YouTubeTranscriptApi

logger = logging.getLogger(__name__)

def search_youtube(query):
    """Search YouTube for relevant videos"""
    try:
        # This would require YouTube API setup
        # For now, return empty results
        return []
    except Exception as e:
        logger.error(f"Error searching YouTube: {e}")
        return []

def fetch_transcripts(video_details):
    """Fetch transcripts from YouTube videos"""
    try:
        transcripts = []
        for video in video_details:
            try:
                transcript = YouTubeTranscriptApi.get_transcript(video['video_id'])
                transcripts.append({
                    'video_id': video['video_id'],
                    'title': video['title'],
                    'transcript': transcript
                })
            except Exception as e:
                logger.warning(f"Could not fetch transcript for video {video['video_id']}: {e}")
                continue
        return transcripts
    except Exception as e:
        logger.error(f"Error fetching transcripts: {e}")
        return []

def search_google(query, num_results=3):
    """Search Google for relevant information"""
    try:
        # This would require Google Custom Search API setup
        # For now, return empty results
        return []
    except Exception as e:
        logger.error(f"Error searching Google: {e}")
        return []

def fetch_malaysia_news(query=None, category=None, max_results=None):
    """Fetch Malaysia news using NewsData.io API"""
    try:
        from config import Config
        
        if not Config.NEWSDATA_API_KEY:
            logger.warning("NewsData API key not configured")
            return []
        
        client = NewsDataApiClient(apikey=Config.NEWSDATA_API_KEY)
        
        # Build query parameters
        params = {
            'country': 'my',
            'language': 'en',
            'category': category or ['business', 'technology', 'politics', 'economy'],
            'size': min(max_results or 10, 10)  # API limit
        }
        
        if query:
            params['q'] = query
        
        # Make API request
        response = client.news_api(**params)
        
        if response.get('status') == 'success':
            articles = response.get('results', [])
            logger.info(f"Fetched {len(articles)} Malaysia news articles")
            return articles
        else:
            logger.error(f"NewsData API error: {response.get('message', 'Unknown error')}")
            return []
            
    except Exception as e:
        logger.error(f"Error fetching Malaysia news: {e}")
        return []

def fetch_malaysia_stock_news(ticker=None, company_name=None, sector=None):
    """Fetch Malaysia stock-specific news"""
    try:
        # Build search query
        query_parts = []
        if ticker:
            query_parts.append(ticker)
        if company_name:
            query_parts.append(company_name)
        if sector:
            query_parts.append(sector)
        
        query = ' '.join(query_parts) if query_parts else None
        
        # Fetch news with business category
        articles = fetch_malaysia_news(
            query=query,
            category=['business', 'economy'],
            max_results=20
        )
        
        # Filter for stock-relevant articles
        stock_articles = []
        for article in articles:
            content = (article.get('title', '') + ' ' + article.get('description', '')).lower()
            
            # Check for stock-related keywords
            stock_keywords = ['stock', 'share', 'equity', 'market', 'trading', 'investment', 'financial']
            if any(keyword in content for keyword in stock_keywords):
                stock_articles.append(article)
        
        logger.info(f"Filtered {len(stock_articles)} stock-relevant articles from {len(articles)} total")
        return stock_articles
        
    except Exception as e:
        logger.error(f"Error fetching Malaysia stock news: {e}")
        return []

def get_malaysia_market_overview():
    """Get Malaysia market overview"""
    try:
        # Fetch general business news for market overview
        articles = fetch_malaysia_news(
            category=['business', 'economy'],
            max_results=15
        )
        
        # Structure as market overview
        overview = {
            'total_articles': len(articles),
            'latest_news': articles[:5],
            'market_sentiment': 'neutral',  # Would need sentiment analysis
            'key_themes': [],  # Would need topic extraction
            'last_updated': time.time()
        }
        
        return overview
        
    except Exception as e:
        logger.error(f"Error getting Malaysia market overview: {e}")
        return {'error': str(e)}

def search_malaysia_news_by_keywords(keywords, max_results=20):
    """Search Malaysia news by specific keywords"""
    try:
        if isinstance(keywords, list):
            query = ' '.join(keywords)
        else:
            query = str(keywords)
        
        articles = fetch_malaysia_news(
            query=query,
            max_results=max_results
        )
        
        return articles
        
    except Exception as e:
        logger.error(f"Error searching Malaysia news by keywords: {e}")
        return []

def send_email_notification(to_email, subject, body, html_body=None):
    """Send email notification"""
    try:
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        from config import Config
        
        if not Config.EMAIL_USER or not Config.EMAIL_PASSWORD:
            logger.warning("Email credentials not configured")
            return False
        
        # Create message
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = Config.EMAIL_USER
        msg['To'] = to_email
        
        # Add text and HTML parts
        text_part = MIMEText(body, 'plain')
        msg.attach(text_part)
        
        if html_body:
            html_part = MIMEText(html_body, 'html')
            msg.attach(html_part)
        
        # Send email
        with smtplib.SMTP(Config.EMAIL_HOST, Config.EMAIL_PORT) as server:
            server.starttls()
            server.login(Config.EMAIL_USER, Config.EMAIL_PASSWORD)
            server.send_message(msg)
        
        logger.info(f"Email sent successfully to {to_email}")
        return True
        
    except Exception as e:
        logger.error(f"Error sending email: {e}")
        return False

def check_price_alerts():
    """Check for price alerts (placeholder implementation)"""
    try:
        # This would check user watchlists for price alerts
        # For now, return empty list
        return []
    except Exception as e:
        logger.error(f"Error checking price alerts: {e}")
        return []

def send_news_alert(user_id, ticker, news_data):
    """Send news alert to user"""
    try:
        # This would send news alerts to users
        # For now, just log the alert
        logger.info(f"News alert for user {user_id}, ticker {ticker}: {news_data.get('title', 'No title')}")
        return True
    except Exception as e:
        logger.error(f"Error sending news alert: {e}")
        return False
