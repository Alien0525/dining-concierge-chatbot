"""
LF0 - API Gateway Handler
Receives chat messages from frontend, sends to Lex bot, returns response
"""

import json
import boto3

def lambda_handler(event, context):
    """
    Entry point for Lambda function.
    
    Flow:
    1. Extract message from API request
    2. Send to Lex bot
    3. Get Lex response
    4. Return to API Gateway (which returns to frontend)
    
    Args:
        event: API Gateway request (contains user message)
        context: Lambda context (metadata, unused here)
    
    Returns:
        API Gateway response with Lex's reply
    """
    
    # Parse incoming request
    # API Gateway wraps the actual request in 'body'
    try:
        body = json.loads(event['body']) if isinstance(event.get('body'), str) else event.get('body', {})
    except:
        body = {}
    
    # Extract user message
    # Frontend sends: {"messages": [{"unstructured": {"text": "Hello"}}]}
    messages = body.get('messages', [])
    
    if not messages:
        return {
            'statusCode': 400,
            'headers': {
                'Access-Control-Allow-Origin': '*',  # CORS - allows frontend to call this
                'Content-Type': 'application/json'
            },
            'body': json.dumps({'message': 'No message provided'})
        }
    
    # Get the actual text message
    user_message = messages[0].get('unstructured', {}).get('text', '')
    
    if not user_message:
        return {
            'statusCode': 400,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Content-Type': 'application/json'
            },
            'body': json.dumps({'message': 'Empty message'})
        }
    
    # For now, return a placeholder response
    # We'll add Lex integration after creating the bot
    bot_response = "I'm still under development. Please come back later."
    
    # Format response to match API spec
    response_body = {
        'messages': [
            {
                'type': 'unstructured',
                'unstructured': {
                    'text': bot_response
                }
            }
        ]
    }
    
    return {
        'statusCode': 200,
        'headers': {
            'Access-Control-Allow-Origin': '*',  # CORS header - critical!
            'Content-Type': 'application/json'
        },
        'body': json.dumps(response_body)
    }