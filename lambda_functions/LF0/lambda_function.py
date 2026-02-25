"""
LF0 - Chat API Handler
======================
Role:  Sits behind API Gateway. Receives every message the frontend sends,
       forwards it to the Amazon Lex V2 bot, and returns Lex's reply.

Flow:
    Browser  →  API Gateway  →  LF0  →  Lex V2  →  LF0  →  API Gateway  →  Browser

Environment variables (set in Lambda console → Configuration → Environment variables):
    LEX_BOT_ID       – e.g.  ABCDE12345
    LEX_BOT_ALIAS_ID – e.g.  TSTALIASID   (use 'TSTALIASID' for TestBotAlias during dev,
                              or your published alias ID after you create one)
    LEX_LOCALE_ID    – e.g.  en_US  (default if not set)
    AWS_REGION_NAME  – e.g.  us-east-1   (Lambda already has AWS_DEFAULT_REGION
                              but we use our own var to avoid collision)

IAM permissions needed on LF0's execution role:
    lex:RecognizeText   on  arn:aws:lex:<region>:<account>:bot-alias/<botId>/<aliasId>
"""

import json
import os
import logging
import boto3
from botocore.exceptions import ClientError

# ── Logging ──────────────────────────────────────────────────────────────────
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ── Lex V2 client (initialised once per container, not per invocation) ────────
lex_client = boto3.client(
    'lexv2-runtime',
    region_name=os.environ.get('AWS_REGION_NAME', 'us-east-1')
)

# ── Bot identifiers from environment variables ────────────────────────────────
BOT_ID       = os.environ.get('LEX_BOT_ID', '')
BOT_ALIAS_ID = os.environ.get('LEX_BOT_ALIAS_ID', 'TSTALIASID')
LOCALE_ID    = os.environ.get('LEX_LOCALE_ID', 'en_US')

# ── CORS headers returned on every response ───────────────────────────────────
# '*' allows the S3-hosted frontend (any origin) to call this API.
CORS_HEADERS = {
    'Access-Control-Allow-Origin':  '*',
    'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
    'Access-Control-Allow-Methods': 'OPTIONS,POST',
    'Content-Type':                 'application/json',
}

def lambda_handler(event, context):
    """
    Called by API Gateway on every POST /chatbot request.

    Expected request body (matches swagger.yaml):
        {
          "messages": [
            {
              "type": "unstructured",
              "unstructured": {
                "id":        "<session-id>",   // used as Lex sessionId
                "text":      "Hello",
                "timestamp": "2026-02-25T..."  // optional, ignored
              }
            }
          ]
        }

    Returns:
        {
          "messages": [
            {
              "type": "unstructured",
              "unstructured": { "text": "<bot reply>" }
            }
          ]
        }
    """

    logger.info("Event received: %s", json.dumps(event))

    # ── 1. Handle OPTIONS pre-flight (CORS) ──────────────────────────────────
    # Browsers send an OPTIONS request before the real POST.
    # API Gateway can handle this via a Mock integration, but handling it here
    # too means it works regardless of how the Gateway is configured.
    if event.get('httpMethod') == 'OPTIONS':
        return _response(200, {})

    # ── 2. Parse the request body ─────────────────────────────────────────────
    body = _parse_body(event)
    if body is None:
        return _response(400, {'error': 'Invalid JSON in request body'})

    messages = body.get('messages', [])
    if not messages:
        return _response(400, {'error': 'No messages provided'})

    # ── 3. Extract text and session ID from the first message ─────────────────
    first_msg    = messages[0]
    unstructured = first_msg.get('unstructured', {})
    user_text    = unstructured.get('text', '').strip()
    # session_id keeps the Lex conversation going across multiple turns.
    # The frontend generates a stable UUID per browser session and sends it here.
    session_id   = unstructured.get('id', 'default-session')

    if not user_text:
        return _response(400, {'error': 'Empty message text'})

    logger.info("User [session=%s]: %s", session_id, user_text)

    # ── 4. Validate bot config ────────────────────────────────────────────────
    if not BOT_ID:
        logger.error("LEX_BOT_ID environment variable is not set")
        return _response(500, {'error': 'Bot not configured. Set LEX_BOT_ID env var.'})

    # ── 5. Call Lex V2 ───────────────────────────────────────────────────────
    bot_reply = _call_lex(session_id, user_text)
    if bot_reply is None:
        return _response(502, {'error': 'Failed to get response from Lex'})

    logger.info("Bot [session=%s]: %s", session_id, bot_reply)

    # ── 6. Format response to match the API spec ─────────────────────────────
    response_body = {
        'messages': [
            {
                'type': 'unstructured',
                'unstructured': {
                    'text': bot_reply
                }
            }
        ]
    }

    return _response(200, response_body)


# ─────────────────────────────────────────────────────────────────────────────
#  LEX HELPER
# ─────────────────────────────────────────────────────────────────────────────
def _call_lex(session_id, text):
    """
    Send `text` to the Lex V2 bot and return the plain-text reply string.

    Args:
        session_id (str): Identifies the conversation. Same ID across turns
                          keeps the slot-filling context alive in Lex.
        text (str):       The user's message.

    Returns:
        str | None: Bot's reply text, or None on error.
    """
    try:
        response = lex_client.recognize_text(
            botId=BOT_ID,
            botAliasId=BOT_ALIAS_ID,
            localeId=LOCALE_ID,
            sessionId=session_id,
            text=text
        )

        # response['messages'] is a list of message objects.
        # Each has 'contentType' ('PlainText' | 'SSML' | 'CustomPayload')
        # and 'content'.  We join all PlainText messages with a space.
        lex_messages = response.get('messages', [])

        if not lex_messages:
            # Lex returned no messages — shouldn't happen in normal flow
            logger.warning("Lex returned empty messages list for session %s", session_id)
            return "I didn't quite get that. Could you rephrase?"

        # Collect all plain-text parts (Lex can return multiple message objects)
        reply_parts = [
            m['content']
            for m in lex_messages
            if m.get('contentType') == 'PlainText' and m.get('content')
        ]

        if reply_parts:
            return ' '.join(reply_parts)

        # Fallback: use the first message's content whatever the type
        return lex_messages[0].get('content', "I'm not sure how to respond to that.")

    except ClientError as e:
        error_code = e.response['Error']['Code']
        logger.error("Lex ClientError [%s]: %s", error_code, str(e))

        # Surface a user-friendly message for common errors
        if error_code == 'ResourceNotFoundException':
            return "I'm not set up yet. Please check the bot configuration."
        if error_code == 'AccessDeniedException':
            return "I don't have permission to access the bot. Check IAM roles."

        return "Something went wrong on my end. Please try again."

    except Exception as e:
        logger.exception("Unexpected error calling Lex: %s", str(e))
        return "Something went wrong. Please try again."


# ─────────────────────────────────────────────────────────────────────────────
#  RESPONSE / BODY HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def _parse_body(event):
    """
    Extract and JSON-parse the request body from the API Gateway event.
    API Gateway passes the body as a JSON string in event['body'].
    """
    raw = event.get('body')
    if raw is None:
        # Might be a direct Lambda test invocation with the body already a dict
        return event if 'messages' in event else {}
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        logger.error("Could not parse request body: %s", raw)
        return None


def _response(status_code, body_dict):
    """
    Build a standard API Gateway proxy response dict.

    Args:
        status_code (int): HTTP status code.
        body_dict (dict):  Response payload; will be JSON-serialised.

    Returns:
        dict: API Gateway response object.
    """
    return {
        'statusCode': status_code,
        'headers':    CORS_HEADERS,
        'body':       json.dumps(body_dict)
    }