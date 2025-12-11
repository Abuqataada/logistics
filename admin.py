from flask import Blueprint, render_template, request, jsonify, redirect, url_for
from flask_login import login_required, current_user
from flask_admin.contrib.sqla import ModelView
from extensions import db, admin
from models import User, Booking, Partnership, Payment, TrackingUpdate
from datetime import datetime, timedelta

bp = Blueprint('admin_routes', __name__)

# Admin model views
class AdminModelView(ModelView):
    def is_accessible(self):
        return current_user.is_authenticated and current_user.is_admin
    
    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for('users.login'))

def setup_admin(app):
    """Setup Flask-Admin"""
    # Add admin views
    admin.add_view(AdminModelView(User, db.session))
    admin.add_view(AdminModelView(Booking, db.session))
    admin.add_view(AdminModelView(Partnership, db.session))
    admin.add_view(AdminModelView(Payment, db.session))
    admin.add_view(AdminModelView(TrackingUpdate, db.session))

@bp.route('/dashboard')
@login_required
def dashboard():
    if not current_user.is_admin:
        return redirect(url_for('index'))
    
    # Statistics
    today = datetime.utcnow().date()
    
    stats = {
        'total_bookings': Booking.query.count(),
        'today_bookings': Booking.query.filter(
            db.func.date(Booking.created_at) == today
        ).count(),
        'pending_bookings': Booking.query.filter_by(status='pending').count(),
        'active_bookings': Booking.query.filter(
            Booking.status.in_(['confirmed', 'in_transit'])
        ).count(),
        'total_users': User.query.count(),
        'pending_partnerships': Partnership.query.filter_by(status='pending').count()
    }
    
    # Recent bookings
    recent_bookings = Booking.query\
        .order_by(Booking.created_at.desc())\
        .limit(10).all()
    
    return render_template('admin/dashboard.html',
                         stats=stats,
                         recent_bookings=recent_bookings)

@bp.route('/bookings/manage')
@login_required
def manage_bookings():
    if not current_user.is_admin:
        return redirect(url_for('index'))
    
    status_filter = request.args.get('status', 'all')
    page = request.args.get('page', 1, type=int)
    
    query = Booking.query
    
    if status_filter != 'all':
        query = query.filter_by(status=status_filter)
    
    bookings = query.order_by(Booking.created_at.desc())\
        .paginate(page=page, per_page=20)
    
    return render_template('admin/manage_bookings.html',
                         bookings=bookings,
                         status_filter=status_filter)

@bp.route('/booking/<booking_id>/update-status', methods=['POST'])
@login_required
def update_booking_status(booking_id):
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        data = request.json
        booking = Booking.query.get(booking_id)
        
        if not booking:
            return jsonify({'error': 'Booking not found'}), 404
        
        booking.status = data['status']
        
        # Add tracking update
        if 'location' in data and 'description' in data:
            update = TrackingUpdate(
                booking_id=booking_id,
                location=data['location'],
                status=data['status'],
                description=data['description']
            )
            db.session.add(update)
        
        booking.updated_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify({'success': True})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@bp.route('/partnerships')
@login_required
def partnerships():
    if not current_user.is_admin:
        return redirect(url_for('index'))
    
    status_filter = request.args.get('status', 'pending')
    page = request.args.get('page', 1, type=int)
    
    query = Partnership.query
    
    if status_filter != 'all':
        query = query.filter_by(status=status_filter)
    
    partnerships = query.order_by(Partnership.created_at.desc())\
        .paginate(page=page, per_page=20)
    
    return render_template('admin/partnerships.html',
                         partnerships=partnerships,
                         status_filter=status_filter)

@bp.route('/partnership/<int:id>/update', methods=['POST'])
@login_required
def update_partnership(id):
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        data = request.json
        partnership = Partnership.query.get(id)
        
        if not partnership:
            return jsonify({'error': 'Not found'}), 404
        
        partnership.status = data['status']
        
        if 'notes' in data:
            partnership.admin_notes = data['notes']
        
        partnership.updated_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify({'success': True})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 400