"""
LF1 - Enhanced Lex Code Hook with Smart Conversation Memory
Handles: repeat searches, partial changes, date collection, email pre-fill
FIXED: Handles optional slots correctly
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
    Lex V2 code hook handler with enhanced memory
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
    
    elif intent_name == 'RepeatLastSearchIntent':
        return handle_repeat_search(event, session_id)
    
    elif intent_name == 'DiningSuggestionsIntent':
        return handle_dining_suggestions(event, invocation_source, session_id)
    
    return close(event, 'Failed', 'I did not understand that.')


def handle_greeting(event, session_id):
    """
    Enhanced greeting with personalization and action buttons
    """
    
    # Try to get user's last search
    user_id = get_user_id(session_id)
    last_search = get_user_preferences(user_id)
    
    if last_search:
        # Personalized greeting with options
        cuisine = last_search.get('cuisine', '')
        location = last_search.get('location', '')
        
        message = f"Welcome back! Last time you searched for {cuisine} food in {location}. Would you like the same, or something different today?"
    else:
        # First-time greeting
        message = "Hi there! I can help you find restaurants in and around NYC. What are you looking for today?"
    
    return close(event, 'Fulfilled', message)

def handle_repeat_search(event, session_id):
    slots = event['sessionState']['intent']['slots']
    invocation_source = event['invocationSource']
    session_attributes = event['sessionState'].get('sessionAttributes', {})

    user_id = get_user_id(session_id)
    last_search = get_user_preferences(user_id)

    input_transcript = event.get('inputTranscript', '').lower()
    
    different_keywords = ['different', 'new', 'no', 'nope', 'change', 'something else']
    same_keywords = ['same', 'yes', 'yeah', 'repeat', 'again']
    
    wants_different = any(kw in input_transcript for kw in different_keywords)
    wants_same = any(kw in input_transcript for kw in same_keywords)
    
    # Only use the session flag if user didn't explicitly say "same" this turn
    previously_different = (
        session_attributes.get('wants_different') == 'true' and not wants_same
    )

    if wants_different or previously_different:
        location = get_slot_value(slots, 'Location')
        
        if not location:
            return {
                'sessionState': {
                    'dialogAction': {
                        'type': 'ElicitSlot',
                        'slotToElicit': 'Location'
                    },
                    'intent': {
                        'name': 'DiningSuggestionsIntent',
                        'slots': {
                            'Location': None,
                            'Cuisine': None,
                            'DiningDate': None,
                            'DiningTime': None,
                            'NumberOfPeople': None,
                            'Email': None
                        },
                        'state': 'InProgress',
                        'confirmationState': 'None'
                    },
                    'sessionAttributes': {**session_attributes, 'wants_different': 'true'}
                },
                'messages': [{
                    'contentType': 'PlainText',
                    'content': 'Sure! Which area would you like to dine in? (Manhattan, Brooklyn, Queens, Bronx, Staten Island, Jersey City, Hoboken, or Long Island City)'
                }]
            }
        else:
            return {
                'sessionState': {
                    'dialogAction': {
                        'type': 'ElicitSlot',
                        'slotToElicit': 'Cuisine'
                    },
                    'intent': {
                        'name': 'DiningSuggestionsIntent',
                        'slots': {
                            'Location': create_slot_value(location),
                            'Cuisine': None,
                            'DiningDate': None,
                            'DiningTime': None,
                            'NumberOfPeople': None,
                            'Email': None
                        },
                        'state': 'InProgress',
                        'confirmationState': 'None'
                    },
                    'sessionAttributes': {**session_attributes, 'wants_different': 'false'}
                },
                'messages': [{
                    'contentType': 'PlainText',
                    'content': 'What cuisine would you like to try?'
                }]
            }

    # Clear the flag for same/repeat path
    session_attributes = {**session_attributes, 'wants_different': 'false'}

    if not last_search:
        return close(event, 'Fulfilled',
            "Hi there! I can help you find restaurants in and around NYC. What are you looking for today?")

    if invocation_source == 'DialogCodeHook':
        location    = get_slot_value(slots, 'Location')    or last_search.get('location')
        cuisine     = get_slot_value(slots, 'Cuisine')     or last_search.get('cuisine')
        num_people  = get_slot_value(slots, 'NumberOfPeople') or last_search.get('num_people', '2')
        email       = get_slot_value(slots, 'Email')       or last_search.get('email')
        dining_date = get_slot_value(slots, 'DiningDate')  or 'today'
        dining_time = get_slot_value(slots, 'DiningTime')  or 'tonight'

        if not location or not cuisine or not email:
            return close(event, 'Failed',
                "Sorry, I'm missing some required information. Please try again.")

        save_user_preferences(user_id, {
            'location':         location,
            'cuisine':          cuisine,
            'email':            email,
            'num_people':       num_people,
            'last_search_time': datetime.now().isoformat()
        })

        message_body = {
            'location':    location,
            'cuisine':     cuisine,
            'dining_date': dining_date,
            'dining_time': dining_time,
            'num_people':  num_people,
            'email':       email,
            'timestamp':   datetime.now().isoformat()
        }

        try:
            sqs.send_message(QueueUrl=SQS_QUEUE_URL, MessageBody=json.dumps(message_body))
            print(f"Sent repeat-search to SQS: {message_body}")
        except Exception as e:
            print(f"Error sending to SQS: {e}")
            return close(event, 'Failed', "Sorry, something went wrong. Please try again.")

        return close(event, 'Fulfilled',
            f"You're all set! I'll send {cuisine} restaurant suggestions in {location} to {email} shortly. Have a great day!")

    return close(event, 'Failed', "Something went wrong. Please try again.")

def handle_dining_suggestions(event, invocation_source, session_id):
    """
    Handle new DiningSuggestionsIntent with date support
    """
    
    slots = event['sessionState']['intent']['slots']
    
    # DialogCodeHook - validate slots
    if invocation_source == 'DialogCodeHook':
        # Validate slots
        validation_result = validate_slots(slots)
        
        if not validation_result['isValid']:
            # Can't use elicit_slot for optional slots
            return close(
                event, 
                'Failed', 
                validation_result['message'] + " Please try again."
            )
        
        return delegate(event)
    
    # FulfillmentCodeHook - save preferences and push to SQS
    elif invocation_source == 'FulfillmentCodeHook':
        # Extract slot values
        location = get_slot_value(slots, 'Location')
        cuisine = get_slot_value(slots, 'Cuisine')
        dining_date = get_slot_value(slots, 'DiningDate')
        dining_time = get_slot_value(slots, 'DiningTime')
        num_people = get_slot_value(slots, 'NumberOfPeople')
        email = get_slot_value(slots, 'Email')
        
        # Save user preferences for next time
        user_id = get_user_id(session_id)
        save_user_preferences(user_id, {
            'location': location,
            'cuisine': cuisine,
            'email': email,
            'num_people': num_people,
            'last_search_time': datetime.now().isoformat()
        })
        
        # Push to SQS
        message_body = {
            'location': location,
            'cuisine': cuisine,
            'dining_date': dining_date,
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


def create_slot_value(value):
    """Create a proper slot value structure for Lex"""
    if not value:
        return None
    
    return {
        'shape': 'Scalar',
        'value': {
            'originalValue': str(value),
            'interpretedValue': str(value),
            'resolvedValues': [str(value)]
        }
    }


def get_user_id(session_id):
    """Generate consistent user ID from session ID"""
    return hashlib.md5(session_id.encode()).hexdigest()[:16]


def get_user_preferences(user_id):
    """Retrieve user's last search preferences from DynamoDB"""
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
    """Save user's search preferences to DynamoDB"""
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
    """Validate slot values"""
    
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
    """Extract slot value from Lex V2 slot structure"""
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
            'intent': event['sessionState']['intent'],
            'sessionAttributes': event['sessionState'].get('sessionAttributes', {})
        }
    }


def close(event, fulfillment_state, message):
    """Close the intent"""
    return {
        'sessionState': {
            'dialogAction': {'type': 'Close'},
            'intent': {
                'name': event['sessionState']['intent']['name'],
                'slots': event['sessionState']['intent'].get('slots', {}),
                'state': fulfillment_state
            },
            'sessionAttributes': event['sessionState'].get('sessionAttributes', {})
        },
        'messages': [
            {
                'contentType': 'PlainText',
                'content': message
            }
        ]
    }