"""
LF1 - Lex Code Hook
Handles intent validation and fulfillment for the Lex chatbot
"""

# check the confirmation section in the dining suggestions intent

#instance type - t3.small / medium
#general purpose - gp3
#data nodes - 1
#abs storage - 10 minimal
#opensearch -postman add few restaurants

import json
import boto3
from datetime import datetime
import os

# SQS client
sqs = boto3.client('sqs')
SQS_QUEUE_URL = os.environ.get('SQS_QUEUE_URL')

def lambda_handler(event, context):
    """
    Lex V2 code hook handler.
    """
    
    print(f"Received event: {json.dumps(event)}")
    
    # Get intent information
    intent_name = event['sessionState']['intent']['name']
    invocation_source = event['invocationSource']
    
    # Route to appropriate handler
    if intent_name == 'GreetingIntent':
        return close(event, 'Fulfilled', 'Hi there, how can I help?')
    
    elif intent_name == 'ThankYouIntent':
        return close(event, 'Fulfilled', "You're welcome!")
    
    elif intent_name == 'DiningSuggestionsIntent':
        return handle_dining_suggestions(event, invocation_source)
    
    # Fallback
    return close(event, 'Failed', 'I did not understand that.')


def handle_dining_suggestions(event, invocation_source):
    """
    Handle DiningSuggestionsIntent - collect slots and validate
    """
    
    slots = event['sessionState']['intent']['slots']
    
    # DialogCodeHook - validate slots as user provides them
    if invocation_source == 'DialogCodeHook':
        # Validate slots
        validation_result = validate_slots(slots)
        
        if not validation_result['isValid']:
            # Invalid slot - ask again
            return elicit_slot(
                event,
                validation_result['violatedSlot'],
                validation_result['message']
            )
        
        # All provided slots are valid - continue collecting
        return delegate(event)
    
    # FulfillmentCodeHook - all slots collected, push to SQS
    elif invocation_source == 'FulfillmentCodeHook':
        # Extract slot values
        location = get_slot_value(slots, 'Location')
        cuisine = get_slot_value(slots, 'Cuisine')
        dining_time = get_slot_value(slots, 'DiningTime')
        num_people = get_slot_value(slots, 'NumberOfPeople')
        email = get_slot_value(slots, 'Email')
        
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


def validate_slots(slots):
    """
    Validate slot values
    """
    
    # Extract slot values first (THIS WAS MISSING)
    location = get_slot_value(slots, 'Location')
    cuisine = get_slot_value(slots, 'Cuisine')
    num_people = get_slot_value(slots, 'NumberOfPeople')
    email = get_slot_value(slots, 'Email')
    
    # Now validate them
    # Validate location (expanded to multiple areas)
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
    Handles different slot value formats
    """
    if slots.get(slot_name) and slots[slot_name].get('value'):
        slot_value = slots[slot_name]['value']
        
        # Try different value fields in order of preference
        if 'interpretedValue' in slot_value:
            return slot_value['interpretedValue']
        elif 'originalValue' in slot_value:
            return slot_value['originalValue']
        elif 'resolvedValues' in slot_value and slot_value['resolvedValues']:
            return slot_value['resolvedValues'][0]
    
    return None


def delegate(event):
    """
    Tell Lex to continue collecting slots
    """
    return {
        'sessionState': {
            'dialogAction': {
                'type': 'Delegate'
            },
            'intent': event['sessionState']['intent']
        }
    }


def elicit_slot(event, slot_to_elicit, message):
    """
    Ask for a specific slot again
    """
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
    """
    Close the intent
    """
    return {
        'sessionState': {
            'dialogAction': {
                'type': 'Close'
            },
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