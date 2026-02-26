"""
LF2 - Enhanced Queue Worker
Polls SQS, queries OpenSearch for restaurant IDs, fetches details from DynamoDB, sends email via SES.

Flow:
    SQS message
        → OpenSearch  (get random restaurant IDs by cuisine + location)
        → DynamoDB batch_get_item  (fetch full details by RestaurantId)
        → SES  (send HTML email)

Fallback (when OpenSearch is unreachable / not configured / returns nothing):
        → DynamoDB scan filtered by Cuisine + Area
        → SES
"""

import json
import boto3
import os
import urllib.request
import urllib.error
import base64
import traceback
from decimal import Decimal
from datetime import datetime

# ── AWS clients ───────────────────────────────────────────────────────────────
dynamodb        = boto3.resource('dynamodb', region_name='us-east-1')
dynamodb_client = boto3.client('dynamodb',   region_name='us-east-1')
sqs             = boto3.client('sqs',        region_name='us-east-1')
ses             = boto3.client('ses',        region_name='us-east-1')

# ── Config from Lambda environment variables ──────────────────────────────────
DYNAMODB_TABLE      = os.environ.get('DYNAMODB_TABLE', 'yelp-restaurants')
SQS_QUEUE_URL       = os.environ.get('SQS_QUEUE_URL')
FROM_EMAIL          = os.environ.get('FROM_EMAIL')
# OpenSearch — optional. If blank, code falls back to DynamoDB scan.
OPENSEARCH_ENDPOINT = os.environ.get('OPENSEARCH_ENDPOINT', '')
OPENSEARCH_USER     = os.environ.get('OPENSEARCH_USER', '')
OPENSEARCH_PASS     = os.environ.get('OPENSEARCH_PASS', '')
OPENSEARCH_INDEX    = 'restaurants'


# ─────────────────────────────────────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────
def lambda_handler(event, context):
    """Triggered by CloudWatch Events every minute. Polls SQS."""

    response = sqs.receive_message(
        QueueUrl=SQS_QUEUE_URL,
        MaxNumberOfMessages=10,
        WaitTimeSeconds=0
    )

    messages = response.get('Messages', [])
    if not messages:
        print("No messages in queue")
        return {'statusCode': 200, 'body': 'No messages to process'}

    print(f"Processing {len(messages)} messages")

    for message in messages:
        try:
            body = json.loads(message['Body'])

            cuisine     = body.get('cuisine', '').capitalize()
            location    = body.get('location', 'Manhattan')
            num_people  = body.get('num_people', '2')
            dining_date = body.get('dining_date', 'today')
            dining_time = body.get('dining_time', 'tonight')
            email       = body.get('email')

            print(f"Request: {cuisine} in {location} for {num_people} on {dining_date} at {dining_time}")

            restaurants = get_restaurant_recommendations(cuisine, location, count=5)

            if restaurants and email:
                send_email(email, restaurants, cuisine, location,
                           num_people, dining_date, dining_time)

            sqs.delete_message(
                QueueUrl=SQS_QUEUE_URL,
                ReceiptHandle=message['ReceiptHandle']
            )
            print(f"Successfully processed request for {email}")

        except Exception as e:
            print(f"Error processing message: {e}")
            print(traceback.format_exc())

    return {'statusCode': 200, 'body': f'Processed {len(messages)} messages'}


# ─────────────────────────────────────────────────────────────────────────────
#  ORCHESTRATOR
# ─────────────────────────────────────────────────────────────────────────────
def get_restaurant_recommendations(cuisine, location, count=5):
    """
    Primary:  OpenSearch (random IDs) → DynamoDB batch_get (full details)
    Fallback: DynamoDB scan           (when OpenSearch is gone / not configured)
    """

    # ── Try OpenSearch path ───────────────────────────────────────────────────
    ids = query_opensearch(cuisine, location, count)

    if ids:
        restaurants = fetch_from_dynamodb_by_ids(ids)
        if restaurants:
            restaurants.sort(key=lambda x: float(x.get('Rating', 0)), reverse=True)
            print(f"OpenSearch→DynamoDB path: returning {len(restaurants)} restaurants")
            return restaurants
        print("OpenSearch returned IDs but DynamoDB batch_get found nothing — falling back")

    # ── DynamoDB scan fallback ────────────────────────────────────────────────
    print("Using DynamoDB scan fallback")
    return fetch_from_dynamodb_scan(cuisine, location, count)


# ─────────────────────────────────────────────────────────────────────────────
#  STEP 1 — OpenSearch: get random restaurant IDs
# ─────────────────────────────────────────────────────────────────────────────
def query_opensearch(cuisine, location, count=5):
    """
    Query OpenSearch for random restaurant IDs matching cuisine + location.
    Uses function_score + random_score so recommendations vary each call.

    Returns list of RestaurantId strings, or [] on any failure.
    """
    if not OPENSEARCH_ENDPOINT or not OPENSEARCH_USER or not OPENSEARCH_PASS:
        print("OpenSearch env vars not set — skipping")
        return []

    cuisine_norm  = cuisine.strip().capitalize()
    location_norm = location.strip().title()

    query = {
        "size": count,
        "query": {
            "function_score": {
                "query": {
                    "bool": {
                        "must": [
                            {"match": {"Cuisine": cuisine_norm}},
                            {"match": {"Area":    location_norm}}
                        ]
                    }
                },
                "functions": [{"random_score": {}}],
                "score_mode": "sum",
                "boost_mode": "replace"
            }
        },
        "_source": ["RestaurantId"]   # only the ID; full details come from DynamoDB
    }

    url     = f"{OPENSEARCH_ENDPOINT.rstrip('/')}/{OPENSEARCH_INDEX}/_search"
    payload = json.dumps(query).encode('utf-8')
    token   = base64.b64encode(
        f"{OPENSEARCH_USER}:{OPENSEARCH_PASS}".encode()
    ).decode()

    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            'Content-Type':  'application/json',
            'Authorization': f'Basic {token}'
        },
        method='POST'
    )

    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            result = json.loads(resp.read().decode('utf-8'))

        hits = result.get('hits', {}).get('hits', [])
        # _source.RestaurantId if stored, otherwise fall back to _id
        ids  = [h['_source'].get('RestaurantId') or h.get('_id') for h in hits]
        ids  = [i for i in ids if i]

        print(f"OpenSearch: {len(ids)} IDs for {cuisine_norm}/{location_norm}: {ids}")
        return ids

    except urllib.error.HTTPError as e:
        print(f"OpenSearch HTTP {e.code}: {e.read().decode()}")
        return []
    except Exception as e:
        print(f"OpenSearch error (falling back to DynamoDB): {e}")
        return []


# ─────────────────────────────────────────────────────────────────────────────
#  STEP 2a — DynamoDB: batch-fetch full details by RestaurantId list
# ─────────────────────────────────────────────────────────────────────────────
def fetch_from_dynamodb_by_ids(restaurant_ids):
    """
    Fetch full restaurant records using DynamoDB batch_get_item (up to 100 keys).
    Returns list of plain dicts with numeric fields as floats.
    """
    if not restaurant_ids:
        return []

    keys = [{'RestaurantId': {'S': str(rid)}} for rid in restaurant_ids]

    try:
        response  = dynamodb_client.batch_get_item(
            RequestItems={
                DYNAMODB_TABLE: {
                    'Keys':          keys,
                    'ConsistentRead': False
                }
            }
        )
        raw_items = response.get('Responses', {}).get(DYNAMODB_TABLE, [])

        restaurants = []
        for item in raw_items:
            flat = {}
            for k, v in item.items():
                # DynamoDB typed value → plain Python
                if 'S' in v:
                    flat[k] = v['S']
                elif 'N' in v:
                    flat[k] = float(v['N'])
                else:
                    flat[k] = list(v.values())[0]
            restaurants.append(flat)

        print(f"DynamoDB batch_get: {len(restaurants)} records returned")
        return restaurants

    except Exception as e:
        print(f"DynamoDB batch_get error: {e}")
        print(traceback.format_exc())
        return []


# ─────────────────────────────────────────────────────────────────────────────
#  STEP 2b — DynamoDB scan fallback (no OpenSearch)
# ─────────────────────────────────────────────────────────────────────────────
def fetch_from_dynamodb_scan(cuisine, location, count=5):
    """
    Scan DynamoDB filtering by Cuisine and Area.
    Sort by Rating descending, return top N.
    Used when OpenSearch is not available.
    """
    table = dynamodb.Table(DYNAMODB_TABLE)

    location_map = {
        'manhattan':        'Manhattan',
        'brooklyn':         'Brooklyn',
        'queens':           'Queens',
        'bronx':            'Bronx',
        'staten island':    'Staten Island',
        'jersey city':      'Jersey City',
        'hoboken':          'Hoboken',
        'long island city': 'Long Island City'
    }
    area = location_map.get(location.lower(), location)

    try:
        resp  = table.scan(
            FilterExpression='Cuisine = :c AND Area = :a',
            ExpressionAttributeValues={':c': cuisine, ':a': area}
        )
        items = resp.get('Items', [])

        if not items:
            print(f"DynamoDB scan: no {cuisine} in {area}; trying cuisine-only fallback")
            resp  = table.scan(
                FilterExpression='Cuisine = :c',
                ExpressionAttributeValues={':c': cuisine}
            )
            items = resp.get('Items', [])

        # Decimal → float
        for r in items:
            for key in ('Rating', 'Latitude', 'Longitude'):
                if key in r and isinstance(r[key], Decimal):
                    r[key] = float(r[key])

        items.sort(key=lambda x: float(x.get('Rating', 0)), reverse=True)
        selected = items[:count]
        print(f"DynamoDB scan fallback: returning {len(selected)} restaurants")
        return selected

    except Exception as e:
        print(f"DynamoDB scan error: {e}")
        print(traceback.format_exc())
        return []


# ─────────────────────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def na(val, fallback='NA'):
    """Return string value, or fallback if missing / empty / null."""
    if val is None or str(val).strip() in ('', 'None', 'N/A', 'null'):
        return fallback
    return str(val).strip()


# ─────────────────────────────────────────────────────────────────────────────
#  EMAIL
# ─────────────────────────────────────────────────────────────────────────────
def send_email(to_email, restaurants, cuisine, location,
               num_people, dining_date, dining_time):
    """Send HTML + plain-text restaurant recommendations email via SES."""

    # ── Format time ───────────────────────────────────────────────────────────
    try:
        ts = str(dining_time)
        if ts and ':' in ts and 'PM' not in ts.upper() and 'AM' not in ts.upper():
            hour, minute = ts.split(':')[:2]
            hour   = int(hour)
            suffix = 'PM' if hour >= 12 else 'AM'
            hour12 = hour % 12 or 12
            time_str = f"{hour12}:{minute} {suffix}"
        else:
            time_str = na(dining_time, 'tonight')
    except Exception:
        time_str = na(dining_time, 'tonight')

    # ── Format date ───────────────────────────────────────────────────────────
    dl = str(dining_date).lower() if dining_date else ''
    if dl == 'today':      date_str = 'today'
    elif dl == 'tomorrow': date_str = 'tomorrow'
    elif dl:               date_str = f"on {dining_date}"
    else:                  date_str = 'today'

    # ── Per-restaurant entries ────────────────────────────────────────────────
    html_entries = []
    text_entries = []

    for i, r in enumerate(restaurants, 1):
        name         = na(r.get('Name'))
        address_raw  = na(r.get('Address'))
        area         = na(r.get('Area', location))
        rating       = na(r.get('Rating'))
        review_count = na(r.get('ReviewCount'), '0')
        phone        = na(r.get('Phone'))
        lat          = r.get('Latitude')
        lon          = r.get('Longitude')

        full_address = f"{address_raw}, {area}" if address_raw != 'NA' else area

        try:
            stars = '⭐' * min(5, int(float(rating)))
        except Exception:
            stars = ''

        # Google Maps link embedded in address
        if lat and lon:
            try:
                maps_url     = f"https://maps.google.com/?q={float(lat)},{float(lon)}"
                address_html = (f'<a href="{maps_url}" '
                                f'style="color:#4285F4;text-decoration:none;">'
                                f'{full_address}</a>')
                address_text = f"{full_address} ( {maps_url} )"
            except Exception:
                address_html = full_address
                address_text = full_address
        else:
            address_html = full_address
            address_text = full_address

        html_entries.append(f"""
        <div style="margin-bottom:20px;padding:15px;background:#f9f9f9;
                    border-left:3px solid #C9A96E;border-radius:4px;">
            <div style="font-size:16px;font-weight:bold;color:#333;margin-bottom:6px;">
                {i}. {name} {stars}
            </div>
            <div style="color:#666;margin-bottom:6px;">({rating}/5, {review_count} reviews)</div>
            <div style="color:#555;margin-bottom:4px;">📍 {address_html}</div>
            <div style="color:#555;">📞 {phone}</div>
        </div>""")

        text_entries.append(
            f"{i}. {name} {stars} ({rating}/5, {review_count} reviews)\n"
            f"   📍 {address_text}\n"
            f"   📞 {phone}\n"
        )

    # ── HTML body ─────────────────────────────────────────────────────────────
    html_body = f"""
    <html><head><meta charset="UTF-8"></head>
    <body style="font-family:Arial,sans-serif;line-height:1.6;color:#333;
                 max-width:600px;margin:0 auto;padding:20px;">
        <div style="background:#131008;color:#EDE5D0;padding:20px;
                    border-radius:8px 8px 0 0;">
            <h1 style="margin:0;font-size:24px;color:#C9A96E;">
                🍽️ Your Restaurant Recommendations
            </h1>
        </div>
        <div style="background:#fff;padding:20px;border-radius:0 0 8px 8px;">
            <p>Hello!</p>
            <p>Here are my top <strong>{len(restaurants)}</strong>
               <strong>{cuisine}</strong> restaurant recommendations in
               <strong>{location}</strong> for
               <strong>{num_people} people</strong>
               {date_str} at <strong>{time_str}</strong>:</p>
            {''.join(html_entries)}
            <p style="margin-top:30px;">Enjoy your meal! 🍽️</p>
            <div style="margin-top:30px;padding-top:20px;border-top:1px solid #ddd;
                        font-size:12px;color:#999;">
                Powered by Dining Concierge Chatbot
            </div>
        </div>
    </body></html>"""

    # ── Plain text fallback ───────────────────────────────────────────────────
    text_body = (
        f"Hello!\n\n"
        f"Here are my top {len(restaurants)} {cuisine} restaurant recommendations "
        f"in {location} for {num_people} people {date_str} at {time_str}:\n\n"
        + '\n'.join(text_entries)
        + "\nEnjoy your meal! 🍽️\n\n---\nPowered by Dining Concierge Chatbot\n"
    )

    # ── Send ──────────────────────────────────────────────────────────────────
    try:
        resp = ses.send_email(
            Source=FROM_EMAIL,
            Destination={'ToAddresses': [to_email]},
            Message={
                'Subject': {
                    'Data':    f'🍽️ Top {len(restaurants)} {cuisine} Restaurants in {location}',
                    'Charset': 'UTF-8'
                },
                'Body': {
                    'Html': {'Data': html_body,  'Charset': 'UTF-8'},
                    'Text': {'Data': text_body,  'Charset': 'UTF-8'}
                }
            }
        )
        print(f"Email sent to {to_email}, MessageId: {resp['MessageId']}")

    except Exception as e:
        print(f"Error sending email: {e}")
        print(traceback.format_exc())
        raise