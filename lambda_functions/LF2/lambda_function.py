"""
LF2 - Queue Worker
Polls SQS for restaurant requests, queries DynamoDB, sends email via SES
"""

import json
import boto3
import random
from decimal import Decimal
from boto3.dynamodb.conditions import Key
import os

# AWS clients
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
sqs = boto3.client('sqs', region_name='us-east-1')
ses = boto3.client('ses', region_name='us-east-1')

# Configuration
DYNAMODB_TABLE = os.environ.get('DYNAMODB_TABLE', 'yelp-restaurants')
SQS_QUEUE_URL = os.environ.get('SQS_QUEUE_URL')
FROM_EMAIL = os.environ.get('FROM_EMAIL')

def lambda_handler(event, context):
    """
    Triggered by CloudWatch Events every minute.
    Polls SQS queue for restaurant requests.
    
    Flow:
    1. Pull message from SQS
    2. Query DynamoDB for restaurants matching cuisine
    3. Format email with recommendations
    4. Send via SES
    5. Delete message from SQS
    """
    
    # Pull messages from SQS (up to 10 at a time)
    response = sqs.receive_message(
        QueueUrl=SQS_QUEUE_URL,
        MaxNumberOfMessages=10,  # Process up to 10 requests per invocation
        WaitTimeSeconds=0  # Don't wait if queue is empty
    )
    
    messages = response.get('Messages', [])
    
    if not messages:
        print("No messages in queue")
        return {'statusCode': 200, 'body': 'No messages to process'}
    
    print(f"Processing {len(messages)} messages")
    
    # Process each message
    for message in messages:
        try:
            # Parse message body
            body = json.loads(message['Body'])
            
            # Extract user preferences
            cuisine = body.get('cuisine', '').capitalize()
            location = body.get('location', 'Manhattan')
            num_people = body.get('num_people', '2')
            dining_time = body.get('dining_time', 'today')
            email = body.get('email')
            
            print(f"Request: {cuisine} in {location} for {num_people} people at {dining_time}")
            
            # Get restaurant recommendations (now with location filtering)
            restaurants = get_restaurant_recommendations(cuisine, location)
            
            # Send email
            if restaurants and email:
                send_email(email, restaurants, cuisine, location, num_people, dining_time)
            
            # Delete message from queue (processed successfully)
            sqs.delete_message(
                QueueUrl=SQS_QUEUE_URL,
                ReceiptHandle=message['ReceiptHandle']
            )
            
            print(f"Successfully processed request for {email}")
            
        except Exception as e:
            print(f"Error processing message: {e}")
            # Message stays in queue, will be retried
    
    return {'statusCode': 200, 'body': f'Processed {len(messages)} messages'}
    
def get_restaurant_recommendations(cuisine, location, price_range=None, count=5):
    """
    Query DynamoDB for restaurants with filters
    
    Args:
        cuisine: Cuisine type
        location: Area/borough
        price_range: Price filter ($, $$, $$$, $$$$) - optional
        count: Number of recommendations (default 5)
    """
    
    table = dynamodb.Table(DYNAMODB_TABLE)
    
    try:
        # Map location
        location_mapping = {
            'manhattan': 'Manhattan',
            'brooklyn': 'Brooklyn',
            'queens': 'Queens',
            'bronx': 'Bronx',
            'staten island': 'Staten Island',
            'jersey city': 'Jersey City',
            'hoboken': 'Hoboken',
            'long island city': 'Long Island City'
        }
        
        area = location_mapping.get(location.lower(), location)
        
        # Build filter expression
        if price_range and price_range.lower() != 'any':
            filter_expr = 'Cuisine = :cuisine AND Area = :area AND PriceRange = :price'
            expr_values = {
                ':cuisine': cuisine,
                ':area': area,
                ':price': price_range
            }
        else:
            filter_expr = 'Cuisine = :cuisine AND Area = :area'
            expr_values = {
                ':cuisine': cuisine,
                ':area': area
            }
        
        print(f"Searching: {cuisine} in {area}, Price: {price_range or 'Any'}")
        
        # Scan with filter
        response = table.scan(
            FilterExpression=filter_expr,
            ExpressionAttributeValues=expr_values
        )
        
        restaurants = response.get('Items', [])
        
        # Sort by rating (descending)
        restaurants.sort(key=lambda x: float(x.get('Rating', 0)), reverse=True)
        
        # Take top 5 (or count specified)
        selected = restaurants[:min(count, len(restaurants))]
        
        # Convert Decimal to float
        for restaurant in selected:
            if 'Rating' in restaurant:
                restaurant['Rating'] = float(restaurant['Rating'])
            if 'Latitude' in restaurant:
                restaurant['Latitude'] = float(restaurant['Latitude'])
            if 'Longitude' in restaurant:
                restaurant['Longitude'] = float(restaurant['Longitude'])
        
        print(f"Found {len(restaurants)} total, returning top {len(selected)} by rating")
        
        return selected
        
    except Exception as e:
        print(f"Error querying DynamoDB: {e}")
        return []
    
def send_email(to_email, restaurants, cuisine, location, num_people, dining_time):
    """
    Send restaurant recommendations via SES
    """
    
    # Build restaurant list with full details
    restaurant_list = []
    for i, restaurant in enumerate(restaurants, 1):
        name = restaurant.get('Name', 'Unknown')
        address = restaurant.get('Address', 'N/A')
        area = restaurant.get('Area', location)
        rating = restaurant.get('Rating', 'N/A')
        review_count = restaurant.get('ReviewCount', 0)
        phone = restaurant.get('Phone', 'N/A')
        price = restaurant.get('PriceRange', 'N/A')
        
        # Google Maps link
        maps_query = f"{name} {address}".replace(' ', '+')
        maps_link = f"https://www.google.com/maps/search/?api=1&query={maps_query}"
        
        restaurant_info = f"""{i}. {name} {"⭐" * int(float(rating))} ({rating}/5, {review_count} reviews)
   📍 {address}, {area}
   💰 Price: {price}
   📞 {phone}
   🗺️ View on Maps: {maps_link}
"""
        restaurant_list.append(restaurant_info)
    
    # Format email body
    email_body = f"""Hello! 

Here are my top {len(restaurants)} {cuisine} restaurant recommendations in {location} for {num_people} people, for {dining_time}:

{chr(10).join(restaurant_list)}

Enjoy your meal! 🍽️

---
Powered by Dining Concierge Chatbot
"""
    
    # Send via SES
    try:
        response = ses.send_email(
            Source=FROM_EMAIL,
            Destination={'ToAddresses': [to_email]},
            Message={
                'Subject': {
                    'Data': f'🍽️ Top {len(restaurants)} {cuisine} Restaurants in {location}',
                    'Charset': 'UTF-8'
                },
                'Body': {
                    'Text': {
                        'Data': email_body,
                        'Charset': 'UTF-8'
                    }
                }
            }
        )
        print(f"Email sent to {to_email}")
    except Exception as e:
        print(f"Error sending email: {e}")
        raise

# For local testing
if __name__ == '__main__':
    # Simulate SQS message
    test_event = {}
    lambda_handler(test_event, None)