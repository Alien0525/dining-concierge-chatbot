"""
LF1 - Lex Code Hook with Conversation Memory
"""

import json
import boto3
from datetime import datetime
import os
import hashlib

# Clients
sqs = boto3.client('sqs')
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')

# Configuration
SQS_QUEUE_URL = os.environ.get('SQS_QUEUE_URL')
USER_PREFS_TABLE = 'user-preferences'

def lambda_handler(event, context):
    """
    Lex V2 code hook handler with memory
    """
    
    print(f"Received event: {json.dumps(event)}")
    
    intent_name = event['sessionState']['intent']['name']
    invocation_source = event['invocationSource']
    session_id = event['sessionId']
    
    # Route to handlers
    if intent_name == 'GreetingIntent':
        return handle_greeting(event, session_id)
    
    elif intent_name == 'ThankYouIntent':
        return close(event, 'Fulfilled', "You're welcome!")
    
    elif intent_name == 'DiningSuggestionsIntent':
        return handle_dining_suggestions(event, invocation_source, session_id)
    
    return close(event, 'Failed', 'I did not understand that.')


def handle_greeting(event, session_id):
    """
    Enhanced greeting with personalization based on history
    """
    
    # Try to get user's last search
    user_id = get_user_id(session_id)
    last_search = get_user_preferences(user_id)
    
    if last_search:
        # Personalized greeting
        cuisine = last_search.get('cuisine', '')
        location = last_search.get('location', '')
        
        message = f"Welcome back! Last time you searched for {cuisine} food in {location}. Would you like the same, or something different today?"
    else:
        # First-time greeting
        message = "Hi there! I can help you find restaurants in the NYC area (Manhattan, Brooklyn, Queens, Bronx, Staten Island, Jersey City, Hoboken, and Long Island City). What are you looking for today?"
    
    return close(event, 'Fulfilled', message)


def handle_dining_suggestions(event, invocation_source, session_id):
    """
    Handle DiningSuggestionsIntent with memory
    """
    
    slots = event['sessionState']['intent']['slots']
    
    # DialogCodeHook - validate slots
    if invocation_source == 'DialogCodeHook':
        validation_result = validate_slots(slots)
        
        if not validation_result['isValid']:
            return elicit_slot(
                event,
                validation_result['violatedSlot'],
                validation_result['message']
            )
        
        return delegate(event)
    
    # FulfillmentCodeHook - save preferences and push to SQS
    elif invocation_source == 'FulfillmentCodeHook':
        # Extract slot values
        location = get_slot_value(slots, 'Location')
        cuisine = get_slot_value(slots, 'Cuisine')
        dining_time = get_slot_value(slots, 'DiningTime')
        num_people = get_slot_value(slots, 'NumberOfPeople')
        email = get_slot_value(slots, 'Email')
        
        # Save user preferences for next time
        user_id = get_user_id(session_id)
        save_user_preferences(user_id, {
            'location': location,
            'cuisine': cuisine,
            'num_people': num_people,
            'last_search_time': datetime.now().isoformat()
        })
        
        # Push to SQS
        message_body = {
            'location': location,
            'cuisine': cuisine,
            'dining_time': dining_time,
            'num_people': num_people,
            'email': email,
            'timestamp': datetime.now().isoformat()
        }
        
        try:
            sqs.send_message(
                QueueUrl=SQS_QUEUE_URL,
                MessageBody=json.dumps(message_body)
            )
            print(f"Sent message to SQS: {message_body}")
        except Exception as e:
            print(f"Error sending to SQS: {e}")
        
        return close(event, 'Fulfilled', "You're all set. Expect my suggestions shortly! Have a good day.")


def get_user_id(session_id):
    """
    Generate consistent user ID from session ID
    """
    return hashlib.md5(session_id.encode()).hexdigest()[:16]


def get_user_preferences(user_id):
    """
    Retrieve user's last search preferences from DynamoDB
    
    Returns:
        dict or None: User preferences if found
    """
    try:
        table = dynamodb.Table(USER_PREFS_TABLE)
        response = table.get_item(Key={'UserId': user_id})
        
        if 'Item' in response:
            return response['Item']
        return None
    except Exception as e:
        print(f"Error getting user preferences: {e}")
        return None


def save_user_preferences(user_id, preferences):
    """
    Save user's search preferences to DynamoDB
    
    Args:
        user_id: Unique user identifier
        preferences: Dict with location, cuisine, etc.
    """
    try:
        table = dynamodb.Table(USER_PREFS_TABLE)
        
        item = {
            'UserId': user_id,
            **preferences
        }
        
        table.put_item(Item=item)
        print(f"Saved preferences for user {user_id}")
    except Exception as e:
        print(f"Error saving user preferences: {e}")


def validate_slots(slots):
    """
    Validate slot values
    """
    
    location = get_slot_value(slots, 'Location')
    cuisine = get_slot_value(slots, 'Cuisine')
    num_people = get_slot_value(slots, 'NumberOfPeople')
    email = get_slot_value(slots, 'Email')
    
    # Validate location
    valid_locations = [
        'manhattan', 'brooklyn', 'queens', 'bronx', 'staten island',
        'jersey city', 'hoboken', 'long island city'
    ]
    
    if location:
        location_lower = location.lower()
        if not any(valid_loc in location_lower for valid_loc in valid_locations):
            return {
                'isValid': False,
                'violatedSlot': 'Location',
                'message': 'Sorry, I only have suggestions for Manhattan, Brooklyn, Queens, Bronx, Staten Island, Jersey City, Hoboken, or Long Island City.'
            }
    
    # Validate cuisine
    valid_cuisines = [
        'japanese', 'italian', 'chinese', 'mexican', 'indian', 'thai', 'korean',
        'french', 'mediterranean', 'american', 'vietnamese', 'spanish'
    ]
    
    if cuisine:
        if cuisine.lower() not in valid_cuisines:
            return {
                'isValid': False,
                'violatedSlot': 'Cuisine',
                'message': f"Sorry, I don't have suggestions for {cuisine}. Try Japanese, Italian, Chinese, Mexican, Indian, Thai, Korean, French, Mediterranean, American, Vietnamese, or Spanish."
            }
    
    # Validate number of people
    if num_people:
        try:
            num = int(num_people)
            if num < 1 or num > 20:
                return {
                    'isValid': False,
                    'violatedSlot': 'NumberOfPeople',
                    'message': 'Please enter a number between 1 and 20.'
                }
        except:
            return {
                'isValid': False,
                'violatedSlot': 'NumberOfPeople',
                'message': 'Please enter a valid number.'
            }
    
    # Basic email validation
    if email:
        if '@' not in email or '.' not in email:
            return {
                'isValid': False,
                'violatedSlot': 'Email',
                'message': 'Please enter a valid email address.'
            }
    
    return {'isValid': True}


def get_slot_value(slots, slot_name):
    """
    Extract slot value from Lex V2 slot structure
    """
    if slots.get(slot_name) and slots[slot_name].get('value'):
        slot_value = slots[slot_name]['value']
        
        if 'interpretedValue' in slot_value:
            return slot_value['interpretedValue']
        elif 'originalValue' in slot_value:
            return slot_value['originalValue']
        elif 'resolvedValues' in slot_value and slot_value['resolvedValues']:
            return slot_value['resolvedValues'][0]
    
    return None


def delegate(event):
    """Tell Lex to continue collecting slots"""
    return {
        'sessionState': {
            'dialogAction': {'type': 'Delegate'},
            'intent': event['sessionState']['intent']
        }
    }


def elicit_slot(event, slot_to_elicit, message):
    """Ask for a specific slot again"""
    return {
        'sessionState': {
            'dialogAction': {
                'type': 'ElicitSlot',
                'slotToElicit': slot_to_elicit
            },
            'intent': event['sessionState']['intent']
        },
        'messages': [
            {
                'contentType': 'PlainText',
                'content': message
            }
        ]
    }


def close(event, fulfillment_state, message):
    """Close the intent"""
    return {
        'sessionState': {
            'dialogAction': {'type': 'Close'},
            'intent': {
                'name': event['sessionState']['intent']['name'],
                'slots': event['sessionState']['intent']['slots'],
                'state': fulfillment_state
            }
        },
        'messages': [
            {
                'contentType': 'PlainText',
                'content': message
            }
        ]
    }