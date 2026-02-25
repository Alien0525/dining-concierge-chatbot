"""
LF1 - Lex Code Hook with Conversation Memory
Handles: GreetingIntent, ThankYouIntent, DiningSuggestionsIntent, RepeatLastSearchIntent
"""

import json
import boto3
from datetime import datetime
import os
import hashlib

sqs      = boto3.client('sqs')
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')

SQS_QUEUE_URL    = os.environ.get('SQS_QUEUE_URL')
USER_PREFS_TABLE = 'user-preferences'


# ─────────────────────────────────────────────────────────────────────────────
def lambda_handler(event, context):
    print(f"Event: {json.dumps(event)}")

    intent_name       = event['sessionState']['intent']['name']
    invocation_source = event['invocationSource']
    session_id        = event['sessionId']

    if intent_name == 'GreetingIntent':
        return handle_greeting(event, session_id)

    elif intent_name == 'ThankYouIntent':
        return close(event, 'Fulfilled', "You're welcome!")

    elif intent_name == 'RepeatLastSearchIntent':
        return handle_repeat_search(event, session_id)

    elif intent_name == 'DiningSuggestionsIntent':
        return handle_dining_suggestions(event, invocation_source, session_id)

    return close(event, 'Failed', "I didn't understand that.")


# ─────────────────────────────────────────────────────────────────────────────
def handle_greeting(event, session_id):
    user_id     = get_user_id(session_id)
    last_search = get_user_preferences(user_id)

    if last_search:
        cuisine  = last_search.get('cuisine', '')
        location = last_search.get('location', '')
        message  = (
            f"Welcome back! Last time you searched for {cuisine} food in {location}. "
            f"Would you like the same, or something different today?"
        )
    else:
        message = "Hi there! How can I help you today?"

    return close(event, 'Fulfilled', message)


# ─────────────────────────────────────────────────────────────────────────────
def handle_repeat_search(event, session_id):
    """
    Called when Lex routes to RepeatLastSearchIntent (user replied to greeting).

    KEY FIX:
    When the user wants something different, we cannot simply switch intents
    inside a DialogCodeHook — Lex will ignore an ElicitSlot for a different intent
    and re-invoke this same hook. Instead we:
      1. Detect "different" from inputTranscript
      2. Return a Close (Fulfilled) on RepeatLastSearchIntent
         with a session attribute 'pending_dining_suggestions=true'
      3. Ask the user for their location as a plain message
      4. The user's next message ("Manhattan") will be routed by Lex to
         DiningSuggestionsIntent normally (or we guide them with the next turn)

    When the user wants the SAME, we send the previous prefs straight to SQS.
    """
    slots              = event['sessionState']['intent']['slots']
    session_attributes = event['sessionState'].get('sessionAttributes', {})
    input_transcript   = event.get('inputTranscript', '').lower()

    user_id     = get_user_id(session_id)
    last_search = get_user_preferences(user_id)

    # ── Keyword detection ────────────────────────────────────────────────────
    different_keywords = ['different', 'new', 'no', 'nope', 'change', 'something else', 'something different']
    same_keywords      = ['same', 'yes', 'yeah', 'yep', 'sure', 'repeat', 'again', 'ok', 'okay']

    wants_different = any(kw in input_transcript for kw in different_keywords)
    wants_same      = any(kw in input_transcript for kw in same_keywords)

    # ── "Something different" path ───────────────────────────────────────────
    # Close this intent cleanly and instruct Lex to start DiningSuggestionsIntent
    # by setting a session attribute. The user's very next message will be treated
    # as the start of a fresh DiningSuggestionsIntent conversation.
    if wants_different:
        return {
            'sessionState': {
                'dialogAction': {'type': 'Close'},
                'intent': {
                    'name': 'RepeatLastSearchIntent',
                    'state': 'Fulfilled'
                },
                'sessionAttributes': {
                    **session_attributes,
                    'wants_different': 'true'
                }
            },
            'messages': [{
                'contentType': 'PlainText',
                'content': (
                    'Sure! Let\'s find something new. '
                    'Which area would you like to dine in? '
                    '(Manhattan, Brooklyn, Queens, Bronx, Staten Island, '
                    'Jersey City, Hoboken, or Long Island City)'
                )
            }]
        }

    # ── No clear signal yet — ask again ─────────────────────────────────────
    if not wants_same and not wants_different:
        return {
            'sessionState': {
                'dialogAction': {'type': 'Close'},
                'intent': {
                    'name': 'RepeatLastSearchIntent',
                    'state': 'Fulfilled'
                },
                'sessionAttributes': session_attributes
            },
            'messages': [{
                'contentType': 'PlainText',
                'content': (
                    'Sorry, I didn\'t catch that. '
                    'Would you like the same as last time, or something different?'
                )
            }]
        }

    # ── "Same" path ──────────────────────────────────────────────────────────
    if not last_search:
        return close(event, 'Fulfilled',
            "I don't have a previous search on file. What are you looking for today?")

    location   = last_search.get('location')
    cuisine    = last_search.get('cuisine')
    email      = last_search.get('email')
    num_people = last_search.get('num_people', '2')

    if not (location and cuisine and email):
        return close(event, 'Failed',
            "Sorry, I'm missing some details from your last search. Let's start fresh.")

    message_body = {
        'location':    location,
        'cuisine':     cuisine,
        'dining_date': 'today',
        'dining_time': 'tonight',
        'num_people':  num_people,
        'email':       email,
        'timestamp':   datetime.now().isoformat()
    }

    try:
        sqs.send_message(QueueUrl=SQS_QUEUE_URL, MessageBody=json.dumps(message_body))
        print(f"Sent repeat-same to SQS: {message_body}")
    except Exception as e:
        print(f"SQS error: {e}")
        return close(event, 'Failed', "Sorry, something went wrong. Please try again.")

    return close(event, 'Fulfilled',
        f"You're all set! I'll send {cuisine} restaurant suggestions in {location} "
        f"to {email} shortly. Have a great day!")


# ─────────────────────────────────────────────────────────────────────────────
def handle_dining_suggestions(event, invocation_source, session_id):
    slots = event['sessionState']['intent']['slots']

    if invocation_source == 'DialogCodeHook':
        validation = validate_slots(slots)
        if not validation['isValid']:
            return close(event, 'Failed', validation['message'] + " Please try again.")
        return delegate(event)

    elif invocation_source == 'FulfillmentCodeHook':
        location   = get_slot_value(slots, 'Location')
        cuisine    = get_slot_value(slots, 'Cuisine')
        dining_date = get_slot_value(slots, 'DiningDate')
        dining_time = get_slot_value(slots, 'DiningTime')
        num_people  = get_slot_value(slots, 'NumberOfPeople')
        email       = get_slot_value(slots, 'Email')

        user_id = get_user_id(session_id)
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
            print(f"Sent to SQS: {message_body}")
        except Exception as e:
            print(f"SQS error: {e}")

        return close(event, 'Fulfilled',
            "You're all set. Expect my suggestions shortly! Have a good day.")


# ─────────────────────────────────────────────────────────────────────────────
#  VALIDATION
# ─────────────────────────────────────────────────────────────────────────────
def validate_slots(slots):
    location   = get_slot_value(slots, 'Location')
    cuisine    = get_slot_value(slots, 'Cuisine')
    num_people = get_slot_value(slots, 'NumberOfPeople')
    email      = get_slot_value(slots, 'Email')

    valid_locations = [
        'manhattan', 'brooklyn', 'queens', 'bronx', 'staten island',
        'jersey city', 'hoboken', 'long island city'
    ]

    if location:
        if not any(v in location.lower() for v in valid_locations):
            return {
                'isValid': False,
                'message': 'Sorry, I only have suggestions for Manhattan, Brooklyn, Queens, '
                           'Bronx, Staten Island, Jersey City, Hoboken, or Long Island City.'
            }

    valid_cuisines = [
        'japanese', 'italian', 'chinese', 'mexican', 'indian', 'thai',
        'korean', 'french', 'mediterranean', 'american', 'vietnamese', 'spanish'
    ]

    if cuisine and cuisine.lower() not in valid_cuisines:
        return {
            'isValid': False,
            'message': f"Sorry, I don't have suggestions for {cuisine}. "
                       f"Try Japanese, Italian, Chinese, Mexican, Indian, Thai, "
                       f"Korean, French, Mediterranean, American, Vietnamese, or Spanish."
        }

    if num_people:
        try:
            n = int(num_people)
            if not (1 <= n <= 20):
                return {'isValid': False, 'message': 'Please enter a number between 1 and 20.'}
        except ValueError:
            return {'isValid': False, 'message': 'Please enter a valid number of people.'}

    if email and ('@' not in email or '.' not in email):
        return {'isValid': False, 'message': 'Please enter a valid email address.'}

    return {'isValid': True}


# ─────────────────────────────────────────────────────────────────────────────
#  DYNAMODB HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def get_user_id(session_id):
    return hashlib.md5(session_id.encode()).hexdigest()[:16]


def get_user_preferences(user_id):
    try:
        table    = dynamodb.Table(USER_PREFS_TABLE)
        response = table.get_item(Key={'UserId': user_id})
        return response.get('Item')
    except Exception as e:
        print(f"DynamoDB get error: {e}")
        return None


def save_user_preferences(user_id, preferences):
    try:
        table = dynamodb.Table(USER_PREFS_TABLE)
        table.put_item(Item={'UserId': user_id, **preferences})
        print(f"Saved prefs for {user_id}")
    except Exception as e:
        print(f"DynamoDB save error: {e}")


# ─────────────────────────────────────────────────────────────────────────────
#  LEX RESPONSE HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def get_slot_value(slots, slot_name):
    s = slots.get(slot_name)
    if s and s.get('value'):
        v = s['value']
        return v.get('interpretedValue') or v.get('originalValue') or (
            v['resolvedValues'][0] if v.get('resolvedValues') else None
        )
    return None


def create_slot_value(value):
    if not value:
        return None
    return {
        'shape': 'Scalar',
        'value': {
            'originalValue':    str(value),
            'interpretedValue': str(value),
            'resolvedValues':   [str(value)]
        }
    }


def delegate(event):
    return {
        'sessionState': {
            'dialogAction': {'type': 'Delegate'},
            'intent':       event['sessionState']['intent'],
            'sessionAttributes': event['sessionState'].get('sessionAttributes', {})
        }
    }


def close(event, fulfillment_state, message):
    return {
        'sessionState': {
            'dialogAction': {'type': 'Close'},
            'intent': {
                'name':  event['sessionState']['intent']['name'],
                'slots': event['sessionState']['intent'].get('slots', {}),
                'state': fulfillment_state
            },
            'sessionAttributes': event['sessionState'].get('sessionAttributes', {})
        },
        'messages': [{
            'contentType': 'PlainText',
            'content':     message
        }]
    }