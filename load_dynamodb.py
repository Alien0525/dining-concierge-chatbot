"""
Load expanded restaurant data to DynamoDB
"""

import boto3
import json
from datetime import datetime
from decimal import Decimal
import config

def convert_floats_to_decimal(data):
    """Recursively convert all floats to Decimal"""
    return json.loads(json.dumps(data), parse_float=Decimal)

def load_restaurants_to_dynamodb(json_file='restaurants_expanded.json'):
    """
    Load restaurants from JSON file into DynamoDB
    """
    dynamodb = boto3.resource('dynamodb', region_name=config.AWS_REGION)
    table = dynamodb.Table(config.DYNAMODB_TABLE_NAME)
    
    # Load restaurant data
    with open(json_file, 'r') as f:
        restaurants = json.load(f)
    
    print(f"Loading {len(restaurants)} restaurants to DynamoDB...")
    
    # Batch write
    with table.batch_writer() as batch:
        for i, restaurant in enumerate(restaurants, 1):
            # Ensure timestamp exists
            if 'insertedAtTimestamp' not in restaurant:
                restaurant['insertedAtTimestamp'] = datetime.now().isoformat()
            
            # Convert floats to Decimal
            restaurant = convert_floats_to_decimal(restaurant)
            
            # Write to DynamoDB
            batch.put_item(Item=restaurant)
            
            if i % 100 == 0:
                print(f"  Uploaded {i}/{len(restaurants)}...")
    
    print(f"Successfully uploaded {len(restaurants)} restaurants!")

if __name__ == '__main__':
    load_restaurants_to_dynamodb()