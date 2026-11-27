#!/usr/bin/env python3
"""Refresh checking-bonus offers from public bonus roundup pages.

Reads data/curated.json (hand-researched offers with states, churn rules, etc.),
scrapes Doctor of Credit's "Best Bank Account Bonuses" page and Fat Stacks
Academy's checking-bonus list, merges them, and writes site/data/offers.json.

Design rules:
- Never wipe good data because a site was down or changed its layout: if a source
  fails or parses suspiciously few offers, it is ignored for this run and offers keep
  their previous "last seen" dates.
- Curated details win; scraped data only updates the bonus amount, adds missing
  churn/expiry info, records when an offer was last listed, and adds new offers.
"""
import datetime as dt
import json
import os
import re
import shutil
import sys
import urllib.request

from bs4 import BeautifulSoup

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TODAY = dt.date.today().isoformat()
NOW = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
UA = "BankBonusTracker/1.0 (personal bonus tracker; +https://github.com/LukeOnopa/bank-bonus-tracking)"
STATES = set("AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY".split())
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
DOC_URL = "https://www.doctorofcredit.com/best-bank-account-bonuses/"
FS_URLS = [f"https://www.fatstacksacademy.com/blog/best-checking-bonuses-{y}" for y in (dt.date.today().year, dt.date.today().year - 1)]
MIN_DOC, MIN_FS = 5, 20  # fewer parsed offers than this = treat source as broken


def fetch(url, timeout=40):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def clean(s):
    return re.sub(r"\s+", " ", (s or "").replace("–", "-").replace("—", "-").replace("\xa0", " ")).strip()


ALIASES = {"charlesschwab": "schwab", "citibank": "citi", "bmoharris": "bmo", "usbancorp": "us", "verveacu": "verve", "vervecu": "verve",
           "fourleaffcu": "fourleaf", "bethpagefcu": "fourleaf", "53": "fifththird", "pncvirtualwallet": "pnc", "keybanknationalassociation": "key", "keybank": "key"}


def norm(name):
    s = clean(name).lower()
    s = re.sub(r"\(.*?\)|\[.*?\]", " ", s).replace("&", " and ")
    s = s.replace("federal credit union", " fcu ").replace("credit union", " cu ")
    s = re.sub(r"\b(the|bank|n\.?a\.?|national association|financial|group|a|inc|of america)\b", " ", s) if not s.startswith("bank of") else re.sub(r"\b(the|n\.?a\.?)\b", " ", s)
    s = re.sub(r"[^a-z0-9]", "", s)
    return ALIASES.get(s, s)


def money_vals(s):
    return [int(m.replace(",", "")) for m in re.findall(r"\$\s?([\d,]{2,7})(?![\d,]*%)", s)]


def parse_date(s):
    m = re.search(r"\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b", s)
    if m:
        y = int(m[3]); y = y + 2000 if y < 100 else y
        return f"{y:04d}-{int(m[1]):02d}-{int(m[2]):02d}"
    m = re.search(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2}),?\s+(\d{4})", s, re.I)
    if m:
        return f"{int(m[3]):04d}-{MONTHS[m[1].lower()]:02d}-{int(m[2]):02d}"
    return None


def parse_reqs(text):
    """Pull structured requirements out of free text."""
    t = clean(text)
    out = {}
    if re.search(r"no (?:direct deposit|dd) (?:is )?required|direct deposit (?:is )?not required|\bno dd\b", t, re.I):
        out["dd"] = 0
    else:
        m = re.search(r"\$([\d,]+)\s*(?:-|to|–)\s*\$([\d,]+)\+?\s*(?:in |of )?(?:total |qualifying |eligible )?(?:direct deposits?|dd)", t, re.I)
        if m:
            out["mindd"], out["dd"] = int(m[1].replace(",", "")), int(m[2].replace(",", ""))
        else:
            m = re.search(r"(?:direct deposits? (?:of|totaling|totalling) |dd of )\$([\d,]+)|\$([\d,]+)\+?\s*(?:/mo(?:nth)?\s*)?(?:in |of )?(?:total |qualifying |eligible |recurring )?(?:direct deposits?|dd)\b", t, re.I)
            if m:
                out["dd"] = int((m[1] or m[2]).replace(",", ""))
                k = re.search(r"\b(\d|two|three|four)\s+(?:qualifying\s+|separate\s+)?direct deposits?\s+of\s+\$" + re.escape(m[1] or m[2]), t, re.I)
                if k:
                    out["dd"] *= {"two": 2, "three": 3, "four": 4}.get(k[1].lower(), None) or int(k[1])
                if re.search(r"\$[\d,]+\+?\s*/mo(?:nth)?", m[0]) or re.match(r"\s*(?:per|each|a|every)\s+month|\s*monthly", t[m.end():m.end() + 20], re.I):
                    out["mdd"] = out["dd"]
            elif re.search(r"direct deposit|\bdd\b", t, re.I):
                out["dd"] = 1  # some DD required, amount unknown
    m = re.search(r"(?:within|in|first)\s+(\d{2,3})\s+days", t, re.I)
    if m:
        out["win"] = int(m[1])
    m = re.search(r"(\d{1,3})\+?\s+(?:qualifying\s+|debit(?:\s+card)?\s+)?(?:purchases|transactions|tx)\b", t, re.I)
    if m:
        out["tx"] = int(m[1])
    m = re.search(r"(\d{1,2})\s*-?\s*mo(?:nth)?s?\s*(?:cooldown|anti-churn)", t, re.I) or re.search(r"once every (\d{1,2}) months", t, re.I)
    if m:
        out["cd"] = int(m[1])
    elif re.search(r"once every (two|2) years|24 months", t, re.I):
        out["cd"] = 24
    m = re.search(r"\$(\d+(?:\.\d\d)?)\s*(?:/mo|monthly|per month)\s*(?:fee)?", t, re.I)
    if m:
        out["fee"] = "None" if float(m[1]) == 0 else f"${m[1]}"
    if re.search(r"hard pull", t, re.I):
        out["pull"] = "hard"
    elif re.search(r"soft pull", t, re.I):
        out["pull"] = "soft"
    m = re.search(r"(?:expires?|valid (?:through|until)|ends?|through|until|by)\s+((?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4}|\d{1,2}/\d{1,2}/\d{2,4})", t, re.I)
    if m:
        out["exp"] = parse_date(m[1])
    return out


def states_in(text):
    return sorted({s for s in re.findall(r"\b([A-Z]{2})\b", text) if s in STATES})


# ---------------- Doctor of Credit ----------------
def parse_doc(html):
    soup = BeautifulSoup(html, "html.parser")
    body = soup.select_one(".entry-content, article, main") or soup
    offers, section = [], ""
    for el in body.find_all(["h2", "h3"]):
        txt = clean(el.get_text(" "))
        if el.name == "h2":
            section = txt.lower()
            continue
        if not any(k in section for k in ("checking", "state specific", "region specific", "branch specific")):
            continue
        if re.search(r"\bbusiness\b|\bbrokerage\b|\bIRA\b|\bCD\b|credit card", txt, re.I):
            continue
        if re.search(r"savings", txt, re.I) and not re.search(r"checking", txt, re.I):
            continue
        amts = money_vals(txt)
        if not amts:
            continue
        dash = re.search(r"\s-\s", txt)
        head, tail = (txt[:dash.start()], txt[dash.end():]) if dash else (txt, "")
        name = clean(re.split(r"\$|\bup to\b", re.sub(r"^\[[^\]]*\]\s*", "", head), flags=re.I)[0])
        if len(name) < 2:
            continue
        # collect body until next heading
        parts, links = [], {}
        for sib in el.next_siblings:
            if getattr(sib, "name", None) in ("h2", "h3"):
                break
            if getattr(sib, "find_all", None):
                parts.append(sib.get_text(" "))
                for a in sib.find_all("a", href=True):
                    lt = clean(a.get_text()).lower()
                    if "direct link" in lt and "direct" not in links:
                        links["direct"] = a["href"]
                    elif "full post" in lt and "post" not in links:
                        links["post"] = a["href"]
            elif isinstance(sib, str):
                parts.append(sib)
        bodytxt = clean(" ".join(parts))
        st = states_in(tail) or states_in(re.findall(r"^\[([^\]]+)\]", txt)[0] if txt.startswith("[") else "")
        o = {"b": name, "amt": max(amts), "src": "doc", "heading": txt,
             "st": st if st else ("ALL" if "checking" in section and "state" not in section else "?"),
             "req": bodytxt[:240], "url": next((u for u in (links.get("direct"), links.get("post")) if u and u.startswith("https://")), DOC_URL)}
        o.update(parse_reqs(bodytxt))
        if re.search(r"in branch", txt, re.I):
            o["branch"] = 1
        offers.append(o)
    return offers


# ---------------- Fat Stacks ----------------
FS_HEAD = re.compile(r"^(?:#?\d{1,3}\.?\s+)?(?P<name>[A-Za-z0-9][^$|]{1,80}?)\s*\$\s*(?P<amt>[\d,]{2,7})\+?(?:\s+top pick)?$", re.I)


def parse_fs(html):
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style", "nav", "footer", "header"]):
        t.decompose()
    cands = []
    for el in soup.find_all(True):
        txt = clean(el.get_text(" "))
        if len(txt) > 110 or not FS_HEAD.match(txt):
            continue
        cands.append(el)
    # keep only the deepest matching elements
    cset = set(map(id, cands))
    heads = [e for e in cands if not any(id(d) in cset for d in e.find_all(True))]
    hset = set(map(id, heads))
    offers, seen = [], set()
    for h in heads:
        m = FS_HEAD.match(clean(h.get_text(" ")))
        name = clean(re.sub(r"^\d{1,3}\s+", "", m["name"]))
        if re.fullmatch(r"(top|best|up to|earn|get|bonus|total).*", name, re.I):
            continue
        parts, link = [], None
        for nxt in h.next_elements:
            if getattr(nxt, "name", None) and id(nxt) in hset:
                break
            if isinstance(nxt, str):
                parts.append(nxt)
            elif getattr(nxt, "name", None) == "a" and not link and "/blog/" in (nxt.get("href") or ""):
                link = nxt["href"]
            if sum(map(len, parts)) > 900:
                break
        bodytxt = clean(" ".join(parts))
        if re.search(r"business (?:checking|account)|\(business\)", bodytxt[:300] + name, re.I):
            continue
        if re.search(r"no longer available|expired|offer (?:has )?ended", bodytxt[:400], re.I):
            continue
        key = (norm(name), m["amt"])
        if key in seen:
            continue
        seen.add(key)
        if link and link.startswith("/"):
            link = "https://www.fatstacksacademy.com" + link
        o = {"b": name, "amt": int(m["amt"].replace(",", "")), "src": "fs", "req": bodytxt[:240],
             "url": link if (link or "").startswith("https://") else FS_URLS[0], "st": "?"}
        o.update(parse_reqs(bodytxt))
        offers.append(o)
    return offers


# ---------------- merge ----------------
def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:40]


def merge(curated, scraped, prev, ok_sources):
    prev_by_id = {o["id"]: o for o in prev}
    by_norm = {}
    for c in curated:
        by_norm.setdefault(norm(c["b"]), []).append(c)
    used, out = set(), []
    groups = {}
    for i, s in enumerate(scraped):
        n = norm(s["b"])
        key = n if n in by_norm else next((k for k in by_norm if len(min(k, n, key=len)) >= 5 and (k.startswith(n) or n.startswith(k))), None)
        if key:
            groups.setdefault(key, []).append(s)
            used.add(i)
    for c in curated:
        o = dict(c)
        p = prev_by_id.get(o["id"], {})
        o["seen"], o["first"] = p.get("seen"), p.get("first", TODAY)
        for k in ("changed", "prevAmt"):
            if k in p:
                o[k] = p[k]
        n = norm(c["b"])
        hits = groups.get(n, [])
        if hits:
            o["seen"] = TODAY
            o["srcs"] = sorted({h["src"] for h in hits})
            siblings = by_norm.get(n, [])
            if len(siblings) == 1:
                doc = [h for h in hits if h["src"] == "doc"]
                new_amt = (doc or hits)[0]["amt"]
                old_amt = p.get("amt", c["amt"])
                if new_amt != old_amt and 25 <= new_amt <= 5000:
                    o["prevAmt"], o["changed"] = old_amt, TODAY
                o["amt"] = new_amt if 25 <= new_amt <= 5000 else c["amt"]
            for h in hits:
                if o.get("cd") is None and h.get("cd"):
                    o["cd"], o["cdSrc"] = h["cd"], h["src"]
                if not o.get("exp") and h.get("exp") and h["exp"] >= TODAY:
                    o["exp"] = h["exp"]
                if h["src"] == "doc" and h.get("url", "").startswith("https://") and h["url"] != DOC_URL:
                    o["offerUrl"] = h["url"]
        out.append(o)
    # brand-new offers
    autos = {}
    for i, s in enumerate(scraped):
        if i in used or not (25 <= s["amt"] <= 5000):
            continue
        k = (norm(s["b"]), s["amt"])
        a = autos.get(k)
        if a:  # same offer on both sites: prefer DoC states, fill gaps from Fat Stacks
            for f in ("dd", "mindd", "mdd", "win", "tx", "cd", "fee", "pull", "exp"):
                if a.get(f) is None and s.get(f) is not None:
                    a[f] = s[f]
            if a["st"] == "?" and s["st"] != "?":
                a["st"] = s["st"]
            a["srcs"] = sorted(set(a["srcs"]) | {s["src"]})
            continue
        b = s["b"]
        t = "cu" if re.search(r"credit union|\bfcu\b|\bcu\b", b, re.I) else "fin" if re.search(r"chime|current|varo|percapita|money\b", b, re.I) else "bank"
        autos[k] = {"id": "auto-" + slug(b) + "-" + str(s["amt"]), "b": b, "a": "Checking", "t": t, "amt": s["amt"],
                    "dd": s.get("dd"), "mindd": s.get("mindd"), "mdd": s.get("mdd"), "win": s.get("win", 90), "tx": s.get("tx"),
                    "keep": None, "cd": s.get("cd"), "st": s["st"], "pull": s.get("pull", "?"), "fee": s.get("fee", "See terms"),
                    "exp": s.get("exp") if (s.get("exp") or "") >= TODAY else None, "req": s.get("req", ""), "url": s.get("url"),
                    "auto": 1, "srcs": [s["src"]], "seen": TODAY}
    for a in autos.values():
        a = {k: v for k, v in a.items() if v is not None or k in ("keep", "cd")}
        a["first"] = prev_by_id.get(a["id"], {}).get("first", TODAY)
        out.append(a)
    # keep recently seen auto offers that a source missed this run (or whose source failed)
    have = {o["id"] for o in out}
    for p in prev:
        if p.get("auto") and p["id"] not in have and p.get("seen"):
            age = (dt.date.today() - dt.date.fromisoformat(p["seen"])).days
            if age <= 14:
                out.append(p)
    return out


def main():
    curated = json.load(open(os.path.join(ROOT, "data", "curated.json")))
    prev, prev_meta = [], {}
    pages = os.environ.get("PAGES_URL", "").rstrip("/")
    if pages:
        try:
            pj = json.loads(fetch(pages + "/data/offers.json", 20))
            prev, prev_meta = pj.get("offers", []), pj
        except Exception as e:
            print("No previous offers.json:", e)
    sources, scraped = [], []
    for name, urls, parser, minimum in (("Doctor of Credit", [DOC_URL], parse_doc, MIN_DOC), ("Fat Stacks Academy", FS_URLS, parse_fs, MIN_FS)):
        rec = {"name": name, "ok": False, "count": 0, "url": urls[0]}
        for url in urls:
            try:
                got = parser(fetch(url))
                rec.update(url=url, count=len(got))
                if len(got) >= minimum:
                    rec["ok"] = True
                    scraped += got
                    break
                rec["error"] = f"Only {len(got)} offers parsed — page layout may have changed"
            except Exception as e:
                rec["error"] = f"{type(e).__name__}: {e}"[:200]
        if rec["ok"]:
            rec["lastOk"] = NOW
        else:
            old = next((s for s in prev_meta.get("sources", []) if s.get("name") == name), {})
            if old.get("lastOk"):
                rec["lastOk"] = old["lastOk"]
        sources.append(rec)
        print(name, rec)
    ok = [s["name"] for s in sources if s["ok"]]
    if not ok and prev:
        offers = prev  # every source failed: republish last good data untouched
    else:
        offers = merge(curated, scraped, prev, ok)
    data = {"generated": NOW, "sources": sources, "offers": offers,
            "unmatched": sorted({s["heading"] if s.get("heading") else s["b"] for s in scraped})[:400]}
    site = os.path.join(ROOT, "site")
    shutil.rmtree(site, ignore_errors=True)
    os.makedirs(os.path.join(site, "data"))
    shutil.copy(os.path.join(ROOT, "index.html"), site)
    with open(os.path.join(site, "data", "offers.json"), "w") as f:
        json.dump(data, f, separators=(",", ":"))
    print(f"Wrote {len(offers)} offers ({sum(1 for o in offers if o.get('auto'))} auto-added); sources ok: {ok or 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
