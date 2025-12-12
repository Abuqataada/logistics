from datetime import datetime, timezone
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from extensions import db  # Only import db

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    phone = db.Column(db.String(20), unique=True)
    password_hash = db.Column(db.String(256))
    first_name = db.Column(db.String(64))
    last_name = db.Column(db.String(64))
    company_name = db.Column(db.String(128))
    is_active = db.Column(db.Boolean, default=True)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_login = db.Column(db.DateTime(timezone=True))
    
    # Relationships
    bookings = db.relationship('Booking', backref='user', lazy='dynamic')
    addresses = db.relationship('Address', backref='user', lazy='dynamic')
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def __repr__(self):
        return f'<User {self.email}>'

class Booking(db.Model):
    __tablename__ = 'bookings'
    
    id = db.Column(db.String(20), primary_key=True)  # Format: BOOK-YYYYMMDD-XXXX
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    # Simplified for now - remove foreign keys to avoid complexity
    pickup_address = db.Column(db.String(500))
    delivery_address = db.Column(db.String(500))
    
    # Booking Details
    package_type = db.Column(db.String(50))  # Document, Parcel, Cargo, etc.
    weight = db.Column(db.Float)  # in kg
    dimensions = db.Column(db.String(100))  # LxWxH in cm
    package_value = db.Column(db.Float)
    insurance_required = db.Column(db.Boolean, default=False)
    special_instructions = db.Column(db.Text)
    
    # Status Tracking
    status = db.Column(db.String(50), default='pending')  # pending, confirmed, in_transit, delivered, cancelled
    payment_status = db.Column(db.String(50), default='unpaid')  # unpaid, partial, paid
    tracking_number = db.Column(db.String(100), unique=True)
    
    # Payment
    amount = db.Column(db.Float)
    currency = db.Column(db.String(3), default='USD')
    payment_method = db.Column(db.String(50))
    stripe_payment_intent_id = db.Column(db.String(100))
    
    # Dates
    pickup_date = db.Column(db.DateTime(timezone=True))
    delivery_date = db.Column(db.DateTime(timezone=True))
    estimated_delivery = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # Relationships
    payments = db.relationship('Payment', backref='booking', lazy='dynamic')
    tracking_updates = db.relationship('TrackingUpdate', backref='booking', lazy='dynamic')
    
    def generate_tracking_number(self):
        import secrets
        self.tracking_number = f'TRK-{secrets.token_hex(8).upper()}'

class Address(db.Model):
    __tablename__ = 'addresses'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    address_type = db.Column(db.String(20))  # pickup, delivery, billing
    contact_name = db.Column(db.String(128))
    contact_phone = db.Column(db.String(20))
    address_line1 = db.Column(db.String(255))
    address_line2 = db.Column(db.String(255))
    city = db.Column(db.String(100))
    state = db.Column(db.String(100))
    country = db.Column(db.String(100))
    postal_code = db.Column(db.String(20))
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    is_default = db.Column(db.Boolean, default=False)
    
class Payment(db.Model):
    __tablename__ = 'payments'
    
    id = db.Column(db.String(50), primary_key=True)  # Payment intent ID or transaction ID
    booking_id = db.Column(db.String(20), db.ForeignKey('bookings.id'))
    amount = db.Column(db.Float)
    currency = db.Column(db.String(3), default='USD')
    payment_method = db.Column(db.String(50))  # card, bank_transfer, etc.
    stripe_payment_intent_id = db.Column(db.String(100))
    status = db.Column(db.String(50))  # succeeded, pending, failed
    receipt_url = db.Column(db.String(500))
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class TrackingUpdate(db.Model):
    __tablename__ = 'tracking_updates'
    
    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.String(20), db.ForeignKey('bookings.id'))
    location = db.Column(db.String(255))
    status = db.Column(db.String(100))
    description = db.Column(db.Text)
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    timestamp = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class Partnership(db.Model):
    __tablename__ = 'partnerships'
    
    id = db.Column(db.Integer, primary_key=True)
    company_name = db.Column(db.String(255))
    contact_person = db.Column(db.String(128))
    email = db.Column(db.String(120))
    phone = db.Column(db.String(20))
    business_type = db.Column(db.String(100))  # Logistics Partner, Corporate Client, etc.
    message = db.Column(db.Text)
    status = db.Column(db.String(50), default='pending')  # pending, approved, rejected
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class ChatMessage(db.Model):
    __tablename__ = 'chat_messages'
    
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    recipient_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    message = db.Column(db.Text)
    is_read = db.Column(db.Boolean, default=False)
    timestamp = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
class PricingConfig(db.Model):
    __tablename__ = 'pricing_configs'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, default='Default Pricing')
    is_active = db.Column(db.Boolean, default=True)
    price_per_km = db.Column(db.Float, default=200.0)  # ₦ per km
    minimum_price = db.Column(db.Float, default=500.0)  # Minimum delivery price
    weight_surcharge_per_kg = db.Column(db.Float, default=1.5)  # ₦ per kg over 5kg
    heavy_surcharge_per_kg = db.Column(db.Float, default=2.0)  # ₦ per kg over 20kg
    insurance_rate = db.Column(db.Float, default=0.02)  # 2% of declared value
    
    # Service type multipliers
    express_multiplier = db.Column(db.Float, default=1.5)
    standard_multiplier = db.Column(db.Float, default=1.0)
    economy_multiplier = db.Column(db.Float, default=0.8)
    
    # Additional fees
    signature_fee = db.Column(db.Float, default=200.0)  # Fee for signature required
    
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=datetime.now(timezone.utc), 
                          onupdate=datetime.now(timezone.utc))
    
    @classmethod
    def get_current(cls):
        """Get the current active pricing configuration"""
        config = cls.query.filter_by(is_active=True).first()
        if not config:
            # Create default config if none exists
            config = cls()
            db.session.add(config)
            db.session.commit()
        return config