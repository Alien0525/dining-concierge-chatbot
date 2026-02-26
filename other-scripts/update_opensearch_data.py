"""
Update existing OpenSearch documents to add Area field
More efficient than deleting and reloading everything
"""

import json
import requests
from requests.auth import HTTPBasicAuth
import os

OPENSEARCH_ENDPOINT = os.environ.get('OPENSEARCH_ENDPOINT')
MASTER_USER = os.environ.get('MASTER_USER')
MASTER_PASS = os.environ.get('MASTER_PASS')
INDEX = "restaurants"

auth = HTTPBasicAuth(MASTER_USER, MASTER_PASS)
headers = {"Content-Type": "application/json"}

# Load your restaurant data
print("Loading restaurant data from file...")
with open("../restaurants_expanded.json") as f:
    restaurants = json.load(f)

print(f"Found {len(restaurants)} restaurants in file")

# Create a mapping of BusinessID -> Area
restaurant_map = {r["BusinessID"]: r.get("Area", "Unknown") for r in restaurants}

print(f"\nFetching all documents from OpenSearch...")

# Get all documents from OpenSearch
query = {
    "size": 10000,  # Adjust if you have more restaurants
    "query": {"match_all": {}}
}

response = requests.post(
    f"{OPENSEARCH_ENDPOINT}/{INDEX}/_search",
    auth=auth,
    headers=headers,
    json=query
)

if response.status_code != 200:
    print(f"Error fetching documents: {response.status_code}")
    print(response.text)
    exit(1)

hits = response.json().get('hits', {}).get('hits', [])
print(f"Found {len(hits)} documents in OpenSearch")

# Update each document with Area field
updated = 0
not_found = 0
errors = 0

print("\nUpdating documents with Area field...")

for hit in hits:
    doc_id = hit['_id']
    source = hit['_source']
    
    # Get RestaurantID (note: capital D in your current index)
    restaurant_id = source.get('RestaurantID') or source.get('RestaurantId')
    
    if not restaurant_id:
        print(f"  ⚠ Document {doc_id} has no RestaurantID, skipping")
        continue
    
    # Look up Area from your data
    area = restaurant_map.get(restaurant_id)
    
    if not area:
        print(f"  ⚠ RestaurantID {restaurant_id} not found in data file")
        not_found += 1
        area = "Unknown"
    
    # Update the document
    update_body = {
        "doc": {
            "Area": area,
            "RestaurantId": restaurant_id  # Also fix the spelling (lowercase d)
        }
    }
    
    response = requests.post(
        f"{OPENSEARCH_ENDPOINT}/{INDEX}/_update/{doc_id}",
        auth=auth,
        headers=headers,
        json=update_body
    )
    
    if response.status_code in (200, 201):
        updated += 1
        if updated % 100 == 0:
            print(f"  Updated {updated} documents...")
    else:
        errors += 1
        print(f"  ✗ Error updating {restaurant_id}: {response.status_code} - {response.text[:100]}")

print("\n" + "=" * 80)
print(f"Update complete!")
print(f"  ✓ Successfully updated: {updated}")
print(f"  ⚠ Not found in data file: {not_found}")
print(f"  ✗ Errors: {errors}")
print("=" * 80)

print("\nRunning test query to verify...")

# Test query
test_query = {
    "size": 3,
    "query": {
        "bool": {
            "must": [
                {"match": {"Cuisine": "Italian"}},
                {"match": {"Area": "Manhattan"}}
            ]
        }
    },
    "_source": ["RestaurantId", "Cuisine", "Area"]
}

response = requests.post(
    f"{OPENSEARCH_ENDPOINT}/{INDEX}/_search",
    auth=auth,
    headers=headers,
    json=test_query
)

if response.status_code == 200:
    hits = response.json().get('hits', {}).get('hits', [])
    print(f"\n✓ Test query (Italian in Manhattan): {len(hits)} results")
    for hit in hits:
        src = hit['_source']
        print(f"  - {src.get('RestaurantId')} ({src.get('Cuisine')} in {src.get('Area')})")
else:
    print(f"\n✗ Test query failed: {response.status_code}")

print("\n🎉 Done! Your OpenSearch index now has Area field and should work with Lambda queries.")