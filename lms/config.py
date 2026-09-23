import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'lms-super-secret-key-2024')
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///lms.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads')
    MAX_CONTENT_LENGTH = 100 * 1024 * 1024  # 100 MB max upload
    ALLOWED_EXTENSIONS = {'pdf', 'ppt', 'pptx', 'doc', 'docx', 'mp4', 'avi', 'mov', 'png', 'jpg', 'jpeg', 'gif', 'txt'}
    WTF_CSRF_ENABLED = True
