"""
Load restaurant data from restaurants.json into DynamoDB
Creates table if it doesn't exist, then batch uploads all restaurants
"""

import boto3
import json
from datetime import datetime
from decimal import Decimal
from botocore.exceptions import ClientError
import config

def decimal_default(obj):
    """
    Helper function to convert float to Decimal.
    
    Why: DynamoDB doesn't support Python float type
    Must use Decimal for all numeric values with decimals
    """
    if isinstance(obj, float):
        return Decimal(str(obj))
    raise TypeError

def convert_floats_to_decimal(data):
    """
    Recursively convert all floats in nested dict to Decimal.
    
    Why: Restaurant data has floats (Rating: 4.3, Latitude: 40.75)
    DynamoDB requires Decimal type instead
    This function handles nested structures automatically
    """
    return json.loads(json.dumps(data), parse_float=Decimal)

def create_dynamodb_table():
    """
    Creates DynamoDB table for storing restaurant data.
    
    Table Design:
    - Partition Key: BusinessID (unique identifier from Yelp)
    - On-demand billing: pay only for actual reads/writes
    - No provisioned capacity needed
    """
    dynamodb = boto3.resource('dynamodb', region_name=config.AWS_REGION)
    table_name = config.DYNAMODB_TABLE_NAME
    
    try:
        # Check if table already exists to avoid errors
        existing_tables = boto3.client('dynamodb', region_name=config.AWS_REGION).list_tables()['TableNames']
        
        if table_name in existing_tables:
            print(f"Table '{table_name}' already exists")
            return dynamodb.Table(table_name)
        
        # Create new table
        table = dynamodb.create_table(
            TableName=table_name,
            KeySchema=[
                {'AttributeName': 'BusinessID', 'KeyType': 'HASH'}  # Partition key
            ],
            AttributeDefinitions=[
                {'AttributeName': 'BusinessID', 'AttributeType': 'S'}  # String type
            ],
            BillingMode='PAY_PER_REQUEST'  # On-demand pricing (no capacity planning)
        )
        
        print(f"Creating table '{table_name}'...")
        table.wait_until_exists()  # Wait for creation to complete
        print(f"Table created successfully")
        return table
        
    except ClientError as e:
        print(f"Error: {e}")
        raise

def load_restaurants_to_dynamodb(json_file='restaurants.json'):
    """
    Loads restaurant data from JSON file into DynamoDB.
    
    Process:
    - Read all restaurants from JSON
    - Convert floats to Decimal (DynamoDB requirement)
    - Batch write for efficiency (25 items per batch automatically)
    - Add timestamp if missing
    """
    dynamodb = boto3.resource('dynamodb', region_name=config.AWS_REGION)
    table = dynamodb.Table(config.DYNAMODB_TABLE_NAME)
    
    # Load restaurant data from file
    with open(json_file, 'r') as f:
        restaurants = json.load(f)
    
    print(f"Uploading {len(restaurants)} restaurants...")
    
    # Batch writer handles batching automatically (up to 25 items per request)
    with table.batch_writer() as batch:
        for i, restaurant in enumerate(restaurants, 1):
            # Ensure timestamp exists (assignment requirement)
            if 'insertedAtTimestamp' not in restaurant:
                restaurant['insertedAtTimestamp'] = datetime.now().isoformat()
            
            # Convert all float values to Decimal
            # This handles Rating (4.3), Latitude (40.75), Longitude (-73.98)
            restaurant = convert_floats_to_decimal(restaurant)
            
            # Write to DynamoDB
            batch.put_item(Item=restaurant)
            
            # Progress indicator every 100 items
            if i % 100 == 0:
                print(f"  {i}/{len(restaurants)}...")
    
    print(f"Upload complete: {len(restaurants)} restaurants")

def verify_data():
    """
    Quick verification that data loaded correctly.
    
    Checks:
    - Can query table
    - Items exist
    - Data structure looks correct
    """
    dynamodb = boto3.resource('dynamodb', region_name=config.AWS_REGION)
    table = dynamodb.Table(config.DYNAMODB_TABLE_NAME)
    
    # Scan to get a few sample items
    response = table.scan(Limit=5)
    print(f"\nVerification: {len(response['Items'])} items found")
    
    # Show sample item to confirm structure
    if response['Items']:
        sample = response['Items'][0]
        print(f"Sample: {sample['Name']} - {sample['Cuisine']} - Rating: {sample['Rating']}")

if __name__ == '__main__':
    print("Starting DynamoDB setup...\n")
    create_dynamodb_table()
    load_restaurants_to_dynamodb()
    verify_data()
    print("\nDynamoDB setup complete!")