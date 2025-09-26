#!/usr/bin/env python3
"""
Reliable Daily News Scheduler using APScheduler
- Uses APScheduler for reliable scheduling
- Runs independently as a background service
- Handles timezone properly (Malaysia time)
- Includes logging and error handling
"""

import os
import sys
import logging
import signal
import time
from datetime import datetime
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR
import pytz

# Add current directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from daily_news_notification_system import DailyNewsNotificationSystem

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('daily_news_scheduler.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class DailyNewsScheduler:
    """Reliable daily news scheduler using APScheduler"""
    
    def __init__(self):
        """Initialize the scheduler"""
        self.scheduler = None
        self.news_system = None
        self.malaysia_tz = pytz.timezone('Asia/Kuala_Lumpur')
        
        # Initialize the daily news system
        try:
            self.news_system = DailyNewsNotificationSystem()
            logger.info("✅ Daily News Notification System initialized successfully")
        except Exception as e:
            logger.error(f"❌ Failed to initialize Daily News System: {e}")
            raise
    
    def run_daily_news_processing(self):
        """Execute the daily news processing"""
        try:
            logger.info("🚀 Starting scheduled daily news processing...")
            start_time = datetime.now(self.malaysia_tz)
            
            # Run the daily news processing
            self.news_system.daily_news_processing_and_notification()
            
            end_time = datetime.now(self.malaysia_tz)
            duration = (end_time - start_time).total_seconds()
            
            logger.info(f"✅ Daily news processing completed successfully in {duration:.2f} seconds")
            logger.info(f"🕐 Completed at: {end_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            
        except Exception as e:
            logger.error(f"❌ Error in daily news processing: {str(e)}")
            raise
    
    def job_listener(self, event):
        """Listen to job events for logging"""
        if event.exception:
            logger.error(f"❌ Job failed: {event.exception}")
        else:
            logger.info(f"✅ Job executed successfully: {event.job_id}")
    
    def start_scheduler(self, schedule_time="08:00"):
        """Start the APScheduler with daily news processing"""
        try:
            # Create scheduler
            self.scheduler = BlockingScheduler(timezone=self.malaysia_tz)
            
            # Add job listener
            self.scheduler.add_listener(self.job_listener, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)
            
            # Add daily job
            hour, minute = schedule_time.split(":")
            self.scheduler.add_job(
                func=self.run_daily_news_processing,
                trigger=CronTrigger(hour=int(hour), minute=int(minute), timezone=self.malaysia_tz),
                id='daily_news_processing',
                name='Daily News Processing and Notification',
                replace_existing=True,
                max_instances=1
            )
            
            logger.info("🚀 Daily News Scheduler started successfully")
            logger.info(f"📅 Scheduled to run daily at {schedule_time} Malaysia time")
            logger.info(f"🕐 Current time: {datetime.now(self.malaysia_tz).strftime('%Y-%m-%d %H:%M:%S %Z')}")
            
            # Print all scheduled jobs
            jobs = self.scheduler.get_jobs()
            for job in jobs:
                next_run = getattr(job, 'next_run_time', 'Not scheduled yet')
                logger.info(f"📋 Scheduled job: {job.name} - Next run: {next_run}")
            
            # Start the scheduler (this will block)
            logger.info("🔄 Scheduler is running... Press Ctrl+C to stop")
            self.scheduler.start()
            
        except Exception as e:
            logger.error(f"❌ Failed to start scheduler: {str(e)}")
            raise
    
    def stop_scheduler(self):
        """Stop the scheduler gracefully"""
        if self.scheduler and self.scheduler.running:
            logger.info("🛑 Stopping scheduler...")
            self.scheduler.shutdown(wait=True)
            logger.info("✅ Scheduler stopped successfully")
    
    def add_test_job(self, minutes_from_now=1):
        """Add a test job that runs in a few minutes"""
        if not self.scheduler:
            logger.error("❌ Scheduler not initialized")
            return
        
        test_time = datetime.now(self.malaysia_tz).replace(second=0, microsecond=0)
        test_time = test_time.replace(minute=test_time.minute + minutes_from_now)
        
        self.scheduler.add_job(
            func=self.run_daily_news_processing,
            trigger='date',
            run_date=test_time,
            id='test_news_processing',
            name='Test News Processing',
            replace_existing=True
        )
        
        logger.info(f"🧪 Test job scheduled for: {test_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")

def signal_handler(signum, frame):
    """Handle shutdown signals"""
    logger.info(f"🛑 Received signal {signum}, shutting down...")
    sys.exit(0)

def main():
    """Main function"""
    # Set up signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        scheduler = DailyNewsScheduler()
        
        # Default schedule time (can be overridden via command line)
        schedule_time = "08:00"  # 8:00 AM Malaysia time
        
        # Check command line arguments
        if len(sys.argv) > 1:
            if sys.argv[1] == "test":
                # Test mode - schedule for 2 minutes from now
                current_time = datetime.now(scheduler.malaysia_tz)
                test_time = current_time.replace(second=0, microsecond=0)
                # Handle minute overflow
                new_minute = (test_time.minute + 2) % 60
                new_hour = test_time.hour + ((test_time.minute + 2) // 60)
                test_time = test_time.replace(hour=new_hour % 24, minute=new_minute)
                schedule_time = test_time.strftime("%H:%M")
                logger.info(f"🧪 TEST MODE: Scheduling for {schedule_time}")
            elif ":" in sys.argv[1]:
                # Custom time provided
                schedule_time = sys.argv[1]
                logger.info(f"⏰ Custom schedule time: {schedule_time}")
        
        # Start the scheduler
        scheduler.start_scheduler(schedule_time)
        
    except KeyboardInterrupt:
        logger.info("🛑 Scheduler stopped by user")
    except Exception as e:
        logger.error(f"❌ Fatal error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
