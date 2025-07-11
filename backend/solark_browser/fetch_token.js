// File: backend/solark_browser/fetch_token.js
// Purpose: Authenticate with SolArkCloud via OAuth and store a valid access token

const fs = require('fs');
const axios = require('axios');
require('dotenv').config();

// === 1. Ensure credentials exist ===
const email = process.env.SOLARK_EMAIL;
const password = process.env.SOLARK_PASSWORD;

if (!email || !password) {
  console.error('❌ Missing SOLARK_EMAIL or SOLARK_PASSWORD in .env');
  process.exit(1);
}

// === 2. Build payload and headers ===
const url = 'https://api.solarkcloud.com/oauth/token';

const data = {
  grant_type: 'password',
  username: email,
  password: password,
  scope: 'all',
};

const headers = {
  'Content-Type': 'application/json',
  Origin: 'https://www.solarkcloud.com',
  Referer: 'https://www.solarkcloud.com/',
};

// === 3. Perform login and store token ===
(async () => {
  try {
    console.log('🔐 Authenticating with SolArkCloud...');
    const res = await axios.post(url, data, { headers });
    console.log('🧾 Full response:', JSON.stringify(res.data, null, 2));

    const token = res.data?.data?.access_token;
    if (!token) throw new Error('No access_token in response');

    fs.writeFileSync('auth_token.txt', token);
    console.log('✅ Token saved to auth_token.txt');
  } catch (err) {
    console.error('❌ Failed to fetch token:', err.message);
    if (err.response?.data) {
      fs.writeFileSync('fetch_token_error.json', JSON.stringify(err.response.data, null, 2));
      console.error('💾 Saved response to fetch_token_error.json');
    }
    process.exit(1);
  }
})();
