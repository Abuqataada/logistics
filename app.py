from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from extensions import db, login_manager, mail, cors, admin
from models import User, Booking, Partnership, Address, Payment, TrackingUpdate
import os
import secrets
from datetime import datetime
import urllib.parse

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