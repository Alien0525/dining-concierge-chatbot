"""
LF1 - Lex Code Hook with Conversation Memory
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


def lambda_handler(event, context):
    print(f"Event: {json.dumps(event)}")

    intent_name       = event['sessionState']['intent']['name']
    invocation_source = event['invocationSource']
    session_id        = event['sessionId']
    session_attrs     = event['sessionState'].get('sessionAttributes', {})

    # ── If we flagged "wants_different" in a previous turn,
    #    force into DiningSuggestionsIntent regardless of what Lex routed ──────
    if session_attrs.get('wants_different') == 'true' and \
       intent_name != 'DiningSuggestionsIntent':
        return elicit_dining_location(event, session_attrs)

    if intent_name == 'GreetingIntent':
        return handle_greeting(event, session_id)
    elif intent_name == 'ThankYouIntent':
        return close(event, 'Fulfilled', "You're welcome!")
    elif intent_name == 'RepeatLastSearchIntent':
        return handle_repeat_search(event, session_id)
    elif intent_name == 'DiningSuggestionsIntent':
        return handle_dining_suggestions(event, invocation_source, session_id)

    return close(event, 'Failed', "I didn't understand that. Could you rephrase?")


# ─────────────────────────────────────────────────────────────────────────────
def handle_greeting(event, session_id):
    session_attrs = event['sessionState'].get('sessionAttributes', {})

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
def elicit_dining_location(event, session_attrs):
    """
    Redirect into DiningSuggestionsIntent by eliciting the Location slot.
    Called when wants_different=true but Lex routed elsewhere.
    """
    # Clear the flag so we don't loop
    new_attrs = {**session_attrs, 'wants_different': 'false'}
    return {
        'sessionState': {
            'dialogAction': {
                'type': 'ElicitSlot',
                'slotToElicit': 'Location'
            },
            'intent': {
                'name': 'DiningSuggestionsIntent',
                'slots': {
                    'Location':      None,
                    'Cuisine':       None,
                    'DiningDate':    None,
                    'DiningTime':    None,
                    'NumberOfPeople':None,
                    'Email':         None
                },
                'state': 'InProgress',
                'confirmationState': 'None'
            },
            'sessionAttributes': new_attrs
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


# ─────────────────────────────────────────────────────────────────────────────
def handle_repeat_search(event, session_id):
    slots         = event['sessionState']['intent']['slots']
    session_attrs = event['sessionState'].get('sessionAttributes', {})
    transcript    = event.get('inputTranscript', '').lower().strip()

    user_id     = get_user_id(session_id)
    last_search = get_user_preferences(user_id)

    different_kw = ['different', 'new', 'no', 'nope', 'change', 'something else',
                    'something different', 'other']
    same_kw      = ['same', 'yes', 'yeah', 'yep', 'sure', 'repeat', 'again', 'ok', 'okay']

    wants_different = any(kw in transcript for kw in different_kw)
    wants_same      = any(kw in transcript for kw in same_kw)

    # ── Wants something different ─────────────────────────────────────────────
    if wants_different:
        # Set flag and elicit Location for DiningSuggestionsIntent
        new_attrs = {**session_attrs, 'wants_different': 'true'}
        return {
            'sessionState': {
                'dialogAction': {
                    'type': 'ElicitSlot',
                    'slotToElicit': 'Location'
                },
                'intent': {
                    'name': 'DiningSuggestionsIntent',
                    'slots': {
                        'Location':      None,
                        'Cuisine':       None,
                        'DiningDate':    None,
                        'DiningTime':    None,
                        'NumberOfPeople':None,
                        'Email':         None
                    },
                    'state': 'InProgress',
                    'confirmationState': 'None'
                },
                'sessionAttributes': new_attrs
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

    # ── No clear signal ───────────────────────────────────────────────────────
    if not wants_same:
        return close(event, 'Fulfilled',
            "Sorry, I didn't catch that. "
            "Would you like the same as last time, or something different?")

    # ── Wants same ────────────────────────────────────────────────────────────
    if not last_search:
        return close(event, 'Fulfilled',
            "I don't have a previous search on file. What are you looking for today?")

    location   = last_search.get('location', 'NA')
    cuisine    = last_search.get('cuisine', 'NA')
    email      = last_search.get('email', 'NA')
    num_people = last_search.get('num_people', '2')

    if not all([location, cuisine, email]) or 'NA' in [location, cuisine, email]:
        return close(event, 'Failed',
            "Sorry, I'm missing some details from your last search. Let's start fresh.")

    msg = {
        'location':    location,
        'cuisine':     cuisine,
        'dining_date': 'today',
        'dining_time': 'tonight',
        'num_people':  num_people,
        'email':       email,
        'timestamp':   datetime.now().isoformat()
    }

    try:
        sqs.send_message(QueueUrl=SQS_QUEUE_URL, MessageBody=json.dumps(msg))
        print(f"Repeat-same SQS: {msg}")
    except Exception as e:
        print(f"SQS error: {e}")
        return close(event, 'Failed', "Sorry, something went wrong. Please try again.")

    return close(event, 'Fulfilled',
        f"You're all set! I'll send {cuisine} restaurant suggestions in {location} "
        f"to {email} shortly. Have a great day!")


# ─────────────────────────────────────────────────────────────────────────────
def handle_dining_suggestions(event, invocation_source, session_id):
    slots         = event['sessionState']['intent']['slots']
    session_attrs = event['sessionState'].get('sessionAttributes', {})

    # Clear wants_different flag now that we're properly in DiningSuggestionsIntent
    if session_attrs.get('wants_different') == 'true':
        session_attrs = {**session_attrs, 'wants_different': 'false'}

    if invocation_source == 'DialogCodeHook':
        v = validate_slots(slots)
        if not v['isValid']:
            return close(event, 'Failed', v['message'] + " Please try again.")
        # Pass updated session attrs through delegate
        return {
            'sessionState': {
                'dialogAction': {'type': 'Delegate'},
                'intent': event['sessionState']['intent'],
                'sessionAttributes': session_attrs
            }
        }

    elif invocation_source == 'FulfillmentCodeHook':
        location    = get_slot_value(slots, 'Location')
        cuisine     = get_slot_value(slots, 'Cuisine')
        dining_date = get_slot_value(slots, 'DiningDate')
        dining_time = get_slot_value(slots, 'DiningTime')
        num_people  = get_slot_value(slots, 'NumberOfPeople')
        email       = get_slot_value(slots, 'Email')

        uid = get_user_id(session_id)
        save_user_preferences(uid, {
            'location':         location or 'NA',
            'cuisine':          cuisine  or 'NA',
            'email':            email    or 'NA',
            'num_people':       num_people or '2',
            'last_search_time': datetime.now().isoformat()
        })

        msg = {
            'location':    location    or 'NA',
            'cuisine':     cuisine     or 'NA',
            'dining_date': dining_date or 'today',
            'dining_time': dining_time or 'tonight',
            'num_people':  num_people  or '2',
            'email':       email       or 'NA',
            'timestamp':   datetime.now().isoformat()
        }

        try:
            sqs.send_message(QueueUrl=SQS_QUEUE_URL, MessageBody=json.dumps(msg))
        except Exception as e:
            print(f"SQS error: {e}")

        return close(event, 'Fulfilled',
            "You're all set. Expect my suggestions shortly! Have a good day.")


# ─────────────────────────────────────────────────────────────────────────────
def validate_slots(slots):
    location   = get_slot_value(slots, 'Location')
    cuisine    = get_slot_value(slots, 'Cuisine')
    num_people = get_slot_value(slots, 'NumberOfPeople')
    email      = get_slot_value(slots, 'Email')

    valid_locs = ['manhattan','brooklyn','queens','bronx','staten island',
                  'jersey city','hoboken','long island city']
    valid_cuis = ['japanese','italian','chinese','mexican','indian','thai','korean',
                  'french','mediterranean','american','vietnamese','spanish']

    if location and not any(v in location.lower() for v in valid_locs):
        return {'isValid': False, 'message':
            'I only have suggestions for Manhattan, Brooklyn, Queens, Bronx, '
            'Staten Island, Jersey City, Hoboken, or Long Island City.'}

    if cuisine and cuisine.lower() not in valid_cuis:
        return {'isValid': False, 'message':
            f"I don't have suggestions for {cuisine}. Try Japanese, Italian, Chinese, "
            f"Mexican, Indian, Thai, Korean, French, Mediterranean, American, "
            f"Vietnamese, or Spanish."}

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
def get_user_id(session_id):
    return hashlib.md5(session_id.encode()).hexdigest()[:16]

def get_user_preferences(user_id):
    try:
        r = dynamodb.Table(USER_PREFS_TABLE).get_item(Key={'UserId': user_id})
        return r.get('Item')
    except Exception as e:
        print(f"DynamoDB get error: {e}"); return None

def save_user_preferences(user_id, prefs):
    try:
        dynamodb.Table(USER_PREFS_TABLE).put_item(Item={'UserId': user_id, **prefs})
    except Exception as e:
        print(f"DynamoDB save error: {e}")

def get_slot_value(slots, name):
    s = slots.get(name)
    if s and s.get('value'):
        v = s['value']
        return (v.get('interpretedValue') or v.get('originalValue') or
                (v['resolvedValues'][0] if v.get('resolvedValues') else None))
    return None

def close(event, state, message):
    return {
        'sessionState': {
            'dialogAction': {'type': 'Close'},
            'intent': {
                'name':  event['sessionState']['intent']['name'],
                'slots': event['sessionState']['intent'].get('slots', {}),
                'state': state
            },
            'sessionAttributes': event['sessionState'].get('sessionAttributes', {})
        },
        'messages': [{'contentType': 'PlainText', 'content': message}]
    }