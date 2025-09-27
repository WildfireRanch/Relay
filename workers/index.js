#!/usr/bin/env node
/**
 * =============================================================================
 * File: workers/scheduler/index.js
 * Purpose: Single-process job scheduler (no YAML, all npm) to orchestrate
 *          cloud pulls from Victron VRM (REST) and Sol-Ark, and push into Postgres.
 * Author: Echo (COO/Strategist)
 * Created: 2025-09-26
 *
 * Summary
 *  - Uses node-cron for cron-like schedules (UTC).
 *  - Pulls VRM /overview every 5 min; /stats (hours) hourly; calls your Sol-Ark
 *    endpoint/scraper every N minutes.
 *  - Writes results into Postgres tables created by db/migrations/2025-09-26_vrm_schema.sql.
 *
 * Key Env Vars (Railway → Variables)
 *  - DATABASE_URL   : postgres://user:pass@host/db
 *  - VRM_API_TOKEN  : VRM access token (Preferences → Integrations → Access tokens)
 *  - IDSITE         : VRM idSite (e.g., 290928)
 *  - VRM_BASE_URL   : (optional) default https://vrmapi.victronenergy.com/v2
 *  - SOLARK_URL     : (optional) your Sol-Ark scraper endpoint (HTTP) or device URL
 *  - SOLARK_KEY     : (optional) auth/token for Sol-Ark scraper
 *
 * Ops Notes
 *  - Schedules are UTC; adjust cron strings if you want different cadences.
 *  - Retries: simple bounded retry w/ exponential backoff.
 *  - Idempotency: INSERT ... ON CONFLICT guards duplicates on facts tables.
 * =============================================================================
 */

const cron = require('node-cron');
const got = require('got').default;
const { Client } = require('pg');

// ---------- Config -------------------------------------------------------------
const VRM_BASE_URL = process.env.VRM_BASE_URL?.trim() || 'https://vrmapi.victronenergy.com/v2';
const VRM_API_TOKEN = (process.env.VRM_API_TOKEN || '').trim();
const IDSITE = parseInt(process.env.IDSITE || '0', 10);

const SOLARK_URL = process.env.SOLARK_URL?.trim();
const SOLARK_KEY = process.env.SOLARK_KEY?.trim();

const DATABASE_URL = process.env.DATABASE_URL;

if (!DATABASE_URL || !VRM_API_TOKEN || !IDSITE) {
  console.error('[FATAL] Missing env: DATABASE_URL, VRM_API_TOKEN, IDSITE are required.');
  process.exit(1);
}

// ---------- PG Client (single, reused) ----------------------------------------
const db = new Client({ connectionString: DATABASE_URL });
db.connect().then(() => console.log('[OK] Connected to Postgres')).catch(e => {
  console.error('[FATAL] Postgres connect failed:', e);
  process.exit(1);
});

// ---------- Helpers: HTTP with retries ----------------------------------------
async function httpJSON(url, { headers = {}, searchParams, method = 'GET', json, retries = 3, timeoutMs = 15000 } = {}) {
  let lastErr;
  for (let i = 0; i <= retries; i++) {
    try {
      const res = await got(url, {
        method,
        headers,
        searchParams,
        json,
        timeout: { request: timeoutMs },
        throwHttpErrors: true,
        retry: { limit: 0 },
      }).json();
      return res;
    } catch (e) {
      lastErr = e;
      const backoff = Math.min(8000, 500 * Math.pow(2, i));
      console.warn(`[WARN] HTTP ${method} ${url} failed (attempt ${i + 1}/${retries + 1}): ${e.message}. Backing off ${backoff}ms`);
      await new Promise(r => setTimeout(r, backoff));
    }
  }
  throw lastErr;
}

// ---------- Jobs: VRM /overview → vrm.site_overview ---------------------------
async function jobVrmOverview() {
  const url = `${VRM_BASE_URL}/installations/${IDSITE}/overview`;
  const data = await httpJSON(url, { headers: { 'X-Authorization': `Token ${VRM_API_TOKEN}`, 'Accept': 'application/json' } });
  if (data?.success === false) throw new Error(`VRM overview error: ${JSON.stringify(data)}`);

  // Extract a few convenience fields if present
  const rec = data.records || data; // some payloads are directly records
  const ts = new Date().toISOString();
  const battery_soc = num(rec.battery_soc ?? rec.battery?.soc);
  const pv_power_w   = num(rec.pv_power ?? rec.pv?.power);
  const load_power_w = num(rec.load_power ?? rec.load?.power);
  const grid_power_w = num(rec.grid_power ?? rec.grid?.power);
  const generator_w  = num(rec.generator_power ?? rec.generator?.power);

  await db.query(`
    INSERT INTO vrm.site_overview (ts, site_id, payload, battery_soc, pv_power_w, load_power_w, grid_power_w, generator_w)
    VALUES ($1,$2,$3::jsonb,$4,$5,$6,$7,$8)
    ON CONFLICT (site_id, ts) DO NOTHING
  `, [ts, IDSITE, JSON.stringify(data), battery_soc, pv_power_w, load_power_w, grid_power_w, generator_w]);

  console.log(`[OK] VRM overview upsert @ ${ts}`);
}

// ---------- Jobs: VRM /stats → vrm.energy_stats -------------------------------
async function jobVrmStatsHours() {
  const end = new Date();
  const start = new Date(end.getTime() - 48 * 3600 * 1000); // last 48 hours
  const url = `${VRM_BASE_URL}/installations/${IDSITE}/stats`;
  const data = await httpJSON(url, {
    headers: { 'X-Authorization': `Token ${VRM_API_TOKEN}`, 'Accept': 'application/json' },
    searchParams: {
      type: 'hours',
      start: start.toISOString().replace(/\.\d{3}Z$/, 'Z'),
      end:   end.toISOString().replace(/\.\d{3}Z$/, 'Z'),
    }
  });
  if (!data?.records) throw new Error('VRM stats missing records');

  // Insert each hourly window (idempotent on window_start)
  const inserts = data.records.map(r => {
    const ws = iso(r.start);  // VRM returns ISO; ensure string
    const we = iso(r.end);
    const payload = JSON.stringify(r);
    const pv_wh   = int(r.pv_yield ?? r.pv ?? r.pv_yield_wh);
    const load_wh = int(r.consumption ?? r.load_cons_wh ?? r.consumption_wh);
    const grid_in = int(r.grid_in ?? r.grid_in_wh);
    const grid_out= int(r.grid_out ?? r.grid_out_wh);
    const bat_in  = int(r.battery_in ?? r.battery_in_wh);
    const bat_out = int(r.battery_out ?? r.battery_out_wh);
    return db.query(`
      INSERT INTO vrm.energy_stats
        (site_id, window_start, window_end, granularity, payload, pv_yield_wh, load_cons_wh, grid_in_wh, grid_out_wh, battery_in_wh, battery_out_wh)
      VALUES ($1,$2,$3,'hours',$4::jsonb,$5,$6,$7,$8,$9,$10)
      ON CONFLICT (site_id, window_start, granularity) DO UPDATE
        SET payload = EXCLUDED.payload
    `, [IDSITE, ws, we, payload, pv_wh, load_wh, grid_in, grid_out, bat_in, bat_out]);
  });
  await Promise.all(inserts);
  console.log(`[OK] VRM stats(hours) upserted ${data.records.length} windows`);
}

// ---------- Jobs: Sol-Ark scrape (HTTP example) -------------------------------
async function jobSolArk() {
  if (!SOLARK_URL) {
    console.log('[SKIP] SOLARK_URL not set');
    return;
  }
  const headers = SOLARK_KEY ? { Authorization: `Bearer ${SOLARK_KEY}` } : {};
  const payload = await httpJSON(SOLARK_URL, { headers, timeoutMs: 12000 });
  // Example: write raw payload into a staging table you own (adjust to your schema)
  await db.query(`
    CREATE TABLE IF NOT EXISTS solark.raw_ingest (
      ts timestamptz NOT NULL DEFAULT now(),
      payload jsonb NOT NULL
    )`);
  await db.query(`INSERT INTO solark.raw_ingest (payload) VALUES ($1::jsonb)`, [JSON.stringify(payload)]);
  console.log('[OK] Sol-Ark scrape stored');
}

// ---------- Cron wiring (UTC) -------------------------------------------------
/**
 * Cron syntax: m h dom mon dow (UTC)
 * - VRM overview: every 5 minutes
 * - VRM stats(hours): at minute 7 every hour (jitter away from :00)
 * - Sol-Ark: every 2 minutes (tune as you like)
 */
function wireCrons() {
  cron.schedule('*/5 * * * *', wrap('vrm_overview', jobVrmOverview), { timezone: 'UTC' });
  cron.schedule('7 * * * *',   wrap('vrm_stats_hours', jobVrmStatsHours), { timezone: 'UTC' });
  cron.schedule('*/2 * * * *', wrap('solark_scrape', jobSolArk), { timezone: 'UTC' });
  console.log('[OK] Scheduler started (UTC). Jobs: vrm_overview:*/5m, vrm_stats_hours:hourly@07, solark:*/2m');
}

// ---------- Utilities ---------------------------------------------------------
function wrap(name, fn) {
  return async () => {
    const t0 = Date.now();
    try {
      await fn();
      console.log(`[DONE] ${name} ${Date.now() - t0}ms`);
    } catch (e) {
      console.error(`[FAIL] ${name}:`, e.message);
    }
  };
}
const num = v => (v == null ? null : Number(v));
const int = v => (v == null ? null : Math.round(Number(v)));
const iso = v => (typeof v === 'string' ? v : new Date(v).toISOString().replace(/\.\d{3}Z$/, 'Z'));

// ---------- Boot --------------------------------------------------------------
wireCrons();

// Graceful shutdown
process.on('SIGINT', async () => { await db.end(); process.exit(0); });
process.on('SIGTERM', async () => { await db.end(); process.exit(0); });
