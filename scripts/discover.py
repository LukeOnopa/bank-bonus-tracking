#!/usr/bin/env python3
"""Find checking-account bonuses on banks' and credit unions' own websites.

Pilot: banks with branches in the chosen states (FDIC BankFind) and credit unions
headquartered there (NCUA). For each institution's website it reads robots.txt and
sitemaps, picks a few likely promotion pages, and pulls out the bonus amount and
requirements with the same rules the roundup scraper uses.

Each run crawls only the sites that are due (oldest first) within a time budget, and
carries everything else over from the previous run's published file, so the hourly
job covers the whole list over a few hours and rechecks each site about weekly.

Finds are written to a separate file (data/discovered.json) marked unverified; they
never change the main offer list.

Ground rules: follow robots.txt, one request at a time per site with a pause between,
an honest user agent, and skip anything that blocks automated visitors (never work
around CAPTCHAs or bot checks).

Usage:
  python scripts/discover.py --out site/data/discovered.json [--prev URL_OR_PATH]
         [--states MN,WI,IA,ND,SD] [--minutes 5] [--workers 8] [--max-sites N]
"""
import argparse
import datetime as dt
import gzip
import hashlib
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.request
import urllib.robotparser
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scrape import clean, norm, page_amounts, parse_reqs  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOW = dt.datetime.now(dt.timezone.utc)
TODAY = NOW.date().isoformat()
UA = "BankBonusTracker/1.0 (finds checking bonuses on banks' own sites; +https://github.com/LukeOnopa/bank-bonus-tracking)"
FDIC = "https://api.fdic.gov/banks"
NCUA = "https://mapping.ncua.gov/api"
PILOT_STATES = ["MN", "WI", "IA", "ND", "SD"]
LIST_MAX_AGE_DAYS = 7      # refresh the institution list weekly
RECHECK_DAYS = 7           # recheck a site weekly...
RECHECK_FOUND_DAYS = 2     # ...or every 2 days if it had a bonus
PAGE_DELAY = 1.5           # seconds between requests to the same site
MAX_PAGES = 6              # promotion pages read per site
MAX_SITEMAP_URLS = 20000
TIMEOUT = 15

# words in a URL or link text that suggest a promotion page (weight)
URL_WORDS = [(r"bonus", 5), (r"promo", 4), (r"special[-_ ]?offer|offers?\b", 3), (r"switch", 3), (r"new[-_ ]?(?:account|customer|member)", 2),
             (r"open[-_ ]?(?:an?[-_ ]?)?account", 2), (r"checking", 2), (r"reward", 1), (r"cash", 1)]
# pages about other products; a bonus there isn't a checking bonus
NOT_CHECKING = r"\b(?:certificate|\bcds?\b|money market|savings account|credit card|business|commercial|mortgage|home equity|heloc|auto loan|refer(?:ral|-a-friend| a friend))\b"
SKIP_URL = re.compile(r"\.(?:pdf|jpe?g|png|gif|svg|zip|docx?|xlsx?|mp4)(?:$|\?)|/(?:careers?|jobs|investor|news|press|blog/page|login|sign-?in|privacy|terms)\b", re.I)

_print_lock = threading.Lock()


def log(*a):
    with _print_lock:
        print(*a, flush=True)


# ---------------- fetching ----------------
class Blocked(Exception):
    """The site refused automated visitors (403/429/CAPTCHA). Never retried within a run."""


def get(url, timeout=TIMEOUT, accept="text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.5", data=None, limit=4_000_000):
    headers = {"User-Agent": UA, "Accept": accept, "Accept-Language": "en-US"}
    if data is not None:
        data = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, headers=headers, data=data)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read(limit)
            if body[:2] == b"\x1f\x8b":
                body = gzip.decompress(body)
            return r.geturl(), body.decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        if e.code in (401, 403, 429, 503):
            raise Blocked(f"HTTP {e.code}") from None
        raise


def get_json(url, data=None, tries=6):
    for n in range(tries):  # the government APIs occasionally reset connections; back off and retry
        try:
            return json.loads(get(url, timeout=60, accept="application/json", data=data, limit=50_000_000)[1])
        except (urllib.error.URLError, ConnectionError, TimeoutError, Blocked):
            if n == tries - 1:
                raise
            time.sleep(2 * 2 ** n)


# FDIC lists some banks' corporate sites; their checking offers live on the consumer site
SITE_FIX = {"jpmorganchase.com": "https://www.chase.com", "citigroup.com": "https://www.citi.com", "citibank.com": "https://www.citi.com",
            "bankofamerica.com": "https://www.bankofamerica.com", "pnc.com": "https://www.pnc.com", "wellsfargo.com": "https://www.wellsfargo.com",
            "capitalone.com": "https://www.capitalone.com", "bmo.com": "https://www.bmo.com", "huntington.com": "https://www.huntington.com",
            "associatedbank.com": "https://www.associatedbank.com", "td.com": "https://www.td.com"}


def site_root(web):
    web = (web or "").strip().strip("/")
    if not web or " " in web:
        return None
    if not re.match(r"https?://", web, re.I):
        web = "https://" + web
    p = urlparse(web)
    if not p.hostname or "." not in p.hostname:
        return None
    host = p.hostname.lower()
    return SITE_FIX.get(host.removeprefix("www."), f"https://{host}")


# ---------------- institution list ----------------
def fdic_banks(states):
    """Banks with at least one branch in the states, with their website and branch states."""
    certs = {}
    for st in states:
        offset = 0
        while True:
            j = get_json(f"{FDIC}/locations?filters=STALP%3A{st}&fields=CERT,STALP&limit=10000&offset={offset}")
            for row in j["data"]:
                certs.setdefault(int(row["data"]["CERT"]), set()).add(st)
            offset += len(j["data"])
            if not j["data"] or offset >= j["meta"]["total"]:
                break
    out = []
    ids = sorted(certs)
    for i in range(0, len(ids), 100):
        q = "%20OR%20".join(str(c) for c in ids[i:i + 100])
        j = get_json(f"{FDIC}/institutions?filters=ACTIVE%3A1%20AND%20CERT%3A({q})&fields=NAME,WEBADDR,STALP,CITY,ASSET,CERT&limit=200")
        for row in j["data"]:
            d = row["data"]
            site = site_root(d.get("WEBADDR"))
            out.append({"id": f"fdic-{d['CERT']}", "name": clean(d["NAME"]), "kind": "bank", "site": site,
                        "hq": d.get("STALP"), "states": sorted(certs[int(d["CERT"])]), "assets": d.get("ASSET")})
    return out


def ncua_credit_unions(states, workers=3):
    """Active credit unions headquartered in the states, with their website."""
    found = []
    for st in states:
        skip = 0
        while True:
            j = get_json(f"{NCUA}/ResearchCreditUnion/GetDetailSearch", data={
                "cuName": None, "charterNumber": None, "region": None, "state": st, "city": None, "zipCode": None,
                "fomType": None, "lowIncome": None, "isMdi": None, "skip": skip, "take": 100})
            found += [r for r in j["results"] if r.get("isActive") and not r.get("isCorporate")]
            skip += 100
            if skip >= j["totalResultCount"]:
                break

    def detail(r):
        try:
            d = get_json(f"{NCUA}/CreditUnionDetails/GetCreditUnionDetails/{r['charterNumber']}")
        except Exception as e:  # one missing record shouldn't sink the list
            log(f"  NCUA detail failed for {r['charterNumber']}: {type(e).__name__}")
            return None
        return {"id": f"ncua-{r['charterNumber']}", "name": clean(d.get("creditUnionName") or r["name"]).title(), "kind": "cu",
                "site": site_root(d.get("creditUnionWebsite")), "hq": r["state"], "states": [r["state"]],
                "assets": int(d.get("creditUnionAssets") or 0) // 1000}

    with ThreadPoolExecutor(workers) as ex:
        return [x for x in ex.map(detail, found) if x]


def institutions(states, prev):
    p = prev.get("list") or {}
    age = (NOW - dt.datetime.fromisoformat(p["built"])).days if p.get("built") else 999
    if p.get("states") == states and age < LIST_MAX_AGE_DAYS and p.get("items") and not p.get("retry"):
        return p
    log(f"Building the institution list for {', '.join(states)}...")
    items, failed = [], []
    for name, kind, fn in (("FDIC", "bank", fdic_banks), ("NCUA", "cu", ncua_credit_unions)):
        try:
            got = fn(states)
            log(f"  {name}: {len(got)} institutions")
            items += got
        except Exception as e:
            log(f"  {name} failed: {type(e).__name__}: {e}")
            failed.append(name)
            keep = [i for i in p.get("items") or [] if i["kind"] == kind and p.get("states") == states]
            if keep:
                log(f"  keeping last list's {len(keep)} from {name}")
            items += keep
    # a failed source is retried on the next run instead of waiting a week
    return {"built": NOW.isoformat(timespec="seconds"), "states": states, "items": items, "retry": failed}


# ---------------- finding promotion pages ----------------
def url_score(url, text=""):
    s = (urlparse(url).path + " " + text).lower()
    score = sum(w for pat, w in URL_WORDS if re.search(pat, s))
    if re.search(r"\$\s?\d{2,4}", text):
        score += 3
    if re.search(NOT_CHECKING, s, re.I):
        score -= 4
    return score


def same_site(url, root):
    h, r = (urlparse(url).hostname or "").lower(), urlparse(root).hostname
    return h == r or h.removeprefix("www.") == r.removeprefix("www.") or h.endswith("." + r.removeprefix("www."))


def sitemap_urls(sitemaps, root, pause):
    urls, seen, queue = [], set(), list(sitemaps)
    while queue and len(seen) < 8 and len(urls) < MAX_SITEMAP_URLS:
        sm = queue.pop(0)
        if sm in seen:
            continue
        seen.add(sm)
        try:
            pause()
            _, xml = get(sm, accept="application/xml,text/xml,*/*")
        except Exception:
            continue
        locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", xml)
        if "<sitemapindex" in xml:  # an index of sitemaps: prefer ones that look like pages, not posts or images
            queue += sorted(locs, key=lambda u: (not re.search(r"page|product|checking|promo|offer", u, re.I), u))[:6]
        else:
            urls += [u.replace("&amp;", "&") for u in locs if same_site(u, root)]
    return urls


def candidates(root, robots, pause):
    """Likely promotion pages from the sitemaps and the homepage links, best first."""
    sitemaps = list(robots.site_maps() or []) or [root + "/sitemap.xml"]
    scored = {}
    for u in sitemap_urls(sitemaps, root, pause):
        s = url_score(u)
        if s >= 4 and not SKIP_URL.search(u):
            scored[u] = max(scored.get(u, 0), s)
    try:
        pause()
        final, html = get(root + "/")
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            u = urljoin(final, a["href"]).split("#")[0]
            if not u.startswith("http") or not same_site(u, root) or SKIP_URL.search(u):
                continue
            s = url_score(u, clean(a.get_text(" "))[:120])
            if s >= 4:
                scored[u] = max(scored.get(u, 0), s)
        home = (final, html)
    except Blocked:
        raise
    except Exception:
        home = None
    ranked = sorted(scored, key=lambda u: (-scored[u], len(u)))
    return [u for u in ranked if robots.can_fetch(UA, u)][:MAX_PAGES], home


# ---------------- reading a page ----------------
def plain(t):
    """Rewrite banks' wording into the roundup style parse_reqs reads: '$1,000 or more in direct deposits' -> '$1,000+ in direct deposits'."""
    t = re.sub(r"(\$[\d,]+)\s*(?:or more|or greater|minimum)\b", r"\1+", t, flags=re.I)
    t = re.sub(r"\b(?:at least|a minimum of|minimum of|totaling at least)\s+(\$[\d,]+)", r"\1+", t, flags=re.I)
    t = re.sub(r"(\$[\d,]+\+?)\s+(?:or more\s+)?in\s+(?:qualifying\s+|eligible\s+)?(?:electronic\s+)?direct\s+deposits?", r"\1 in direct deposits", t, flags=re.I)
    t = re.sub(r"\b(?:expired|ended|offer valid through)\b", "expires", t, flags=re.I)
    return t


def closest_product(text, a, b, reach=220):
    """'checking' or 'other': whichever product is named nearest the dollar amount (None if neither is close)."""
    lo = max(0, a - reach)
    best = None
    for kind, pat in (("checking", r"checking"), ("other", NOT_CHECKING)):
        for m in re.finditer(pat, text[lo: b + reach], re.I):
            pos = lo + m.start()
            d = a - pos if pos < a else pos - b
            if best is None or d < best[0]:
                best = (d, kind)
    return best and best[1]


def extract(url, html):
    """Checking-bonus offers stated on a page. Returns (finds, status)."""
    text, amts, strong = page_amounts(html)
    if len(text) < 400:
        return [], "needs-browser"
    finds = []
    for m in re.finditer(r"\$\s?([\d,]{2,6})(?![\d,]*%)", text):
        amt = int(m[1].replace(",", ""))
        if amt not in strong or not 100 <= amt <= 3000:
            continue
        win = text[max(0, m.start() - 400): m.end() + 600]
        near = text[max(0, m.start() - 160): m.end() + 160]
        if closest_product(text, m.start(), m.end()) != "checking":
            continue
        if re.search(r"\b(?:apy|interest rate|cash back on|per referral|for each friend)\b", near, re.I):
            continue
        req = parse_reqs(plain(win))
        conf = 1 + bool(req.get("dd") or req.get("tx")) + bool(req.get("win")) + bool(re.search(r"new (?:checking )?(?:account|customer|member)|open a", win, re.I))
        if req.get("exp") and req["exp"] < TODAY:
            continue
        finds.append({"amt": amt, "url": url, "conf": "high" if conf >= 3 else "medium" if conf == 2 else "low",
                      "snippet": clean(near)[:240], **{k: v for k, v in req.items() if k in ("dd", "mindd", "mdd", "win", "tx", "exp", "fee")}})
    best = {}
    for f in finds:  # one find per amount, keep the most detailed
        k = f["amt"]
        if k not in best or len(f) > len(best[k]):
            best[k] = f
    return sorted(best.values(), key=lambda f: -f["amt"])[:3], "ok"


def read_robots(root, pause):
    rp = urllib.robotparser.RobotFileParser()
    try:
        pause()
        _, txt = get(root + "/robots.txt", accept="text/plain,*/*", limit=500_000)
        rp.parse(txt.splitlines())
    except Blocked:
        raise
    except Exception:
        rp.parse([])  # no robots.txt: everything allowed
    return rp


def crawl_site(inst, prev_site, deadline):
    root = inst.get("site")
    rec = {"checked": NOW.isoformat(timespec="seconds"), "pages": {}}
    if not root:
        return dict(rec, status="no-website")
    last = [0.0]

    def pause():
        wait = last[0] + PAGE_DELAY - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        last[0] = time.monotonic()
        if time.monotonic() > deadline + 60:
            raise TimeoutError("run time budget used up")

    try:
        robots = read_robots(root, pause)
        if not robots.can_fetch(UA, root + "/"):
            return dict(rec, status="robots-disallowed")
        urls, home = candidates(root, robots, pause)
        finds, statuses = [], []
        old_pages = (prev_site or {}).get("pages", {})
        for u in urls:
            try:
                pause()
                final, html = (home if home and u.rstrip("/") == home[0].rstrip("/") else get(u))
            except Blocked:
                raise
            except TimeoutError:
                raise
            except Exception as e:
                statuses.append("error")
                rec["pages"][u] = {"status": f"error: {type(e).__name__}"}
                continue
            if not same_site(final, root):
                continue
            h = hashlib.sha1(clean(BeautifulSoup(html, "html.parser").get_text(" ")).encode()).hexdigest()[:12]
            got, st = extract(final, html)
            statuses.append(st)
            rec["pages"][u] = {"status": st, "hash": h, "changed": TODAY if old_pages.get(u, {}).get("hash") != h else old_pages[u].get("changed", TODAY)}
            finds += got
        best = {}
        for f in finds:  # the same offer often appears on several pages; keep the most detailed copy
            if f["amt"] not in best or (len(f), f["conf"] == "high") > (len(best[f["amt"]]), best[f["amt"]]["conf"] == "high"):
                best[f["amt"]] = f
        rec["finds"] = sorted(best.values(), key=lambda f: -f["amt"])
        rec["status"] = "found" if finds else "no-pages" if not urls else "needs-browser" if statuses and all(s == "needs-browser" for s in statuses) else "no-bonus"
        return rec
    except Blocked as e:
        return dict(rec, status="blocked", why=str(e))
    except TimeoutError:
        return None  # out of time; try again next run
    except Exception as e:
        return dict(rec, status="error", why=f"{type(e).__name__}: {e}"[:120])


def due(inst, site):
    if not site or not site.get("checked"):
        return True
    age = (NOW - dt.datetime.fromisoformat(site["checked"])).total_seconds() / 86400
    return age >= (RECHECK_FOUND_DAYS if site.get("finds") else RECHECK_DAYS)


# ---------------- run ----------------
def load_prev(src):
    if not src:
        return {}
    try:
        if re.match(r"https?://", src):
            return json.loads(get(src, accept="application/json", limit=50_000_000)[1])
        with open(src) as f:
            return json.load(f)
    except Exception as e:
        log(f"No previous results ({type(e).__name__}); starting fresh.")
        return {}


def known_banks():
    try:
        with open(os.path.join(ROOT, "data", "curated.json")) as f:
            return {norm(o["b"]) for o in json.load(f)}
    except Exception:
        return set()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default=os.path.join(ROOT, "site", "data", "discovered.json"))
    ap.add_argument("--prev", default=None, help="previous discovered.json (URL or path)")
    ap.add_argument("--states", default=",".join(PILOT_STATES))
    ap.add_argument("--minutes", type=float, default=5, help="time budget for crawling")
    ap.add_argument("--workers", type=int, default=8, help="sites crawled at once (each site is still one request at a time)")
    ap.add_argument("--max-sites", type=int, default=0, help="crawl at most this many sites (0 = as many as fit in the time)")
    a = ap.parse_args(argv)
    states = sorted({s.strip().upper() for s in a.states.split(",") if s.strip()})
    start = time.monotonic()
    deadline = start + a.minutes * 60

    prev = load_prev(a.prev)
    lst = institutions(states, prev)
    sites = {k: v for k, v in (prev.get("sites") or {}).items()}
    items = lst["items"]
    todo = sorted((i for i in items if due(i, sites.get(i["id"]))), key=lambda i: (sites.get(i["id"], {}).get("checked", ""), -(i.get("assets") or 0)))
    if a.max_sites:
        todo = todo[:a.max_sites]
    log(f"{len(items)} institutions; {len(todo)} due for a check; crawling for up to {a.minutes:g} min with {a.workers} at a time.")

    done = 0
    with ThreadPoolExecutor(a.workers) as ex:
        it = iter(todo)
        running = {}
        while True:
            while len(running) < a.workers and time.monotonic() < deadline:
                inst = next(it, None)
                if inst is None:
                    break
                running[ex.submit(crawl_site, inst, sites.get(inst["id"]), deadline)] = inst
            if not running:
                break
            fut = next(as_completed(running))
            inst = running.pop(fut)
            rec = fut.result()
            if rec is None:
                continue
            sites[inst["id"]] = rec
            done += 1
            tag = f"{len(rec.get('finds') or [])} bonus(es)" if rec["status"] == "found" else rec["status"]
            log(f"  {inst['name'][:40]:40} {inst.get('site') or '-':45} {tag}")

    known = known_banks()
    by_id = {i["id"]: i for i in items}
    finds = []
    for iid, s in sites.items():
        inst = by_id.get(iid)
        if not inst:
            continue
        for f in s.get("finds") or []:
            finds.append({"inst": iid, "bank": inst["name"], "kind": inst["kind"], "states": inst["states"], "site": inst["site"],
                          "known": norm(inst["name"]) in known, "checked": s["checked"][:10], **f})
    finds.sort(key=lambda f: (f["known"], {"high": 0, "medium": 1, "low": 2}[f["conf"]], -f["amt"]))
    counts = {}
    for s in sites.values():
        counts[s.get("status", "?")] = counts.get(s.get("status", "?"), 0) + 1
    out = {"generated": NOW.isoformat(timespec="seconds"), "states": states, "unverified": True,
           "note": "Found automatically on banks' own websites. Not checked by a person; confirm on the bank's page before applying.",
           "summary": {"institutions": len(items), "checked": len(sites), "crawled_this_run": done, "status": counts,
                       "finds": len(finds), "new_banks": len({f["inst"] for f in finds if not f["known"]})},
           "finds": finds, "list": lst, "sites": sites}
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w") as f:
        json.dump(out, f, separators=(",", ":"))
    log(f"Crawled {done} sites in {(time.monotonic() - start) / 60:.1f} min. "
        f"{len(sites)}/{len(items)} checked so far. Status: {counts}. Bonuses found: {len(finds)} "
        f"({out['summary']['new_banks']} banks not in the curated list).")
    for f in finds[:25]:
        log(f"  {'NEW ' if not f['known'] else '    '}{f['conf']:6} ${f['amt']:<5} {f['bank'][:36]:36} dd={f.get('dd', '-')} win={f.get('win', '-')} {f['url']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
