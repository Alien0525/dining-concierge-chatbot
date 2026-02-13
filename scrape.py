"""
Yelp Restaurant Scraper
Scrapes restaurant data from Yelp Fusion API for Manhattan.
Collects 1000+ restaurants across multiple cuisine types.
"""

import requests
import json
import time
from datetime import datetime
import config

def scrape_restaurants():
    """
    Scrapes restaurants from Yelp API for multiple cuisines in Manhattan.
    
    Purpose:
    - Populate DynamoDB with restaurant data
    - Provide data for ElasticSearch indexing
    - Enable chatbot to make recommendations
    
    Returns:
        list: List of restaurant dictionaries with full details
    """
    all_restaurants = []
    seen_ids = set()
    
    print(f"Starting Yelp scraping for {config.TARGET_LOCATION}")
    print(f"Target: {config.TOTAL_RESTAURANTS_TARGET} restaurants across {len(config.CUISINES)} cuisines\n")
    
    for cuisine in config.CUISINES:
        print(f"Scraping {cuisine.upper()} restaurants...")
        cuisine_count = 0
        offset = 0
        
        while cuisine_count < config.RESTAURANTS_PER_CUISINE and offset < 1000:
            
            # Construct API request
            url = f"{config.YELP_API_BASE_URL}/businesses/search"
            headers = {'Authorization': f'Bearer {config.YELP_API_KEY}'}
            params = {
                'location': config.TARGET_LOCATION,
                'term': f'{cuisine} restaurant',
                'limit': config.YELP_API_LIMIT,
                'offset': offset
            }
            
            # Make API call
            response = requests.get(url, headers=headers, params=params)
            
            # Handle API errors
            if response.status_code != 200:
                print(f"  API error: {response.status_code} - {response.text}")
                break
            
            data = response.json()
            businesses = data.get('businesses', [])
            
            # Stop if no more results
            if not businesses:
                print(f"  No more results for {cuisine}")
                break
            
            # Process each restaurant
            for business in businesses:
                business_id = business['id']
                
                # Skip duplicates
                if business_id in seen_ids:
                    continue
                
                seen_ids.add(business_id)
                
                # Structure restaurant data according to assignment requirements
                # Required fields: Business ID, Name, Address, Coordinates, 
                # Number of Reviews, Rating, Zip Code
                restaurant = {
                    'BusinessID': business_id,
                    'Name': business['name'],
                    'Address': business['location'].get('address1', 'N/A'),
                    'Latitude': business['coordinates']['latitude'],
                    'Longitude': business['coordinates']['longitude'],
                    'ReviewCount': business['review_count'],
                    'Rating': business['rating'],
                    'ZipCode': business['location'].get('zip_code', 'N/A'),
                    'Cuisine': cuisine.capitalize(),
                    'City': business['location'].get('city', 'New York'),
                    'State': business['location'].get('state', 'NY'),
                    'Phone': business.get('display_phone', 'N/A'),
                    'insertedAtTimestamp': datetime.now().isoformat()
                }
                
                all_restaurants.append(restaurant)
                cuisine_count += 1
                
                if cuisine_count >= config.RESTAURANTS_PER_CUISINE:
                    break
            
            # Pagination
            offset += config.YELP_API_LIMIT
            
            # Rate limiting to be respectful to Yelp API
            # 0.2 seconds between requests = max 5 requests/second
            time.sleep(0.2)
        
        print(f"  Collected {cuisine_count} {cuisine} restaurants\n")
    
    print(f"Total restaurants scraped: {len(all_restaurants)}")
    return all_restaurants

def save_restaurants(restaurants, filename='restaurants.json'):
    """
    Saves restaurant data to JSON file.
    
    Purpose:
    - Human-readable format for inspection
    - Easy to load into DynamoDB later
    - Backup of scraped data
    
    Args:
        restaurants (list): List of restaurant dictionaries
        filename (str): Output filename
    """
    with open(filename, 'w') as f:
        json.dump(restaurants, f, indent=2)
    
    print(f"Saved {len(restaurants)} restaurants to {filename}")

def print_summary(restaurants):
    """
    Prints summary statistics of scraped data.
    
    Purpose:
    - Quick validation of data quality
    - Ensure we have good distribution across cuisines
    
    Args:
        restaurants (list): List of restaurant dictionaries
    """
    print("\nSummary Statistics:")
    print(f"Total restaurants: {len(restaurants)}")
    
    # Count by cuisine
    cuisine_counts = {}
    for restaurant in restaurants:
        cuisine = restaurant['Cuisine']
        cuisine_counts[cuisine] = cuisine_counts.get(cuisine, 0) + 1
    
    print("\nBreakdown by cuisine:")
    for cuisine, count in sorted(cuisine_counts.items()):
        print(f"  {cuisine}: {count}")
    
    # Average rating
    total_rating = sum(r['Rating'] for r in restaurants)
    avg_rating = total_rating / len(restaurants) if restaurants else 0
    print(f"\nAverage rating: {avg_rating:.2f}")

if __name__ == '__main__':
    # Main execution
    restaurants = scrape_restaurants()
    save_restaurants(restaurants)
    print_summary(restaurants)