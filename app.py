from flask import Flask, current_app, render_template, request, redirect, url_for, flash, jsonify, session
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from extensions import db, login_manager, mail, cors, admin
from models import User, Booking, Partnership, Address, Payment, TrackingUpdate
from services.booking_service import BookingService
import os
import secrets
from datetime import datetime
import urllib.parse

from geopy.distance import geodesic
import requests
import json

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
    
    # Setup login manager
    login_manager.login_view = 'users.login'
    login_manager.login_message_category = 'info'
    
    # Set up user_loader
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))
    
    # Import and register blueprints
    from users import bp as users_bp
    from admin import bp as admin_bp  # This will now be 'admin_routes' blueprint
    
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
                            now=datetime.now(),
                            whatsapp_number=app.config.get('WHATSAPP_NUMBER', '1234567890'))

    @app.route('/services')
    def services():
        """Services page"""
        return render_template('services.html')

    @app.route('/track')
    @login_required
    def track_delivery_page():
        """Tracking page"""
        tracking_number = request.args.get('tracking_number', '')
        if tracking_number:
            # If tracking number is provided, show results
            booking = Booking.query.filter_by(tracking_number=tracking_number).first()
            if booking:
                updates = booking.tracking_updates.order_by(TrackingUpdate.timestamp.desc()).all()
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
            name = request.form['name']
            email = request.form['email']
            subject = request.form['subject']
            message = request.form['message']
            
            # Here you would typically save to database and send email
            # For now, just show success message
            
            flash('Thank you for your message! We will get back to you soon.', 'success')
            return redirect(url_for('index'))
        except Exception as e:
            flash(f'Error sending message: {str(e)}', 'error')
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
                for field in required_fields:
                    if not data.get(field):
                        flash(f'{field.replace("_", " ").title()} is required', 'error')
                        return redirect(url_for('book_delivery'))
                
                # Generate booking ID
                booking_id = f"BOOK-{datetime.now().strftime('%Y%m%d')}-{secrets.token_hex(4).upper()}"
                
                # Create booking
                booking = Booking(
                    id=booking_id,
                    user_id=current_user.id if current_user.is_authenticated else None,
                    pickup_address=data['pickup_address'],
                    delivery_address=data['delivery_address'],
                    package_type=data['package_type'],
                    weight=float(data['weight']),
                    dimensions=data.get('dimensions'),
                    package_value=float(data.get('package_value', 0)) if data.get('package_value') else None,
                    insurance_required='insurance_required' in data,
                    special_instructions=data.get('special_instructions'),
                    status='pending',
                    payment_status='unpaid',
                    amount=float(data.get('amount', 0)),
                    currency='NGN',
                    pickup_date=datetime.strptime(data['pickup_date'], '%Y-%m-%d') if data.get('pickup_date') else None,
                    tracking_number=f'TRK-{secrets.token_hex(8).upper()}'
                )
                
                db.session.add(booking)
                db.session.commit()
                
                # Save addresses if requested and user is logged in
                if current_user.is_authenticated and 'save_addresses' in data:
                    # Save pickup address
                    pickup_address = Address(
                        user_id=current_user.id,
                        address_type='pickup',
                        contact_name=data['pickup_contact'],
                        contact_phone=data['pickup_phone'],
                        address_line1=data['pickup_address'].split(',')[0] if ',' in data['pickup_address'] else data['pickup_address']
                    )
                    
                    # Save delivery address
                    delivery_address = Address(
                        user_id=current_user.id,
                        address_type='delivery',
                        contact_name=data['delivery_contact'],
                        contact_phone=data['delivery_phone'],
                        address_line1=data['delivery_address'].split(',')[0] if ',' in data['delivery_address'] else data['delivery_address']
                    )
                    
                    db.session.add(pickup_address)
                    db.session.add(delivery_address)
                    db.session.commit()
                
                flash(f'Booking created successfully! Your tracking number is: {booking.tracking_number}', 'success')
                
                # If user is logged in, redirect to their dashboard
                if current_user.is_authenticated:
                    return redirect(url_for('users.dashboard'))
                else:
                    return redirect(url_for('track_delivery', tracking_number=booking.tracking_number))
                    
            except Exception as e:
                flash(f'Booking failed: {str(e)}', 'error')
                return redirect(url_for('book_delivery'))
        
        # GET request - render the form
        user_addresses = []
        if current_user.is_authenticated:
            # Convert SQLAlchemy query to list
            user_addresses = list(current_user.addresses)
        
        return render_template('booking.html', user_addresses=user_addresses)

    @app.route('/api/geocode', methods=['POST'])
    def api_geocode():
        """Geocode address using Distance Matrix AI API with fallback"""
        try:
            data = request.json
            address = data.get('address', '').strip()
            
            if not address:
                return jsonify({'success': False, 'error': 'Address is required'})
            
            # Check if we have the booking service and API key
            if hasattr(current_app, 'booking_service') and current_app.booking_service.geocoding_api_key:
                try:
                    booking_service = current_app.booking_service
                    geocode_result = booking_service.geocode_address(address)
                    
                    if geocode_result:
                        return jsonify({
                            'success': True,
                            'formatted_address': geocode_result['formatted_address'],
                            'latitude': geocode_result['latitude'],
                            'longitude': geocode_result['longitude'],
                            'address_components': geocode_result.get('address_components', {})
                        })
                except Exception as service_error:
                    current_app.logger.warning(f"Geocoding service error: {str(service_error)}")
            
            # Fallback to OpenStreetMap Nominatim (free, no API key required)
            try:
                import requests
                nominatim_url = "https://nominatim.openstreetmap.org/search"
                params = {
                    'q': f"{address}, Nigeria",
                    'format': 'json',
                    'limit': 1,
                    'addressdetails': 1
                }
                
                headers = {
                    'User-Agent': 'MajestyXpress/1.0'  # Required by Nominatim
                }
                
                response = requests.get(nominatim_url, params=params, headers=headers, timeout=5)
                
                if response.status_code == 200:
                    results = response.json()
                    if results:
                        location = results[0]
                        return jsonify({
                            'success': True,
                            'formatted_address': location.get('display_name', address),
                            'latitude': float(location['lat']),
                            'longitude': float(location['lon']),
                            'address_components': location.get('address', {})
                        })
            except Exception as fallback_error:
                current_app.logger.warning(f"OpenStreetMap geocoding failed: {str(fallback_error)}")
            
            # Ultimate fallback - return mock data
            return jsonify({
                'success': True,
                'formatted_address': address,
                'latitude': 9.081999,  # Lagos coordinates as fallback
                'longitude': 8.675277,
                'address_components': {}
            })
            
        except Exception as e:
            current_app.logger.error(f"Geocoding API error: {str(e)}")
            # Return mock data instead of error
            return jsonify({
                'success': True,
                'formatted_address': address if 'address' in locals() else 'Unknown',
                'latitude': 9.081999,
                'longitude': 8.675277,
                'address_components': {}
            })

    @app.route('/api/calculate-route', methods=['POST'])
    def api_calculate_route():
        """Calculate route with fallback to mock data"""
        try:
            data = request.json
            origin = data.get('origin', '').strip()
            destination = data.get('destination', '').strip()
            mode = data.get('mode', 'driving')
            
            if not origin or not destination:
                return jsonify({'success': False, 'error': 'Both origin and destination are required'})
            
            # Check if we have the booking service and API key
            distance_data = None
            if hasattr(current_app, 'booking_service') and current_app.booking_service.distance_matrix_api_key:
                try:
                    booking_service = current_app.booking_service
                    distance_data = booking_service.calculate_distance_matrix(origin, destination, mode)
                except Exception as service_error:
                    current_app.logger.warning(f"Route calculation service error: {str(service_error)}")
            
            # If API failed or not available, use mock data
            if not distance_data:
                distance_data = generate_mock_route_data(origin, destination, mode)
            
            if distance_data:
                return jsonify(distance_data)
            else:
                return jsonify({'success': False, 'error': 'Failed to calculate distance'})
                
        except Exception as e:
            current_app.logger.error(f"Route calculation API error: {str(e)}")
            # Generate mock data as fallback
            mock_data = generate_mock_route_data(
                origin if 'origin' in locals() else 'Unknown',
                destination if 'destination' in locals() else 'Unknown',
                mode
            )
            return jsonify(mock_data if mock_data else {'success': False, 'error': str(e)})

    def generate_mock_route_data(origin, destination, mode='driving'):
        """Generate mock route data for testing"""
        try:
            import hashlib
            import random
            from math import radians, sin, cos, sqrt, atan2
            
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
            
            # Calculate base price
            price_per_km = current_app.config.get('PRICE_PER_KM', 200)
            base_price = distance_km * price_per_km
            minimum_price = current_app.config.get('MINIMUM_DELIVERY_PRICE', 500)
            
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
            current_app.logger.error(f"Mock route generation failed: {str(e)}")
            return None
    
    @app.route('/api/calculate-price', methods=['POST'])
    def api_calculate_price():
        """Calculate price based on distance and other factors"""
        try:
            data = request.json
            
            # Get distance data
            distance_data = data.get('distance_data')
            if not distance_data:
                return jsonify({'success': False, 'error': 'Distance data is required'})
            
            # Get other factors
            weight = float(data.get('weight', 0))
            package_value = float(data.get('package_value', 0))
            service_type = data.get('service_type', 'standard')
            insurance_required = data.get('insurance_required', False)
            signature_required = data.get('signature_required', False)
            
            # Calculate price directly using config values
            from config import Config
            
            # Start with base price from distance data
            base_price = distance_data.get('base_price', 0)
            total_price = base_price
            
            # Add weight surcharge
            weight_surcharge = Config.WEIGHT_SURCHARGE_PER_KG
            heavy_surcharge = Config.HEAVY_SURCHARGE_PER_KG
            
            if weight > 5:
                total_price += (weight - 5) * weight_surcharge
            if weight > 20:
                total_price += (weight - 20) * heavy_surcharge
            
            # Apply service type multiplier
            service_multipliers = {
                'express': Config.EXPRESS_MULTIPLIER,
                'standard': Config.STANDARD_MULTIPLIER,
                'economy': Config.ECONOMY_MULTIPLIER
            }
            
            multiplier = service_multipliers.get(service_type, 1.0)
            total_price *= multiplier
            
            # Add insurance
            if insurance_required and package_value > 0:
                total_price += package_value * Config.INSURANCE_RATE
            
            # Add signature required fee
            if signature_required:
                total_price += Config.SIGNATURE_FEE
            
            # Ensure minimum price
            if total_price < Config.MINIMUM_DELIVERY_PRICE:
                total_price = Config.MINIMUM_DELIVERY_PRICE
            
            return jsonify({
                'success': True,
                'final_price': round(total_price, 2),
                'currency': 'NGN',
                'price_breakdown': {
                    'base_price': base_price,
                    'service_type': service_type,
                    'service_multiplier': multiplier,
                    'weight': weight,
                    'weight_surcharge': weight_surcharge,
                    'insurance_required': insurance_required,
                    'insurance_rate': Config.INSURANCE_RATE if insurance_required else 0,
                    'signature_required': signature_required,
                    'signature_fee': Config.SIGNATURE_FEE if signature_required else 0,
                    'minimum_adjustment': max(0, Config.MINIMUM_DELIVERY_PRICE - total_price)
                }
            })
                
        except Exception as e:
            current_app.logger.error(f"Price calculation API error: {str(e)}")
            return jsonify({'success': False, 'error': str(e)})        

    @app.route('/track-delivery/<tracking_number>', methods=['GET', 'POST'])
    @login_required
    def track_delivery(tracking_number):
        """Track delivery by tracking number"""
        if request.method == 'POST':
            booking = Booking.query.filter_by(tracking_number=tracking_number).first()
            if not booking:
                return render_template('tracking.html', error='Tracking number not found')
        
            # Get tracking updates for this booking
            updates = booking.tracking_updates.order_by(TrackingUpdate.timestamp.desc()).all()
        
            return render_template('tracking.html', booking=booking, updates=updates)
        return render_template('tracking.html')
    
    @app.route('/track/<tracking_number>')
    @login_required
    def api_track(tracking_number):
        """API endpoint for tracking"""
        booking = Booking.query.filter_by(tracking_number=tracking_number).first()
        if not booking:
            return jsonify({'error': 'Not found'}), 404
        
        return jsonify({
            'tracking_number': booking.tracking_number,
            'status': booking.status,
            'pickup_address': booking.pickup_address,
            'delivery_address': booking.delivery_address,
            'created_at': booking.created_at.isoformat()
        })
    
    @app.route('/partnership', methods=['GET', 'POST'])
    @login_required
    def partnership():
        if request.method == 'POST':
            try:
                data = request.form
                partnership = Partnership(
                    company_name=data['company_name'],
                    contact_person=data['contact_person'],
                    email=data['email'],
                    phone=data['phone'],
                    business_type=data['business_type'],
                    message=data.get('message', '')
                )
                
                db.session.add(partnership)
                db.session.commit()
                
                flash('Partnership application submitted!', 'success')
                return redirect(url_for('index'))
                
            except Exception as e:
                flash(f'Application failed: {str(e)}', 'error')
                return redirect(url_for('partnership'))
        
        return render_template('partnership.html')
    
    @app.route('/api/address/<int:address_id>')
    @login_required
    def get_address(address_id):
        """API endpoint to get address details"""
        address = Address.query.get_or_404(address_id)
        
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
                'address_line2': address.address_line2,
                'city': address.city,
                'state': address.state,
                'postal_code': address.postal_code,
                'country': address.country,
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
            user_message = f"Hello Majesty Xpress, I'm {current_user.first_name or current_user.username}. I'd like to book a dispatch service."
        else:
            user_message = default_message
        
        # URL encode the message
        encoded_message = urllib.parse.quote(user_message)
        
        # Create WhatsApp URL (use your actual number)
        whatsapp_number = app.config.get('WHATSAPP_NUMBER', '2348012345678')
        whatsapp_url = f"https://wa.me/{whatsapp_number}?text={encoded_message}"
        
        # Redirect to WhatsApp
        return redirect(whatsapp_url)

    @app.route('/whatsapp-track')
    def whatsapp_track():
        """Generate WhatsApp URL for tracking"""
        default_message = "Hello Majesty Xpress Logistics, I need help tracking my shipment."
        
        if current_user.is_authenticated:
            user_message = f"Hello Majesty Xpress, I'm {current_user.first_name or current_user.username}. I need help tracking my shipment."
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
            # Get form data
            name = request.form.get('name', '').strip()
            phone = request.form.get('phone', '').strip()
            service_type = request.form.get('service_type', 'General Dispatch')
            pickup_location = request.form.get('pickup_location', '').strip()
            delivery_location = request.form.get('delivery_location', '').strip()
            package_details = request.form.get('package_details', '').strip()
            urgency = request.form.get('urgency', 'Standard')
            
            # Auto-fill if user is logged in
            if current_user.is_authenticated:
                if not name and current_user.first_name:
                    name = f"{current_user.first_name} {current_user.last_name or ''}".strip()
                if not phone and current_user.phone:
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
            user_message = f"Hello Majesty Xpress, I'm {current_user.first_name or current_user.username}. I'd like to get a delivery quote."
        else:
            user_message = default_message
        
        encoded_message = urllib.parse.quote(user_message)
        whatsapp_number = app.config.get('WHATSAPP_NUMBER', '2348012345678')
        whatsapp_url = f"https://wa.me/{whatsapp_number}?text={encoded_message}"
        
        return redirect(whatsapp_url)

    @app.route('/admin-seed')
    def admin_seed():
        if User.query.filter_by(email='admin@example.com').first():
            return 'Admin user already exists'
        
        admin_user = User(
            email='admin@example.com',
            first_name='Admin',
            last_name='User',
            is_admin=True
        )
        admin_user.set_password('admin123')
        
        db.session.add(admin_user)
        db.session.commit()
        
        return 'Admin user created: admin@example.com / admin123'
    
    # Create tables
    with app.app_context():
        db.create_all()
    
    return app

app = create_app()

if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', debug=True)