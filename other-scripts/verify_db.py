"""
Verify expanded restaurant data in DynamoDB
"""

import boto3
from decimal import Decimal

dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
table = dynamodb.Table('yelp-restaurants')

def verify_data():
    """
    Scan DynamoDB and show statistics
    """
    
    print("Scanning DynamoDB table...")
    
    # Scan all items
    response = table.scan()
    items = response['Items']
    
    # Continue scanning if more items
    while 'LastEvaluatedKey' in response:
        response = table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
        items.extend(response['Items'])
    
    print(f"\nTotal restaurants in DynamoDB: {len(items)}")
    
    # Count by Area
    print("\n" + "="*60)
    print("By Area:")
    print("="*60)
    area_counts = {}
    for item in items:
        area = item.get('Area', 'Unknown')
        area_counts[area] = area_counts.get(area, 0) + 1
    
    for area, count in sorted(area_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"  {area}: {count}")
    
    # Count by Cuisine
    print("\n" + "="*60)
    print("By Cuisine:")
    print("="*60)
    cuisine_counts = {}
    for item in items:
        cuisine = item.get('Cuisine', 'Unknown')
        cuisine_counts[cuisine] = cuisine_counts.get(cuisine, 0) + 1
    
    for cuisine, count in sorted(cuisine_counts.items()):
        print(f"  {cuisine}: {count}")
    
    # Check for new fields
    print("\n" + "="*60)
    print("Sample Restaurant (checking new fields):")
    print("="*60)
    sample = items[0]
    print(f"  Name: {sample.get('Name')}")
    print(f"  Area: {sample.get('Area')}")
    print(f"  Cuisine: {sample.get('Cuisine')}")
    print(f"  Price Range: {sample.get('PriceRange', 'N/A')}")
    print(f"  Categories: {sample.get('Categories', [])}")
    print(f"  Rating: {sample.get('Rating')}")
    print(f"  Address: {sample.get('Address')}")
    print(f"  City: {sample.get('City')}")
    print(f"  State: {sample.get('State')}")
    
    # Test area filtering
    print("\n" + "="*60)
    print("Testing Area Filtering:")
    print("="*60)
    
    test_areas = ['Manhattan', 'Brooklyn', 'Queens', 'Jersey City']
    for area in test_areas:
        area_items = [i for i in items if i.get('Area') == area]
        japanese = [i for i in area_items if i.get('Cuisine') == 'Japanese']
        print(f"  {area}: {len(area_items)} total, {len(japanese)} Japanese")

if __name__ == '__main__':
    verify_data()