"""
LF1 - Lex Code Hook
Handles intent validation and fulfillment for the Lex chatbot
"""

import json
import boto3
import config
from datetime import datetime

sqs = boto3.client('sqs')
SQS_QUEUE_URL = config.SQS_QUEUE_URL

def lambda_handler(event, context):
    """
    Lex calls this function before responding to user.
    
    Flow:
    1. Lex identifies user intent (Greeting, ThankYou, DiningSuggestions)
    2. This function validates/processes the intent
    3. Returns instructions to Lex on how to respond
    
    Args:
        event: Contains intent name, slots, session attributes
        context: Lambda context
    
    Returns:
        Lex response directive (what to say, what to do next)
    """
    
    # Get intent information from Lex
    intent_name = event.get('currentIntent', {}).get('name')
    slots = event.get('currentIntent', {}).get('slots', {})
    
    # Route to appropriate handler based on intent
    if intent_name == 'GreetingIntent':
        return handle_greeting()
    
    elif intent_name == 'ThankYouIntent':
        return handle_thank_you()
    
    elif intent_name == 'DiningSuggestionsIntent':
        return handle_dining_suggestions(slots, event)
    
    # Fallback for unknown intents
    return {
        'dialogAction': {
            'type': 'Close',
            'fulfillmentState': 'Failed',
            'message': {
                'contentType': 'PlainText',
                'content': 'I did not understand that.'
            }
        }
    }

def handle_greeting():
    """
    Responds to greeting intent.
    Simple acknowledgment to start conversation.
    """
    return {
        'dialogAction': {
            'type': 'Close',
            'fulfillmentState': 'Fulfilled',
            'message': {
                'contentType': 'PlainText',
                'content': 'Hi there, how can I help?'
            }
        }
    }

def handle_thank_you():
    """
    Responds to thank you intent.
    Polite acknowledgment.
    """
    return {
        'dialogAction': {
            'type': 'Close',
            'fulfillmentState': 'Fulfilled',
            'message': {
                'contentType': 'PlainText',
                'content': "You're welcome!"
            }
        }
    }

def handle_dining_suggestions(slots, event):
    """
    Main intent - collects restaurant preferences and sends to SQS.
    
    Slots to collect:
    - Location: Where to dine (must be Manhattan)
    - Cuisine: Type of food (Japanese, Italian, etc.)
    - DiningTime: When to dine
    - NumberOfPeople: Party size
    - Email: Where to send recommendations
    
    Flow:
    1. Validate each slot as user provides it
    2. Once all collected, push to SQS
    3. Confirm to user
    """
    
    # Check if we're in validation or fulfillment
    invocation_source = event.get('invocationSource')
    
    if invocation_source == 'DialogCodeHook':
        # Lex is asking us to validate slots during conversation
        validation_result = validate_slots(slots)
        
        if not validation_result['isValid']:
            # Slot is invalid - tell Lex to re-prompt
            return {
                'dialogAction': {
                    'type': 'ElicitSlot',
                    'intentName': 'DiningSuggestionsIntent',
                    'slots': slots,
                    'slotToElicit': validation_result['violatedSlot'],
                    'message': {
                        'contentType': 'PlainText',
                        'content': validation_result['message']
                    }
                }
            }
        
        # All slots valid so far, continue collecting
        return {
            'dialogAction': {
                'type': 'Delegate',
                'slots': slots
            }
        }
    
    # All slots collected - fulfill the intent
    # Push request to SQS queue
    message_body = {
        'location': slots.get('Location'),
        'cuisine': slots.get('Cuisine'),
        'dining_time': slots.get('DiningTime'),
        'num_people': slots.get('NumberOfPeople'),
        'email': slots.get('Email'),
        'timestamp': datetime.now().isoformat()
    }
    
    # Push messages to SQS queue
    sqs.send_message(
        QueueUrl=SQS_QUEUE_URL,
        MessageBody=json.dumps(message_body)
    )
    
    return {
        'dialogAction': {
            'type': 'Close',
            'fulfillmentState': 'Fulfilled',
            'message': {
                'contentType': 'PlainText',
                'content': "You're all set. Expect my suggestions shortly! Have a good day."
            }
        }
    }

def validate_slots(slots):
    """
    Validates user input for each slot.
    
    Rules:
    - Location: Must be Manhattan
    - Cuisine: Must be one we have data for
    - DiningTime: Valid date/time format
    - NumberOfPeople: Positive number
    - Email: Basic email format check
    """
    
    location = slots.get('Location')
    cuisine = slots.get('Cuisine')
    num_people = slots.get('NumberOfPeople')
    email = slots.get('Email')
    
    # Validate location (Manhattan only)
    if location and location.lower() not in ['manhattan', 'nyc', 'new york']:
        return {
            'isValid': False,
            'violatedSlot': 'Location',
            'message': f"Sorry, I can't fulfill requests for {location}. Please enter Manhattan."
        }
    
    # Validate cuisine (must match our data)
    valid_cuisines = ['japanese', 'italian', 'chinese', 'mexican', 'indian', 'thai', 'korean']
    if cuisine and cuisine.lower() not in valid_cuisines:
        return {
            'isValid': False,
            'violatedSlot': 'Cuisine',
            'message': f"Sorry, I don't have suggestions for {cuisine}. Try Japanese, Italian, Chinese, Mexican, Indian, Thai, or Korean."
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
    if email and '@' not in email:
        return {
            'isValid': False,
            'violatedSlot': 'Email',
            'message': 'Please enter a valid email address.'
        }
    
    # All valid
    return {'isValid': True}