class PaymentService:
    def __init__(self, app):
        self.app = app
    
    def handle_stripe_event(self, event):
        """Handle Stripe webhook events"""
        self.app.logger.info(f"Received Stripe event: {event['type']}")