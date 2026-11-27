// Quick refresh: read the two bonus roundup lists and merge them into the latest full offer list.
// A TypeScript copy of the roundup parts of scripts/scrape.py (parse_doc, parse_fs, parse_reqs, merge), kept
// deliberately small. tests/e2e/parity.mjs checks it against the Python version on the same pages, so the two
// can't drift apart unnoticed. The slow enrichment (articles, federal lookups, bank-page checks, crawler) stays
// in the daily Python run; offers this adds are marked quick: 1 until that run fills them in.

export const DOC_URL = "https://www.doctorofcredit.com/best-bank-account-bonuses/";
export const FS_URL = (y: number) => `https://www.fatstacksacademy.com/blog/best-checking-bonuses-${y}`;
const STATES = new Set("AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY".split(" "));
const MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"];
const ALIASES: Record<string, string> = {
  charlesschwab: "schwab", citibank: "citi", bmoharris: "bmo", usbancorp: "us", verve: "verve", bethpage: "fourleaf", "53": "fifththird",
  pncvirtualwallet: "pnc", keybank: "key", keybanknational: "key", capitalone360: "capitalone", secumaryland: "secu",
  trustonefinancial: "trustone", chaseprivateclient: "chase", huntingtonnational: "huntington", wellsfargobank: "wellsfargo", td: "td",
  tdbank: "td", citizensbank: "citizens",
};
const GENERIC = /\b(the|banks?|n\.?a\.?|national association|financial|group|company|co|inc|corp|federal credit union|credit union|fcu|cu|federal|checking|savings|account|accounts|bonus|bonuses|and|a|by|personal|online|new)\b/g;
const THIRD_PARTY = ["doctorofcredit.com", "fatstacksacademy.com", "thebonusstack.com", "reddit.com", "bit.ly", "tinyurl.com"];
const NAME_STOP = new Set(["bank", "banks", "credit", "union", "federal", "the", "and", "of", "na", "fcu", "cu", "financial", "community", "national",
  "trust", "savings", "first", "checking", "account", "company", "group", "state", "city", "american", "america"]);
const KNOWN_DOMAINS: Record<string, string[]> = {
  chase: ["chase.com"], bankofamerica: ["bankofamerica.com", "bofa.com"], us: ["usbank.com"], citi: ["citi.com", "citibank.com"],
  wellsfargo: ["wellsfargo.com", "wf.com"], key: ["key.com"], fifththird: ["53.com"], td: ["td.com", "tdbank.com"], navy: ["navyfederal.org"],
  bmo: ["bmo.com"], pnc: ["pnc.com"], schwab: ["schwab.com"], capitalone: ["capitalone.com"], hsbc: ["hsbc.com", "us.hsbc.com"],
  truist: ["truist.com"], regions: ["regions.com"], citizens: ["citizensbank.com"], huntington: ["huntington.com"], sofi: ["sofi.com"],
  fourleaf: ["fourleaffcu.org"], bok: ["bokfinancial.com"],
};

// ---------------- text helpers (same as scrape.py) ----------------
export const clean = (s: string | null | undefined) => (s || "").replace(/–/g, "-").replace(/—/g, "-").replace(/ /g, " ").replace(/\s+/g, " ").trim();

export function norm(name: string): string {
  let s = clean(name).toLowerCase();
  s = s.replace(/\(.*?\)|\[.*?\]/g, " ").replace(/&/g, " and ");
  s = s.replace(/\bbank of\b/g, "bankof");
  s = s.replace(GENERIC, " ");
  s = s.replace(/[^a-z0-9]/g, "");
  return ALIASES[s] ?? s;
}

export function cleanName(name: string): string {
  let n = clean(name).replace(/^\[[^\]]*\]\s*/, "");
  for (;;) {
    const m = n.match(/[\s,&]+(?:and\s+)?\b([A-Z]{2})\s*$/);
    if (!m || !STATES.has(m[1])) break;
    n = n.slice(0, m.index);
  }
  n = n.replace(/\s*[-–:,]\s*$/, "");
  n = n.replace(/\s+(?:checking|savings)?\s*(?:bonus|offer)?\s*$/i, "").trim();
  return n;
}

export const moneyVals = (s: string) => [...s.matchAll(/\$\s?([\d,]{2,7})(?![\d,]*%)/g)].map((m) => parseInt(m[1].replace(/,/g, ""), 10));
export const statesIn = (t: string) => [...new Set([...t.matchAll(/\b([A-Z]{2})\b/g)].map((m) => m[1]).filter((s) => STATES.has(s)))].sort();
export const slug = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 40);
const pad = (n: number) => String(n).padStart(2, "0");

export function parseDate(s: string): string | null {
  let m = s.match(/\b(\d{1,2})\/(\d{1,2})\/(\d{2,4})\b/);
  if (m) {
    let y = parseInt(m[3], 10);
    if (y < 100) y += 2000;
    return `${y}-${pad(+m[1])}-${pad(+m[2])}`;
  }
  m = s.match(/\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2}),?\s+(\d{4})/i);
  if (m) return `${m[3]}-${pad(MONTHS.indexOf(m[1].toLowerCase()) + 1)}-${pad(+m[2])}`;
  return null;
}

// deno-lint-ignore no-explicit-any
export function parseReqs(text: string): Record<string, any> {
  const t = clean(text);
  // deno-lint-ignore no-explicit-any
  const out: Record<string, any> = {};
  const num = (s: string) => parseInt(s.replace(/,/g, ""), 10);
  if (/no (?:direct deposit|dd) (?:is )?required|direct deposit (?:is )?not required|\bno dd\b/i.test(t)) out.dd = 0;
  else {
    let m = t.match(/\$([\d,]+)\s*(?:-|to|–)\s*\$([\d,]+)\+?\s*(?:in |of )?(?:total |qualifying |eligible )?(?:direct deposits?|dd)/i);
    if (m) { out.mindd = num(m[1]); out.dd = num(m[2]); }
    else {
      m = t.match(/(?:direct deposits? (?:of|totaling|totalling) |dd of )\$([\d,]+)|\$([\d,]+)\+?\s*(?:\/mo(?:nth)?\s*)?(?:in |of )?(?:total |qualifying |eligible |recurring )?(?:direct deposits?|dd)\b/i);
      if (m) {
        const amt = m[1] || m[2];
        out.dd = num(amt);
        const k = t.match(new RegExp("\\b(\\d|two|three|four)\\s+(?:qualifying\\s+|separate\\s+)?direct deposits?\\s+of\\s+\\$" + amt.replace(/[$,]/g, (c) => "\\" + c), "i"));
        if (k) out.dd *= ({ two: 2, three: 3, four: 4 } as Record<string, number>)[k[1].toLowerCase()] || parseInt(k[1], 10);
        const after = t.slice((m.index || 0) + m[0].length, (m.index || 0) + m[0].length + 20);
        if (/\$[\d,]+\+?\s*\/mo(?:nth)?/.test(m[0]) || /^\s*(?:per|each|a|every)\s+month|^\s*monthly/i.test(after)) out.mdd = out.dd;
      } else if (/direct deposit|\bdd\b/i.test(t)) out.dd = 1;
    }
  }
  let m = t.match(/(?:within|in|first)\s+(\d{2,3})\s+days/i);
  if (m) out.win = parseInt(m[1], 10);
  m = t.match(/(\d{1,3})\+?\s+(?:qualifying\s+|debit(?:\s+card)?\s+)?(?:purchases|transactions|tx)\b/i);
  if (m) out.tx = parseInt(m[1], 10);
  m = t.match(/(\d{1,2})\s*-?\s*mo(?:nth)?s?\s*(?:cooldown|anti-churn)/i) || t.match(/once every (\d{1,2}) months/i);
  if (m) out.cd = parseInt(m[1], 10);
  else if (/once every (two|2) years|24 months/i.test(t)) out.cd = 24;
  m = t.match(/\$(\d+(?:\.\d\d)?)\s*(?:\/mo|monthly|per month)\s*(?:fee)?/i);
  if (m) out.fee = parseFloat(m[1]) === 0 ? "None" : `$${m[1]}`;
  if (/hard pull/i.test(t)) out.pull = "hard";
  else if (/soft pull/i.test(t)) out.pull = "soft";
  m = t.match(/(?:expires?|valid (?:through|until)|ends?|through|until|by)\s+((?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4}|\d{1,2}\/\d{1,2}\/\d{2,4})/i);
  if (m) out.exp = parseDate(m[1]);
  return out;
}

function hostOf(url: string): string {
  try { return new URL(url).hostname.toLowerCase().replace(/^www\./, ""); } catch { return ""; }
}

export function linkMatchesBank(bank: string, url: string): boolean {
  const host = hostOf(url);
  if (!host || !url.startsWith("https://") || THIRD_PARTY.some((d) => host === d || host.endsWith("." + d))) return false;
  const n = norm(bank);
  if (KNOWN_DOMAINS[n]) return KNOWN_DOMAINS[n].some((d) => host === d || host.endsWith("." + d));
  const labels = host.replace(/[^a-z0-9.]/g, "").split(".").slice(0, -1);
  const site = labels.join("");
  const words = (clean(bank).toLowerCase().match(/[a-z0-9]+/g) || []).filter((w) => !NAME_STOP.has(w));
  if (words.some((w) => w.length >= 4 && site.includes(w))) return true;
  if (n && n.length >= 4) {
    for (const lbl of labels) {
      const rest = lbl.includes(n) ? lbl.replace(n, "") : null;
      if (rest !== null && (n.length >= 8 || ["", "bank", "cu", "fcu", "online", "banking", "creditunion", "fed", "federal", "financial"].includes(rest))) return true;
      if (lbl.length >= 5 && n.includes(lbl)) return true;
    }
  }
  const initials = (clean(bank).toLowerCase().replace(/\(.*?\)/g, "").match(/[a-z0-9]+/g) || []).filter((w) => !["the", "of", "and", "a"].includes(w)).map((w) => w[0]).join("");
  return initials.length >= 3 && labels.some((l) => l.startsWith(initials));
}

function articleAboutBank(bank: string, url: string): boolean {
  let path = "";
  try { path = new URL(url).pathname.toLowerCase().replace(/[^a-z0-9]/g, ""); } catch { return false; }
  const words = (clean(bank).toLowerCase().match(/[a-z0-9]+/g) || []).filter((w) => !NAME_STOP.has(w) && w.length >= 3);
  const n = norm(bank);
  return Boolean((n && n.length >= 3 && path.includes(n)) || words.some((w) => path.includes(w)));
}

// ---------------- DOM helpers (BeautifulSoup's get_text(" ") and document order) ----------------
// deno-lint-ignore no-explicit-any
type Node = any;
function text(el: Node): string {
  const parts: string[] = [];
  const walk = (n: Node) => {
    if (n.nodeType === 3) {
      // adjacent text pieces (the parser splits text at entities like &amp;) belong together, as in BeautifulSoup
      if (n.previousSibling && n.previousSibling.nodeType === 3 && parts.length) parts[parts.length - 1] += n.data ?? n.textContent;
      else parts.push(n.data ?? n.textContent);
    } else if (n.childNodes) for (const c of n.childNodes) walk(c);
  };
  walk(el);
  return parts.join(" ");
}
function* after(start: Node): Generator<Node> { // every node after start in document order, including its descendants
  const stack: Node[] = [];
  let n: Node = start;
  if (n.firstChild) { yield* descend(n.firstChild); }
  while (n) {
    let s = n.nextSibling;
    while (s) { yield* descend(s); s = s.nextSibling; }
    n = n.parentNode;
    if (!n || n.nodeType === 9) break;
  }
  void stack;
}
function* descend(n: Node): Generator<Node> {
  yield n;
  for (let c = n.firstChild; c; c = c.nextSibling) yield* descend(c);
}

// deno-lint-ignore no-explicit-any
export type Scraped = Record<string, any>;

export function parseDoc(html: string, DOMParser: Node): Scraped[] {
  const doc = new DOMParser().parseFromString(html, "text/html");
  const body = doc.querySelector(".entry-content, article, main") || doc.body || doc;
  const offers: Scraped[] = [];
  let section = "";
  for (const el of body.querySelectorAll("h2, h3")) {
    const txt = clean(text(el));
    if (el.tagName.toLowerCase() === "h2") { section = txt.toLowerCase(); continue; }
    if (!["checking", "state specific", "region specific", "branch specific"].some((k) => section.includes(k))) continue;
    if (/\bbusiness\b|\bbrokerage\b|\bIRA\b|\bCD\b|credit card/i.test(txt)) continue;
    if (/savings/i.test(txt) && !/checking/i.test(txt)) continue;
    const amts = moneyVals(txt);
    if (!amts.length) continue;
    const dash = txt.match(/\s-\s/);
    const head = dash ? txt.slice(0, dash.index) : txt, tail = dash ? txt.slice((dash.index || 0) + dash[0].length) : "";
    if (/youth|student|college|teen|kids|minor/i.test(txt) && !/adult/i.test(txt)) continue;
    const name = cleanName(head.replace(/^\[[^\]]*\]\s*/, "").split(/\$|\bup to\b/i)[0]);
    if (name.length < 2) continue;
    const parts: string[] = [], links: Record<string, string> = {};
    for (let sib = el.nextSibling; sib; sib = sib.nextSibling) {
      const tag = sib.tagName ? sib.tagName.toLowerCase() : "";
      if (["h2", "h3", "h4"].includes(tag) || (sib.querySelector && sib.querySelector("h2, h3, h4"))) break;
      if (sib.nodeType === 1) {
        parts.push(text(sib));
        for (const a of sib.querySelectorAll("a[href]")) {
          const lt = clean(a.textContent).toLowerCase(), href = a.getAttribute("href");
          if (lt.includes("direct link") && !links.direct && linkMatchesBank(name || txt, href)) links.direct = href;
          else if (lt.includes("full post") && !links.post) links.post = href;
        }
      } else if (sib.nodeType === 3) {
        if (sib.previousSibling && sib.previousSibling.nodeType === 3 && parts.length) parts[parts.length - 1] += sib.data ?? sib.textContent;
        else parts.push(sib.data ?? sib.textContent);
      }
    }
    const bodytxt = clean(parts.join(" "));
    const bracket = txt.startsWith("[") ? (txt.match(/^\[([^\]]+)\]/) || [])[1] || "" : "";
    const st = statesIn(txt.includes("$") ? txt.slice(txt.indexOf("$")) : tail).length ? statesIn(txt.includes("$") ? txt.slice(txt.indexOf("$")) : tail) : statesIn(bracket);
    const o: Scraped = { b: name, amt: Math.max(...amts), src: "doc", heading: txt,
      st: st.length ? st : (section.includes("checking") && !section.includes("state") ? "ALL" : "?"),
      req: bodytxt.slice(0, 240), url: [links.direct, links.post].find((u) => u && u.startsWith("https://")) || DOC_URL };
    const post = links.post || "";
    o.srcUrl = post.startsWith("https://") && articleAboutBank(name, post) ? post : DOC_URL;
    Object.assign(o, parseReqs(bodytxt));
    if (/in branch/i.test(txt)) o.branch = 1;
    offers.push(o);
  }
  return offers;
}

const FS_HEAD = /^(?:#?\d{1,3}\.?\s+)?(?<name>[A-Za-z0-9][^$|]{1,80}?)\s*\$\s*(?<amt>[\d,]{2,7})\+?(?:\s+top pick)?$/i;

export function parseFs(html: string, DOMParser: Node): Scraped[] {
  const doc = new DOMParser().parseFromString(html, "text/html");
  for (const t of doc.querySelectorAll("script, style, nav, footer, header")) t.remove();
  const all = [...doc.querySelectorAll("*")];
  const cands = all.filter((el) => { const t = clean(text(el)); return t.length <= 110 && FS_HEAD.test(t); });
  const cset = new Set(cands);
  const heads = cands.filter((e) => ![...e.querySelectorAll("*")].some((d) => cset.has(d)));
  const hset = new Set(heads);
  const offers: Scraped[] = [], seen = new Set<string>();
  for (const h of heads) {
    const m = clean(text(h)).match(FS_HEAD)!;
    const name = cleanName(m.groups!.name.replace(/^\d{1,3}\s+/, ""));
    if (/youth|student|college|teen|kids/i.test(name)) continue;
    if (/^(top|best|up to|earn|get|bonus|total).*$/is.test(name)) continue;
    let card = h;
    while (card.parentElement && ![...card.parentElement.querySelectorAll("*")].some((x: Node) => x !== h && hset.has(x))) card = card.parentElement;
    const ancestors: Node[] = [];
    for (let p = h.parentElement; p; p = p.parentElement) if (p.tagName.toLowerCase() === "a" && p.getAttribute("href")) ancestors.push(p);
    const link = [...ancestors, ...card.querySelectorAll("a[href]")].map((a: Node) => a.getAttribute("href") || "").find((u: string) => u.includes("/blog/")) || null;
    const parts: string[] = [];
    let size = 0;
    for (const nxt of after(h)) {
      if (nxt.nodeType === 1 && hset.has(nxt)) break;
      if (nxt.nodeType === 3 && !h.contains(nxt)) {
        const d = nxt.data ?? nxt.textContent;
        if (nxt.previousSibling && nxt.previousSibling.nodeType === 3 && parts.length) parts[parts.length - 1] += d; else parts.push(d);
        size += d.length;
      }
      if (size > 900) break;
    }
    const bodytxt = clean(parts.join(" "));
    if (/business (?:checking|account)|\(business\)/i.test(bodytxt.slice(0, 300) + name)) continue;
    if (/no longer available|expired|offer (?:has )?ended/i.test(bodytxt.slice(0, 400))) continue;
    const key = norm(name) + "|" + m.groups!.amt;
    if (seen.has(key)) continue;
    seen.add(key);
    let url = link || "";
    if (url.startsWith("/")) url = "https://www.fatstacksacademy.com" + url;
    const o: Scraped = { b: name, amt: parseInt(m.groups!.amt.replace(/,/g, ""), 10), src: "fs", req: bodytxt.slice(0, 240),
      url: url.startsWith("https://") ? url : FS_URL(new Date().getUTCFullYear()), st: "?" };
    Object.assign(o, parseReqs(bodytxt));
    offers.push(o);
  }
  return offers;
}

// ---------------- quick merge ----------------
const isCompiler = (u?: string) => /(^|\.)(doctorofcredit|fatstacksacademy)\.com$/.test(hostOf(u || ""));

/** Merge fresh roundup listings into the latest full offer list. Never removes offers (the daily run handles that). */
// deno-lint-ignore no-explicit-any
export function quickMerge(base: any, scraped: Scraped[], today: string) {
  // deno-lint-ignore no-explicit-any
  const offers: any[] = (base.offers || []).map((o: any) => ({ ...o }));
  const byNorm = new Map<string, Scraped[]>();
  for (const s of scraped) if (s.amt >= 25 && s.amt <= 5000) byNorm.set(norm(s.b), [...(byNorm.get(norm(s.b)) || []), s]);
  // deno-lint-ignore no-explicit-any
  const listed = new Map<string, any[]>();
  for (const o of offers) if (!o.crawl && !o.custom) listed.set(norm(o.b), [...(listed.get(norm(o.b)) || []), o]);
  let changed = 0, stillListed = 0;
  for (const [n, group] of listed) {
    const hits = byNorm.get(n);
    if (!hits) continue;
    for (const o of group) { o.seen = today; stillListed++; }
    if (group.length !== 1) continue; // several offers from one bank: amounts can't be matched safely
    const o = group[0];
    const doc = hits.filter((h) => h.src === "doc");
    const amt = (doc[0] || hits[0]).amt;
    if (amt !== o.amt) { o.prevAmt = o.amt; o.changed = today; o.amt = amt; changed++; }
  }
  // brand-new offers: listed on a roundup but not on the site yet
  // deno-lint-ignore no-explicit-any
  const added: any[] = [];
  for (const [n, hits] of byNorm) {
    if (listed.has(n)) continue;
    const s = hits.find((h) => h.src === "doc") || hits[0];
    const merged: Scraped = { ...s };
    for (const h of hits) for (const f of ["dd", "mindd", "mdd", "win", "tx", "cd", "fee", "pull", "exp"]) if (merged[f] == null && h[f] != null) merged[f] = h[f];
    if (merged.st === "?") merged.st = hits.find((h) => h.st !== "?")?.st ?? "?";
    const b = s.b;
    const t = /credit union|\bfcu\b|\bcu\b/i.test(b) ? "cu" : /chime|current|varo|percapita|money\b/i.test(b) ? "fin" : "bank";
    const article = [s.srcUrl, s.url, ...hits.map((h) => h.url)].find((u) => isCompiler(u) && !/best-bank-account-bonuses\/?$|best-checking-bonuses-\d{4}\/?$/.test(u));
    // deno-lint-ignore no-explicit-any
    const o: any = {
      id: "auto-" + slug(n), b, a: "Checking", t, amt: s.amt, dd: merged.dd ?? null, win: merged.win ?? 90, tx: merged.tx ?? null, keep: null,
      cd: merged.cd ?? null, pull: merged.pull ?? "?", fee: merged.fee ?? "See terms", req: s.req || "", auto: 1, quick: 1,
      srcs: [...new Set(hits.map((h) => h.src))].sort(), seen: today, first: today, refUrl: article,
    };
    if (merged.mindd != null) o.mindd = merged.mindd;
    if (merged.mdd != null) o.mdd = merged.mdd;
    if (merged.exp && merged.exp >= today) o.exp = merged.exp;
    // states: the roundup's list until the daily run checks the federal lists; nationwide only when Doctor of Credit's section says so
    if (Array.isArray(merged.st)) { o.st = merged.st; o.stSrc = "article"; }
    else if (merged.st === "ALL" && hits.some((h) => h.src === "doc" && h.st === "ALL")) { o.st = "ALL"; o.natSrc = "Doctor of Credit"; }
    else o.st = "?";
    // links: only the bank's own page, never the roundup article
    const direct = hits.map((h) => h.url).find((u) => u && linkMatchesBank(b, u));
    if (direct) { o.offerUrl = direct; o.url = "https://" + new URL(direct).hostname; }
    added.push(o);
  }
  offers.push(...added);
  return { offers, added, changed, stillListed };
}
