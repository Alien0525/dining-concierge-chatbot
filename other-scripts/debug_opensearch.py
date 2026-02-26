"""
Debug OpenSearch Index
Tests queries and shows what's actually in the index
"""

import requests
from requests.auth import HTTPBasicAuth
import json
import os

# Configuration - set these as environment variables
OPENSEARCH_ENDPOINT = os.environ.get('OPENSEARCH_ENDPOINT')
MASTER_USER = os.environ.get('MASTER_USER')
MASTER_PASS = os.environ.get('MASTER_PASS')
INDEX = "restaurants"

auth = HTTPBasicAuth(MASTER_USER, MASTER_PASS)
headers = {"Content-Type": "application/json"}

print("=" * 80)
print("OPENSEARCH DEBUG SCRIPT")
print("=" * 80)

# 1. Check if index exists
print("\n1. Checking if index exists...")
response = requests.get(
    f"{OPENSEARCH_ENDPOINT}/{INDEX}",
    auth=auth
)
if response.status_code == 200:
    print(f"✓ Index '{INDEX}' exists")
    mapping = response.json()
    print(f"  Mapping: {json.dumps(mapping.get(INDEX, {}).get('mappings', {}), indent=2)}")
else:
    print(f"✗ Index '{INDEX}' does not exist: {response.status_code}")
    print("  You need to create it and load data first!")
    exit(1)

# 2. Get total document count
print("\n2. Getting total document count...")
response = requests.get(
    f"{OPENSEARCH_ENDPOINT}/{INDEX}/_count",
    auth=auth
)
if response.status_code == 200:
    count = response.json().get('count', 0)
    print(f"✓ Total documents: {count}")
    if count == 0:
        print("  ⚠ No documents in index! Run load_opensearch_fixed.py to load data.")
        exit(1)
else:
    print(f"✗ Error getting count: {response.status_code}")

# 3. Get sample documents
print("\n3. Getting sample documents...")
query = {
    "size": 5,
    "query": {"match_all": {}}
}
response = requests.post(
    f"{OPENSEARCH_ENDPOINT}/{INDEX}/_search",
    auth=auth,
    headers=headers,
    json=query
)
if response.status_code == 200:
    hits = response.json().get('hits', {}).get('hits', [])
    print(f"✓ Sample documents ({len(hits)}):")
    for i, hit in enumerate(hits, 1):
        source = hit['_source']
        print(f"  {i}. {json.dumps(source, indent=6)}")
else:
    print(f"✗ Error: {response.status_code} - {response.text}")

# 4. Check field names
print("\n4. Analyzing field names in documents...")
if hits:
    sample = hits[0]['_source']
    print(f"✓ Fields found: {list(sample.keys())}")
    print(f"  RestaurantId present: {'RestaurantId' in sample}")
    print(f"  Cuisine present: {'Cuisine' in sample}")
    print(f"  Area present: {'Area' in sample}")
    
    if 'Area' not in sample:
        print("\n  ⚠ WARNING: 'Area' field is MISSING!")
        print("  This is why location queries return 0 results.")
        print("  Fix: Re-run load_opensearch_fixed.py to add Area field.")

# 5. Test actual query that Lambda uses
print("\n5. Testing Lambda-style query...")
test_queries = [
    {"cuisine": "Italian", "location": "Manhattan"},
    {"cuisine": "Japanese", "location": "Brooklyn"},
    {"cuisine": "Chinese", "location": "Queens"}
]

for test in test_queries:
    cuisine = test["cuisine"]
    location = test["location"]
    
    query = {
        "size": 5,
        "query": {
            "function_score": {
                "query": {
                    "bool": {
                        "must": [
                            {"match": {"Cuisine": cuisine}},
                            {"match": {"Area": location}}
                        ]
                    }
                },
                "functions": [{"random_score": {}}],
                "score_mode": "sum",
                "boost_mode": "replace"
            }
        },
        "_source": ["RestaurantId", "Cuisine", "Area"]
    }
    
    response = requests.post(
        f"{OPENSEARCH_ENDPOINT}/{INDEX}/_search",
        auth=auth,
        headers=headers,
        json=query
    )
    
    if response.status_code == 200:
        hits = response.json().get('hits', {}).get('hits', [])
        print(f"\n  Query: {cuisine} in {location}")
        print(f"  Results: {len(hits)} restaurants")
        if hits:
            for hit in hits[:3]:
                src = hit['_source']
                print(f"    - {src.get('RestaurantId')} ({src.get('Cuisine')} in {src.get('Area')})")
        else:
            print(f"    ⚠ No results! Check if you have {cuisine} restaurants in {location}")
    else:
        print(f"  ✗ Query error: {response.status_code} - {response.text}")

# 6. Aggregation by Cuisine and Area
print("\n6. Checking data distribution...")
agg_query = {
    "size": 0,
    "aggs": {
        "cuisines": {
            "terms": {"field": "Cuisine.keyword", "size": 20}
        },
        "areas": {
            "terms": {"field": "Area.keyword", "size": 20}
        }
    }
}

response = requests.post(
    f"{OPENSEARCH_ENDPOINT}/{INDEX}/_search",
    auth=auth,
    headers=headers,
    json=agg_query
)

if response.status_code == 200:
    aggs = response.json().get('aggregations', {})
    
    print("\n  Cuisines in index:")
    cuisines = aggs.get('cuisines', {}).get('buckets', [])
    for bucket in cuisines[:10]:
        print(f"    - {bucket['key']}: {bucket['doc_count']} restaurants")
    
    print("\n  Areas in index:")
    areas = aggs.get('areas', {}).get('buckets', [])
    for bucket in areas[:10]:
        print(f"    - {bucket['key']}: {bucket['doc_count']} restaurants")
else:
    print(f"  Note: Aggregation failed (may need keyword fields)")

print("\n" + "=" * 80)
print("DEBUG COMPLETE")
print("=" * 80)