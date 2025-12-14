from flask import Flask, current_app, render_template, request, redirect, url_for, flash, jsonify, session
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from extensions import db, login_manager, mail, cors, admin
from models import User, Booking, Partnership, Address, Payment, TrackingUpdate
from services.booking_service import BookingService
import os
import secrets
from datetime import datetime, timezone  # Fixed: Added timezone import
import urllib.parse
from functools import wraps  # Added for admin_required decorator

from geopy.distance import geodesic
import requests
import json
import hashlib  # Moved to top-level
import random  # Moved to top-level
from math import radians, sin, cos, sqrt, atan2  # Moved to top-level

from geocoding import geocode_address as geo_geocode, calculate_route as geo_calculate_route

def generate_mock_route_data(origin, destination, mode='driving'):
    """Generate mock route data for testing - moved outside create_app"""
    try:
        def mock_coords(text):
            # Generate consistent coordinates based on text hash
            hash_obj = hashlib.md5(text.encode())
            hash_int = int(hash_obj.hexdigest()[:8], 16)
            
            # Nigeria bounds: lat 4-14, lng 3-15
            lat = 4 + (hash_int % 100000) / 100000 * 10
            lng = 3 + (hash_int // 100000 % 100000) / 100000 * 12
            
            return {'lat': round(lat, 6), 'lng': round(lng, 6)}
        
        def haversine_distance(lat1, lon1, lat2, lon2):
            R = 6371  # Earth radius in kilometers
            
            lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
            dlat = lat2 - lat1
            dlon = lon2 - lon1
            
            a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
            c = 2 * atan2(sqrt(a), sqrt(1-a))
            
            return R * c
        
        # Get mock coordinates
        origin_coords = mock_coords(origin)
        dest_coords = mock_coords(destination)
        
        # Calculate distance
        distance_km = haversine_distance(
            origin_coords['lat'], origin_coords['lng'],
            dest_coords['lat'], dest_coords['lng']
        )
        
        # Add realistic randomness
        distance_km = max(1, round(distance_km * random.uniform(0.8, 1.2), 1))
        
        # Calculate duration based on mode
        mode_speeds = {
            'driving': random.uniform(30, 60),  # km/h
            'walking': random.uniform(4, 6),    # km/h
            'bicycling': random.uniform(12, 20) # km/h
        }
        
        speed = mode_speeds.get(mode, 40)
        duration_hours = distance_km / speed
        duration_minutes = int(duration_hours * 60)
        
        # Format duration text
        if duration_hours < 1:
            duration_text = f"{duration_minutes} min"
        else:
            hours = int(duration_hours)
            minutes = int((duration_hours - hours) * 60)
            duration_text = f"{hours} hr {minutes} min"
        
        # Calculate base price using defaults if not in app context
        try:
            price_per_km = current_app.config.get('PRICE_PER_KM', 200)
            minimum_price = current_app.config.get('MINIMUM_DELIVERY_PRICE', 500)
        except RuntimeError:
            price_per_km = 200
            minimum_price = 500
        
        base_price = distance_km * price_per_km
        
        if base_price < minimum_price:
            base_price = minimum_price
        
        return {
            'success': True,
            'driving_distance_km': round(distance_km, 2),
            'driving_distance_text': f"{distance_km} km",
            'duration_seconds': duration_minutes * 60,
            'duration_text': duration_text,
            'base_price': round(base_price, 2),
            'origin_coords': origin_coords,
            'destination_coords': dest_coords,
            'origin_address': origin,
            'destination_address': destination,
            'mode': mode
        }
    except Exception as e:
        try:
            current_app.logger.error(f"Mock route generation failed: {str(e)}")
        except RuntimeError:
            print(f"Mock route generation failed: {str(e)}")
        return None


def create_app():
    app = Flask(__name__)
    
    # Import config
    from config import Config
    app.config.from_object(Config)
    
    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)
    mail.init_app(app)
    admin.init_app(app)
    cors.init_app(app)

    # Initialize BookingService
    app.booking_service = BookingService(app)

    return app

# Fixed: Only create app once
app = create_app()

# Setup login manager
login_manager.login_view = 'users.login'
login_manager.login_message_category = 'info'
    
# Set up user_loader
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))
    
# Fixed: Admin required decorator
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('You need admin privileges to access this page.', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function
    
# Import and register blueprints
from users import ubp as users_bp
from admin import abp as admin_bp  # This will now be 'admin_routes' blueprint

app.register_blueprint(users_bp, url_prefix='/users')
app.register_blueprint(admin_bp, url_prefix='/admin')  # URL stays same, just blueprint name changed

# Setup admin views
from admin import setup_admin
setup_admin(app)

# Routes
@app.route('/')
def index():
    """Main landing page"""
    return render_template('index.html', 
                        now=datetime.now(timezone.utc),  # Fixed: timezone-aware
                        whatsapp_number=app.config.get('WHATSAPP_NUMBER', '1234567890'))

@app.route('/services')
def services():
    """Services page"""
    return render_template('services.html')

@app.route('/track')
def track_delivery_page():
    """Tracking page - Fixed: removed login_required for public tracking"""
    tracking_number = request.args.get('tracking_number', '').strip()
    if tracking_number:
        # If tracking number is provided, show results
        booking = Booking.query.filter_by(tracking_number=tracking_number).first()
        if booking:
            # Fixed: Check if tracking_updates is a relationship or needs different access
            try:
                updates = TrackingUpdate.query.filter_by(booking_id=booking.id)\
                    .order_by(TrackingUpdate.timestamp.desc()).all()
            except Exception:
                updates = []
            return render_template('tracking.html', booking=booking, updates=updates)
        else:
            return render_template('tracking.html', error='Tracking number not found', tracking_number=tracking_number)
    else:
        # Just show the form
        return render_template('tracking.html')

@app.route('/contact-submit', methods=['POST'])
def contact_submit():
    """Handle contact form submission"""
    try:
        name = request.form.get('name', '').strip()  # Fixed: use .get() with default
        email = request.form.get('email', '').strip()
        subject = request.form.get('subject', '').strip()
        message = request.form.get('message', '').strip()
            
        # Validate required fields
        if not all([name, email, subject, message]):
            flash('Please fill in all required fields.', 'error')
            return redirect(url_for('index'))
            
        # Here you would typically save to database and send email
        # For now, just show success message
            
        flash('Thank you for your message! We will get back to you soon.', 'success')
        return redirect(url_for('index'))
    except Exception as e:
        app.logger.error(f"Contact form error: {str(e)}")
        flash('Error sending message. Please try again.', 'error')
        return redirect(url_for('index'))
    
@app.route('/book-delivery', methods=['GET', 'POST'])
@login_required
def book_delivery():
    if request.method == 'POST':
        try:
            data = request.form
                
            # Validate required fields
            required_fields = ['pickup_address', 'delivery_address', 'package_type', 'weight', 
                            'pickup_contact', 'pickup_phone', 'delivery_contact', 'delivery_phone',
                            'service_type', 'pickup_date']
                
            missing_fields = []
            for field in required_fields:
                if not data.get(field, '').strip():
                    missing_fields.append(field.replace("_", " ").title())
                
            if missing_fields:
                flash(f'Missing required fields: {", ".join(missing_fields)}', 'error')
                return redirect(url_for('book_delivery'))
                
            # Generate booking ID
            booking_id = f"BOOK-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{secrets.token_hex(4).upper()}"
                
            # Fixed: Safe float conversion
            def safe_float(value, default=0.0):
                try:
                    if value is None or value == '':
                        return default
                    return float(value)
                except (ValueError, TypeError):
                    return default
                
            # Fixed: Safe date parsing
            def safe_parse_date(date_str, default=None):
                if not date_str:
                    return default or datetime.now(timezone.utc)
                try:
                    # Handle different date formats
                    if 'T' in date_str:
                        return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                    return datetime.strptime(date_str, '%Y-%m-%d')
                except (ValueError, TypeError):
                    return default or datetime.now(timezone.utc)
                
            # Create booking
            booking = Booking(
                id=booking_id,
                user_id=current_user.id,  # Fixed: Removed unnecessary check since @login_required
                pickup_address=data['pickup_address'].strip(),
                delivery_address=data['delivery_address'].strip(),
                package_type=data['package_type'],
                weight=safe_float(data.get('weight'), 0),
                dimensions=data.get('dimensions', '').strip() or None,
                package_value=safe_float(data.get('package_value')) or None,
                insurance_required='insurance_required' in data,
                special_instructions=data.get('special_instructions', '').strip() or None,
                status='pending',
                payment_status='unpaid',
                amount=safe_float(data.get('amount'), 0),
                currency='NGN',
                pickup_date=safe_parse_date(data.get('pickup_date')),
                tracking_number=f'TRK-{secrets.token_hex(8).upper()}'
            )
                
            db.session.add(booking)
            db.session.commit()
                
            # Save addresses if requested
            if 'save_addresses' in data:
                try:
                    # Save pickup address
                    pickup_addr_line = data['pickup_address'].split(',')[0].strip() if ',' in data['pickup_address'] else data['pickup_address'].strip()
                    pickup_address = Address(
                    user_id=current_user.id,
                        address_type='pickup',
                        contact_name=data['pickup_contact'].strip(),
                        contact_phone=data['pickup_phone'].strip(),
                        address_line1=pickup_addr_line
                    )
                    
                    # Save delivery address
                    delivery_addr_line = data['delivery_address'].split(',')[0].strip() if ',' in data['delivery_address'] else data['delivery_address'].strip()
                    delivery_address = Address(
                        user_id=current_user.id,
                        address_type='delivery',
                        contact_name=data['delivery_contact'].strip(),
                        contact_phone=data['delivery_phone'].strip(),
                        address_line1=delivery_addr_line
                    )
                    
                    db.session.add(pickup_address)
                    db.session.add(delivery_address)
                    db.session.commit()
                except Exception as addr_error:
                    app.logger.warning(f"Failed to save addresses: {str(addr_error)}")
                    # Don't fail the whole booking for address save failure
            
            flash(f'Booking created successfully! Your tracking number is: {booking.tracking_number}', 'success')
            return redirect(url_for('users.dashboard'))
                
        except Exception as e:
            db.session.rollback()  # Fixed: Rollback on error
            app.logger.error(f"Booking creation failed: {str(e)}")
            flash(f'Booking failed: {str(e)}', 'error')
            return redirect(url_for('book_delivery'))
    
    # GET request - render the form
    user_addresses = []
    try:
        user_addresses = list(Address.query.filter_by(user_id=current_user.id).all())
    except Exception as e:
        app.logger.warning(f"Failed to load user addresses: {str(e)}")
    
    return render_template('booking.html', user_addresses=user_addresses)


@app.route('/api/geocode', methods=['POST'])
def api_geocode():
    """Geocode address using improved Nigerian geocoding"""
    try:
        data = request.get_json(silent=True) or {}
        address = data.get('address', '').strip()
        
        if not address:
            return jsonify({'success': False, 'error': 'Address is required'}), 400
        
        # Use the improved geocoding
        result = geo_geocode(address)
        
        if result:
            return jsonify({
                'success': True,
                'formatted_address': result['formatted_address'],
                'latitude': result['latitude'],
                'longitude': result['longitude'],
                'match_type': result.get('match_type', 'unknown'),
                'is_approximate': result.get('is_approximate', False)
            })
        
        return jsonify({
            'success': False, 
            'error': 'Could not geocode address. Please try a more specific address.'
        }), 404
        
    except Exception as e:
        current_app.logger.error(f"Geocoding API error: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/calculate-route', methods=['POST'])
def api_calculate_route():
    """Calculate route using improved geocoding"""
    try:
        data = request.get_json(silent=True) or {}
        origin = data.get('origin', '').strip()
        destination = data.get('destination', '').strip()
        mode = data.get('mode', 'driving')
        
        if not origin or not destination:
            return jsonify({'success': False, 'error': 'Both origin and destination are required'}), 400
        
        # Use improved route calculation
        result = geo_calculate_route(origin, destination, mode)
        
        if result.get('success'):
            # Add base price calculation
            from config import Config
            price_per_km = getattr(Config, 'PRICE_PER_KM', 200)
            minimum_price = getattr(Config, 'MINIMUM_DELIVERY_PRICE', 500)
            
            base_price = result['driving_distance_km'] * price_per_km
            if base_price < minimum_price:
                base_price = minimum_price
            
            result['base_price'] = round(base_price, 2)
            
            return jsonify(result)
        else:
            return jsonify(result), 400
            
    except Exception as e:
        current_app.logger.error(f"Route calculation API error: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
    
@app.route('/api/calculate-price', methods=['POST'])
def api_calculate_price():
    """Calculate price based on distance and other factors"""
    try:
        data = request.get_json(silent=True) or {}  # Fixed: Handle None json
        
        # Get distance data
        distance_data = data.get('distance_data')
        if not distance_data:
            return jsonify({'success': False, 'error': 'Distance data is required'}), 400
        
        # Fixed: Safe float conversion with validation
        def safe_float(value, default=0.0):
            try:
                if value is None or value == '':
                    return default
                return float(value)
            except (ValueError, TypeError):
                return default
        
        # Get other factors
        weight = safe_float(data.get('weight'), 0)
        package_value = safe_float(data.get('package_value'), 0)
        service_type = data.get('service_type', 'standard')
        insurance_required = bool(data.get('insurance_required', False))
        signature_required = bool(data.get('signature_required', False))
        
        # Calculate price directly using config values
        from config import Config
        
        # Start with base price from distance data
        base_price = safe_float(distance_data.get('base_price'), 0)
        total_price = base_price
        
        # Add weight surcharge
        weight_surcharge = getattr(Config, 'WEIGHT_SURCHARGE_PER_KG', 50)
        heavy_surcharge = getattr(Config, 'HEAVY_SURCHARGE_PER_KG', 100)
        
        weight_surcharge_amount = 0
        if weight > 5:
            weight_surcharge_amount = (weight - 5) * weight_surcharge
            total_price += weight_surcharge_amount
        if weight > 20:
            heavy_surcharge_amount = (weight - 20) * heavy_surcharge
            total_price += heavy_surcharge_amount
        
        # Apply service type multiplier
        service_multipliers = {
            'express': getattr(Config, 'EXPRESS_MULTIPLIER', 1.5),
            'standard': getattr(Config, 'STANDARD_MULTIPLIER', 1.0),
            'economy': getattr(Config, 'ECONOMY_MULTIPLIER', 0.8)
        }
        
        multiplier = service_multipliers.get(service_type, 1.0)
        total_price *= multiplier
        
        # Add insurance
        insurance_amount = 0
        insurance_rate = getattr(Config, 'INSURANCE_RATE', 0.02)
        if insurance_required and package_value > 0:
            insurance_amount = package_value * insurance_rate
            total_price += insurance_amount
        
        # Add signature required fee
        signature_fee = getattr(Config, 'SIGNATURE_FEE', 200)
        if signature_required:
            total_price += signature_fee
        
        # Ensure minimum price
        minimum_price = getattr(Config, 'MINIMUM_DELIVERY_PRICE', 500)
        minimum_adjustment = 0
        if total_price < minimum_price:
            minimum_adjustment = minimum_price - total_price
            total_price = minimum_price
        
        return jsonify({
            'success': True,
            'final_price': round(total_price, 2),
            'currency': 'NGN',
            'price_breakdown': {
                'base_price': round(base_price, 2),
                'service_type': service_type,
                'service_multiplier': multiplier,
                'weight': weight,
                'weight_surcharge': round(weight_surcharge_amount, 2) if weight > 5 else 0,
                'insurance_required': insurance_required,
                'insurance_amount': round(insurance_amount, 2) if insurance_required else 0,
                'signature_required': signature_required,
                'signature_fee': signature_fee if signature_required else 0,
                'minimum_adjustment': round(minimum_adjustment, 2)
            }
        })
            
    except Exception as e:
        current_app.logger.error(f"Price calculation API error: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/track-delivery/<tracking_number>', methods=['GET', 'POST'])
def track_delivery(tracking_number):
    """Track delivery by tracking number - Fixed: Removed duplicate login_required"""
    booking = Booking.query.filter_by(tracking_number=tracking_number).first()
    
    if not booking:
        return render_template('tracking.html', error='Tracking number not found', 
                             tracking_number=tracking_number)
    
    # Get tracking updates for this booking
    try:
        updates = TrackingUpdate.query.filter_by(booking_id=booking.id)\
            .order_by(TrackingUpdate.timestamp.desc()).all()
    except Exception:
        updates = []
    
    return render_template('tracking.html', booking=booking, updates=updates)

@app.route('/api/track/<tracking_number>')  # Fixed: Changed route to avoid conflict
def api_track(tracking_number):
    """API endpoint for tracking"""
    booking = Booking.query.filter_by(tracking_number=tracking_number).first()
    if not booking:
        return jsonify({'success': False, 'error': 'Not found'}), 404
    
    # Get tracking updates
    try:
        updates = TrackingUpdate.query.filter_by(booking_id=booking.id)\
            .order_by(TrackingUpdate.timestamp.desc()).all()
        updates_data = [{
            'status': u.status,
            'location': u.location,
            'description': u.description,
            'timestamp': u.timestamp.isoformat() if u.timestamp else None
        } for u in updates]
    except Exception:
        updates_data = []
    
    return jsonify({
        'success': True,
        'tracking_number': booking.tracking_number,
        'status': booking.status,
        'pickup_address': booking.pickup_address,
        'delivery_address': booking.delivery_address,
        'created_at': booking.created_at.isoformat() if booking.created_at else None,
        'estimated_delivery': booking.estimated_delivery.isoformat() if hasattr(booking, 'estimated_delivery') and booking.estimated_delivery else None,
        'updates': updates_data
    })

@app.route('/partnership', methods=['GET', 'POST'])
def partnership():
    """Partnership page - Fixed: Removed login_required to allow public applications"""
    if request.method == 'POST':
        try:
            data = request.form
            
            # Fixed: Validate required fields
            required_fields = ['company_name', 'contact_person', 'email', 'phone', 'business_type']
            missing_fields = []
            for field in required_fields:
                if not data.get(field, '').strip():
                    missing_fields.append(field.replace('_', ' ').title())
            
            if missing_fields:
                flash(f'Missing required fields: {", ".join(missing_fields)}', 'error')
                return redirect(url_for('partnership'))
            
            partnership_entry = Partnership(
                company_name=data['company_name'].strip(),
                contact_person=data['contact_person'].strip(),
                email=data['email'].strip(),
                phone=data['phone'].strip(),
                business_type=data['business_type'].strip(),
                message=data.get('message', '').strip()
            )
            
            db.session.add(partnership_entry)
            db.session.commit()
            
            # Try to send notification email
            try:
                if hasattr(current_app, 'booking_service'):
                    current_app.booking_service.send_partnership_notification(partnership_entry)
            except Exception as notify_error:
                app.logger.warning(f"Failed to send partnership notification: {str(notify_error)}")
            
            flash('Partnership application submitted successfully!', 'success')
            return redirect(url_for('index'))
            
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Partnership application failed: {str(e)}")
            flash('Application failed. Please try again.', 'error')
            return redirect(url_for('partnership'))
        
    return render_template('partnership.html')
    
@app.route('/api/address/<int:address_id>')
@login_required
def get_address(address_id):
    """API endpoint to get address details"""
    address = Address.query.get(address_id)
    
    if not address:
        return jsonify({'success': False, 'error': 'Address not found'}), 404
    
    # Check if address belongs to current user
    if address.user_id != current_user.id:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    return jsonify({
        'success': True,
        'address': {
            'id': address.id,
            'contact_name': address.contact_name,
            'contact_phone': address.contact_phone,
            'address_line1': address.address_line1,
            'address_line2': getattr(address, 'address_line2', None),
            'city': getattr(address, 'city', None),
            'state': getattr(address, 'state', None),
            'postal_code': getattr(address, 'postal_code', None),
            'country': getattr(address, 'country', 'Nigeria'),
            'address_type': address.address_type
        }
    })

# Routes for WhatsApp integration
@app.route('/whatsapp-dispatch')
def whatsapp_dispatch():
    """Generate WhatsApp URL for dispatch booking"""
    default_message = "Hello Majesty Xpress Logistics, I'd like to book a dispatch/delivery service."
    
    # Get user info if logged in
    if current_user.is_authenticated:
        user_name = current_user.first_name or current_user.username or 'User'
        user_message = f"Hello Majesty Xpress, I'm {user_name}. I'd like to book a dispatch service."
    else:
        user_message = default_message
    
    # URL encode the message
    encoded_message = urllib.parse.quote(user_message)
    
    # Create WhatsApp URL
    whatsapp_number = app.config.get('WHATSAPP_NUMBER', '2348012345678')
    whatsapp_url = f"https://wa.me/{whatsapp_number}?text={encoded_message}"
    
    # Redirect to WhatsApp
    return redirect(whatsapp_url)

@app.route('/whatsapp-track')
def whatsapp_track():
    """Generate WhatsApp URL for tracking"""
    default_message = "Hello Majesty Xpress Logistics, I need help tracking my shipment."
    
    if current_user.is_authenticated:
        user_name = current_user.first_name or current_user.username or 'User'
        user_message = f"Hello Majesty Xpress, I'm {user_name}. I need help tracking my shipment."
    else:
        user_message = default_message
    
    encoded_message = urllib.parse.quote(user_message)
    whatsapp_number = app.config.get('WHATSAPP_NUMBER', '2348012345678')
    whatsapp_url = f"https://wa.me/{whatsapp_number}?text={encoded_message}"
    
    return redirect(whatsapp_url)

@app.route('/whatsapp-dispatch-form', methods=['GET', 'POST'])
def whatsapp_dispatch_form():
    """Form to collect dispatch details before WhatsApp redirect"""
    if request.method == 'POST':
        # Get form data with safe defaults
        name = request.form.get('name', '').strip()
        phone = request.form.get('phone', '').strip()
        service_type = request.form.get('service_type', 'General Dispatch')
        pickup_location = request.form.get('pickup_location', '').strip()
        delivery_location = request.form.get('delivery_location', '').strip()
        package_details = request.form.get('package_details', '').strip()
        urgency = request.form.get('urgency', 'Standard')
        
        # Auto-fill if user is logged in
        if current_user.is_authenticated:
            if not name:
                first_name = current_user.first_name or ''
                last_name = current_user.last_name or ''
                name = f"{first_name} {last_name}".strip() or current_user.username or ''
            if not phone and hasattr(current_user, 'phone') and current_user.phone:
                phone = current_user.phone
        
        # Validate required fields
        if not name or not phone or not pickup_location or not delivery_location:
            flash('Please fill in all required fields', 'error')
            return redirect(url_for('whatsapp_dispatch_form'))
        
        # Build WhatsApp message
        message_lines = [
            "🔄 *DISPATCH BOOKING REQUEST* 🔄",
            "",
            "Hello Majesty Xpress Logistics!",
            "",
            "I'd like to book a dispatch service:",
            "",
            f"*Name:* {name}",
            f"*Phone:* {phone}",
            f"*Service Type:* {service_type}",
            f"*Urgency:* {urgency}",
            f"*Pickup Location:* {pickup_location}",
            f"*Delivery Location:* {delivery_location}",
        ]
        
        if package_details:
            message_lines.append(f"*Package Details:* {package_details}")
        
        message_lines.extend([
            "",
            "Please provide:",
            "1. A quote for this service",
            "2. Available time slots",
            "3. Required documentation",
            "",
            "Thank you!",
        ])
        
        full_message = "\n".join(message_lines)
        encoded_message = urllib.parse.quote(full_message)
        
        # Get WhatsApp number from config
        whatsapp_number = app.config.get('WHATSAPP_NUMBER', '2347065894127')
        whatsapp_url = f"https://wa.me/{whatsapp_number}?text={encoded_message}"
        
        # Store in session for tracking (optional)
        session['last_dispatch_name'] = name
        session['last_dispatch_phone'] = phone
        
        flash('Redirecting to WhatsApp...', 'success')
        return redirect(whatsapp_url)
    
    # GET request - show form
    return render_template('users/whatsapp_dispatch_form.html')

@app.route('/whatsapp-quote')
def whatsapp_quote():
    """Get a quick quote via WhatsApp"""
    default_message = "Hello Majesty Xpress Logistics, I'd like to get a quote for a delivery service."
    
    if current_user.is_authenticated:
        user_name = current_user.first_name or current_user.username or 'User'
        user_message = f"Hello Majesty Xpress, I'm {user_name}. I'd like to get a delivery quote."
    else:
        user_message = default_message
    
    encoded_message = urllib.parse.quote(user_message)
    whatsapp_number = app.config.get('WHATSAPP_NUMBER', '2348012345678')
    whatsapp_url = f"https://wa.me/{whatsapp_number}?text={encoded_message}"
    
    return redirect(whatsapp_url)

# Fixed: Secured admin-seed route
@app.route('/admin-seed')
@login_required
@admin_required
def admin_seed():
    """Create admin user - requires existing admin authentication"""
    if User.query.filter_by(email='admin@example.com').first():
        return jsonify({'message': 'Admin user already exists'}), 400
    
    admin_user = User(
        email='admin@example.com',
        first_name='Admin',
        last_name='User',
        is_admin=True
    )
    admin_user.set_password('admin123')
    
    db.session.add(admin_user)
    db.session.commit()
    
    return jsonify({'message': 'Admin user created: admin@example.com'})

# Fixed: Added CLI command for initial admin creation (more secure)
@app.cli.command('create-admin')
def create_admin_command():
    """Create initial admin user via CLI"""
    if User.query.filter_by(email='admin@example.com').first():
        print('Admin user already exists')
        return
    
    admin_user = User(
        email='admin@example.com',
        first_name='Admin',
        last_name='User',
        is_admin=True
    )
    admin_user.set_password('admin123')  # Change this in production!
    
    db.session.add(admin_user)
    db.session.commit()
    
    print('Admin user created: admin@example.com / admin123')
    print('IMPORTANT: Change the password immediately!')

# Error handlers
@app.errorhandler(404)
def not_found_error(error):
    return render_template('errors/404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('errors/500.html'), 500

@app.errorhandler(403)
def forbidden_error(error):
    return render_template('errors/403.html'), 403

# Create tables
with app.app_context():
    db.create_all()






if __name__ == '__main__':
    # Fixed: Removed duplicate create_app() call
    app.run(host='0.0.0.0', debug=True)