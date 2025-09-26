"""
Data processing utilities for the Stock Analysis Application
"""

import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional, Tuple
import yfinance as yf
from retrying import retry

logger = logging.getLogger(__name__)

def calculate_recency_boost(doc):
    """Calculate recency boost for documents based on their timestamp"""
    try:
        if not doc or 'timestamp' not in doc:
            return 1.0
        
        # Parse timestamp
        if isinstance(doc['timestamp'], str):
            doc_time = datetime.fromisoformat(doc['timestamp'].replace('Z', '+00:00'))
        else:
            doc_time = doc['timestamp']
        
        # Calculate days since publication
        now = datetime.now(timezone.utc)
        days_old = (now - doc_time).days
        
        # Apply recency boost (newer = higher boost)
        if days_old <= 1:
            return 1.5  # 50% boost for very recent news
        elif days_old <= 7:
            return 1.3  # 30% boost for recent news
        elif days_old <= 30:
            return 1.1  # 10% boost for somewhat recent news
        else:
            return 1.0  # No boost for old news
            
    except Exception as e:
        logger.error(f"Error calculating recency boost: {e}")
        return 1.0

def calculate_company_relevance(doc, query, ticker=None, conversation_context=None):
    """Calculate company relevance score for documents"""
    try:
        relevance_score = 0.0
        content = doc.get('content', '').lower()
        query_lower = query.lower()
        
        # Direct ticker mention
        if ticker and ticker.lower() in content:
            relevance_score += 0.4
        
        # Company name mentions (basic)
        if ticker:
            # This would need a mapping from ticker to company name
            # For now, using basic keyword matching
            company_keywords = [ticker.lower()]
            for keyword in company_keywords:
                if keyword in content:
                    relevance_score += 0.3
        
        # Query keyword matching
        query_words = set(query_lower.split())
        content_words = set(content.split())
        overlap = len(query_words.intersection(content_words))
        if overlap > 0:
            relevance_score += min(0.3, overlap * 0.1)
        
        # Context relevance
        if conversation_context:
            context_keywords = []
            if conversation_context.get('ticker'):
                context_keywords.append(conversation_context['ticker'].lower())
            if conversation_context.get('summary'):
                context_words = conversation_context['summary'].lower().split()
                context_keywords.extend(context_words[:5])  # First 5 words
            
            for keyword in context_keywords:
                if keyword in content:
                    relevance_score += 0.1
        
        return min(1.0, relevance_score)
        
    except Exception as e:
        logger.error(f"Error calculating company relevance: {e}")
        return 0.0

def calculate_cross_encoder_score(cross_encoder, query, doc):
    """Calculate cross-encoder score for document relevance"""
    try:
        if not cross_encoder or not doc:
            return 0.0
        
        content = doc.get('content', '')
        if not content:
            return 0.0
        
        # Truncate content if too long
        if len(content) > 512:
            content = content[:512]
        
        # Calculate cross-encoder score
        score = cross_encoder.predict([(query, content)])
        return float(score[0])
        
    except Exception as e:
        logger.error(f"Error calculating cross-encoder score: {e}")
        return 0.0

def calculate_conversation_context_relevance(doc, conversation_context):
    """Calculate relevance based on conversation context"""
    try:
        if not conversation_context or not doc:
            return 0.0
        
        relevance_score = 0.0
        content = doc.get('content', '').lower()
        
        # Previous ticker relevance
        if conversation_context.get('ticker') and conversation_context['ticker'].lower() in content:
            relevance_score += 0.3
        
        # Previous topic relevance
        if conversation_context.get('summary'):
            summary_words = set(conversation_context['summary'].lower().split())
            content_words = set(content.split())
            overlap = len(summary_words.intersection(content_words))
            if overlap > 0:
                relevance_score += min(0.2, overlap * 0.05)
        
        # Previous insights relevance
        if conversation_context.get('actionable_insights'):
            insights_text = ' '.join(conversation_context['actionable_insights']).lower()
            insights_words = set(insights_text.split())
            content_words = set(content.split())
            overlap = len(insights_words.intersection(content_words))
            if overlap > 0:
                relevance_score += min(0.2, overlap * 0.05)
        
        return min(1.0, relevance_score)
        
    except Exception as e:
        logger.error(f"Error calculating conversation context relevance: {e}")
        return 0.0

def calculate_feedback_based_score(doc, query, ticker, feedback_insights):
    """Calculate score based on user feedback insights"""
    try:
        if not feedback_insights or not doc:
            return 0.0
        
        score = 0.0
        content = doc.get('content', '').lower()
        
        # Positive feedback patterns
        if feedback_insights.get('preferred_sources'):
            for source in feedback_insights['preferred_sources']:
                if source.lower() in content:
                    score += 0.2
        
        # Negative feedback patterns
        if feedback_insights.get('avoided_sources'):
            for source in feedback_insights['avoided_sources']:
                if source.lower() in content:
                    score -= 0.3
        
        # Content type preferences
        if feedback_insights.get('preferred_content_types'):
            for content_type in feedback_insights['preferred_content_types']:
                if content_type.lower() in content:
                    score += 0.1
        
        return max(0.0, min(1.0, score))
        
    except Exception as e:
        logger.error(f"Error calculating feedback-based score: {e}")
        return 0.0

@retry(stop_max_attempt_number=3, wait_exponential_multiplier=1000, wait_exponential_max=10000)
def fetch_financial_data(ticker, company_name=None):
    """Fetch financial data for a given ticker with retry logic"""
    try:
        if not ticker:
            return None
        
        # Clean ticker symbol
        ticker = ticker.strip().upper()
        
        # Create yfinance ticker object
        stock = yf.Ticker(ticker)
        
        # Fetch basic info
        info = stock.info
        
        # Fetch recent price data
        hist = stock.history(period="5d")
        
        # Fetch recommendations
        recommendations = stock.recommendations
        
        # Fetch earnings calendar
        calendar = stock.calendar
        
        # Fetch analyst info
        analyst_info = stock.analyst_info
        
        # Compile financial data
        financial_data = {
            'ticker': ticker,
            'company_name': company_name or info.get('longName', ticker),
            'current_price': info.get('currentPrice', info.get('regularMarketPrice')),
            'previous_close': info.get('previousClose'),
            'market_cap': info.get('marketCap'),
            'volume': info.get('volume'),
            'avg_volume': info.get('averageVolume'),
            'pe_ratio': info.get('trailingPE'),
            'forward_pe': info.get('forwardPE'),
            'peg_ratio': info.get('pegRatio'),
            'price_to_book': info.get('priceToBook'),
            'debt_to_equity': info.get('debtToEquity'),
            'return_on_equity': info.get('returnOnEquity'),
            'profit_margins': info.get('profitMargins'),
            'revenue_growth': info.get('revenueGrowth'),
            'earnings_growth': info.get('earningsGrowth'),
            'beta': info.get('beta'),
            'dividend_yield': info.get('dividendYield'),
            'sector': info.get('sector'),
            'industry': info.get('industry'),
            'employees': info.get('fullTimeEmployees'),
            'website': info.get('website'),
            'description': info.get('longBusinessSummary'),
            '52_week_high': info.get('fiftyTwoWeekHigh'),
            '52_week_low': info.get('fiftyTwoWeekLow'),
            'price_history': hist.to_dict() if not hist.empty else {},
            'recommendations': recommendations.to_dict() if recommendations is not None and not recommendations.empty else {},
            'earnings_calendar': calendar.to_dict() if calendar is not None and not calendar.empty else {},
            'analyst_info': analyst_info.to_dict() if analyst_info is not None and not analyst_info.empty else {},
            'last_updated': datetime.now(timezone.utc).isoformat()
        }
        
        logger.info(f"Successfully fetched financial data for {ticker}")
        return financial_data
        
    except Exception as e:
        logger.error(f"Error fetching financial data for {ticker}: {e}")
        return None

def fetch_financial_data_for_llm(ticker, company_name=None):
    """Fetch and format financial data specifically for LLM consumption"""
    try:
        financial_data = fetch_financial_data(ticker, company_name)
        if not financial_data:
            return None
        
        # Format for LLM consumption
        formatted_data = {
            'ticker': financial_data.get('ticker'),
            'company_name': financial_data.get('company_name'),
            'current_price': financial_data.get('current_price'),
            'market_cap': financial_data.get('market_cap'),
            'pe_ratio': financial_data.get('pe_ratio'),
            'sector': financial_data.get('sector'),
            'industry': financial_data.get('industry'),
            'description': financial_data.get('description', '')[:500] if financial_data.get('description') else '',
            'key_metrics': {
                'debt_to_equity': financial_data.get('debt_to_equity'),
                'return_on_equity': financial_data.get('return_on_equity'),
                'profit_margins': financial_data.get('profit_margins'),
                'revenue_growth': financial_data.get('revenue_growth'),
                'earnings_growth': financial_data.get('earnings_growth'),
                'beta': financial_data.get('beta'),
                'dividend_yield': financial_data.get('dividend_yield')
            }
        }
        
        return formatted_data
        
    except Exception as e:
        logger.error(f"Error formatting financial data for LLM: {e}")
        return None

def format_financial_data_for_llm(company_data):
    """Format company data for LLM consumption"""
    try:
        if not company_data:
            return "No financial data available."
        
        formatted_text = f"""
Company: {company_data.get('company_name', 'N/A')} ({company_data.get('ticker', 'N/A')})
Current Price: ${company_data.get('current_price', 'N/A')}
Market Cap: ${company_data.get('market_cap', 'N/A')}
P/E Ratio: {company_data.get('pe_ratio', 'N/A')}
Sector: {company_data.get('sector', 'N/A')}
Industry: {company_data.get('industry', 'N/A')}

Key Metrics:
- Debt to Equity: {company_data.get('key_metrics', {}).get('debt_to_equity', 'N/A')}
- Return on Equity: {company_data.get('key_metrics', {}).get('return_on_equity', 'N/A')}
- Profit Margins: {company_data.get('key_metrics', {}).get('profit_margins', 'N/A')}
- Revenue Growth: {company_data.get('key_metrics', {}).get('revenue_growth', 'N/A')}
- Beta: {company_data.get('key_metrics', {}).get('beta', 'N/A')}
- Dividend Yield: {company_data.get('key_metrics', {}).get('dividend_yield', 'N/A')}

Description: {company_data.get('description', 'No description available.')}
"""
        return formatted_text.strip()
        
    except Exception as e:
        logger.error(f"Error formatting company data for LLM: {e}")
        return "Error formatting financial data."

def calculate_token_usage_and_cost(response, model_name):
    """Calculate token usage and cost for API responses"""
    try:
        if not response:
            return {"tokens": 0, "cost": 0.0}
        
        # Basic token estimation (rough approximation)
        response_text = str(response)
        estimated_tokens = len(response_text.split()) * 1.3  # Rough estimation
        
        # Cost per token (approximate rates)
        cost_per_token = {
            'gpt-4o-mini': 0.00015 / 1000,  # $0.15 per 1K tokens
            'gpt-4': 0.03 / 1000,  # $30 per 1K tokens
            'text-embedding-3-small': 0.00002 / 1000  # $0.02 per 1K tokens
        }
        
        cost = estimated_tokens * cost_per_token.get(model_name, 0.00015 / 1000)
        
        return {
            "tokens": int(estimated_tokens),
            "cost": round(cost, 6),
            "model": model_name
        }
        
    except Exception as e:
        logger.error(f"Error calculating token usage: {e}")
        return {"tokens": 0, "cost": 0.0}

def calculate_llamaindex_token_usage(agent, response, model_name):
    """Calculate token usage for LlamaIndex agent responses"""
    try:
        if not agent or not response:
            return {"tokens": 0, "cost": 0.0}
        
        # Get token usage from LlamaIndex if available
        if hasattr(response, 'response_metadata'):
            metadata = response.response_metadata
            if 'token_usage' in metadata:
                return {
                    "tokens": metadata['token_usage'].get('total_tokens', 0),
                    "cost": metadata['token_usage'].get('total_cost', 0.0),
                    "model": model_name
                }
        
        # Fallback to estimation
        return calculate_token_usage_and_cost(str(response), model_name)
        
    except Exception as e:
        logger.error(f"Error calculating LlamaIndex token usage: {e}")
        return {"tokens": 0, "cost": 0.0}
