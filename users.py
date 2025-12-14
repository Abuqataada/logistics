from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from extensions import db
from models import User, Booking, Address, TrackingUpdate
import re
from datetime import datetime

ubp = Blueprint('users', __name__)

@ubp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        try:
            data = request.form
            
            # Validate email
            if not re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', data['email']):
                flash('Invalid email format', 'error')
                return redirect(url_for('users.register'))
            
            # Check if user exists
            if User.query.filter_by(email=data['email']).first():
                flash('Email already registered', 'error')
                return redirect(url_for('users.register'))
            
            # Create user
            user = User(
                email=data['email'],
                phone=data.get('phone'),
                first_name=data.get('first_name'),
                last_name=data.get('last_name'),
                company_name=data.get('company_name')
            )
            user.set_password(data['password'])
            
            db.session.add(user)
            db.session.commit()
            
            # Auto login
            login_user(user)
            flash('Registration successful!', 'success')
            return redirect(url_for('index'))
            
        except Exception as e:
            flash(f'Registration failed: {str(e)}', 'error')
            return redirect(url_for('users.register'))
    
    return render_template('users/register.html')

@ubp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        try:
            data = request.form
            user = User.query.filter_by(email=data['email']).first()
            
            if user and user.check_password(data['password']):
                if not user.is_active:
                    flash('Account is deactivated', 'error')
                    return redirect(url_for('users.login'))
                
                login_user(user)
                user.last_login = datetime.utcnow()
                db.session.commit()
                
                flash('Login successful!', 'success')
                # Redirect admin users to admin dashboard, others to index
                if user.is_admin:
                    return redirect(url_for('admin_routes.dashboard'))  # Updated this line
                return redirect(url_for('index'))
            
            flash('Invalid email or password', 'error')
            return redirect(url_for('users.login'))
            
        except Exception as e:
            flash(f'Login failed: {str(e)}', 'error')
            return redirect(url_for('users.login'))
    
    return render_template('users/login.html')

@ubp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out', 'info')
    return redirect(url_for('index'))

@ubp.route('/dashboard')
@login_required
def dashboard():
    # Get user's bookings
    bookings = Booking.query.filter_by(user_id=current_user.id)\
        .order_by(Booking.created_at.desc()).limit(10).all()
    
    print("Current User ID:", current_user.id)
    print("Bookings Retrieved:", bookings)
    # Get recent addresses
    addresses = Address.query.filter_by(user_id=current_user.id)\
        .order_by(Address.id.desc()).limit(5).all()
    
    # Calculate statistics
    total_bookings = len(bookings)
    delivered_count = len([b for b in current_user.bookings if b.status == 'delivered'])
    addresses_count = len(addresses)
    
    return render_template('users/dashboard.html',
                         bookings=bookings,
                         addresses=addresses,
                         user=current_user,
                         total_bookings=total_bookings,
                         delivered_count=delivered_count,
                         addresses_count=addresses_count)

@ubp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        try:
            data = request.form
            
            # Update user profile
            current_user.first_name = data.get('first_name', current_user.first_name)
            current_user.last_name = data.get('last_name', current_user.last_name)
            current_user.phone = data.get('phone', current_user.phone)
            current_user.company_name = data.get('company_name', current_user.company_name)
            
            db.session.commit()
            flash('Profile updated successfully!', 'success')
            return redirect(url_for('users.profile'))
            
        except Exception as e:
            flash(f'Update failed: {str(e)}', 'error')
            return redirect(url_for('users.profile'))
    
    return render_template('users/profile.html')

@ubp.route('/addresses', methods=['GET', 'POST'])
@login_required
def addresses():
    if request.method == 'POST':
        try:
            data = request.form
            
            address = Address(
                user_id=current_user.id,
                address_type=data['address_type'],
                contact_name=data['contact_name'],
                contact_phone=data['contact_phone'],
                address_line1=data['address_line1'],
                address_line2=data.get('address_line2'),
                city=data['city'],
                state=data['state'],
                country=data['country'],
                postal_code=data['postal_code'],
                latitude=data.get('latitude'),
                longitude=data.get('longitude'),
                is_default=data.get('is_default', False)
            )
            
            # If this is default, unset other defaults
            if address.is_default:
                Address.query.filter_by(user_id=current_user.id, 
                                      address_type=address.address_type)\
                    .update({'is_default': False})
            
            db.session.add(address)
            db.session.commit()
            
            flash('Address added successfully!', 'success')
            return redirect(url_for('users.addresses'))
            
        except Exception as e:
            flash(f'Failed to add address: {str(e)}', 'error')
            return redirect(url_for('users.addresses'))
    
    # GET request - return all addresses
    addresses = Address.query.filter_by(user_id=current_user.id).all()
    return render_template('users/addresses.html', addresses=addresses)

@ubp.route('/bookings')
@login_required
def bookings():
    page = request.args.get('page', 1, type=int)
    per_page = 10
    
    bookings = Booking.query.filter_by(user_id=current_user.id)\
        .order_by(Booking.created_at.desc())\
        .paginate(page=page, per_page=per_page)
    
    return render_template('users/bookings.html', bookings=bookings)

@ubp.route('/booking/<booking_id>')
@login_required
def booking_detail(booking_id):
    booking = Booking.query.get(booking_id)
    
    if not booking or booking.user_id != current_user.id:
        flash('Booking not found', 'error')
        return redirect(url_for('users.bookings'))
    
    updates = booking.tracking_updates.order_by(TrackingUpdate.timestamp.desc()).all()
    
    return render_template('users/booking_detail.html',
                         booking=booking,
                         updates=updates)