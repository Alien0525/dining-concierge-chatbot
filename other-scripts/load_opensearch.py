import json
import boto3
import requests
from requests.auth import HTTPBasicAuth
import os

OPENSEARCH_ENDPOINT = os.environ.get('OPENSEARCH_ENDPOINT')
MASTER_USER = os.environ.get('MASTER_USER')
MASTER_PASS = os.environ.get('MASTER_PASS')
INDEX = "restaurants"

# Load from your scraped restaurants.json
with open("../restaurants_expanded.json") as f:
    restaurants = json.load(f)

for r in restaurants:
    doc = {
        "RestaurantId": r["BusinessID"], 
        "Cuisine": r["Cuisine"],
        "Area": r.get("Area", "Unknown") 
    }
    response = requests.post(
        f"{OPENSEARCH_ENDPOINT}/{INDEX}/_doc",
        auth=HTTPBasicAuth(MASTER_USER, MASTER_PASS),
        headers={"Content-Type": "application/json"},
        json=doc
    )
    if response.status_code not in (200, 201):
        print(f"Error loading {r['BusinessID']}: {response.status_code} {response.text}")
    else:
        print(f"✓ Loaded {r['BusinessID']} - {r['Cuisine']} in {r.get('Area', 'Unknown')}")

print(f"Loaded {len(restaurants)} restaurants into OpenSearch")