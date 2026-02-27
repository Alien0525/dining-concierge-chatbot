"""
LF1 - Lex Code Hook with Conversation Memory
"""

import json
import boto3
from datetime import datetime, date, timedelta
import os
import hashlib
import re

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
        # Set asked_repeat so RepeatLastSearchIntent knows we explicitly asked.
        new_attrs = {**session_attrs, 'asked_repeat': 'true'}
        return {
            'sessionState': {
                'dialogAction': {'type': 'Close'},
                'intent': {
                    'name':  event['sessionState']['intent']['name'],
                    'slots': event['sessionState']['intent'].get('slots', {}),
                    'state': 'Fulfilled'
                },
                'sessionAttributes': new_attrs
            },
            'messages': [{'contentType': 'PlainText', 'content': message}]
        }
    else:
        return close(event, 'Fulfilled', "Hi there! How can I help you today?")


# ─────────────────────────────────────────────────────────────────────────────
def elicit_dining_location(event, session_attrs):
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
                    'Location':       None,
                    'Cuisine':        None,
                    'DiningDate':     None,
                    'DiningTime':     None,
                    'NumberOfPeople': None,
                    'Email':          None
                },
                'state': 'InProgress',
                'confirmationState': 'None'
            },
            'sessionAttributes': new_attrs
        },
        'messages': [{
            'contentType': 'PlainText',
            'content': "Sure! Let's find something new. Which area would you like to dine in?"
        }]
    }


# ─────────────────────────────────────────────────────────────────────────────
def handle_repeat_search(event, session_id):
    session_attrs = event['sessionState'].get('sessionAttributes', {})
    transcript    = event.get('inputTranscript', '').lower().strip()

    user_id     = get_user_id(session_id)
    last_search = get_user_preferences(user_id)

    # CRITICAL: Only process same/different if we actually asked the question.
    # asked_repeat is set by handle_greeting when it surfaces the same/different prompt.
    # If it's not set, this is a spurious Lex routing (e.g. "ok" during email slot)
    # — redirect back into DiningSuggestionsIntent from scratch.
    asked_repeat = session_attrs.get('asked_repeat') == 'true'

    if not asked_repeat:
        # Lex misrouted here mid-conversation. Send user back to dining flow.
        return elicit_dining_location(event, session_attrs)

    different_kw = ['different', 'new', 'no', 'nope', 'change', 'something else',
                    'something different', 'other']
    same_kw      = ['same', 'yes', 'yeah', 'yep', 'sure', 'repeat', 'again', 'ok', 'okay']

    wants_different = any(kw in transcript for kw in different_kw)
    wants_same      = any(kw in transcript for kw in same_kw)

    if wants_different:
        new_attrs = {**session_attrs, 'wants_different': 'true', 'asked_repeat': 'false'}
        return {
            'sessionState': {
                'dialogAction': {
                    'type': 'ElicitSlot',
                    'slotToElicit': 'Location'
                },
                'intent': {
                    'name': 'DiningSuggestionsIntent',
                    'slots': {
                        'Location':       None,
                        'Cuisine':        None,
                        'DiningDate':     None,
                        'DiningTime':     None,
                        'NumberOfPeople': None,
                        'Email':          None
                    },
                    'state': 'InProgress',
                    'confirmationState': 'None'
                },
                'sessionAttributes': new_attrs
            },
            'messages': [{
                'contentType': 'PlainText',
                'content': "Sure! Let's find something new. Which area would you like to dine in?"
            }]
        }

    if not wants_same:
        return close(event, 'Fulfilled',
            "Sorry, I didn't catch that. "
            "Would you like the same as last time, or something different?")

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

    if session_attrs.get('wants_different') == 'true':
        session_attrs = {**session_attrs, 'wants_different': 'false'}
    # Clear asked_repeat now that we are inside the dining flow
    session_attrs = {**session_attrs, 'asked_repeat': 'false'}

    if invocation_source == 'DialogCodeHook':
        v = validate_slots(slots)
        if not v['isValid']:
            return elicit_slot(event, v['slot'], v['message'], session_attrs)

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
#  VALIDATION
# ─────────────────────────────────────────────────────────────────────────────
def validate_slots(slots):
    location    = get_slot_value(slots, 'Location')
    cuisine     = get_slot_value(slots, 'Cuisine')
    dining_date = get_slot_value(slots, 'DiningDate')
    dining_time = get_slot_value(slots, 'DiningTime')
    num_people  = get_slot_value(slots, 'NumberOfPeople')
    email       = get_slot_value(slots, 'Email')

    # For date validation we also need the raw original value the user typed,
    # because Lex resolves "-1" to a real ISO date before we see it.
    dining_date_raw = get_slot_original(slots, 'DiningDate')
    dining_time_raw = get_slot_original(slots, 'DiningTime')

    valid_locs = ['manhattan', 'brooklyn', 'queens', 'bronx', 'staten island',
                  'jersey city', 'hoboken', 'long island city']
    valid_cuis = ['japanese', 'italian', 'chinese', 'mexican', 'indian', 'thai', 'korean',
                  'french', 'mediterranean', 'american', 'vietnamese', 'spanish']

    # ── Location ──────────────────────────────────────────────────────────────
    if location and not any(v in location.lower() for v in valid_locs):
        return {
            'isValid': False, 'slot': 'Location',
            'message': (
                'I only have suggestions for Manhattan, Brooklyn, Queens, Bronx, '
                'Staten Island, Jersey City, Hoboken, or Long Island City. '
                'Which area would you like?'
            )
        }

    # ── Cuisine ───────────────────────────────────────────────────────────────
    if cuisine and cuisine.lower() not in valid_cuis:
        return {
            'isValid': False, 'slot': 'Cuisine',
            'message': (
                f"I don't have suggestions for {cuisine}. "
                f"Please choose from: Japanese, Italian, Chinese, Mexican, Indian, "
                f"Thai, Korean, French, Mediterranean, American, Vietnamese, or Spanish."
            )
        }

    # ── Date ──────────────────────────────────────────────────────────────────
    if dining_date:
        # IMPORTANT: Check the raw typed value first.
        # Lex resolves garbage like "-1" into a real ISO date offset from today.
        # We reject any raw value that looks like a bare number or is clearly
        # not a date phrase.
        if dining_date_raw and is_clearly_not_a_date(dining_date_raw):
            return {
                'isValid': False, 'slot': 'DiningDate',
                'message': "That doesn't look like a valid date. Please enter today, tomorrow, or a specific date."
            }

        parsed_date = parse_date(dining_date)
        if parsed_date is None:
            return {
                'isValid': False, 'slot': 'DiningDate',
                'message': "I didn't catch that date. Please enter a valid date, like today, tomorrow, or a specific date."
            }
        if parsed_date < date.today():
            return {
                'isValid': False, 'slot': 'DiningDate',
                'message': f"It looks like that date is in the past. Please enter today's date or a future date."
            }

    # ── Time ──────────────────────────────────────────────────────────────────
    if dining_time:
        # Check raw value for obvious garbage before trusting Lex's interpretation
        if dining_time_raw and is_clearly_not_a_time(dining_time_raw):
            return {
                'isValid': False, 'slot': 'DiningTime',
                'message': "That doesn't look like a valid time. Please enter a time like 7pm or 19:30."
            }
        if not is_valid_time(dining_time):
            return {
                'isValid': False, 'slot': 'DiningTime',
                'message': "That doesn't look like a valid time. Please enter a time like 7pm or 19:30."
            }

    # ── Number of people ──────────────────────────────────────────────────────
    if num_people:
        try:
            n = int(float(num_people))
            if not (1 <= n <= 20):
                return {
                    'isValid': False, 'slot': 'NumberOfPeople',
                    'message': f"{num_people} is out of range. Please enter a number between 1 and 20."
                }
        except (ValueError, TypeError):
            return {
                'isValid': False, 'slot': 'NumberOfPeople',
                'message': "Please enter a valid number of people, between 1 and 20."
            }

    # ── Email ─────────────────────────────────────────────────────────────────
    if email and ('@' not in email or '.' not in email):
        return {
            'isValid': False, 'slot': 'Email',
            'message': "That email address doesn't look right. Please enter a valid email, like name@example.com."
        }

    return {'isValid': True}


# ─────────────────────────────────────────────────────────────────────────────
#  RAW VALUE GUARDS
#  These check what the user actually typed, before Lex resolves it.
#  Lex is too permissive — it resolves "-1" as a relative date, "0" as midnight, etc.
# ─────────────────────────────────────────────────────────────────────────────
def is_clearly_not_a_date(raw):
    """
    Returns True if the raw typed value is obviously not a date.
    Catches: bare numbers like -1, 0, 32, 99
    Allows: "today", "tomorrow", "yesterday", "feb 28", "saturday", "3/1" etc.
    """
    if not raw:
        return False
    v = str(raw).strip()
    # A bare integer (possibly negative) is not a date
    try:
        int(v)
        return True  # "-1", "0", "32" — all rejected
    except ValueError:
        pass
    # A bare float is not a date
    try:
        float(v)
        return True
    except ValueError:
        pass
    return False


def is_clearly_not_a_time(raw):
    """
    Returns True if the raw typed value is obviously not a time.
    Catches: -1, 0, 32, 99
    Allows: "7pm", "7:30", "19:00", "7", "8" (plausible spoken hours)
    """
    if not raw:
        return False
    v = str(raw).strip()
    # Negative number — never a valid time
    try:
        n = int(v)
        if n < 0:
            return True   # -1, -5 etc.
        if n > 23:
            return True   # 32, 60, 99 etc.
        return False      # 0-23: possibly valid hour, let is_valid_time decide
    except ValueError:
        pass
    return False


# ─────────────────────────────────────────────────────────────────────────────
#  DATE / TIME PARSERS
# ─────────────────────────────────────────────────────────────────────────────
def parse_date(value):
    """
    Parse the interpretedValue Lex provides after NLU resolution.
    Returns a date object or None.
    """
    if not value:
        return None

    v = str(value).lower().strip()
    today = date.today()

    if v == 'today':
        return today
    if v == 'tomorrow':
        return today + timedelta(days=1)
    if v == 'yesterday':
        return today - timedelta(days=1)

    # Lex ISO format YYYY-MM-DD
    try:
        return datetime.strptime(v, '%Y-%m-%d').date()
    except ValueError:
        pass

    # Common spoken formats
    for fmt in ('%B %d', '%b %d', '%m/%d', '%m-%d'):
        try:
            parsed    = datetime.strptime(v, fmt)
            candidate = parsed.replace(year=today.year).date()
            if candidate < today:
                candidate = parsed.replace(year=today.year + 1).date()
            return candidate
        except ValueError:
            continue

    return None


def is_valid_time(value):
    """
    Validate the interpretedValue Lex provides after NLU resolution.
    """
    if not value:
        return False

    v = str(value).strip()

    # HH:MM — Lex standard resolved format
    try:
        parts = v.split(':')
        if len(parts) == 2:
            h, m = int(parts[0]), int(parts[1])
            return (0 <= h <= 23) and (0 <= m <= 59)
    except (ValueError, AttributeError):
        pass

    # Bare integer — accept 1-12 as a plausible spoken hour, reject 0 and > 12
    try:
        n = int(v)
        return 1 <= n <= 12
    except ValueError:
        pass

    # "7pm", "7:30pm"
    if re.match(r'^\d{1,2}(:\d{2})?\s*(am|pm)$', v.lower()):
        return True

    return False


# ─────────────────────────────────────────────────────────────────────────────
#  RESPONSE BUILDERS
# ─────────────────────────────────────────────────────────────────────────────
def elicit_slot(event, slot_to_elicit, message, session_attrs):
    return {
        'sessionState': {
            'dialogAction': {
                'type': 'ElicitSlot',
                'slotToElicit': slot_to_elicit
            },
            'intent': {
                'name':  event['sessionState']['intent']['name'],
                'slots': event['sessionState']['intent'].get('slots', {}),
                'state': 'InProgress',
                'confirmationState': 'None'
            },
            'sessionAttributes': session_attrs
        },
        'messages': [{
            'contentType': 'PlainText',
            'content': message
        }]
    }


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


# ─────────────────────────────────────────────────────────────────────────────
#  DYNAMODB HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def get_user_id(session_id):
    return hashlib.md5(session_id.encode()).hexdigest()[:16]

def get_user_preferences(user_id):
    try:
        r = dynamodb.Table(USER_PREFS_TABLE).get_item(Key={'UserId': user_id})
        return r.get('Item')
    except Exception as e:
        print(f"DynamoDB get error: {e}")
        return None

def save_user_preferences(user_id, prefs):
    try:
        dynamodb.Table(USER_PREFS_TABLE).put_item(Item={'UserId': user_id, **prefs})
    except Exception as e:
        print(f"DynamoDB save error: {e}")

def get_slot_value(slots, name):
    """Returns Lex's interpreted/resolved value — what Lex thinks the user meant."""
    s = slots.get(name)
    if s and s.get('value'):
        v = s['value']
        return (v.get('interpretedValue') or v.get('originalValue') or
                (v['resolvedValues'][0] if v.get('resolvedValues') else None))
    return None

def get_slot_original(slots, name):
    """Returns exactly what the user typed, before Lex interpretation."""
    s = slots.get(name)
    if s and s.get('value'):
        return s['value'].get('originalValue')
    return None