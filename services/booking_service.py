from twilio.rest import Client
from extensions import db, mail
from models import Booking, TrackingUpdate, Partnership, PricingConfig
from flask_mail import Message
from flask import render_template, current_app, jsonify, request
from datetime import datetime, timedelta, timezone  # Fixed: proper datetime imports
import requests
import json
import logging
import secrets  # Moved to top-level import
from geopy.distance import geodesic
import time


class BookingService:
    def __init__(self, app):
        self.app = app
        self.logger = app.logger  # Fixed: Store logger for use outside request context
        self.twilio_client = None
        if app.config.get('TWILIO_ACCOUNT_SID'):
            self.twilio_client = Client(
                app.config['TWILIO_ACCOUNT_SID'],
                app.config['TWILIO_AUTH_TOKEN']
            )
        
        # Initialize Distance Matrix AI API configuration
        self.distance_matrix_api_key = app.config.get('DISTANCE_MATRIX_API_KEY')
        self.geocoding_api_key = app.config.get('GEOCODING_API_KEY')
        self.api_base_url = "https://api.distancematrix.ai/maps/api"
        
        # Rate limiting
        self.rate_limit_counter = 0
        self.last_api_call = 0
    
    def _get_logger(self):
        """Get appropriate logger - handles both request and non-request contexts"""
        try:
            return current_app.logger
        except RuntimeError:
            return self.logger
    
    def _check_rate_limit(self):
        """Simple rate limiting for API calls"""
        current_time = time.time()
        if current_time - self.last_api_call < 0.1:  # 10 requests per second
            time.sleep(0.1)
        self.last_api_call = time.time()
    
    def geocode_address(self, address):
        """Geocode address using Distance Matrix AI Geocoding API"""
        if not self.geocoding_api_key or not address:
            return None
        
        logger = self._get_logger()
        
        try:
            self._check_rate_limit()
            
            # Build API URL
            encoded_address = requests.utils.quote(address)
            url = f"{self.api_base_url}/geocode/json?address={encoded_address}&key={self.geocoding_api_key}"
            
            # Make API request
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if data.get('status') == 'OK' and data.get('result'):
                result = data['result'][0]
                location = result['geometry']['location']
                formatted_address = result.get('formatted_address', address)
                
                # Extract address components
                address_components = {}
                for component in result.get('address_components', []):
                    for type_name in component.get('types', []):  # Fixed: added .get() for safety
                        address_components[type_name] = component.get('long_name', '')
                
                return {
                    'latitude': location['lat'],
                    'longitude': location['lng'],
                    'formatted_address': formatted_address,
                    'address_components': address_components,
                    'place_id': result.get('place_id', ''),
                    'location_type': result['geometry'].get('location_type', 'APPROXIMATE')
                }
            
            logger.warning(f"Geocoding failed for '{address}': {data.get('status')}")
            return None
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Geocoding API request failed: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Geocoding failed for '{address}': {str(e)}")
            return None
    
    def calculate_distance_matrix(self, origin, destination, mode="driving"):
        """Calculate distance using Distance Matrix AI API"""
        if not self.distance_matrix_api_key or not origin or not destination:
            return None
        
        logger = self._get_logger()
        
        try:
            self._check_rate_limit()
            
            # First, geocode both addresses to get coordinates
            origin_geocode = self.geocode_address(origin)
            destination_geocode = self.geocode_address(destination)
            
            if not origin_geocode or not destination_geocode:
                logger.error("Failed to geocode addresses")
                return None
            
            # Build API URL with coordinates
            origins = f"{origin_geocode['latitude']},{origin_geocode['longitude']}"
            destinations = f"{destination_geocode['latitude']},{destination_geocode['longitude']}"
            
            url = f"{self.api_base_url}/distancematrix/json"
            params = {
                'origins': origins,
                'destinations': destinations,
                'key': self.distance_matrix_api_key,
                'mode': mode,
                'units': 'metric'
            }
            
            # Make API request
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if data.get('status') == 'OK' and data.get('rows'):
                row = data['rows'][0]
                elements = row.get('elements', [])
                
                if not elements:  # Fixed: Check if elements exist
                    logger.warning("No elements in distance matrix response")
                    return None
                    
                element = elements[0]
                
                if element.get('status') == 'OK':  # Fixed: use .get() for safety
                    # Extract distance and duration
                    distance_meters = element['distance']['value']
                    distance_km = distance_meters / 1000
                    distance_text = element['distance']['text']
                    
                    duration_seconds = element['duration']['value']
                    duration_text = element['duration']['text']
                    
                    # Get address texts
                    origin_address = data.get('origin_addresses', [origin])[0] if data.get('origin_addresses') else origin
                    destination_address = data.get('destination_addresses', [destination])[0] if data.get('destination_addresses') else destination
                    
                    # Calculate straight-line distance for reference
                    origin_coords = (origin_geocode['latitude'], origin_geocode['longitude'])
                    dest_coords = (destination_geocode['latitude'], destination_geocode['longitude'])
                    straight_distance_km = geodesic(origin_coords, dest_coords).km
                    
                    # Get current pricing configuration
                    pricing_config = PricingConfig.get_current()
                    
                    # Calculate base price
                    base_price = distance_km * pricing_config.price_per_km
                    
                    # Apply minimum price
                    if base_price < pricing_config.minimum_price:
                        base_price = pricing_config.minimum_price
                    
                    return {
                        'success': True,
                        'driving_distance_km': round(distance_km, 2),
                        'driving_distance_text': distance_text,
                        'straight_distance_km': round(straight_distance_km, 2),
                        'duration_seconds': duration_seconds,
                        'duration_text': duration_text,
                        'base_price': round(base_price, 2),
                        'origin_address': origin_address,
                        'destination_address': destination_address,
                        'origin_formatted': origin_geocode['formatted_address'],
                        'destination_formatted': destination_geocode['formatted_address'],
                        'origin_coords': {
                            'lat': origin_geocode['latitude'],
                            'lng': origin_geocode['longitude']
                        },
                        'destination_coords': {
                            'lat': destination_geocode['latitude'],
                            'lng': destination_geocode['longitude']
                        },
                        'mode': mode
                    }
                else:
                    logger.warning(f"Element status not OK: {element.get('status')}")
            
            logger.warning(f"Distance Matrix API returned error: {data.get('status')}")
            return None
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Distance Matrix API request failed: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Distance calculation failed: {str(e)}")
            return None
    
    def calculate_final_price(self, distance_data, weight, package_value, service_type, 
                             insurance_required=False, signature_required=False):
        """Calculate final price with all factors"""
        if not distance_data:
            return None
        
        # Get current pricing configuration
        pricing_config = PricingConfig.get_current()
        
        # Start with base distance price
        total_price = distance_data['base_price']
        
        # Add weight surcharge
        if weight > 5:
            total_price += (weight - 5) * pricing_config.weight_surcharge_per_kg
        if weight > 20:
            total_price += (weight - 20) * pricing_config.heavy_surcharge_per_kg
        
        # Add service type multiplier
        service_multipliers = {
            'express': pricing_config.express_multiplier,
            'standard': pricing_config.standard_multiplier,
            'economy': pricing_config.economy_multiplier
        }
        
        multiplier = service_multipliers.get(service_type, 1.0)
        total_price *= multiplier
        
        # Add insurance
        if insurance_required and package_value > 0:
            total_price += package_value * pricing_config.insurance_rate
        
        # Add signature required fee
        if signature_required:
            total_price += pricing_config.signature_fee
        
        # Ensure minimum price
        if total_price < pricing_config.minimum_price:
            total_price = pricing_config.minimum_price
        
        return round(total_price, 2)
    
    def create_booking(self, data):
        """Create a new booking with distance-based pricing"""
        # Fixed: Removed redundant local import, using top-level imports now
        
        # Generate booking ID
        booking_id = f"BOOK-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{secrets.token_hex(4).upper()}"
        
        # Get pricing configuration
        pricing_config = PricingConfig.get_current()
        
        # Calculate distance and price
        pickup_address = data.get('pickup_address')
        delivery_address = data.get('delivery_address')
        distance_data = None
        
        if pickup_address and delivery_address:
            distance_data = self.calculate_distance_matrix(pickup_address, delivery_address)
        
        # Calculate amount
        weight = float(data.get('weight', 0))
        package_value = float(data.get('package_value', 0))
        service_type = data.get('service_type', 'standard')
        insurance_required = data.get('insurance_required', False)
        signature_required = data.get('signature_required', False)
        
        if distance_data:
            amount = self.calculate_final_price(
                distance_data, weight, package_value, service_type, 
                insurance_required, signature_required
            )
        else:
            # Fallback to minimum price
            amount = pricing_config.minimum_price
        
        # Calculate estimated delivery date
        # Fixed: Handle both string and datetime objects for pickup_date
        pickup_date_raw = data.get('pickup_date')
        if isinstance(pickup_date_raw, str):
            pickup_date = datetime.fromisoformat(pickup_date_raw.replace('Z', '+00:00'))
        elif isinstance(pickup_date_raw, datetime):
            pickup_date = pickup_date_raw
        else:
            pickup_date = datetime.now(timezone.utc)
        
        # Get duration from distance data if available
        if distance_data and 'duration_seconds' in distance_data:
            # Add buffer time for processing and service type
            buffer_days = 1 if service_type == 'express' else 2 if service_type == 'standard' else 4
            estimated_delivery = pickup_date + timedelta(
                seconds=distance_data['duration_seconds'] + (buffer_days * 86400)
            )
        else:
            # Fallback based on service type
            if service_type == 'express':
                estimated_delivery = pickup_date + timedelta(days=1)
            elif service_type == 'standard':
                estimated_delivery = pickup_date + timedelta(days=3)
            else:  # economy
                estimated_delivery = pickup_date + timedelta(days=7)
        
        booking = Booking(
            id=booking_id,
            user_id=data.get('user_id'),
            package_type=data.get('package_type', 'standard'),  # Fixed: added default
            weight=weight,
            dimensions=data.get('dimensions'),
            package_value=package_value,
            insurance_required=insurance_required,
            special_instructions=data.get('special_instructions'),
            amount=amount,
            pickup_date=pickup_date,
            estimated_delivery=estimated_delivery,
            pickup_address=pickup_address,
            delivery_address=delivery_address,
            service_type=service_type,
            pickup_contact=data.get('pickup_contact', ''),
            pickup_phone=data.get('pickup_phone', ''),
            delivery_contact=data.get('delivery_contact', ''),
            delivery_phone=data.get('delivery_phone', ''),
            signature_required=signature_required,
            distance_km=distance_data.get('driving_distance_km') if distance_data else None,
            duration_seconds=distance_data.get('duration_seconds') if distance_data else None,
            base_price=distance_data.get('base_price') if distance_data else None,
            origin_coords=json.dumps(distance_data.get('origin_coords')) if distance_data else None,
            destination_coords=json.dumps(distance_data.get('destination_coords')) if distance_data else None
        )
        
        booking.generate_tracking_number()
        
        db.session.add(booking)
        db.session.commit()
        
        # Send notifications (with error handling)
        try:
            self.send_booking_confirmation(booking)
        except Exception as e:
            self._get_logger().error(f"Failed to send booking confirmation: {str(e)}")
        
        try:
            self.send_whatsapp_notification(booking)
        except Exception as e:
            self._get_logger().error(f"Failed to send WhatsApp notification: {str(e)}")
        
        return booking
    
    def send_whatsapp_notification(self, booking):
        """Send WhatsApp notification"""
        if not self.twilio_client:
            return None
        
        # Fixed: Check if user and phone exist before sending
        if not booking.user or not booking.user.phone:
            self._get_logger().warning(f"Cannot send WhatsApp for booking {booking.id}: no user phone")
            return None
        
        try:
            message = self.twilio_client.messages.create(
                body=f"Your booking #{booking.id} has been confirmed. "
                     f"Tracking number: {booking.tracking_number}. "
                     f"Est. delivery: {booking.estimated_delivery.strftime('%Y-%m-%d')}",
                from_=f"whatsapp:{self.app.config['TWILIO_PHONE_NUMBER']}",
                to=f"whatsapp:{booking.user.phone}"
            )
            return message.sid
        except Exception as e:
            self._get_logger().error(f"WhatsApp notification failed: {str(e)}")
            return None
    
    def send_booking_confirmation(self, booking):
        """Send email confirmation"""
        if not self.app.config.get('MAIL_USERNAME'):
            return None
        
        # Fixed: Check if user and email exist
        if not booking.user or not booking.user.email:
            self._get_logger().warning(f"Cannot send email for booking {booking.id}: no user email")
            return None
        
        msg = Message(
            subject=f"Booking Confirmation #{booking.id}",
            recipients=[booking.user.email],
            sender=self.app.config['MAIL_USERNAME']
        )
        
        try:
            msg.html = render_template('emails/booking_confirmation.html', 
                                      booking=booking)
            mail.send(msg)
            return True
        except Exception as e:
            self._get_logger().error(f"Email sending failed: {str(e)}")
            return None
    
    def send_partnership_notification(self, partnership):
        """Notify admin about partnership application"""
        admin_email = self.app.config.get('ADMIN_EMAIL')
        mail_username = self.app.config.get('MAIL_USERNAME')
        
        # Fixed: Check if admin email and mail config exist
        if not admin_email or not mail_username:
            self._get_logger().warning("Cannot send partnership notification: missing email config")
            return None
        
        msg = Message(
            subject=f"New Partnership Application - {partnership.company_name}",
            recipients=[admin_email],
            sender=mail_username
        )
        
        msg.body = f"""
        New Partnership Application:
        
        Company: {partnership.company_name}
        Contact: {partnership.contact_person}
        Email: {partnership.email}
        Phone: {partnership.phone}
        Business Type: {partnership.business_type}
        Message: {partnership.message}
        """
        
        try:
            mail.send(msg)
            return True
        except Exception as e:
            self._get_logger().error(f"Partnership notification failed: {str(e)}")
            return None
    
    def update_tracking(self, booking_id, location, status, description):
        """Add tracking update"""
        booking = Booking.query.get(booking_id)
        if not booking:
            return None
        
        update = TrackingUpdate(
            booking_id=booking_id,
            location=location,
            status=status,
            description=description
        )
        
        booking.status = status
        booking.updated_at = datetime.now(timezone.utc)  # Fixed: proper datetime usage
        
        db.session.add(update)
        db.session.commit()
        
        # Send status update notification
        try:
            self.send_status_update(booking, status)
        except Exception as e:
            self._get_logger().error(f"Failed to send status update: {str(e)}")
        
        return update
    
    # Fixed: Added missing send_status_update method
    def send_status_update(self, booking, status):
        """Send status update notification to user"""
        if not booking.user:
            return None
        
        # Send email notification
        if booking.user.email and self.app.config.get('MAIL_USERNAME'):
            try:
                msg = Message(
                    subject=f"Booking #{booking.id} Status Update: {status}",
                    recipients=[booking.user.email],
                    sender=self.app.config['MAIL_USERNAME']
                )
                
                msg.body = f"""
                Your booking status has been updated.
                
                Booking ID: {booking.id}
                Tracking Number: {booking.tracking_number}
                New Status: {status}
                
                Track your package at: {self.app.config.get('APP_URL', '')}/track/{booking.tracking_number}
                """
                
                mail.send(msg)
            except Exception as e:
                self._get_logger().error(f"Status update email failed: {str(e)}")
        
        # Send WhatsApp notification
        if self.twilio_client and booking.user.phone:
            try:
                self.twilio_client.messages.create(
                    body=f"Booking #{booking.id} update: Status changed to {status}. "
                         f"Track: {booking.tracking_number}",
                    from_=f"whatsapp:{self.app.config['TWILIO_PHONE_NUMBER']}",
                    to=f"whatsapp:{booking.user.phone}"
                )
            except Exception as e:
                self._get_logger().error(f"Status update WhatsApp failed: {str(e)}")
        
        return True