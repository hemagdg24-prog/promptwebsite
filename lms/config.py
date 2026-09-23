import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'lms-super-secret-key-2024')
    if os.environ.get('VERCEL'):
        SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:////tmp/lms.db')
        UPLOAD_FOLDER = '/tmp/uploads'
    else:
        SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///lms.db')
        UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads')
        
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MAX_CONTENT_LENGTH = 100 * 1024 * 1024  # 100 MB max upload
    ALLOWED_EXTENSIONS = {'pdf', 'ppt', 'pptx', 'doc', 'docx', 'mp4', 'avi', 'mov', 'png', 'jpg', 'jpeg', 'gif', 'txt'}
    WTF_CSRF_ENABLED = True
