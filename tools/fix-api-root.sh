#!/bin/bash

# Directory to scan (update as needed)
SRC_DIR="./frontend/src"

echo "🔍 Scanning for direct API URL usage in $SRC_DIR ..."

# Find all files with process.env.NEXT_PUBLIC_API_URL
FILES=$(grep -rl "process.env.NEXT_PUBLIC_API_URL" "$SRC_DIR")

for file in $FILES; do
  echo "⚡ Updating $file ..."

  # Add import at the top (if not already present)
  grep -q 'import { API_ROOT } from "@/lib/api";' "$file" || \
    sed -i '1i import { API_ROOT } from "@/lib/api";' "$file"

  # Replace all process.env.NEXT_PUBLIC_API_URL with API_ROOT
  sed -i 's/process\.env\.NEXT_PUBLIC_API_URL/API_ROOT/g' "$file"
done

echo "✅ All done! Review changes with: git diff"
