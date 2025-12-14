# geocoding.py
"""
Nigerian geocoding utilities with fallback location database
"""

import requests
import time
from typing import Optional, Dict, Tuple
import re

# Known locations in Abuja and major Nigerian cities
NIGERIAN_LOCATIONS = {
    # Abuja Locations
    'kubwa': {'lat': 9.1167, 'lng': 7.3833, 'city': 'Abuja'},
    'chikakore': {'lat': 9.1200, 'lng': 7.3700, 'city': 'Abuja'},
    'lifecamp': {'lat': 9.0820, 'lng': 7.4010, 'city': 'Abuja'},
    'life camp': {'lat': 9.0820, 'lng': 7.4010, 'city': 'Abuja'},
    'julius berger': {'lat': 9.0800, 'lng': 7.4000, 'city': 'Abuja'},
    'gwarinpa': {'lat': 9.0833, 'lng': 7.4167, 'city': 'Abuja'},
    'wuse': {'lat': 9.0765, 'lng': 7.4897, 'city': 'Abuja'},
    'wuse 2': {'lat': 9.0780, 'lng': 7.4750, 'city': 'Abuja'},
    'maitama': {'lat': 9.0833, 'lng': 7.5000, 'city': 'Abuja'},
    'asokoro': {'lat': 9.0422, 'lng': 7.5256, 'city': 'Abuja'},
    'garki': {'lat': 9.0167, 'lng': 7.4833, 'city': 'Abuja'},
    'garki 2': {'lat': 9.0200, 'lng': 7.4900, 'city': 'Abuja'},
    'jabi': {'lat': 9.0667, 'lng': 7.4333, 'city': 'Abuja'},
    'utako': {'lat': 9.0736, 'lng': 7.4392, 'city': 'Abuja'},
    'lugbe': {'lat': 8.9833, 'lng': 7.3833, 'city': 'Abuja'},
    'nyanya': {'lat': 9.0167, 'lng': 7.5667, 'city': 'Abuja'},
    'karu': {'lat': 9.0333, 'lng': 7.6167, 'city': 'Abuja'},
    'mpape': {'lat': 9.1167, 'lng': 7.4833, 'city': 'Abuja'},
    'dutse': {'lat': 9.0667, 'lng': 7.5000, 'city': 'Abuja'},
    'bwari': {'lat': 9.2833, 'lng': 7.3833, 'city': 'Abuja'},
    'gwagwalada': {'lat': 8.9500, 'lng': 7.0833, 'city': 'Abuja'},
    'airport road': {'lat': 9.0500, 'lng': 7.4500, 'city': 'Abuja'},
    'central area': {'lat': 9.0578, 'lng': 7.4951, 'city': 'Abuja'},
    'area 1': {'lat': 9.0400, 'lng': 7.4800, 'city': 'Abuja'},
    'area 3': {'lat': 9.0450, 'lng': 7.4850, 'city': 'Abuja'},
    'area 11': {'lat': 9.0550, 'lng': 7.4700, 'city': 'Abuja'},
    'kado': {'lat': 9.0900, 'lng': 7.4600, 'city': 'Abuja'},
    'dawaki': {'lat': 9.1100, 'lng': 7.4800, 'city': 'Abuja'},
    'katampe': {'lat': 9.0950, 'lng': 7.4300, 'city': 'Abuja'},
    'lokogoma': {'lat': 8.9700, 'lng': 7.4200, 'city': 'Abuja'},
    'apo': {'lat': 9.0000, 'lng': 7.5100, 'city': 'Abuja'},
    'durumi': {'lat': 9.0100, 'lng': 7.4600, 'city': 'Abuja'},
    'gudu': {'lat': 9.0050, 'lng': 7.4800, 'city': 'Abuja'},
    'wuye': {'lat': 9.0800, 'lng': 7.4600, 'city': 'Abuja'},
    
    # Lagos Locations
    'ikeja': {'lat': 6.6018, 'lng': 3.3515, 'city': 'Lagos'},
    'victoria island': {'lat': 6.4281, 'lng': 3.4219, 'city': 'Lagos'},
    'vi': {'lat': 6.4281, 'lng': 3.4219, 'city': 'Lagos'},
    'lekki': {'lat': 6.4698, 'lng': 3.5852, 'city': 'Lagos'},
    'ikoyi': {'lat': 6.4549, 'lng': 3.4367, 'city': 'Lagos'},
    'yaba': {'lat': 6.5095, 'lng': 3.3711, 'city': 'Lagos'},
    'surulere': {'lat': 6.5059, 'lng': 3.3509, 'city': 'Lagos'},
    'maryland': {'lat': 6.5714, 'lng': 3.3633, 'city': 'Lagos'},
    'ajah': {'lat': 6.4667, 'lng': 3.6000, 'city': 'Lagos'},
    'oshodi': {'lat': 6.5333, 'lng': 3.3333, 'city': 'Lagos'},
    'apapa': {'lat': 6.4500, 'lng': 3.3667, 'city': 'Lagos'},
    'festac': {'lat': 6.4667, 'lng': 3.2833, 'city': 'Lagos'},
    'marina': {'lat': 6.4500, 'lng': 3.4000, 'city': 'Lagos'},
    'ojuelegba': {'lat': 6.5167, 'lng': 3.3667, 'city': 'Lagos'},
    'mushin': {'lat': 6.5333, 'lng': 3.3500, 'city': 'Lagos'},
    'agege': {'lat': 6.6167, 'lng': 3.3167, 'city': 'Lagos'},
    'ogba': {'lat': 6.6167, 'lng': 3.3333, 'city': 'Lagos'},
    'berger': {'lat': 6.6000, 'lng': 3.3500, 'city': 'Lagos'},
    'iyana ipaja': {'lat': 6.6167, 'lng': 3.2667, 'city': 'Lagos'},
    'alimosho': {'lat': 6.6167, 'lng': 3.2500, 'city': 'Lagos'},
    
    # Port Harcourt
    'port harcourt': {'lat': 4.8156, 'lng': 7.0498, 'city': 'Port Harcourt'},
    'trans amadi': {'lat': 4.8000, 'lng': 7.0333, 'city': 'Port Harcourt'},
    'rumuokoro': {'lat': 4.8500, 'lng': 7.0167, 'city': 'Port Harcourt'},
    'rumuola': {'lat': 4.8333, 'lng': 7.0333, 'city': 'Port Harcourt'},
    'gra port harcourt': {'lat': 4.8167, 'lng': 7.0167, 'city': 'Port Harcourt'},
    
    # Kano
    'kano': {'lat': 12.0022, 'lng': 8.5920, 'city': 'Kano'},
    'sabon gari kano': {'lat': 11.9833, 'lng': 8.5333, 'city': 'Kano'},
    
    # Ibadan
    'ibadan': {'lat': 7.3775, 'lng': 3.9470, 'city': 'Ibadan'},
    'bodija': {'lat': 7.4167, 'lng': 3.9000, 'city': 'Ibadan'},
    'challenge': {'lat': 7.3667, 'lng': 3.9167, 'city': 'Ibadan'},
    'ui': {'lat': 7.4500, 'lng': 3.9000, 'city': 'Ibadan'},
    
    # Enugu
    'enugu': {'lat': 6.4584, 'lng': 7.5464, 'city': 'Enugu'},
    'independence layout': {'lat': 6.4500, 'lng': 7.5000, 'city': 'Enugu'},
    
    # Other major cities
    'kaduna': {'lat': 10.5222, 'lng': 7.4383, 'city': 'Kaduna'},
    'benin city': {'lat': 6.3350, 'lng': 5.6037, 'city': 'Benin City'},
    'warri': {'lat': 5.5167, 'lng': 5.7500, 'city': 'Warri'},
    'calabar': {'lat': 4.9517, 'lng': 8.3220, 'city': 'Calabar'},
    'jos': {'lat': 9.8965, 'lng': 8.8583, 'city': 'Jos'},
    'maiduguri': {'lat': 11.8333, 'lng': 13.1500, 'city': 'Maiduguri'},
    'owerri': {'lat': 5.4833, 'lng': 7.0333, 'city': 'Owerri'},
    'uyo': {'lat': 5.0500, 'lng': 7.9333, 'city': 'Uyo'},
    'akure': {'lat': 7.2500, 'lng': 5.1950, 'city': 'Akure'},
    'abeokuta': {'lat': 7.1608, 'lng': 3.3483, 'city': 'Abeokuta'},
    'ilorin': {'lat': 8.4799, 'lng': 4.5418, 'city': 'Ilorin'},
    'lokoja': {'lat': 7.8000, 'lng': 6.7333, 'city': 'Lokoja'},
    'sokoto': {'lat': 13.0622, 'lng': 5.2339, 'city': 'Sokoto'},
    'zaria': {'lat': 11.0667, 'lng': 7.7000, 'city': 'Zaria'},
}


def normalize_address(address: str) -> str:
    """Normalize address for matching"""
    # Convert to lowercase
    normalized = address.lower().strip()
    # Remove common words
    remove_words = ['street', 'road', 'avenue', 'close', 'crescent', 'drive', 
                   'estate', 'layout', 'phase', 'extension', 'ext', 'nigeria',
                   'fct', 'state', ',', '.', '-', 'near', 'opposite', 'beside',
                   'behind', 'after', 'before', 'junction', 'bus stop']
    for word in remove_words:
        normalized = normalized.replace(word, ' ')
    # Remove extra spaces
    normalized = ' '.join(normalized.split())
    return normalized


def find_known_location(address: str) -> Optional[Dict]:
    """
    Try to find a known location in the address string.
    Returns coordinates if found.
    """
    normalized = normalize_address(address)
    
    # Try to find exact matches first
    for location_name, coords in NIGERIAN_LOCATIONS.items():
        if location_name in normalized:
            return {
                'latitude': coords['lat'],
                'longitude': coords['lng'],
                'formatted_address': f"{location_name.title()}, {coords['city']}, Nigeria",
                'city': coords['city'],
                'match_type': 'known_location',
                'matched_term': location_name
            }
    
    return None


def geocode_with_nominatim(address: str, timeout: int = 10) -> Optional[Dict]:
    """
    Geocode using OpenStreetMap Nominatim API.
    Free, no API key required.
    """
    try:
        # Rate limiting - Nominatim requires max 1 request per second
        time.sleep(1.1)
        
        nominatim_url = "https://nominatim.openstreetmap.org/search"
        
        # Try with full address first
        params = {
            'q': address,
            'format': 'json',
            'limit': 1,
            'addressdetails': 1,
            'countrycodes': 'ng'  # Limit to Nigeria
        }
        
        headers = {
            'User-Agent': 'MajestyXpressLogistics/1.0 (contact@majestyxpress.com)'
        }
        
        response = requests.get(nominatim_url, params=params, headers=headers, timeout=timeout)
        
        if response.status_code == 200:
            results = response.json()
            if results:
                location = results[0]
                return {
                    'latitude': float(location['lat']),
                    'longitude': float(location['lon']),
                    'formatted_address': location.get('display_name', address),
                    'address_components': location.get('address', {}),
                    'match_type': 'nominatim'
                }
        
        # If no results, try simplified search
        simplified = normalize_address(address)
        params['q'] = f"{simplified}, Nigeria"
        
        response = requests.get(nominatim_url, params=params, headers=headers, timeout=timeout)
        
        if response.status_code == 200:
            results = response.json()
            if results:
                location = results[0]
                return {
                    'latitude': float(location['lat']),
                    'longitude': float(location['lon']),
                    'formatted_address': location.get('display_name', address),
                    'address_components': location.get('address', {}),
                    'match_type': 'nominatim_simplified'
                }
        
        return None
        
    except Exception as e:
        print(f"Nominatim geocoding error: {str(e)}")
        return None


def geocode_address(address: str) -> Optional[Dict]:
    """
    Main geocoding function with fallbacks:
    1. Try known locations database
    2. Try Nominatim
    3. Return None if all fail
    """
    if not address or len(address.strip()) < 3:
        return None
    
    address = address.strip()
    
    # First, try known locations (fast, offline)
    known_result = find_known_location(address)
    if known_result:
        print(f"Found in known locations: {known_result['matched_term']}")
        return known_result
    
    # Try Nominatim (online, slower)
    nominatim_result = geocode_with_nominatim(address)
    if nominatim_result:
        print(f"Found via Nominatim: {nominatim_result['formatted_address'][:50]}...")
        return nominatim_result
    
    # Final fallback - try to extract city name
    for city_name, coords in NIGERIAN_LOCATIONS.items():
        if city_name in address.lower():
            return {
                'latitude': coords['lat'],
                'longitude': coords['lng'],
                'formatted_address': f"{address} (approximate: {city_name.title()})",
                'match_type': 'city_fallback',
                'is_approximate': True
            }
    
    return None


def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate distance between two points using Haversine formula.
    Returns distance in kilometers.
    """
    from math import radians, sin, cos, sqrt, atan2
    
    R = 6371  # Earth's radius in kilometers
    
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))
    
    return R * c


def calculate_route(origin: str, destination: str, mode: str = 'driving') -> Optional[Dict]:
    """
    Calculate route between two addresses.
    """
    # Geocode both addresses
    origin_geo = geocode_address(origin)
    dest_geo = geocode_address(destination)
    
    if not origin_geo:
        return {'success': False, 'error': f'Could not locate origin: {origin}'}
    
    if not dest_geo:
        return {'success': False, 'error': f'Could not locate destination: {destination}'}
    
    # Calculate straight-line distance
    straight_distance = calculate_distance(
        origin_geo['latitude'], origin_geo['longitude'],
        dest_geo['latitude'], dest_geo['longitude']
    )
    
    # Estimate driving distance (typically 1.2-1.5x straight line in urban areas)
    # Use 1.3x for cities, 1.2x for highways
    is_same_city = origin_geo.get('city') == dest_geo.get('city')
    distance_multiplier = 1.3 if is_same_city else 1.25
    
    driving_distance = straight_distance * distance_multiplier
    
    # Estimate duration based on mode and distance
    speed_kmh = {
        'driving': 35 if is_same_city else 60,  # City traffic vs highway
        'walking': 5,
        'bicycling': 15
    }
    
    avg_speed = speed_kmh.get(mode, 35)
    duration_hours = driving_distance / avg_speed
    duration_seconds = int(duration_hours * 3600)
    duration_minutes = int(duration_hours * 60)
    
    # Format duration text
    if duration_hours < 1:
        duration_text = f"{duration_minutes} min"
    else:
        hours = int(duration_hours)
        minutes = int((duration_hours - hours) * 60)
        duration_text = f"{hours} hr {minutes} min" if minutes > 0 else f"{hours} hr"
    
    return {
        'success': True,
        'driving_distance_km': round(driving_distance, 1),
        'driving_distance_text': f"{round(driving_distance, 1)} km",
        'straight_distance_km': round(straight_distance, 1),
        'duration_seconds': duration_seconds,
        'duration_text': duration_text,
        'origin_coords': {
            'lat': origin_geo['latitude'],
            'lng': origin_geo['longitude']
        },
        'destination_coords': {
            'lat': dest_geo['latitude'],
            'lng': dest_geo['longitude']
        },
        'origin_address': origin_geo['formatted_address'],
        'destination_address': dest_geo['formatted_address'],
        'origin_match_type': origin_geo.get('match_type', 'unknown'),
        'destination_match_type': dest_geo.get('match_type', 'unknown'),
        'mode': mode,
        'is_same_city': is_same_city
    }


# Test function
if __name__ == '__main__':
    # Test with your addresses
    test_cases = [
        ("Chikakore, Kubwa, Abuja", "Julius Berger, Lifecamp, Abuja"),
        ("Wuse 2, Abuja", "Maitama, Abuja"),
        ("Ikeja, Lagos", "Victoria Island, Lagos"),
        ("Abuja", "Lagos"),
    ]
    
    for origin, dest in test_cases:
        print(f"\n{'='*60}")
        print(f"From: {origin}")
        print(f"To: {dest}")
        result = calculate_route(origin, dest)
        if result.get('success'):
            print(f"Distance: {result['driving_distance_text']}")
            print(f"Duration: {result['duration_text']}")
            print(f"Origin match: {result['origin_match_type']}")
            print(f"Dest match: {result['destination_match_type']}")
        else:
            print(f"Error: {result.get('error')}")