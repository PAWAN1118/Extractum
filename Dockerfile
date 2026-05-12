FROM python:3.11-slim
 
# Install system dependencies including Tesseract and Poppler
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-eng \
    poppler-utils \
    libgl1 \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*
 
# Set working directory
WORKDIR /app
 
# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
 
# Copy frontend and build it
COPY frontend/ ./frontend/
RUN cd frontend && npm install && npx vite build
 
# Copy rest of the app
COPY . .
 
# Create temp upload folder. Results are stored in Supabase.
RUN mkdir -p /tmp/uploads
 
# Expose port
EXPOSE 10000
 
# Start gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:10000", "--workers", "1", "--threads", "4", "--timeout", "300", "app:app"]
