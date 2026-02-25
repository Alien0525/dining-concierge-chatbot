"""
Expanded Yelp Restaurant Scraper
Scrapes restaurants from multiple NYC locations and nearby cities
"""

import requests
import json
import time
from datetime import datetime
import config

# Expanded locations
LOCATIONS = [
    'Manhattan, NY',
    'Brooklyn, NY',
    'Queens, NY',
    'Bronx, NY',
    'Staten Island, NY',
    'Jersey City, NJ',
    'Hoboken, NJ',
    'Long Island City, NY'
]

# Cuisines to collect
CUISINES = ['japanese', 'italian', 'chinese', 'mexican', 'indian', 'thai', 'korean', 
            'french', 'mediterranean', 'american', 'vietnamese', 'spanish']

# Target restaurants per location-cuisine combination
RESTAURANTS_PER_LOCATION_CUISINE = 50  # 8 locations × 12 cuisines × 50 = 4,800 restaurants

def scrape_restaurants():
    """
    Scrape restaurants from multiple locations and cuisines
    """
    all_restaurants = []
    seen_ids = set()
    
    print(f"Starting expanded Yelp scraping...")
    print(f"Locations: {len(LOCATIONS)}, Cuisines: {len(CUISINES)}")
    print(f"Target: ~{len(LOCATIONS) * len(CUISINES) * RESTAURANTS_PER_LOCATION_CUISINE} restaurants\n")
    
    for location in LOCATIONS:
        print(f"\n{'='*60}")
        print(f"LOCATION: {location}")
        print(f"{'='*60}")
        
        for cuisine in CUISINES:
            print(f"\n  Scraping {cuisine.upper()} in {location}...")
            cuisine_count = 0
            offset = 0
            
            while cuisine_count < RESTAURANTS_PER_LOCATION_CUISINE and offset < 1000:
                
                # Make API request
                response = requests.get(
                    f"{config.YELP_API_BASE_URL}/businesses/search",
                    headers={'Authorization': f'Bearer {config.YELP_API_KEY}'},
                    params={
                        'location': location,
                        'term': f'{cuisine} restaurant',
                        'limit': 50,
                        'offset': offset
                    }
                )
                
                if response.status_code != 200:
                    print(f"    API error: {response.status_code}")
                    break
                
                data = response.json()
                businesses = data.get('businesses', [])
                
                if not businesses:
                    break
                
                # Process each restaurant
                for business in businesses:
                    business_id = business['id']
                    
                    # Skip duplicates
                    if business_id in seen_ids:
                        continue
                    
                    seen_ids.add(business_id)
                    
                    # Extract location info
                    location_data = business['location']
                    city = location_data.get('city', '')
                    state = location_data.get('state', '')
                    
                    # Determine borough/area
                    area = determine_area(city, state, location)
                    
                    # Structure restaurant data
                    restaurant = {
                        'BusinessID': business_id,
                        'Name': business['name'],
                        'Address': location_data.get('address1', 'N/A'),
                        'Latitude': business['coordinates']['latitude'],
                        'Longitude': business['coordinates']['longitude'],
                        'ReviewCount': business['review_count'],
                        'Rating': business['rating'],
                        'ZipCode': location_data.get('zip_code', 'N/A'),
                        'Cuisine': cuisine.capitalize(),
                        'City': city,
                        'State': state,
                        'Area': area,  # New field: Manhattan, Brooklyn, etc.
                        'Phone': business.get('display_phone', 'N/A'),
                        'PriceRange': business.get('price', 'N/A'),  # New field
                        'Categories': [cat['title'] for cat in business.get('categories', [])],  # New field
                        'insertedAtTimestamp': datetime.now().isoformat()
                    }
                    
                    all_restaurants.append(restaurant)
                    cuisine_count += 1
                    
                    if cuisine_count >= RESTAURANTS_PER_LOCATION_CUISINE:
                        break
                
                offset += 50
                time.sleep(0.2)  # Rate limiting
            
            print(f"    Collected {cuisine_count} {cuisine} restaurants")
        
        print(f"\n  Total from {location}: {sum(1 for r in all_restaurants if r['Area'] == determine_area('', '', location))}")
    
    print(f"\n{'='*60}")
    print(f"TOTAL RESTAURANTS SCRAPED: {len(all_restaurants)}")
    print(f"{'='*60}")
    
    return all_restaurants


def determine_area(city, state, search_location):
    """
    Determine the area/borough based on city and state
    """
    city_lower = city.lower()
    
    # NYC Boroughs
    if 'manhattan' in search_location.lower() or city_lower == 'new york':
        return 'Manhattan'
    elif 'brooklyn' in search_location.lower() or city_lower == 'brooklyn':
        return 'Brooklyn'
    elif 'queens' in search_location.lower() or city_lower == 'queens':
        return 'Queens'
    elif 'bronx' in search_location.lower() or city_lower == 'bronx':
        return 'Bronx'
    elif 'staten island' in search_location.lower() or city_lower == 'staten island':
        return 'Staten Island'
    
    # NJ cities
    elif 'jersey city' in search_location.lower() or city_lower == 'jersey city':
        return 'Jersey City'
    elif 'hoboken' in search_location.lower() or city_lower == 'hoboken':
        return 'Hoboken'
    
    # Default
    else:
        return city if city else 'Unknown'


def save_restaurants(restaurants, filename='restaurants_expanded.json'):
    """
    Save restaurant data to JSON file
    """
    with open(filename, 'w') as f:
        json.dump(restaurants, f, indent=2)
    
    print(f"\nSaved to {filename}")


def print_summary(restaurants):
    """
    Print summary statistics
    """
    print("\n" + "="*60)
    print("SUMMARY STATISTICS")
    print("="*60)
    
    print(f"\nTotal restaurants: {len(restaurants)}")
    
    # By area
    print("\nBy Area:")
    area_counts = {}
    for r in restaurants:
        area = r['Area']
        area_counts[area] = area_counts.get(area, 0) + 1
    
    for area, count in sorted(area_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"  {area}: {count}")
    
    # By cuisine
    print("\nBy Cuisine:")
    cuisine_counts = {}
    for r in restaurants:
        cuisine = r['Cuisine']
        cuisine_counts[cuisine] = cuisine_counts.get(cuisine, 0) + 1
    
    for cuisine, count in sorted(cuisine_counts.items()):
        print(f"  {cuisine}: {count}")
    
    # Average rating
    total_rating = sum(r['Rating'] for r in restaurants)
    avg_rating = total_rating / len(restaurants) if restaurants else 0
    print(f"\nAverage rating: {avg_rating:.2f}")


if __name__ == '__main__':
    restaurants = scrape_restaurants()
    save_restaurants(restaurants)
    print_summary(restaurants)