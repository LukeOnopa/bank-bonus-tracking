"""Fill in where an offer is available when the bonus roundups don't say.

For offers with unknown states, find the institution in the official lists and use:
- banks (FDIC BankFind): the states where it has branches
- credit unions (NCUA): the state where it's based
Matches must be unambiguous: the bank's own website domain, or an exact name match
(with a state hint from the article address when several banks share a name).
Anything uncertain stays unknown. Results are cached in offers.json for 30 days.
"""
import datetime as dt
import json
import re
import time
import urllib.error
import urllib.request
from urllib.parse import quote, urlparse

FDIC = "https://api.fdic.gov/banks"
NCUA = "https://mapping.ncua.gov/api"
UA = "BankBonusTracker/1.0 (+https://github.com/LukeOnopa/bank-bonus-tracking)"
CACHE_DAYS = 30
THIRD_PARTY = ("doctorofcredit.com", "fatstacksacademy.com", "reddit.com", "bit.ly", "tinyurl.com")
STATES = set("AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY".split())
CU = re.compile(r"credit union|\bc\.?u\.?\b|\bfcu\b|federal credit", re.I)


def get_json(url, data=None, tries=5):
    headers = {"User-Agent": UA, "Accept": "application/json"}
    body = None
    if data is not None:
        body, headers["Content-Type"] = json.dumps(data).encode(), "application/json"
    for n in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, data=body, headers=headers), timeout=40) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            if n == tries - 1:
                raise
            time.sleep(1.5 * 2 ** n)


def host(url):
    try:
        h = (urlparse(url if "://" in (url or "") else "https://" + (url or "")).hostname or "").lower()
    except ValueError:
        return ""
    return h.removeprefix("www.")


def own_domains(o):
    """The bank's own website domains from the offer's links (not the bonus blogs)."""
    out = set()
    for u in (o.get("offerUrl"), o.get("url"), (o.get("check") or {}).get("url")):
        h = host(u)
        if h and not any(h == d or h.endswith("." + d) for d in THIRD_PARTY):
            out.add(h)
    return out


def same_domain(a, b):
    a, b = host(a), host(b)
    if not a or not b:
        return False
    base = lambda h: ".".join(h.split(".")[-2:])  # noqa: E731
    return a == b or base(a) == base(b)


# two-letter state codes that are also everyday words in article addresses
AMBIGUOUS = {"or", "in", "me", "ok", "hi", "de", "co", "id", "al", "la", "ma", "oh", "mi", "ms", "ne", "us"}


def state_hint(o):
    """State codes in the article address: '/blog/town-bank-wi-checking-bonus' -> {'WI'}."""
    hints = set()
    for u in (o.get("url"), o.get("offerUrl")):
        for tok in re.split(r"[-/_.]", urlparse(u or "").path.lower()):
            if len(tok) == 2 and tok.upper() in STATES and tok not in AMBIGUOUS:
                hints.add(tok.upper())
    return hints


def names_match(norm, a, b):
    return norm(a) and norm(a) == norm(b)


def fdic_candidates(name):
    words = re.sub(r"[^A-Za-z0-9 ]", " ", name).split()
    if not words:
        return []
    q = quote(f'NAME:"{" ".join(words)}"')
    j = get_json(f"{FDIC}/institutions?search={q}&filters=ACTIVE%3A1&fields=NAME,WEBADDR,CERT,STALP&limit=100")
    return [x["data"] for x in j.get("data", [])]


def fdic_states(cert):
    j = get_json(f"{FDIC}/locations?filters=CERT%3A{cert}&fields=STALP&limit=10000")
    return sorted({x["data"]["STALP"] for x in j.get("data", []) if x["data"].get("STALP") in STATES})


def ncua_candidates(name):
    q = re.sub(r"\b(federal credit union|credit union|fcu|cu)\b", "", name, flags=re.I).strip() or name
    j = get_json(f"{NCUA}/ResearchCreditUnion/GetDetailSearch", data={
        "cuName": q, "charterNumber": None, "region": None, "state": None, "city": None, "zipCode": None,
        "fomType": None, "lowIncome": None, "isMdi": None, "skip": 0, "take": 50})
    return [r for r in j.get("results", []) if r.get("isActive") and not r.get("isCorporate")]


def ncua_site(charter):
    try:
        return get_json(f"{NCUA}/CreditUnionDetails/GetCreditUnionDetails/{charter}").get("creditUnionWebsite") or ""
    except Exception:
        return ""


def pick(cands, o, norm, name_key, site_of, state_key):
    """One candidate, or None when it isn't clear which institution this is."""
    doms = own_domains(o)
    if doms:
        by_site = [c for c in cands if any(same_domain(site_of(c), d) for d in doms)]
        if len(by_site) == 1:
            return by_site[0], "website"
    named = [c for c in cands if names_match(norm, c[name_key], o["b"])]
    if len(named) == 1:
        return named[0], "name"
    hint = state_hint(o)
    if hint and len(named) > 1:
        hinted = [c for c in named if c.get(state_key) in hint]
        if len(hinted) == 1:
            return hinted[0], "name+state"
    if doms and len(named) > 1:  # several share the name: check each one's website
        for c in named[:6]:
            if any(same_domain(site_of(c), d) for d in doms):
                return c, "website"
    return None, None


def locate_one(o, norm):
    order = ("ncua", "fdic") if CU.search(o["b"]) else ("fdic", "ncua")
    for src in order:
        if src == "fdic":
            c, how = pick(fdic_candidates(o["b"]), o, norm, "NAME", lambda c: c.get("WEBADDR") or "", "STALP")
            if c:
                st = fdic_states(c["CERT"]) or [c["STALP"]]
                return {"st": st, "stSrc": "branches", "stInst": f"{c['NAME']} (FDIC #{c['CERT']})", "stHow": how}
        else:
            cands = ncua_candidates(o["b"])
            sites = {}
            if own_domains(o) and len(cands) <= 8:
                sites = {r["charterNumber"]: ncua_site(r["charterNumber"]) for r in cands}
            c, how = pick(cands, o, norm, "name", lambda c: sites.get(c["charterNumber"], ""), "state")
            if c:
                return {"st": [c["state"]], "stSrc": "hq", "stInst": f"{c['name'].title()} (NCUA #{c['charterNumber']})", "stHow": how}
    return None


def name_states(name):
    """States written at the end of a name: 'City National Bank VA, WV, OH' -> ['OH', 'VA', 'WV']."""
    m = re.search(r"((?:[\s,&]+(?:and\s+)?[A-Z]{2}\b)+)\s*$", name or "")
    codes = re.findall(r"\b([A-Z]{2})\b", m[1]) if m else []
    return sorted(set(codes)) if codes and all(c in STATES for c in codes) else None


def locate(offers, prev, norm, budget=60, today=None):
    """Fill st for offers whose states are unknown. Returns (located, looked_up)."""
    today = today or dt.date.today()
    old = {p["id"]: p for p in prev if p.get("id")}
    found = looked = 0
    for o in offers:
        if o.get("st") != "?" or o.get("custom"):
            continue
        named = name_states(o["b"])
        if named:
            o.update(st=named, stSrc="name")
            found += 1
            continue
        p = old.get(o["id"]) or {}
        if p.get("stOn") and (today - dt.date.fromisoformat(p["stOn"])).days < CACHE_DAYS:
            if p.get("stSrc"):
                o.update({k: p[k] for k in ("st", "stSrc", "stInst", "stHow", "stOn") if k in p})
                found += 1
            else:
                o["stOn"] = p["stOn"]  # looked up recently and not found: don't retry yet
            continue
        if looked >= budget:
            continue
        looked += 1
        try:
            r = locate_one(o, norm)
        except Exception as e:  # a lookup failure leaves the offer as it was and retries next run
            print(f"  locate failed for {o['b']}: {type(e).__name__}")
            continue
        o["stOn"] = today.isoformat()
        if r:
            o.update(r)
            found += 1
    return found, looked
