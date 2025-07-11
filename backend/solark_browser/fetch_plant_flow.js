// File: backend/solark_browser/fetch_plant_flow.js
// Purpose: Fetch and save today's plant snapshot (flat metrics) from SolArkCloud API

const fs = require('fs');
const axios = require('axios');

// === 1. Load auth token ===
let token;
try {
  token = fs.readFileSync('auth_token.txt', 'utf8').trim();
  if (!token) throw new Error('auth_token.txt is empty');
} catch (err) {
  console.error('❌ Could not read auth_token.txt:', err.message);
  process.exit(1);
}

// === 2. Set plant ID and date ===
const plantId = '146453'; // <-- Change to your actual plant ID if needed
const today = new Date().toISOString().slice(0, 10);

// === 3. Prepare headers and URL ===
const headers = {
  Authorization: `Bearer ${token}`,
  Origin: 'https://www.solarkcloud.com',
  Referer: `https://www.solarkcloud.com/plants/overview/${plantId}/2`,
};
const url = `https://api.solarkcloud.com/api/v1/plant/energy/${plantId}/flow?date=${today}`;

// === 4. Fetch and save plant snapshot ===
(async () => {
  try {
    console.log(`📈 Fetching plant snapshot for Plant ID ${plantId} on ${today}...`);
    const res = await axios.get(url, { headers });

    // === Debug: Print full API response ===
    console.log('🌐 RAW API RESPONSE:', JSON.stringify(res.data, null, 2));

    // === 5. Validate and process the data ===
    const snap = res.data?.data;
    if (!snap || typeof snap !== 'object') {
      throw new Error('No snapshot data returned. Check token, plantId, and date.');
    }

    // === 6. Save to file ===
    fs.writeFileSync('plant_flow.json', JSON.stringify(snap, null, 2));
    console.log('✅ Saved snapshot data to plant_flow.json');

    // === 7. Quick summary of key metrics ===
    console.log(`🔆 PV Power:     ${snap.pvPower} W`);
    console.log(`🔋 Battery Pwr:  ${snap.battPower} W`);
    console.log(`⚡ Load Power:   ${snap.loadOrEpsPower} W`);
    console.log(`🔋 SOC:         ${snap.soc} %`);
    console.log(`🔌 Grid Power:  ${snap.gridOrMeterPower} W`);

  } catch (err) {
    // === 8. Error handling and logging ===
    console.error('❌ Failed to fetch snapshot data:', err.message);
    if (err.response?.data) {
      fs.writeFileSync('plant_flow_error.json', JSON.stringify(err.response.data, null, 2));
      console.error('💾 Saved error response to plant_flow_error.json');
    }
    process.exit(1);
  }
})();
