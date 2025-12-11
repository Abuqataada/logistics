class ChatService:
    def __init__(self, app):
        self.app = app
    
    def send_message(self, sender_id, recipient_id, message):
        """Send chat message"""
        self.app.logger.info(f"Chat message from {sender_id} to {recipient_id}")