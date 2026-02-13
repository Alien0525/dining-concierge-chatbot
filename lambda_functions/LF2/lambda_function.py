"""
LF2 - Queue Worker
Polls SQS for restaurant requests, queries DynamoDB, sends email via SES
"""

import json
import boto3
import random
from decimal import Decimal
from boto3.dynamodb.conditions import Key
import config

# AWS clients
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
sqs = boto3.client('sqs', region_name='us-east-1')
ses = boto3.client('ses', region_name='us-east-1')

# Configuration
DYNAMODB_TABLE = 'yelp-restaurants'
SQS_QUEUE_URL = config.SQS_QUEUE_URL
FROM_EMAIL = 'your_verified_email@example.com'  # Update after SES setup

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
            
            print(f"Request: {cuisine} for {num_people} people at {dining_time}")
            
            # Get restaurant recommendations
            restaurants = get_restaurant_recommendations(cuisine)
            
            # Send email
            if restaurants and email:
                send_email(email, restaurants, cuisine, num_people, dining_time)
            
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

def get_restaurant_recommendations(cuisine, count=3):
    """
    Query DynamoDB for random restaurants of given cuisine.
    
    Since we don't have OpenSearch yet, we'll:
    1. Scan DynamoDB for all restaurants with matching cuisine
    2. Randomly select 3
    
    Note: This is inefficient for large datasets but works fine for 1,327 items
    When we add OpenSearch, we'll query it for IDs first
    
    Args:
        cuisine: Cuisine type (e.g., 'Japanese')
        count: Number of recommendations to return
    
    Returns:
        List of restaurant dictionaries
    """
    
    table = dynamodb.Table(DYNAMODB_TABLE)
    
    try:
        # Scan table for matching cuisine
        # FilterExpression = only return items where Cuisine matches
        response = table.scan(
            FilterExpression='Cuisine = :cuisine',
            ExpressionAttributeValues={':cuisine': cuisine}
        )
        
        restaurants = response.get('Items', [])
        
        if not restaurants:
            print(f"No {cuisine} restaurants found")
            return []
        
        # Randomly select 'count' restaurants
        selected = random.sample(restaurants, min(count, len(restaurants)))
        
        # Convert Decimal to float for email formatting
        for restaurant in selected:
            if 'Rating' in restaurant:
                restaurant['Rating'] = float(restaurant['Rating'])
        
        return selected
        
    except Exception as e:
        print(f"Error querying DynamoDB: {e}")
        return []

def send_email(to_email, restaurants, cuisine, num_people, dining_time):
    """
    Send restaurant recommendations via SES.
    
    Email format matches assignment example:
    "Hello! Here are my Japanese restaurant suggestions for 2 people,
    for today at 7 pm:
    1. Sushi Nakazawa, located at 23 Commerce St
    2. Jin Ramen, located at 3183 Broadway
    3. Nikko, located at 1280 Amsterdam Ave
    
    Enjoy your meal!"
    
    Args:
        to_email: Recipient email
        restaurants: List of restaurant dicts
        cuisine: Cuisine type
        num_people: Party size
        dining_time: When dining
    """
    
    # Build restaurant list
    restaurant_list = []
    for i, restaurant in enumerate(restaurants, 1):
        name = restaurant.get('Name', 'Unknown')
        address = restaurant.get('Address', 'Address not available')
        restaurant_list.append(f"{i}. {name}, located at {address}")
    
    # Format email body
    email_body = f"""Hello! Here are my {cuisine} restaurant suggestions for {num_people} people, for {dining_time}:

{chr(10).join(restaurant_list)}

Enjoy your meal!"""
    
    # Send via SES
    try:
        response = ses.send_email(
            Source=FROM_EMAIL,  # Must be verified in SES
            Destination={'ToAddresses': [to_email]},
            Message={
                'Subject': {
                    'Data': f'{cuisine} Restaurant Recommendations',
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