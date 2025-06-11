#!/bin/bash

# Adjust these as needed:
ZIP_NAME="relay_debug_upload.zip"

# List the folders/files you want to include:
INCLUDE=(
  "main.py"
  "services/"
  "routes/"
  "frontend/src/components/"
  "frontend/src/app/"
  "frontend/src/lib/"
  ".env"
  "requirements.txt"
  "package.json"
  "tsconfig.json"
)

echo "Zipping up project files for debug upload..."

zip -r $ZIP_NAME ${INCLUDE[@]} \
  -x "*.pyc" "*.pyo" "*.log" "*.sqlite3" "*.db" "*.env.local" \
  -x "node_modules/*" ".next/*" ".git/*" "frontend/.next/*" \
  -x "__pycache__/*" ".venv/*" "docs/imported/*" "docs/generated/*"

echo "Created $ZIP_NAME"
