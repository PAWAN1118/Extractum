#!/bin/bash
set -e

# Build React frontend
if [ -f "frontend/package.json" ]; then
  echo "Installing frontend dependencies..."
  cd frontend
  npm install
  chmod +x node_modules/.bin/vite
  ./node_modules/.bin/vite build
  cd ..
fi

echo "Installing Python requirements..."
pip install -r requirements.txt
