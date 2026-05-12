import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    
    # Use /tmp on Render (Linux), local folders on Windows
    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', 'static/uploads')
    
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB max file size
    ALLOWED_EXTENSIONS = {'pdf'}
    
    # Tesseract: Linux path on Render, Windows path locally
    TESSERACT_CMD = os.environ.get('TESSERACT_CMD', '/usr/bin/tesseract')

    # Create upload folder if it doesn't exist. Results are stored in Supabase.
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
