"""
LF2 - Enhanced Queue Worker
Polls SQS, queries DynamoDB, sends email via SES
"""

import json
import boto3
import random
import os
from decimal import Decimal
from datetime import datetime

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
    """
    
    # Pull messages from SQS
    response = sqs.receive_message(
        QueueUrl=SQS_QUEUE_URL,
        MaxNumberOfMessages=10,
        WaitTimeSeconds=0
    )
    
    messages = response.get('Messages', [])
    
    if not messages:
        print("No messages in queue")
        return {'statusCode': 200, 'body': 'No messages to process'}
    
    print(f"Processing {len(messages)} messages")
    
    for message in messages:
        try:
            body = json.loads(message['Body'])
            
            # Extract user preferences
            cuisine = body.get('cuisine', '').capitalize()
            location = body.get('location', 'Manhattan')
            num_people = body.get('num_people', '2')
            dining_date = body.get('dining_date', 'today')
            dining_time = body.get('dining_time', 'tonight')
            email = body.get('email')
            
            print(f"Request: {cuisine} in {location} for {num_people} people on {dining_date} at {dining_time}")
            
            # Get restaurant recommendations
            restaurants = get_restaurant_recommendations(cuisine, location, count=5)
            
            # Send email
            if restaurants and email:
                send_email(email, restaurants, cuisine, location, num_people, dining_date, dining_time)
            
            # Delete message from queue
            sqs.delete_message(
                QueueUrl=SQS_QUEUE_URL,
                ReceiptHandle=message['ReceiptHandle']
            )
            
            print(f"Successfully processed request for {email}")
            
        except Exception as e:
            print(f"Error processing message: {e}")
            import traceback
            print(traceback.format_exc())
    
    return {'statusCode': 200, 'body': f'Processed {len(messages)} messages'}


def get_restaurant_recommendations(cuisine, location, count=5):
    """
    Query DynamoDB for restaurants matching cuisine and location
    Returns top results sorted by rating
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
        
        # Scan with filter for cuisine and area
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
        
        # Sort by rating (descending)
        restaurants.sort(key=lambda x: float(x.get('Rating', 0)), reverse=True)
        
        # Take top N restaurants
        selected = restaurants[:min(count, len(restaurants))]
        
        # Convert Decimal to float for JSON serialization
        for restaurant in selected:
            if 'Rating' in restaurant:
                restaurant['Rating'] = float(restaurant['Rating'])
            if 'Latitude' in restaurant:
                restaurant['Latitude'] = float(restaurant['Latitude'])
            if 'Longitude' in restaurant:
                restaurant['Longitude'] = float(restaurant['Longitude'])
        
        print(f"Returning top {len(selected)} restaurants by rating")
        
        return selected
        
    except Exception as e:
        print(f"Error querying DynamoDB: {e}")
        import traceback
        print(traceback.format_exc())
        return []


def na(val, fallback='NA'):
    """Return value or NA if missing/None/empty."""
    if val is None or str(val).strip() in ('', 'None', 'N/A', 'null'):
        return fallback
    return str(val).strip()


def send_email(to_email, restaurants, cuisine, location, num_people, dining_date, dining_time):
    """
    Send restaurant recommendations via SES using HTML format.
    - Address is hyperlinked to Google Maps (embedded in the text)
    - Missing fields shown as NA
    """

    # ── Format time ──────────────────────────────────────────────────────────
    try:
        ts = str(dining_time)
        if ts and ':' in ts and 'PM' not in ts.upper() and 'AM' not in ts.upper():
            hour, minute = ts.split(':')[:2]
            hour = int(hour)
            suffix = 'PM' if hour >= 12 else 'AM'
            hour12 = hour % 12 or 12
            time_str = f"{hour12}:{minute} {suffix}"
        else:
            time_str = na(dining_time, 'tonight')
    except Exception:
        time_str = na(dining_time, 'tonight')

    # ── Format date ───────────────────────────────────────────────────────────
    dl = str(dining_date).lower() if dining_date else ''
    if dl == 'today':    date_str = 'today'
    elif dl == 'tomorrow': date_str = 'tomorrow'
    elif dl:             date_str = f"on {dining_date}"
    else:                date_str = 'today'

    # ── Build restaurant entries (HTML) ───────────────────────────────────────
    restaurant_html_list = []
    restaurant_text_list = []
    
    for i, r in enumerate(restaurants, 1):
        name         = na(r.get('Name'))
        address_raw  = na(r.get('Address'))
        area         = na(r.get('Area', location))
        rating       = na(r.get('Rating'))
        review_count = na(r.get('ReviewCount'), '0')
        phone        = na(r.get('Phone'))
        lat          = r.get('Latitude')
        lon          = r.get('Longitude')

        # Full address string
        full_address = f"{address_raw}, {area}" if address_raw != 'NA' else area

        # Star rating
        try:
            stars = '⭐' * min(5, int(float(rating)))
        except Exception:
            stars = ''

        # HTML version with embedded link
        if lat and lon:
            try:
                maps_url = f"https://maps.google.com/?q={float(lat)},{float(lon)}"
                address_html = f'<a href="{maps_url}" style="color: #4285F4; text-decoration: none;">{full_address}</a>'
            except Exception:
                address_html = full_address
        else:
            address_html = full_address

        # HTML entry
        html_entry = f"""
        <div style="margin-bottom: 20px; padding: 15px; background-color: #f9f9f9; border-left: 3px solid #C9A96E; border-radius: 4px;">
            <div style="font-size: 16px; font-weight: bold; color: #333; margin-bottom: 8px;">
                {i}. {name} {stars}
            </div>
            <div style="color: #666; margin-bottom: 4px;">
                ({rating}/5, {review_count} reviews)
            </div>
            <div style="margin-top: 8px; color: #555;">
                📍 {address_html}
            </div>
            <div style="margin-top: 4px; color: #555;">
                📞 {phone}
            </div>
        </div>
        """
        restaurant_html_list.append(html_entry)

        # Plain text version (fallback)
        text_entry = (
            f"{i}. {name} {stars} ({rating}/5, {review_count} reviews)\n"
            f"   📍 {full_address}\n"
            f"   📞 {phone}\n"
        )
        restaurant_text_list.append(text_entry)

    # ── Compose HTML email body ───────────────────────────────────────────────
    html_body = f"""
    <html>
    <head>
        <meta charset="UTF-8">
    </head>
    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
        <div style="background-color: #131008; color: #EDE5D0; padding: 20px; border-radius: 8px 8px 0 0;">
            <h1 style="margin: 0; font-size: 24px; color: #C9A96E;">🍽️ Your Restaurant Recommendations</h1>
        </div>
        
        <div style="background-color: #ffffff; padding: 20px; border-radius: 0 0 8px 8px;">
            <p style="font-size: 16px; color: #333;">Hello!</p>
            
            <p style="font-size: 16px; color: #333;">
                Here are my top {len(restaurants)} <strong>{cuisine}</strong> restaurant recommendations 
                in <strong>{location}</strong> for <strong>{num_people} people</strong> {date_str} at <strong>{time_str}</strong>:
            </p>
            
            {''.join(restaurant_html_list)}
            
            <p style="margin-top: 30px; font-size: 16px; color: #333;">
                Enjoy your meal! 🍽️
            </p>
            
            <div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #ddd; font-size: 12px; color: #999;">
                Powered by Dining Concierge Chatbot
            </div>
        </div>
    </body>
    </html>
    """

    # ── Plain text fallback ───────────────────────────────────────────────────
    text_body = (
        f"Hello!\n\n"
        f"Here are my top {len(restaurants)} {cuisine} restaurant recommendations "
        f"in {location} for {num_people} people {date_str} at {time_str}:\n\n"
        + '\n'.join(restaurant_text_list) +
        f"\nEnjoy your meal! 🍽️\n\n---\nPowered by Dining Concierge Chatbot\n"
    )
    
    # Send via SES with both HTML and Text
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
                    'Html': {
                        'Data': html_body,
                        'Charset': 'UTF-8'
                    },
                    'Text': {
                        'Data': text_body,
                        'Charset': 'UTF-8'
                    }
                }
            }
        )
        print(f"Email sent to {to_email}, MessageId: {response['MessageId']}")
    
    except Exception as e:
        print(f"Error sending email: {e}")
        import traceback
        print(traceback.format_exc())
        raise