"""
LF1 - Lex Code Hook with Conversation Memory

Fixes applied:
  - validate_slots now checks DiningDate (no past dates) and DiningTime (valid hour/minute)
  - On validation failure, returns ElicitSlot (re-asks the failing slot) instead of Close
    (which was terminating the intent and falling back to RepeatLastSearchIntent)
"""

import json
import boto3
from datetime import datetime, date
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
        # Flag so RepeatLastSearchIntent knows we explicitly asked this question.
        # Without this, words like "ok" or "no" typed anywhere in the conversation
        # could accidentally misroute to RepeatLastSearchIntent.
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
        message = "Hi there! How can I help you today?"
        return close(event, 'Fulfilled', message)


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

    # asked_repeat is set True only when handle_greeting explicitly asked the
    # same-or-different question. Without this guard, ambiguous words typed
    # during DiningSuggestionsIntent (like "ok", "no") would misroute here,
    # losing the active slot context.
    asked_repeat = session_attrs.get('asked_repeat') == 'true'

    if asked_repeat:
        different_kw = ['different', 'new', 'no', 'nope', 'change', 'something else',
                        'something different', 'other']
        same_kw      = ['same', 'yes', 'yeah', 'yep', 'sure', 'repeat', 'again', 'ok', 'okay']
    else:
        # Stricter — only unambiguous phrases when we haven't asked the question
        different_kw = ['different', 'something different', 'something else', 'something new']
        same_kw      = ['same', 'same as last time', 'repeat', 'again']

    wants_different = any(kw in transcript for kw in different_kw)
    wants_same      = any(kw in transcript for kw in same_kw)

    if wants_different:
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
    # Clear asked_repeat once we're inside the dining flow
    session_attrs = {**session_attrs, 'asked_repeat': 'false'}

    if invocation_source == 'DialogCodeHook':
        v = validate_slots(slots)
        if not v['isValid']:
            # ── KEY FIX: ElicitSlot re-asks the specific failing slot
            #    instead of Close which was killing the intent entirely
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
#  Each failed check now returns 'slot' — the name of the slot to re-elicit.
# ─────────────────────────────────────────────────────────────────────────────
def validate_slots(slots):
    location    = get_slot_value(slots, 'Location')
    cuisine     = get_slot_value(slots, 'Cuisine')
    dining_date = get_slot_value(slots, 'DiningDate')
    dining_time = get_slot_value(slots, 'DiningTime')
    num_people  = get_slot_value(slots, 'NumberOfPeople')
    email       = get_slot_value(slots, 'Email')

    valid_locs = ['manhattan', 'brooklyn', 'queens', 'bronx', 'staten island',
                  'jersey city', 'hoboken', 'long island city']
    valid_cuis = ['japanese', 'italian', 'chinese', 'mexican', 'indian', 'thai', 'korean',
                  'french', 'mediterranean', 'american', 'vietnamese', 'spanish']

    # ── Location ──────────────────────────────────────────────────────────────
    if location and not any(v in location.lower() for v in valid_locs):
        return {
            'isValid': False,
            'slot': 'Location',
            'message': (
                'I only have suggestions for Manhattan, Brooklyn, Queens, Bronx, '
                'Staten Island, Jersey City, Hoboken, or Long Island City. '
                'Which area would you like?'
            )
        }

    # ── Cuisine ───────────────────────────────────────────────────────────────
    if cuisine and cuisine.lower() not in valid_cuis:
        return {
            'isValid': False,
            'slot': 'Cuisine',
            'message': (
                f"I don't have suggestions for {cuisine}. "
                f"Please choose from: Japanese, Italian, Chinese, Mexican, Indian, "
                f"Thai, Korean, French, Mediterranean, American, Vietnamese, or Spanish."
            )
        }

    # ── Date: reject past dates ───────────────────────────────────────────────
    if dining_date:
        parsed_date = parse_date(dining_date)
        if parsed_date is None:
            return {
                'isValid': False,
                'slot': 'DiningDate',
                'message': "I didn't catch that date. Please enter a valid date, like today, tomorrow, or a specific date."
            }
        if parsed_date < date.today():
            return {
                'isValid': False,
                'slot': 'DiningDate',
                'message': (
                    f"It looks like {dining_date} is in the past. "
                    f"Please enter today's date or a future date."
                )
            }

    # ── Time: reject nonsense values like "32" ────────────────────────────────
    if dining_time:
        if not is_valid_time(dining_time):
            return {
                'isValid': False,
                'slot': 'DiningTime',
                'message': "That doesn't look like a valid time. Please enter a time like 7pm or 19:30."
            }

    # ── Number of people ──────────────────────────────────────────────────────
    if num_people:
        try:
            n = int(float(num_people))
            if not (1 <= n <= 20):
                return {
                    'isValid': False,
                    'slot': 'NumberOfPeople',
                    'message': f"{num_people} is out of range. Please enter a number between 1 and 20."
                }
        except (ValueError, TypeError):
            return {
                'isValid': False,
                'slot': 'NumberOfPeople',
                'message': "Please enter a valid number of people, between 1 and 20."
            }

    # ── Email ─────────────────────────────────────────────────────────────────
    if email and ('@' not in email or '.' not in email):
        return {
            'isValid': False,
            'slot': 'Email',
            'message': "That email address doesn't look right. Please enter a valid email, like name@example.com."
        }

    return {'isValid': True}


# ─────────────────────────────────────────────────────────────────────────────
#  DATE / TIME HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def parse_date(value):
    """
    Try to parse the date value Lex provides.
    Lex resolves dates to ISO format (YYYY-MM-DD) in interpretedValue,
    but users can also say 'yesterday', 'today', 'tomorrow'.
    Returns a date object or None if unparseable.
    """
    if not value:
        return None

    v = str(value).lower().strip()

    # Relative keywords
    today = date.today()
    if v == 'today':
        return today
    if v == 'tomorrow':
        from datetime import timedelta
        return today + timedelta(days=1)
    if v == 'yesterday':
        from datetime import timedelta
        return today - timedelta(days=1)

    # Lex ISO format YYYY-MM-DD
    try:
        return datetime.strptime(v, '%Y-%m-%d').date()
    except ValueError:
        pass

    # Try common spoken formats
    for fmt in ('%B %d', '%b %d', '%m/%d', '%m-%d'):
        try:
            parsed = datetime.strptime(v, fmt)
            # Assume current year; if that puts it in the past, use next year
            candidate = parsed.replace(year=today.year).date()
            if candidate < today:
                candidate = parsed.replace(year=today.year + 1).date()
            return candidate
        except ValueError:
            continue

    return None


def is_valid_time(value):
    """
    Validate that the time value is a real time.
    Lex resolves spoken times (e.g. '7pm', '19:30') to HH:MM in interpretedValue.
    We also need to catch raw garbage inputs like '32', '-1', '0', '60'.

    Rules:
      - HH:MM format: hour 0-23, minute 0-59 (Lex standard)
      - Bare integer: only accept 1-12 (plausible spoken hour like "seven")
        Reject 0, negatives, and anything > 12 typed as a bare number
      - 12h text like "7pm" or "7:30pm": accept
    """
    if not value:
        return False

    v = str(value).strip()

    # HH:MM — Lex-resolved format
    try:
        parts = v.split(':')
        if len(parts) == 2:
            h, m = int(parts[0]), int(parts[1])
            return (0 <= h <= 23) and (0 <= m <= 59)
    except (ValueError, AttributeError):
        pass

    # Bare integer — must be 1-12 to be a plausible spoken hour
    # Rejects: 0, -1, 13-99, 32, 60 etc.
    try:
        n = int(v)
        return 1 <= n <= 12
    except ValueError:
        pass

    # Text like "7pm", "7:30pm"
    import re
    if re.match(r'^\d{1,2}(:\d{2})?\s*(am|pm)$', v.lower()):
        return True

    return False


# ─────────────────────────────────────────────────────────────────────────────
#  RESPONSE BUILDERS
# ─────────────────────────────────────────────────────────────────────────────
def elicit_slot(event, slot_to_elicit, message, session_attrs):
    """
    Re-ask a specific slot without closing or failing the intent.
    This keeps the conversation alive inside DiningSuggestionsIntent.
    """
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
    s = slots.get(name)
    if s and s.get('value'):
        v = s['value']
        return (v.get('interpretedValue') or v.get('originalValue') or
                (v['resolvedValues'][0] if v.get('resolvedValues') else None))
    return None