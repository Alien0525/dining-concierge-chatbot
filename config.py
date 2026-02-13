"""
Configuration for Dining Concierge Chatbot
Reads secrets from .env file, stores static config here
"""
import os
from dotenv import load_dotenv

load_dotenv()

# Secrets from environment
YELP_API_KEY = os.environ.get('YELP_API_KEY')
AWS_REGION = os.environ.get('AWS_REGION', 'us-east-1')

# Yelp API Settings
YELP_API_BASE_URL = 'https://api.yelp.com/v3'
YELP_API_LIMIT = 50

# Scraping Configuration
CUISINES = ['japanese', 'italian', 'chinese', 'mexican', 'indian', 'thai', 'korean']
RESTAURANTS_PER_CUISINE = 200
TOTAL_RESTAURANTS_TARGET = 1000

# Location Settings
TARGET_LOCATION = 'Manhattan, NY'

# AWS Configuration
DYNAMODB_TABLE_NAME = 'yelp-restaurants'
OPENSEARCH_INDEX = 'restaurants'
SQS_QUEUE_NAME = 'restaurant-requests'
SQS_QUEUE_URL = os.environ.get('SQS_QUEUE_URL')
FROM_EMAIL = os.environ.get('FROM_EMAIL')