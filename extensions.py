# extensions.py
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_mail import Mail
from flask_cors import CORS
from flask_admin import Admin

# Initialize extensions
db = SQLAlchemy()
login_manager = LoginManager()
mail = Mail()
cors = CORS()
admin = Admin(name='Logistics Admin')