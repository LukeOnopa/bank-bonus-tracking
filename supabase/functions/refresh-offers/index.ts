// Supabase Edge Function "refresh-offers": the site's Refresh offers button (signed-in users).
// Reads the two bonus roundup lists, merges them into the latest full offer list, and saves the result to the
// site_data table, which the site reads alongside the daily data. Takes about 10-20 seconds.
//
// Setup (Supabase dashboard), once:
//   1. SQL Editor: run supabase/setup.sql (creates the site_data table and lets anyone read it).
//   2. Edge Functions -> Deploy a new function -> Via editor. Name it "refresh-offers". Add two files with the
//      contents of index.ts and roundups.ts from this folder. Deploy.
//   3. In the function's details, turn OFF "Verify JWT with legacy secret" / "Enforce JWT verification":
//      this code checks the signed-in user itself, and the browser's pre-flight request carries no token.
//
// POST -> {updated: true, generated, added: [names], changed} or 429 {error: "busy", lastAt, nextAllowedAt}

import { DOMParser } from "npm:linkedom@0.18.9";
import { DOC_URL, FS_URL, parseDoc, parseFs, quickMerge, type Scraped } from "./roundups.ts";

const SITE = "https://lukeonopa.github.io/bank-bonus-tracking/";
const ALLOWED_ORIGINS = ["https://lukeonopa.github.io"];
const MIN_GAP_MIN = 5;          // site-wide: one quick refresh every 5 minutes
const MIN_DOC = 5, MIN_FS = 20; // fewer offers than this = the page layout changed; skip that source
const UA = "BankBonusTracker/1.0 (+https://github.com/LukeOnopa/bank-bonus-tracking)";
const SB_URL = Deno.env.get("SUPABASE_URL") || "";

function cors(req: Request) {
  const origin = req.headers.get("origin") || "";
  return { "Access-Control-Allow-Origin": ALLOWED_ORIGINS.includes(origin) ? origin : ALLOWED_ORIGINS[0],
    "Access-Control-Allow-Headers": "authorization, apikey, content-type", "Access-Control-Allow-Methods": "POST, OPTIONS", "Vary": "Origin" };
}
const reply = (req: Request, status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { ...cors(req), "Content-Type": "application/json" } });

function serviceKey(): string {
  const legacy = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
  if (legacy) return legacy;
  try { return JSON.parse(Deno.env.get("SUPABASE_SECRET_KEYS") || "{}").default || ""; } catch { return ""; }
}
function db(path: string, init: RequestInit = {}) {
  const key = serviceKey();
  const headers: Record<string, string> = { apikey: key, "Content-Type": "application/json", ...(init.headers as Record<string, string> || {}) };
  if (key.startsWith("eyJ")) headers.Authorization = `Bearer ${key}`;
  return fetch(`${SB_URL}/rest/v1/${path}`, { ...init, headers });
}

async function signedIn(req: Request) {
  const auth = req.headers.get("authorization") || "";
  if (!auth.startsWith("Bearer ")) return false;
  const r = await fetch(`${SB_URL}/auth/v1/user`, { headers: { Authorization: auth, apikey: req.headers.get("apikey") || "" } });
  return r.ok && Boolean((await r.json())?.id);
}

async function get(url: string, ms = 12000) {
  const r = await fetch(url, { headers: { "User-Agent": UA, Accept: "text/html,application/json" }, signal: AbortSignal.timeout(ms) });
  if (!r.ok) throw new Error(`${new URL(url).hostname} said ${r.status}`);
  return r.text();
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: cors(req) });
  if (req.method !== "POST") return reply(req, 405, { error: "method" });
  try {
    if (!(await signedIn(req))) return reply(req, 401, { error: "signin", message: "Sign in to refresh offers." });

    // site-wide limit, from the last saved quick refresh
    const row = await (await db("site_data?key=eq.offers&select=data,updated_at")).json();
    const last = row?.[0]?.updated_at ? new Date(row[0].updated_at) : null;
    if (last && Date.now() - last.getTime() < MIN_GAP_MIN * 60000) {
      return reply(req, 429, { error: "busy", lastAt: last.toISOString(), nextAllowedAt: new Date(last.getTime() + MIN_GAP_MIN * 60000).toISOString() });
    }

    // everything at once: the daily file, and both roundup lists
    const year = new Date().getUTCFullYear();
    const [daily, docHtml, fsHtml] = await Promise.allSettled([
      get(SITE + "data/offers.json").then(JSON.parse), get(DOC_URL), get(FS_URL(year)).catch(() => get(FS_URL(year - 1))),
    ]);
    const quick = row?.[0]?.data;
    const dailyData = daily.status === "fulfilled" ? daily.value : null;
    const base = [dailyData, quick].filter(Boolean).sort((a, b) => String(b.generated).localeCompare(String(a.generated)))[0];
    if (!base) return reply(req, 502, { error: "base", message: "Couldn't load the current offers." });

    const sources = [], scraped: Scraped[] = [];
    for (const [name, res, parse, min, url] of [["Doctor of Credit", docHtml, parseDoc, MIN_DOC, DOC_URL], ["Fat Stacks Academy", fsHtml, parseFs, MIN_FS, FS_URL(year)]] as const) {
      const rec: Record<string, unknown> = { name, ok: false, count: 0, url };
      try {
        if (res.status !== "fulfilled") throw res.reason;
        const got = parse(res.value, DOMParser);
        rec.count = got.length;
        if (got.length >= min) { rec.ok = true; rec.lastOk = new Date().toISOString(); scraped.push(...got); }
        else rec.error = `Only ${got.length} offers parsed — page layout may have changed`;
      } catch (e) { rec.error = String((e as Error).message || e).slice(0, 200); }
      sources.push(rec);
    }
    if (!scraped.length) return reply(req, 502, { error: "sources", message: "Couldn't read the bonus sites right now. Try again in a few minutes." });

    const today = new Date().toISOString().slice(0, 10);
    const { offers, added, changed } = quickMerge(base, scraped, today);
    const generated = new Date().toISOString();
    const data = { ...base, generated, quick: true, dailyGenerated: dailyData?.generated ?? base.dailyGenerated ?? null, offers,
      sources: [...sources, ...(base.sources || []).filter((s: { name: string }) => !["Doctor of Credit", "Fat Stacks Academy"].includes(s.name))] };
    const save = await db("site_data?on_conflict=key", { method: "POST", headers: { Prefer: "resolution=merge-duplicates,return=minimal" },
      body: JSON.stringify({ key: "offers", data, updated_at: generated }) });
    if (!save.ok) return reply(req, 500, { error: "save", message: `Saving failed (${save.status})` });
    return reply(req, 200, { updated: true, generated, added: added.map((o) => o.b), changed });
  } catch (e) {
    return reply(req, 500, { error: "server", message: String((e as Error).message || e) });
  }
});
