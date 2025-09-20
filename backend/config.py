import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key'
    NEWS_API_KEY = os.environ.get('NEWS_API_KEY') or 'your-news-api-key'
    
    # Indian stock exchanges
    NSE_SUFFIX = '.NS'
    BSE_SUFFIX = '.BO'
