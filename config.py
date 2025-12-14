# config.py
import os
from datetime import timedelta

class Config:
    # Secret key
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'your-secret-key-change-in-production'
    
    # Database configuration - FIX FOR SQLALCHEMY 1.4+
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///logistics.db')
    
    # Fix for Heroku/Vercel PostgreSQL URLs (they use 'postgres://' but SQLAlchemy needs 'postgresql://')
    if SQLALCHEMY_DATABASE_URI and SQLALCHEMY_DATABASE_URI.startswith('postgres://'):
        SQLALCHEMY_DATABASE_URI = SQLALCHEMY_DATABASE_URI.replace('postgres://', 'postgresql://', 1)
    
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
    }
    
    # Mail configuration
    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'true').lower() in ['true', '1', 'yes']
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER', MAIL_USERNAME)
    
    # Twilio configuration
    TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID')
    TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN')
    TWILIO_PHONE_NUMBER = os.environ.get('TWILIO_PHONE_NUMBER')
    
    # WhatsApp
    WHATSAPP_NUMBER = os.environ.get('WHATSAPP_NUMBER', '2348012345678')
    
    # Admin
    ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL')
    
    # API Keys
    DISTANCE_MATRIX_API_KEY = os.environ.get('DISTANCE_MATRIX_API_KEY')
    GEOCODING_API_KEY = os.environ.get('GEOCODING_API_KEY')
    GOOGLE_MAPS_API_KEY = os.environ.get('GOOGLE_MAPS_API_KEY')
    
    # Pricing configuration
    PRICE_PER_KM = float(os.environ.get('PRICE_PER_KM', 200))
    MINIMUM_DELIVERY_PRICE = float(os.environ.get('MINIMUM_DELIVERY_PRICE', 500))
    WEIGHT_SURCHARGE_PER_KG = float(os.environ.get('WEIGHT_SURCHARGE_PER_KG', 50))
    HEAVY_SURCHARGE_PER_KG = float(os.environ.get('HEAVY_SURCHARGE_PER_KG', 100))
    INSURANCE_RATE = float(os.environ.get('INSURANCE_RATE', 0.02))
    EXPRESS_MULTIPLIER = float(os.environ.get('EXPRESS_MULTIPLIER', 1.5))
    STANDARD_MULTIPLIER = float(os.environ.get('STANDARD_MULTIPLIER', 1.0))
    ECONOMY_MULTIPLIER = float(os.environ.get('ECONOMY_MULTIPLIER', 0.8))
    SIGNATURE_FEE = float(os.environ.get('SIGNATURE_FEE', 200))
    
    # Session
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)
    
    # App URL
    APP_URL = os.environ.get('APP_URL', 'http://localhost:5000')


class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///logistics_dev.db')
    if SQLALCHEMY_DATABASE_URI and SQLALCHEMY_DATABASE_URI.startswith('postgres://'):
        SQLALCHEMY_DATABASE_URI = SQLALCHEMY_DATABASE_URI.replace('postgres://', 'postgresql://', 1)


class ProductionConfig(Config):
    DEBUG = False
    # Ensure we have a proper secret key in production
    SECRET_KEY = os.environ.get('SECRET_KEY')
    if not SECRET_KEY:
        raise ValueError("No SECRET_KEY set for production")


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False


# Config selector
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}