#!/bin/bash

# Change this path to your project's root directory
PROJECT_DIR="/path/to/your/project"

# Name of the zip file (includes timestamp)
ZIP_FILE="relay_codebase_$(date +'%Y%m%d_%H%M%S').zip"

# Navigate to your project directory
cd "$PROJECT_DIR" || { echo "Directory not found"; exit 1; }

# Create the zip archive (excluding node_modules, .git, and __pycache__)
zip -r "../$ZIP_FILE" . -x "node_modules/*" ".git/*" "__pycache__/*" "*.env" "*.venv/*"

echo "Codebase successfully zipped: ../$ZIP_FILE"
