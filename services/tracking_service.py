class TrackingService:
    def __init__(self, app):
        self.app = app
    
    def add_tracking_update(self, booking_id, location, status, description):
        """Add tracking update"""
        from models import TrackingUpdate, db
        from datetime import datetime
        
        update = TrackingUpdate(
            booking_id=booking_id,
            location=location,
            status=status,
            description=description,
            timestamp=datetime.utcnow()
        )
        
        db.session.add(update)
        db.session.commit()
        
        return update