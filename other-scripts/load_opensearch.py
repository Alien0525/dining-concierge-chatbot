"""
load_opensearch.py
==================
Indexes all restaurants from restaurants_expanded.json into OpenSearch.

Each document stores only RestaurantId, Cuisine, and Area —
LF2 uses these IDs to then fetch full details from DynamoDB.
"""

import json
import os
import sys
import time
import requests
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv

load_dotenv()

OPENSEARCH_ENDPOINT = os.environ.get('OPENSEARCH_ENDPOINT', '').rstrip('/')
MASTER_USER         = os.environ.get('MASTER_USER', '')
MASTER_PASS         = os.environ.get('MASTER_PASS', '')
INDEX               = 'restaurants'
BATCH_SIZE          = 500   # bulk API batch size
JSON_FILE           = os.path.join(os.path.dirname(__file__), '..', 'restaurants_expanded.json')


def check_config():
    missing = [v for v in ['OPENSEARCH_ENDPOINT', 'MASTER_USER', 'MASTER_PASS']
               if not os.environ.get(v)]
    if missing:
        print(f"ERROR: Missing environment variables: {', '.join(missing)}")
        print("Set them in your .env file or export them before running.")
        sys.exit(1)


def create_index(auth):
    """Create the index with a clean mapping. Deletes and recreates if it already exists."""
    url = f"{OPENSEARCH_ENDPOINT}/{INDEX}"

    # Check if index exists
    r = requests.head(url, auth=auth, timeout=10)
    if r.status_code == 200:
        print(f"Index '{INDEX}' already exists — deleting and recreating...")
        requests.delete(url, auth=auth, timeout=10)
        time.sleep(1)

    mapping = {
        "mappings": {
            "properties": {
                "RestaurantId": {"type": "keyword"},
                "Cuisine":      {"type": "keyword"},
                "Area":         {"type": "keyword"}
            }
        }
    }

    r = requests.put(
        url,
        auth=auth,
        headers={"Content-Type": "application/json"},
        json=mapping,
        timeout=10
    )

    if r.status_code in (200, 201):
        print(f"Index '{INDEX}' created successfully.")
    else:
        print(f"ERROR creating index: {r.status_code} {r.text}")
        sys.exit(1)


def bulk_index(restaurants, auth):
    """
    Use the OpenSearch Bulk API for fast loading.
    Sends documents in batches of BATCH_SIZE.
    """
    url        = f"{OPENSEARCH_ENDPOINT}/_bulk"
    total      = len(restaurants)
    loaded     = 0
    errors     = 0

    for i in range(0, total, BATCH_SIZE):
        batch = restaurants[i:i + BATCH_SIZE]

        # Build NDJSON payload for bulk API
        payload_lines = []
        for r in batch:
            action = {"index": {"_index": INDEX, "_id": r["BusinessID"]}}
            doc    = {
                "RestaurantId": r["BusinessID"],
                "Cuisine":      r.get("Cuisine", "Unknown"),
                "Area":         r.get("Area", "Unknown")
            }
            payload_lines.append(json.dumps(action))
            payload_lines.append(json.dumps(doc))

        payload = "\n".join(payload_lines) + "\n"

        response = requests.post(
            url,
            auth=auth,
            headers={"Content-Type": "application/x-ndjson"},
            data=payload,
            timeout=30
        )

        if response.status_code not in (200, 201):
            print(f"Bulk error (batch {i//BATCH_SIZE + 1}): {response.status_code} {response.text[:200]}")
            errors += len(batch)
            continue

        result      = response.json()
        batch_errors = sum(1 for item in result.get('items', []) if item.get('index', {}).get('error'))
        errors      += batch_errors
        loaded      += len(batch) - batch_errors

        print(f"  Batch {i//BATCH_SIZE + 1}: loaded {loaded}/{total} ({batch_errors} errors in this batch)")

    return loaded, errors


def verify_count(auth):
    """Check how many documents are in the index."""
    time.sleep(2)  # Let OpenSearch catch up
    r = requests.get(
        f"{OPENSEARCH_ENDPOINT}/{INDEX}/_count",
        auth=auth,
        timeout=10
    )
    if r.status_code == 200:
        return r.json().get('count', '?')
    return '?'


def main():
    check_config()

    auth = HTTPBasicAuth(MASTER_USER, MASTER_PASS)

    # Load restaurant data
    print(f"Loading restaurant data from: {JSON_FILE}")
    if not os.path.exists(JSON_FILE):
        print(f"ERROR: File not found: {JSON_FILE}")
        sys.exit(1)

    with open(JSON_FILE) as f:
        restaurants = json.load(f)

    print(f"Found {len(restaurants)} restaurants to index.\n")

    # Create index
    create_index(auth)

    # Bulk load
    print(f"\nIndexing in batches of {BATCH_SIZE}...")
    start   = time.time()
    loaded, errors = bulk_index(restaurants, auth)
    elapsed = round(time.time() - start, 1)

    # Verify
    count = verify_count(auth)

    print(f"\n{'='*50}")
    print(f"Done in {elapsed}s")
    print(f"  Loaded  : {loaded}")
    print(f"  Errors  : {errors}")
    print(f"  In index: {count}")
    print(f"{'='*50}")

    if errors > 0:
        print(f"\nWARNING: {errors} documents failed to index. Check output above.")
    else:
        print("\nAll restaurants indexed successfully.")


if __name__ == '__main__':
    main()