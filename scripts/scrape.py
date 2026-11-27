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
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from locate import locate  # noqa: E402

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


ALIASES = {"charlesschwab": "schwab", "citibank": "citi", "bmoharris": "bmo", "usbancorp": "us", "verve": "verve",
           "bethpage": "fourleaf", "53": "fifththird", "pncvirtualwallet": "pnc", "keybank": "key", "keybanknational": "key",
           "capitalone360": "capitalone", "secumaryland": "secu", "trustonefinancial": "trustone", "chaseprivateclient": "chase",
           "huntingtonnational": "huntington", "wellsfargobank": "wellsfargo", "td": "td", "tdbank": "td", "citizensbank": "citizens"}
GENERIC = r"\b(the|banks?|n\.?a\.?|national association|financial|group|company|co|inc|corp|federal credit union|credit union|fcu|cu|federal|" \
          r"checking|savings|account|accounts|bonus|bonuses|and|a|by|personal|online|new)\b"


def norm(name):
    """Reduce a bank name to a matching key: 'Navy Federal Credit Union' and 'Navy Federal CU' -> 'navy'."""
    s = clean(name).lower()
    s = re.sub(r"\(.*?\)|\[.*?\]", " ", s).replace("&", " and ")
    s = re.sub(r"\bbank of\b", "bankof", s)  # keep 'Bank of America' distinct from 'America First'
    s = re.sub(GENERIC, " ", s)
    s = re.sub(r"[^a-z0-9]", "", s)
    return ALIASES.get(s, s)


def clean_name(name):
    n = re.sub(r"^\[[^\]]*\]\s*", "", clean(name))
    while True:  # strip trailing state codes like "VA, WV, OH" (but not "CU")
        m = re.search(r"[\s,&]+(?:and\s+)?\b([A-Z]{2})\s*$", n)
        if not m or m[1] not in STATES:
            break
        n = n[:m.start()]
    n = re.sub(r"\s*[-–:,]\s*$", "", n)
    n = re.sub(r"\s+(?:checking|savings)?\s*(?:bonus|offer)?\s*$", "", n, flags=re.I).strip()
    return n


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
        if re.search(r"youth|student|college|teen|kids|minor", txt, re.I) and not re.search(r"adult", txt, re.I):
            continue
        name = clean_name(re.split(r"\$|\bup to\b", re.sub(r"^\[[^\]]*\]\s*", "", head), flags=re.I)[0])
        if len(name) < 2:
            continue
        # collect body until next heading
        parts, links = [], {}
        for sib in el.next_siblings:
            if getattr(sib, "name", None) in ("h2", "h3", "h4") or (getattr(sib, "find_all", None) and sib.find(["h2", "h3", "h4"])):
                break
            if getattr(sib, "find_all", None):
                parts.append(sib.get_text(" "))
                for a in sib.find_all("a", href=True):
                    lt = clean(a.get_text()).lower()
                    if "direct link" in lt and "direct" not in links and link_matches_bank(name or txt, a["href"]):
                        links["direct"] = a["href"]
                    elif "full post" in lt and "post" not in links:
                        links["post"] = a["href"]
            elif isinstance(sib, str):
                parts.append(sib)
        bodytxt = clean(" ".join(parts))
        st = states_in(txt[txt.index("$"):] if "$" in txt else tail) or states_in(re.findall(r"^\[([^\]]+)\]", txt)[0] if txt.startswith("[") else "")
        o = {"b": name, "amt": max(amts), "src": "doc", "heading": txt,
             "st": st if st else ("ALL" if "checking" in section and "state" not in section else "?"),
             "req": bodytxt[:240], "url": next((u for u in (links.get("direct"), links.get("post")) if u and u.startswith("https://")), DOC_URL)}
        post = links.get("post") or ""
        o["srcUrl"] = post if post.startswith("https://") and article_about_bank(name, post) else DOC_URL
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
        name = clean_name(re.sub(r"^\d{1,3}\s+", "", m["name"]))
        if re.search(r"youth|student|college|teen|kids", name, re.I):
            continue
        if re.fullmatch(r"(top|best|up to|earn|get|bonus|total).*", name, re.I):
            continue
        # the offer's own card = the largest ancestor that contains no other offer heading
        card = h
        while card.parent is not None and not any(id(x) in hset for x in card.parent.find_all(True) if x is not h):
            card = card.parent
        link = next((a["href"] for a in ([p for p in h.parents if p.name == "a" and p.get("href")] + card.find_all("a", href=True))
                     if "/blog/" in a.get("href", "")), None)
        parts = []
        for nxt in h.next_elements:
            if getattr(nxt, "name", None) and id(nxt) in hset:
                break
            if isinstance(nxt, str) and h not in nxt.parents:
                parts.append(nxt)
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


# ---------------- link + amount verification ----------------
THIRD_PARTY = ("doctorofcredit.com", "fatstacksacademy.com", "thebonusstack.com", "reddit.com", "bit.ly", "tinyurl.com")
NAME_STOP = {"bank", "banks", "credit", "union", "federal", "the", "and", "of", "na", "fcu", "cu", "financial", "community", "national",
             "trust", "savings", "first", "checking", "account", "company", "group", "state", "city", "american", "america"}
KNOWN_DOMAINS = {"chase": ["chase.com"], "bankofamerica": ["bankofamerica.com", "bofa.com"], "us": ["usbank.com"], "citi": ["citi.com", "citibank.com"],
                 "wellsfargo": ["wellsfargo.com", "wf.com"], "key": ["key.com"], "fifththird": ["53.com"], "td": ["td.com", "tdbank.com"],
                 "navy": ["navyfederal.org"], "bmo": ["bmo.com"], "pnc": ["pnc.com"], "schwab": ["schwab.com"], "capitalone": ["capitalone.com"],
                 "hsbc": ["hsbc.com", "us.hsbc.com"], "truist": ["truist.com"], "regions": ["regions.com"], "citizens": ["citizensbank.com"],
                 "huntington": ["huntington.com"], "sofi": ["sofi.com"], "fourleaf": ["fourleaffcu.org"], "bok": ["bokfinancial.com"]}


def host_of(url):
    try:
        return (urlparse(url).hostname or "").lower().removeprefix("www.")
    except ValueError:
        return ""


def link_matches_bank(bank, url):
    """True if url is on the bank's own website (not a blog, not another bank)."""
    host = host_of(url)
    if not host or not url.startswith("https://") or any(host == d or host.endswith("." + d) for d in THIRD_PARTY):
        return False
    n = norm(bank)
    if n in KNOWN_DOMAINS:
        return any(host == d or host.endswith("." + d) for d in KNOWN_DOMAINS[n])
    labels = re.sub(r"[^a-z0-9.]", "", host).split(".")[:-1]  # drop TLD
    site = "".join(labels)
    words = [w for w in re.findall(r"[a-z0-9]+", clean(bank).lower()) if w not in NAME_STOP]
    if any(len(w) >= 4 and w in site for w in words):
        return True
    if n and len(n) >= 4:
        for lbl in labels:
            rest = lbl.replace(n, "", 1) if n in lbl else None
            if rest is not None and (len(n) >= 8 or rest in ("", "bank", "cu", "fcu", "online", "banking", "creditunion", "fed", "federal", "financial")):
                return True
            if len(lbl) >= 5 and lbl in n:
                return True
    initials = "".join(w[0] for w in re.findall(r"[a-z0-9]+", re.sub(r"\(.*?\)", "", clean(bank).lower())) if w not in ("the", "of", "and", "a"))
    return len(initials) >= 3 and any(lbl.startswith(initials) for lbl in labels)


def article_about_bank(bank, url):
    """True if a blog post URL's slug mentions this bank (catches a neighbouring offer's 'full post' link)."""
    path = re.sub(r"[^a-z0-9]", "", urlparse(url).path.lower())
    words = [w for w in re.findall(r"[a-z0-9]+", clean(bank).lower()) if w not in NAME_STOP and len(w) >= 3]
    n = norm(bank)
    return bool((n and len(n) >= 3 and n in path) or any(w in path for w in words))


def page_amounts(html):
    """Dollar amounts the page ties to a bonus/reward/offer."""
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style", "noscript", "svg"]):
        t.decompose()
    text = clean(soup.get_text(" "))
    amts, strong = set(), set()
    for m in re.finditer(r"\$\s?([\d,]{2,6})(?![\d,]*%)", text):
        v = int(m[1].replace(",", ""))
        if not 25 <= v <= 5000:
            continue
        if re.search(r"bonus|reward|earn|get \$|offer|promotion|cash", text[max(0, m.start() - 120): m.end() + 120].lower()):
            amts.add(v)
        if re.search(r"bonus", text[max(0, m.start() - 60): m.end() + 60].lower()):
            strong.add(v)
    return text, sorted(amts), sorted(strong)


def check_one(o):
    url = o.get("offerUrl")  # only real offer pages; a homepage shows unrelated amounts
    rec = {"on": TODAY, "url": url}
    if not url:
        return dict(rec, status="no-link")
    if not link_matches_bank(o["b"], url):
        return dict(rec, status="bad-link")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; BankBonusTracker/1.0; +https://github.com/LukeOnopa/bank-bonus-tracking)",
                                                   "Accept": "text/html", "Accept-Language": "en-US"})
        with urllib.request.urlopen(req, timeout=15) as r:
            final = r.geturl()
            html = r.read(3_000_000).decode("utf-8", "replace")
    except Exception as e:
        return dict(rec, status="unreadable", why=f"{type(e).__name__}"[:60])
    if not link_matches_bank(o["b"], final):
        return dict(rec, status="bad-link", why="redirected to " + host_of(final))
    text, amts, strong = page_amounts(html)
    if len(text) < 400:
        return dict(rec, status="unreadable", why="page needs a browser")
    rec["amts"] = amts[:8]
    if o["amt"] in amts or f"${o['amt']:,}" in text or f"${o['amt']}" in text:
        return dict(rec, status="confirmed")
    if [a for a in strong if a >= 100]:  # only call it a mismatch when the page ties a real amount to "bonus"
        return dict(rec, status="differs", amts=[a for a in strong if a >= 100][:8])
    return dict(rec, status="no-amount")


def verify(offers, prev, budget=40, max_age_days=1):
    """Re-check the oldest/never-checked offer links each run (polite: a few dozen pages an hour)."""
    prev_chk = {o["id"]: o.get("check") for o in prev if o.get("check")}
    prev_chk.update({"bank:" + norm(o["b"]): o.get("check") for o in prev if o.get("check")})
    due = []
    for o in offers:
        old = prev_chk.get(o["id"]) or prev_chk.get("bank:" + norm(o["b"]))
        url_now = o.get("offerUrl")
        if old and old.get("url") == url_now:
            o["check"] = old
            age = (dt.date.today() - dt.date.fromisoformat(old["on"])).days
            if age < max_age_days:
                continue
        due.append(o)
    due.sort(key=lambda o: (o.get("check") or {}).get("on", ""))
    due = due[:budget]
    with ThreadPoolExecutor(8) as ex:
        for o, rec in zip(due, ex.map(check_one, due)):
            o["check"] = rec
    for o in offers:  # never show a link we know is wrong
        c = o.get("check") or {}
        if c.get("status") == "bad-link" and c.get("url") == o.get("offerUrl"):
            o.pop("offerUrl", None)
        if c.get("status") == "bad-link" and o.get("auto") and c.get("url") == o.get("url"):
            o["url"] = o.get("srcUrl") or DOC_URL
    return sum(1 for o in due)


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
        key = n if n in by_norm else None
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
            doc_st = next((h["st"] for h in hits if h["src"] == "doc" and isinstance(h["st"], list) and h["st"]), None)
            if doc_st and isinstance(o.get("st"), list):
                o["st"] = doc_st  # Doctor of Credit's state list is fresher than the researched footprint
            for h in hits:
                if o.get("cd") is None and h.get("cd"):
                    o["cd"], o["cdSrc"] = h["cd"], h["src"]
                if not o.get("exp") and h.get("exp") and h["exp"] >= TODAY:
                    o["exp"] = h["exp"]
                if h["src"] == "doc" and link_matches_bank(c["b"], h.get("url", "")):
                    o["offerUrl"] = h["url"]
        out.append(o)
    # brand-new offers
    autos = {}
    for i, s in enumerate(scraped):
        if i in used or not (25 <= s["amt"] <= 5000):
            continue
        k = norm(s["b"])
        a = autos.get(k)
        if a:  # same offer on both sites: prefer DoC states, fill gaps from Fat Stacks
            for f in ("dd", "mindd", "mdd", "win", "tx", "cd", "fee", "pull", "exp"):
                if a.get(f) is None and s.get(f) is not None:
                    a[f] = s[f]
            if a["st"] == "?" and s["st"] != "?":
                a["st"] = s["st"]
            if s["src"] == "doc" and a["srcs"] == ["fs"]:  # prefer Doctor of Credit's wording and link
                a.update(b=s["b"], amt=s["amt"], req=s.get("req", a["req"]), url=s.get("url") or a["url"], srcUrl=s.get("srcUrl") or a.get("srcUrl"))
            a["srcs"] = sorted(set(a["srcs"]) | {s["src"]})
            continue
        b = s["b"]
        t = "cu" if re.search(r"credit union|\bfcu\b|\bcu\b", b, re.I) else "fin" if re.search(r"chime|current|varo|percapita|money\b", b, re.I) else "bank"
        autos[k] = {"id": "auto-" + slug(b) + "-" + str(s["amt"]), "b": b, "a": "Checking", "t": t, "amt": s["amt"],
                    "dd": s.get("dd"), "mindd": s.get("mindd"), "mdd": s.get("mdd"), "win": s.get("win", 90), "tx": s.get("tx"),
                    "keep": None, "cd": s.get("cd"), "st": s["st"], "pull": s.get("pull", "?"), "fee": s.get("fee", "See terms"),
                    "exp": s.get("exp") if (s.get("exp") or "") >= TODAY else None, "req": s.get("req", ""), "url": s.get("url"),
                    "auto": 1, "srcs": [s["src"]], "seen": TODAY, "srcUrl": s.get("srcUrl") or s.get("url")}
    for a in autos.values():
        if link_matches_bank(a["b"], a.get("url") or ""):
            a["offerUrl"] = a["url"]
        a["url"] = a.get("srcUrl") or a.get("url")
        a = {k: v for k, v in a.items() if v is not None or k in ("keep", "cd")}
        a["id"] = "auto-" + slug(norm(a["b"]))
        a["first"] = prev_by_id.get(a["id"], {}).get("first", TODAY)
        out.append(a)
    # keep recently seen auto offers that a source missed this run (or whose source failed)
    have_ids, have_banks = {o["id"] for o in out}, {norm(o["b"]) for o in out}
    for p in prev:
        if p.get("auto") and p["id"] not in have_ids and norm(p.get("b", "")) not in have_banks and p.get("seen"):
            age = (dt.date.today() - dt.date.fromisoformat(p["seen"])).days
            if age <= 14:
                p = dict(p, id="auto-" + slug(norm(p["b"])))
                out.append(p)
                have_ids.add(p["id"])
                have_banks.add(norm(p["b"]))
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
    if os.environ.get("SKIP_LOCATE") != "1":
        try:
            found, looked = locate(offers, prev, norm, fetch=fetch, link_ok=link_matches_bank)
            print(f"Located {found} offers with unknown states ({looked} looked up this run)")
        except Exception as e:  # never let this block the refresh
            print("Locating offers failed:", e)
    if os.environ.get("SKIP_VERIFY") != "1":
        n = verify(offers, prev)
        print(f"Checked {n} offer pages against their listed bonus")
    data = {"generated": NOW, "sources": sources, "offers": offers,
            "scrapedNames": sorted({s["heading"] if s.get("heading") else s["b"] for s in scraped})[:500]}
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
