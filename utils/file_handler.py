import os
import uuid
from werkzeug.utils import secure_filename
from typing import Tuple

def allowed_file(filename: str, allowed_extensions: set) -> bool:
    """Check if file extension is allowed"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in allowed_extensions

def save_uploaded_file(file, upload_folder: str) -> Tuple[str, str]:
    """Save uploaded file and return path"""
    filename = secure_filename(file.filename)
    stored_filename = f"{uuid.uuid4().hex}_{filename}"
    filepath = os.path.join(upload_folder, stored_filename)
    file.save(filepath)
    return filepath, filename
