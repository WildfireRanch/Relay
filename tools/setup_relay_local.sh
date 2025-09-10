#!/bin/bash

echo "🚀 Starting Relay environment setup..."

# === 🗂 Create missing directories ===
echo "📁 Creating required directories..."
mkdir -p secrets data/index logs

# === 📄 Create placeholder .env if missing ===
if [ ! -f ".env" ]; then
  echo "⚠️  .env not found. Creating template..."
  cat <<EOF > .env
# === 🚪 Relay Agent Authentication ===
API_KEY=relay-dev

# === 🤖 OpenAI Configuration ===
OPENAI_API_KEY=sk-your-key

# === 📄 Google API / OAuth 2.0 ===
GOOGLE_CREDS_JSON=./secrets/google-creds.json
GOOGLE_TOKEN_JSON=./secrets/google-token.json
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret
OAUTH_REDIRECT_URI=http://localhost:3000/auth/callback
POST_AUTH_REDIRECT_URI=http://localhost:3000/docs

# === ⚙️ Runtime & Embedding ===
ENV=local
INDEX_ROOT=./data/index
KB_EMBED_MODEL=text-embedding-3-large
RELAY_PROJECT_ROOT=.

# === 🌐 CORS / Frontend Integration ===
FRONTEND_ORIGIN=http://localhost:3000

# === 🧠 Frontend (Next.js) ===
NEXT_PUBLIC_API_KEY=relay-dev
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_RELAY_KEY=
EOF
  echo "✅ .env created. Be sure to fill in the real secrets!"
else
  echo "✅ .env already exists."
fi

# === 🐍 Setup Python backend ===
echo "🐍 Setting up Python environment..."
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# === 🌐 Setup frontend ===
echo "🧶 Installing frontend dependencies..."
cd frontend
npm install

echo "✅ Frontend ready. Run it with: npm run dev"
cd ..

# === ✅ Done ===
echo "🎉 Setup complete. Start backend with: source .venv/bin/activate && uvicorn main:app --reload"
