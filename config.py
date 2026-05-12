import os

def _default_tesseract_cmd():
    candidates = [
        os.environ.get('TESSERACT_CMD'),
        r'C:\Program Files\Tesseract-OCR\tesseract.exe',
        r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
        '/usr/bin/tesseract',
        '/usr/local/bin/tesseract',
    ]
    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return candidate
    return os.environ.get('TESSERACT_CMD', 'tesseract')

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    
    # Use /tmp on Render (Linux), local folders on Windows
    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', 'static/uploads')
    
    MAX_CONTENT_LENGTH = int(os.environ.get('MAX_CONTENT_LENGTH', 200 * 1024 * 1024))  # 200MB default
    ALLOWED_EXTENSIONS = {'pdf'}
    
    # Tesseract: Linux path on Render, Windows path locally
    TESSERACT_CMD = _default_tesseract_cmd()
    TESSERACT_PAGE_TIMEOUT = int(os.environ.get('TESSERACT_PAGE_TIMEOUT', '90'))
    OCR_MAX_PAGES = int(os.environ.get('OCR_MAX_PAGES', '25'))
    OCR_MAX_IMAGE_PIXELS = int(os.environ.get('OCR_MAX_IMAGE_PIXELS', '6000000'))
    OCR_TESSERACT_CONFIG = os.environ.get('OCR_TESSERACT_CONFIG', '--oem 1 --psm 6')

    # Create upload folder if it doesn't exist. Results are stored in Supabase.
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
