"""
LF3 - Preference Recall Lambda

Reads last user preferences
Automatically sends recommendation
"""

import json
import boto3
import os
import hashlib
from datetime import datetime

dynamodb = boto3.resource('dynamodb')
sqs = boto3.client('sqs')

USER_PREFS_TABLE = "user-preferences"
SQS_QUEUE_URL = os.environ['SQS_QUEUE_URL']


def lambda_handler(event, context):

    print("EVENT:", json.dumps(event))

    session_id = event['sessionId']

    user_id = generate_user_id(session_id)

    prefs = get_preferences(user_id)

    if not prefs:

        return close(
            event,
            "Hi there! I can help you find restaurants. What would you like today?"
        )

    # Found previous search
    cuisine = prefs['cuisine']
    location = prefs['location']
    num_people = prefs.get('num_people', '2')

    # Send to SQS automatically
    send_to_queue(prefs)

    message = (
        f"Welcome back! "
        f"I've sent you new {cuisine} restaurant recommendations "
        f"in {location}. Check your email shortly!"
    )

    return close(event, message)


# ---------- Helper functions ----------

def generate_user_id(session_id):

    return hashlib.md5(session_id.encode()).hexdigest()[:16]


def get_preferences(user_id):

    table = dynamodb.Table(USER_PREFS_TABLE)

    response = table.get_item(
        Key={'UserId': user_id}
    )

    return response.get('Item')


def send_to_queue(prefs):

    message = {

        "location": prefs['location'],
        "cuisine": prefs['cuisine'],
        "num_people": prefs.get('num_people', '2'),
        "email": prefs['email'],
        "timestamp": datetime.now().isoformat()
    }

    sqs.send_message(

        QueueUrl=SQS_QUEUE_URL,
        MessageBody=json.dumps(message)
    )


def close(event, message):

    return {

        "sessionState": {

            "dialogAction": {

                "type": "Close"
            },

            "intent": {

                "name": event['sessionState']['intent']['name'],
                "state": "Fulfilled"
            }
        },

        "messages": [

            {

                "contentType": "PlainText",
                "content": message
            }
        ]
    }
