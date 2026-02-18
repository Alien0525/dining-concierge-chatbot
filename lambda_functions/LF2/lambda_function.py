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
    
def get_restaurant_recommendations(cuisine, location, count=3):
    """
    Query DynamoDB for restaurants matching cuisine and location
    
    Args:
        cuisine: Cuisine type (e.g., 'Japanese')
        location: Area/borough (e.g., 'Brooklyn')
        count: Number of recommendations
    
    Returns:
        List of restaurant dictionaries
    """
    
    table = dynamodb.Table(DYNAMODB_TABLE)
    
    try:
        # Map common location names to Area values
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
        
        # Normalize location
        area = location_mapping.get(location.lower(), location)
        
        print(f"Searching for {cuisine} restaurants in {area}")
        
        # Scan with filter for both cuisine and area
        response = table.scan(
            FilterExpression='Cuisine = :cuisine AND Area = :area',
            ExpressionAttributeValues={
                ':cuisine': cuisine,
                ':area': area
            }
        )
        
        restaurants = response.get('Items', [])
        
        print(f"Found {len(restaurants)} {cuisine} restaurants in {area}")
        
        if not restaurants:
            # Fallback: try without area filter
            print(f"No restaurants found in {area}, trying {cuisine} anywhere...")
            response = table.scan(
                FilterExpression='Cuisine = :cuisine',
                ExpressionAttributeValues={':cuisine': cuisine}
            )
            restaurants = response.get('Items', [])
        
        if not restaurants:
            return []
        
        # Randomly select restaurants
        selected = random.sample(restaurants, min(count, len(restaurants)))
        
        # Convert Decimal to float for JSON serialization
        for restaurant in selected:
            if 'Rating' in restaurant:
                restaurant['Rating'] = float(restaurant['Rating'])
            if 'Latitude' in restaurant:
                restaurant['Latitude'] = float(restaurant['Latitude'])
            if 'Longitude' in restaurant:
                restaurant['Longitude'] = float(restaurant['Longitude'])
        
        return selected
        
    except Exception as e:
        print(f"Error querying DynamoDB: {e}")
        return []

def send_email(to_email, restaurants, cuisine, location, num_people, dining_time):
    """
    Send restaurant recommendations via SES
    """
    
    # Build restaurant list
    restaurant_list = []
    for i, restaurant in enumerate(restaurants, 1):
        name = restaurant.get('Name', 'Unknown')
        address = restaurant.get('Address', 'Address not available')
        area = restaurant.get('Area', location)
        restaurant_list.append(f"{i}. {name}, located at {address} ({area})")
    
    # Format email body
    email_body = f"""Hello! Here are my {cuisine} restaurant suggestions in {location} for {num_people} people, for {dining_time}:

{chr(10).join(restaurant_list)}

Enjoy your meal!"""
    
    # Send via SES
    try:
        response = ses.send_email(
            Source=FROM_EMAIL,
            Destination={'ToAddresses': [to_email]},
            Message={
                'Subject': {
                    'Data': f'{cuisine} Restaurant Recommendations in {location}',
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
        print(f"Email sent to {to_email}, MessageId: {response['MessageId']}")
    
    except Exception as e:
        print(f"Error sending email: {e}")
        raise

# For local testing
if __name__ == '__main__':
    # Simulate SQS message
    test_event = {}
    lambda_handler(test_event, None)