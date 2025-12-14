import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Security
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    
    # Database 
    #SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL").replace("postgres://", "postgresql://") or 'sqlite:///logistics.db'
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL") or 'sqlite:///logistics.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Debug
    DEBUG = os.environ.get('DEBUG', 'True').lower() == 'true'
    
    # Session
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)
    
    # File Uploads
    UPLOAD_FOLDER = 'static/uploads'
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024
    
    # Other configurations (can be added later)
    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
    MAIL_USE_TLS = True
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')

    # WhatsApp configuration
    WHATSAPP_NUMBER = "2347065894127"
    WHATSAPP_BUSINESS_NAME = "Majesty Xpress Logistics"
    WHATSAPP_HOURS = "24/7"
    WHATSAPP_MESSAGE = "Hello Majesty Xpress, I need assistance with: "

    # Distance Matrix AI API Configuration
    DISTANCE_MATRIX_API_KEY = os.environ.get('DISTANCE_MATRIX_API_KEY')
    GEOCODING_API_KEY = os.environ.get('GEOCODING_API_KEY')
    
    # Pricing Configuration
    PRICE_PER_KM = float(os.environ.get('PRICE_PER_KM', 200))
    MINIMUM_DELIVERY_PRICE = float(os.environ.get('MINIMUM_DELIVERY_PRICE', 500))
    WEIGHT_SURCHARGE_PER_KG = float(os.environ.get('WEIGHT_SURCHARGE_PER_KG', 1.5))
    HEAVY_SURCHARGE_PER_KG = float(os.environ.get('HEAVY_SURCHARGE_PER_KG', 2.0))
    INSURANCE_RATE = float(os.environ.get('INSURANCE_RATE', 0.02))
    EXPRESS_MULTIPLIER = float(os.environ.get('EXPRESS_MULTIPLIER', 1.5))
    STANDARD_MULTIPLIER = float(os.environ.get('STANDARD_MULTIPLIER', 1.0))
    ECONOMY_MULTIPLIER = float(os.environ.get('ECONOMY_MULTIPLIER', 0.8))
    SIGNATURE_FEE = float(os.environ.get('SIGNATURE_FEE', 200))