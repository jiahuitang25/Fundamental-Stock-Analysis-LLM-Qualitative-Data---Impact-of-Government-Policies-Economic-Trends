#!/usr/bin/env python3
"""
Script to fetch historical Malaysia news from newsdata.io from 2025-08-19 until now
and store it in the malaysia_news collection.
"""

import os
import sys
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Add the current directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Load environment variables
load_dotenv()

# Import required modules
from analysis import (
    fetch_historical_malaysia_news,
    news_collection,
    client,
    db
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('historical_news_fetch.log'),
        logging.StreamHandler()
    ]
)

def store_news_in_database(articles, from_date, to_date):
    """
    Store fetched news articles in the malaysia_news collection
    
    Args:
        articles (list): List of processed news articles
        from_date (str): Start date of the fetch period
        to_date (str): End date of the fetch period
    
    Returns:
        dict: Storage results with counts and any errors
    """
    if not articles:
        logging.warning("No articles to store")
        return {"stored_count": 0, "errors": []}
    
    stored_count = 0
    errors = []
    
    for article in articles:
        try:
            # Check if article already exists (by article_id)
            existing = news_collection.find_one({"article_id": article.get("article_id")})
            
            if existing:
                logging.info(f"Article already exists: {article.get('title', 'No title')[:50]}...")
                continue
            
            # Add metadata for tracking
            article["batch_fetch_date"] = from_date
            article["batch_fetch_end_date"] = to_date
            article["batch_created_at"] = datetime.now().isoformat()
            
            # Insert into database
            result = news_collection.insert_one(article)
            
            if result.inserted_id:
                stored_count += 1
                logging.info(f"Stored article: {article.get('title', 'No title')[:50]}... (ID: {result.inserted_id})")
            else:
                errors.append(f"Failed to store article: {article.get('title', 'No title')}")
                
        except Exception as e:
            error_msg = f"Error storing article '{article.get('title', 'No title')}': {str(e)}"
            errors.append(error_msg)
            logging.error(error_msg)
    
    return {
        "stored_count": stored_count,
        "errors": errors,
        "total_processed": len(articles)
    }

def fetch_historical_data_batch(from_date, to_date, max_results=50, categories=None):
    """
    Fetch historical data in batches to handle API limits
    
    Args:
        from_date (str): Start date in YYYY-MM-DD format
        to_date (str): End date in YYYY-MM-DD format
        max_results (int): Maximum results per batch
        categories (list): List of categories to fetch
    
    Returns:
        dict: Fetch results with articles and metadata
    """
    all_articles = []
    total_fetched = 0
    
    # If no categories specified, use all available categories
    if not categories:
        categories = ['business', 'technology', 'politics', 'economy']
    
    logging.info(f"Starting batch fetch from {from_date} to {to_date}")
    logging.info(f"Categories to fetch: {categories}")
    
    for category in categories:
        try:
            logging.info(f"Fetching {category} news...")
            
            # Fetch news for this category
            result = fetch_historical_malaysia_news(
                from_date=from_date,
                to_date=to_date,
                category=category,
                max_results=max_results,
                use_semantic_chunking=True
            )
            
            if result.get('status') == 'success':
                articles = result.get('articles', [])
                all_articles.extend(articles)
                total_fetched += len(articles)
                logging.info(f"Fetched {len(articles)} articles for {category}")
            else:
                logging.error(f"Failed to fetch {category} news: {result.get('error')}")
                
        except Exception as e:
            logging.error(f"Error fetching {category} news: {str(e)}")
    
    # Remove duplicates based on article_id
    unique_articles = []
    seen_ids = set()
    
    for article in all_articles:
        article_id = article.get('article_id')
        if article_id and article_id not in seen_ids:
            unique_articles.append(article)
            seen_ids.add(article_id)
        elif not article_id:
            # If no article_id, use title as identifier
            title = article.get('title', '')
            if title and title not in seen_ids:
                unique_articles.append(article)
                seen_ids.add(title)
    
    logging.info(f"Total unique articles after deduplication: {len(unique_articles)}")
    
    return {
        'status': 'success',
        'total_fetched': total_fetched,
        'unique_articles': len(unique_articles),
        'articles': unique_articles,
        'categories_processed': categories
    }

def main():
    """Main function to fetch and store historical Malaysia news"""
    
    # Configuration
    start_date = "2025-08-19"  # User specified start date
    end_date = datetime.now().strftime('%Y-%m-%d')  # Current date
    max_results_per_category = 50  # Adjust based on API limits
    
    logging.info("=" * 60)
    logging.info("Historical Malaysia News Fetcher")
    logging.info("=" * 60)
    logging.info(f"Fetch period: {start_date} to {end_date}")
    logging.info(f"Max results per category: {max_results_per_category}")
    
    # Check API key
    api_key = os.getenv('NEWSDATA_API_KEY')
    if not api_key:
        logging.error("NEWSDATA_API_KEY not found in environment variables")
        logging.error("Please add it to your .env file")
        return False
    
    # Check database connection
    try:
        # Test database connection
        client.admin.command('ping')
        logging.info("Database connection successful")
    except Exception as e:
        logging.error(f"Database connection failed: {str(e)}")
        return False
    
    # Fetch historical data
    try:
        fetch_result = fetch_historical_data_batch(
            from_date=start_date,
            to_date=end_date,
            max_results=max_results_per_category
        )
        
        if fetch_result['status'] != 'success':
            logging.error("Failed to fetch historical data")
            return False
        
        articles = fetch_result['articles']
        logging.info(f"Successfully fetched {len(articles)} unique articles")
        
        # Store articles in database
        storage_result = store_news_in_database(articles, start_date, end_date)
        
        # Print summary
        logging.info("=" * 60)
        logging.info("FETCH SUMMARY")
        logging.info("=" * 60)
        logging.info(f"Fetch period: {start_date} to {end_date}")
        logging.info(f"Articles fetched: {fetch_result['total_fetched']}")
        logging.info(f"Unique articles: {fetch_result['unique_articles']}")
        logging.info(f"Articles stored: {storage_result['stored_count']}")
        logging.info(f"Storage errors: {len(storage_result['errors'])}")
        
        if storage_result['errors']:
            logging.warning("Storage errors encountered:")
            for error in storage_result['errors']:
                logging.warning(f"  - {error}")
        
        # Show sample of stored articles
        if storage_result['stored_count'] > 0:
            logging.info("\nSample of stored articles:")
            sample_articles = articles[:5]
            for i, article in enumerate(sample_articles, 1):
                title = article.get('title', 'No title')[:60]
                pub_date = article.get('pubDate', 'No date')
                source = article.get('source_name', 'Unknown source')
                logging.info(f"  {i}. {title}... ({source}, {pub_date})")
        
        logging.info("=" * 60)
        logging.info("Historical news fetch completed successfully!")
        logging.info("=" * 60)
        
        return True
        
    except Exception as e:
        logging.error(f"Error in main execution: {str(e)}")
        return False

if __name__ == "__main__":
    success = main()
    
    if success:
        print("\n✅ Historical Malaysia news fetch completed successfully!")
        print("Check the log file 'historical_news_fetch.log' for detailed information.")
    else:
        print("\n❌ Historical Malaysia news fetch failed!")
        print("Check the log file 'historical_news_fetch.log' for error details.")
        sys.exit(1)
