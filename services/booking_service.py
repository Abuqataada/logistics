from twilio.rest import Client
from app import db, mail
from models import Booking, TrackingUpdate, Partnership
from flask_mail import Message
from flask import render_template
import datetime
import requests
import json

class BookingService:
    def __init__(self, app):
        self.app = app
        self.twilio_client = None
        if app.config.get('TWILIO_ACCOUNT_SID'):
            self.twilio_client = Client(
                app.config['TWILIO_ACCOUNT_SID'],
                app.config['TWILIO_AUTH_TOKEN']
            )
    
    def create_booking(self, data):
        """Create a new booking"""
        from datetime import datetime
        
        # Generate booking ID
        import secrets
        booking_id = f"BOOK-{datetime.now(datetime.timezone.utc).strftime('%Y%m%d')}-{secrets.token_hex(4).upper()}"
        
        booking = Booking(
            id=booking_id,
            user_id=data.get('user_id'),
            package_type=data['package_type'],
            weight=data['weight'],
            dimensions=data.get('dimensions'),
            package_value=data.get('package_value'),
            insurance_required=data.get('insurance_required', False),
            special_instructions=data.get('special_instructions'),
            amount=data['amount'],
            pickup_date=datetime.fromisoformat(data['pickup_date']),
            estimated_delivery=datetime.fromisoformat(data['estimated_delivery'])
        )
        
        booking.generate_tracking_number()
        
        db.session.add(booking)
        db.session.commit()
        
        # Send notifications
        self.send_booking_confirmation(booking)
        self.send_whatsapp_notification(booking)
        
        return booking
    
    def send_whatsapp_notification(self, booking):
        """Send WhatsApp notification"""
        if not self.twilio_client:
            return
        
        try:
            message = self.twilio_client.messages.create(
                body=f"Your booking #{booking.id} has been confirmed. "
                     f"Tracking number: {booking.tracking_number}. "
                     f"Est. delivery: {booking.estimated_delivery.strftime('%Y-%m-%d')}",
                from_=f"whatsapp:{self.app.config['TWILIO_PHONE_NUMBER']}",
                to=f"whatsapp:{booking.user.phone}" if booking.user and booking.user.phone else None
            )
            return message.sid
        except Exception as e:
            self.app.logger.error(f"WhatsApp notification failed: {str(e)}")
    
    def send_booking_confirmation(self, booking):
        """Send email confirmation"""
        if not self.app.config.get('MAIL_USERNAME'):
            return
        
        msg = Message(
            subject=f"Booking Confirmation #{booking.id}",
            recipients=[booking.user.email] if booking.user else [],
            sender=self.app.config['MAIL_USERNAME']
        )
        
        msg.html = render_template('emails/booking_confirmation.html', 
                                  booking=booking)
        
        try:
            mail.send(msg)
        except Exception as e:
            self.app.logger.error(f"Email sending failed: {str(e)}")
    
    def send_partnership_notification(self, partnership):
        """Notify admin about partnership application"""
        msg = Message(
            subject=f"New Partnership Application - {partnership.company_name}",
            recipients=[self.app.config.get('ADMIN_EMAIL', '')],
            sender=self.app.config['MAIL_USERNAME']
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
        except Exception as e:
            self.app.logger.error(f"Partnership notification failed: {str(e)}")
    
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
        booking.updated_at = datetime.now(datetime.timezone.utc)
        
        db.session.add(update)
        db.session.commit()
        
        # Send status update notification
        self.send_status_update(booking, status)
        
        return update