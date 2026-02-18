"""
Clean up and normalize Area field in DynamoDB
"""

import boto3
from decimal import Decimal

dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
table = dynamodb.Table('yelp-restaurants')

# Area normalization mapping
AREA_MAPPING = {
    'Manhanttan': 'Manhattan',
    'LONG ISLAND CITY': 'Long Island City',
    'Long island City': 'Long Island City',
    'Long Island': 'Long Island City',
    'Astoria': 'Queens',
    'Sunnyside': 'Queens',
    'Woodside': 'Queens',
    'Jackson Heights': 'Queens',
    'Greenpoint': 'Brooklyn',
    'Forest Hills': 'Queens',
    'East Elmhurst': 'Queens',
    'Astoria Queens': 'Queens',
    'Queens County': 'Queens',
    'Edgewater': 'Jersey City',
    'City': 'Unknown',
    'New York City': 'Manhattan'
}

def cleanup_areas():
    """
    Scan table and fix area names
    """
    
    # Scan all items
    response = table.scan()
    items = response['Items']
    
    while 'LastEvaluatedKey' in response:
        response = table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
        items.extend(response['Items'])
    
    print(f"Scanning {len(items)} restaurants...")
    
    updated = 0
    for item in items:
        area = item.get('Area', 'Unknown')
        
        # Check if needs normalization
        if area in AREA_MAPPING:
            new_area = AREA_MAPPING[area]
            
            # Update item
            table.update_item(
                Key={'BusinessID': item['BusinessID']},
                UpdateExpression='SET Area = :area',
                ExpressionAttributeValues={':area': new_area}
            )
            
            updated += 1
            if updated % 10 == 0:
                print(f"  Updated {updated}...")
    
    print(f"Updated {updated} restaurants")

if __name__ == '__main__':
    cleanup_areas()