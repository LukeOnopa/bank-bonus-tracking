"""Use the bonus roundup articles (Fat Stacks, Doctor of Credit) as a reference, not as the source.

For each offer that came from a roundup, read its article once a week and keep:
- the link to the bank's own offer page (so cards link to the bank, never to the article)
- the article's stated availability (states, or nationwide), to compare with the
  official branch states from FDIC/NCUA
- the stated expiration date, and the requirements summary, to check against

Nothing here is shown as the offer's source; it's stored under o["ref"] and used for
cross-checks.
"""
import datetime as dt
import re
import time
import urllib.request
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

CACHE_DAYS = 7
COMPILERS = ("fatstacksacademy.com", "doctorofcredit.com")
STATES = set("AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY".split())
NAMES = {"alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR", "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
         "district of columbia": "DC", "washington dc": "DC", "washington, d.c.": "DC", "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
         "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS", "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
         "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS", "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
         "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY", "north carolina": "NC", "north dakota": "ND", "ohio": "OH",
         "oklahoma": "OK", "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC", "south dakota": "SD", "tennessee": "TN",
         "texas": "TX", "utah": "UT", "vermont": "VT", "virginia": "VA", "washington": "WA", "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY"}
# the labels that follow "Availability:" in each site's summary box
FS_NEXT = r"Lifetime limit|ChexSystems|Credit pull|Fees|Monthly fee|Payout|Bonus posts|Household|Early"
DOC_NEXT = r"Direct deposit required|Additional requirements|ChexSystems|Credit inquiry|Household limit|Expiration date|Early account termination|Contents"


def is_compiler(u):
    h = (urlparse(u or "").hostname or "").lower()
    return any(h == d or h.endswith("." + d) for d in COMPILERS)


def article_of(o):
    for u in (o.get("refUrl"), o.get("srcUrl"), o.get("url")):
        if u and is_compiler(u) and not re.search(r"best-bank-account-bonuses/?$|best-checking-bonuses-\d{4}/?$", u):
            return u
    return None


def states_from(text):
    """'MN, ND, AZ' / 'Illinois and Wisconsin residents' / 'Nationwide' -> ['AZ','MN','ND'] / ['IL','WI'] / 'ALL' (None if unclear)."""
    t = (text or "").strip()
    if re.search(r"\bnation\s?wide\b|\ball (?:50 )?states\b|\banywhere in the u", t, re.I):
        return "ALL"
    codes = {c for c in re.findall(r"\b([A-Z]{2})\b", t) if c in STATES}
    low = t.lower()
    for name in sorted(NAMES, key=len, reverse=True):  # 'west virginia' before 'virginia'
        if re.search(r"\b" + re.escape(name) + r"\b", low):
            codes.add(NAMES[name])
            low = re.sub(r"\b" + re.escape(name) + r"\b", " ", low)
    return sorted(codes) or None


def parse_date(s):
    m = re.search(r"\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b", s or "")
    if m:
        y = int(m[3]) + (2000 if int(m[3]) < 100 else 0)
        return f"{y:04d}-{int(m[1]):02d}-{int(m[2]):02d}"
    m = re.search(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2}),?\s+(\d{4})", s or "", re.I)
    if m:
        mon = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"].index(m[1].lower()) + 1
        return f"{int(m[3]):04d}-{mon:02d}-{int(m[2]):02d}"
    return None


def read_article(url, html, bank, link_ok, resolve):
    """What the article says about this offer. resolve(url) follows a redirect link to its final address."""
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style", "noscript", "svg", "nav", "footer"]):
        t.decompose()
    body = soup.select_one(".entry-content") or soup.find("article") or soup.body or soup
    text = re.sub(r"\s+", " ", body.get_text(" "))
    fs = "fatstacksacademy.com" in url
    out = {"src": "Fat Stacks" if fs else "Doctor of Credit", "url": url}
    m = re.search(r"Availability:\s*(.+?)\s*(?:" + (FS_NEXT if fs else DOC_NEXT) + r")\b", text)
    if m:
        out["avail"] = m[1][:200]
        st = states_from(m[1])
        if st:
            out["st"] = st
    m = re.search(r"(?:Valid through|Expiration date:|Expires?:?|Offer ends:?)\s*([A-Z][a-z]+\.? \d{1,2},? \d{4}|\d{1,2}/\d{1,2}/\d{2,4})", text)
    if m:
        out["exp"] = parse_date(m[1])
    # the bank's own offer page: the "Open account" / "Direct link to offer" button first, then any link to the bank
    buttons, others = [], []
    for a in body.find_all("a", href=True):
        label = a.get_text(" ", strip=True).lower()
        href = urljoin(url, a["href"])
        (buttons if re.search(r"open (?:an )?account|direct link to (?:the )?offer|apply now|get (?:this )?offer", label) else others).append(href)
    for href in buttons + others:
        final = href
        if is_compiler(href):  # Fat Stacks' buttons go through its own /go/ redirect
            if "/go/" not in href:
                continue
            final = resolve(href) or ""
        if final and link_ok(bank, final):
            out["offerUrl"] = final.split("#")[0]
            break
    return out


def resolve_redirect(u, timeout=20):
    """The address a redirect link ends up at (one HEAD request; no page download)."""
    req = urllib.request.Request(u, method="HEAD", headers={"User-Agent": "BankBonusTracker/1.0 (+https://github.com/LukeOnopa/bank-bonus-tracking)"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.geturl()
    except Exception:
        return None


def reference(offers, prev, fetch, link_ok, today=None, seconds=180, resolve=resolve_redirect):
    """Read the roundup article for each auto-collected offer (cached a week). Returns how many were read this run."""
    today = today or dt.date.today()
    old = {p["id"]: p for p in prev if p.get("id")}
    stop, read = time.monotonic() + seconds, 0
    for o in offers:
        if not o.get("auto"):
            continue
        art = article_of(o)
        if not art:
            continue
        o["refUrl"] = art
        p = (old.get(o["id"]) or {}).get("ref")
        if p and p.get("url") == art and (today - dt.date.fromisoformat(p["on"])).days < CACHE_DAYS:
            ref = dict(p)
        elif time.monotonic() < stop:
            try:
                ref = read_article(art, fetch(art), o["b"], link_ok, resolve)
            except Exception as e:
                print(f"  reference article failed for {o['b']}: {type(e).__name__}")
                continue
            ref["on"] = today.isoformat()
            read += 1
        else:
            continue  # out of time this run; next run continues
        o["ref"] = ref
        if ref.get("offerUrl") and not o.get("offerUrl"):
            o["offerUrl"] = ref["offerUrl"]
    return read


# a bank's page saying the account (not its ATMs) can be opened from anywhere
NATIONWIDE_PAGE = re.compile(r"(?:available|open(?:ed)?|apply)[^.]{0,60}?(?:nationwide|in all 50 states|from anywhere in the (?:u\.?s\.?|united states)|to (?:all )?u\.?s\.? residents)"
                             r"|(?:nationwide|all 50 states)[^.]{0,40}?(?:offer|bonus|account|customers|applicants)", re.I)


def page_says_nationwide(text):
    for m in NATIONWIDE_PAGE.finditer(text or ""):
        if not re.search(r"\batms?\b|branches|locations|network", m[0], re.I):
            return True
    return False


def gate_nationwide(offers, scraped, norm):
    """'Anywhere in the US' needs proof: the offer's article says nationwide, Doctor of Credit lists it in its
    nationwide section, the bank's own page says so, or it was confirmed by hand (natSrc in curated.json).
    Otherwise the states fall back to where the bank has branches (looked up next)."""
    doc_nat = {norm(x["b"]) for x in scraped if x.get("src") == "doc" and x.get("st") == "ALL"}
    for o in offers:
        if o.get("st") != "ALL" or o.get("custom"):
            continue
        ref = o.get("ref") or {}
        if ref.get("st") == "ALL":
            o["natSrc"] = ref.get("src")
        elif norm(o["b"]) in doc_nat:
            o["natSrc"] = "Doctor of Credit"
        elif (o.get("check") or {}).get("nationwide"):
            o["natSrc"] = "bank"
        elif not o.get("natSrc"):
            o["st"], o["stWasAll"] = "?", True
            o.pop("stSrc", None)


def set_aside_roundup_states(offers):
    """Roundup state lists become a reference: the federal lookup decides (nationwide stays nationwide)."""
    for o in offers:
        if o.get("auto") and isinstance(o.get("st"), list) and not o.get("stSrc"):
            o["stRoundup"], o["st"] = o["st"], "?"


def settle(o, today):
    """After the article and the federal lookup: pick the states, link and end date the card shows."""
    if not o.get("auto"):
        return
    ref = o.get("ref") or {}
    said = ref.get("st") or o.get("stRoundup")  # what the roundups say about availability
    if said == "ALL" and o.get("st") != "ALL":
        o.update(st="ALL", stSrc="article", natSrc=ref.get("src") or "the bonus roundups")  # the article confirms it's nationwide
    elif o.get("st") in ("?", None) and said:
        o.update(st=said, stSrc="article")         # no federal match: the roundup's list is all we have
    if said and o.get("stSrc") in ("branches", "hq"):
        o["stCheck"] = {"src": ref.get("src") or "the bonus roundups", "st": said,
                        "agrees": said != "ALL" and set(said) == set(o["st"]) if isinstance(o["st"], list) else said == o["st"]}
    if ref.get("exp"):
        # articles keep old dates when an offer comes back, so only a recent past date means "may have ended"
        if not o.get("exp") and ref["exp"] >= today.isoformat():
            o["exp"] = ref["exp"]
        if (today - dt.timedelta(days=60)).isoformat() <= ref["exp"] < today.isoformat():
            o["refExpired"] = ref["exp"]
    # cards link to the bank, never to the roundup article
    if is_compiler(o.get("url")):
        site = o.get("stSite")
        o["url"] = site or (f"https://{urlparse(o['offerUrl']).hostname}" if o.get("offerUrl") else None)
    if is_compiler(o.get("offerUrl")):
        o.pop("offerUrl")
