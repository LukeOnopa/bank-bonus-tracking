"""Offline tests for the bank-site crawler (scripts/discover.py), using small pages shaped like real ones.
Run: python tests/test_discover.py"""
import datetime as dt
import json
import os
import sys
import tempfile
import urllib.robotparser

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import discover  # noqa: E402

FILLER = "<p>" + "Member FDIC. Equal Housing Lender. Our team is here to help with everyday banking, loans and more. " * 6 + "</p>"
NEXT_YEAR = dt.date.today().year + 1


def page(body):
    return f"<html><body><nav>Home Checking Savings Loans</nav><main>{body}</main>{FILLER}</body></html>"


CHECKING = page(f"""<h1>Get a $400 bonus with a new checking account</h1>
<p>Open a new Smart Checking account and receive $1,000 or more in direct deposits within 90 days to earn the $400 bonus.
Offer ends March 31, {NEXT_YEAR}. New customers only.</p>""")
CD = page("""<h1>Certificate special</h1><p>Earn a $200 bonus when you open a 12-month certificate of deposit with $25,000. Savings and CDs only.</p>
<p>Looking for checking? See our checking accounts.</p>""")
REFERRAL = page("""<h1>Refer a friend</h1><p>Get a $50 bonus for each friend you refer who opens a checking account.</p>""")
EXPIRED = page("""<h1>Checking bonus</h1><p>Open a new checking account and get a $300 bonus with direct deposits of $500 within 60 days.
Offer expired January 5, 2020.</p>""")
JS_ONLY = "<html><body><div id=root></div><script>render()</script></body></html>"
RATE = page("""<h1>High-yield checking</h1><p>Earn 4.00% APY on balances up to $15,000 in Kasasa checking. Bonus rate requires 12 debit card purchases.</p>""")


def test():
    # reading pages
    finds, st = discover.extract("https://bank.example/promo", CHECKING)
    assert st == "ok" and len(finds) == 1, (st, finds)
    f = finds[0]
    assert f["amt"] == 400 and f["dd"] == 1000 and f["win"] == 90 and f["conf"] == "high", f
    assert f["exp"] == f"{NEXT_YEAR}-03-31", f
    assert discover.extract("https://bank.example/cd", CD)[0] == [], "a CD bonus is not a checking bonus"
    assert discover.extract("https://bank.example/refer", REFERRAL)[0] == [], "referral rewards are skipped"
    assert discover.extract("https://bank.example/old", EXPIRED)[0] == [], "expired offers are skipped"
    assert discover.extract("https://bank.example/app", JS_ONLY) == ([], "needs-browser")
    assert discover.extract("https://bank.example/rate", RATE)[0] == [], "interest-rate promos are not bonuses"

    # offers for other audiences are skipped
    youth = page("<h1>Student checking</h1><p>Students ages 16-24 get a $100 bonus when they open a checking account with direct deposit within 60 days.</p>")
    assert discover.extract("https://bank.example/x", youth)[0] == [], "student offers are skipped"
    existing = page("<h1>Checking bonus</h1><p>Existing customers: earn a $200 bonus when you open a second checking account and add direct deposits within 90 days.</p>")
    assert discover.extract("https://bank.example/y", existing)[0] == [], "existing-customer offers are skipped"
    sweeps = page("<h1>Win big</h1><p>Open a checking account for a chance to win $2,000. No purchase necessary.</p>")
    assert discover.extract("https://bank.example/z", sweeps)[0] == [], "sweepstakes are skipped"
    for u in ("/student-checking-promotion", "/high-school-promo/", "/existing-customer-checking-bonus", "/smartcard-promotion/"):
        assert discover.NOT_FOR_NEW.search(u), u
    assert not discover.NOT_FOR_NEW.search("/personal/checking/bonus-offer")
    assert discover.clean_url("https://b.example/promo.html?icid=PB_1&utm_source=x") == "https://b.example/promo.html"

    # tiers on one page become one find; an unknown direct deposit amount isn't shown as $1
    tiered = discover.combine([
        {"amt": 500, "url": "https://r.example/p?icid=1", "conf": "high", "snippet": "a", "dd": 1, "win": 60},
        {"amt": 400, "url": "https://r.example/p", "conf": "medium", "snippet": "b"},
        {"amt": 400, "url": "https://r.example/other", "conf": "high", "snippet": "c"}])
    assert len(tiered) == 2 and tiered[0]["tiers"] == [400, 500] and tiered[0]["amt"] == 500, tiered
    assert tiered[0]["ddAmountUnknown"] and "dd" not in tiered[0], tiered[0]

    # "new" means the site doesn't list the bank yet, under any of its names
    listed = [{"id": "auto-think", "b": "Think Bank", "amt": 200, "st": "?"},
              {"id": "auto-maxx", "b": "Maxx by Cedar Rapids Bank & Trust", "amt": 425, "st": ["IA"]},
              {"id": "royal", "b": "Royal Credit Union", "amt": 400, "st": ["MN", "WI"], "url": "https://www.rcu.org"}]
    m = discover.match_known
    assert m({"name": "Think Mutual Bank", "site": "https://www.thinkbank.com", "states": ["MN"]}, listed)["id"] == "auto-think"
    assert m({"name": "Cedar Rapids Bank and Trust Company", "site": "https://crbt.bank", "states": ["IA"]}, listed)["id"] == "auto-maxx"
    assert m({"name": "Royal", "site": "https://www.rcu.org", "states": ["WI"]}, listed)["id"] == "royal"
    assert m({"name": "Lake Ridge Bank", "site": "https://www.lakeridge.bank", "states": ["WI"]}, listed) is None
    assert discover.known_fields(listed[2], {"amt": 500, "tiers": [400, 500]}) == {"known": True, "knownAs": "royal"}
    assert discover.known_fields(listed[0], {"amt": 300})["knownAmt"] == 200

    # choosing pages to read
    assert discover.url_score("https://bank.example/personal/checking-bonus") > discover.url_score("https://bank.example/personal/checking")
    assert discover.url_score("https://bank.example/promo/cd-special") < 4, "CD promos are not worth reading"
    assert discover.url_score("https://bank.example/x", "Get $300 when you open checking") >= 4, "link text with a dollar amount counts"
    assert discover.SKIP_URL.search("https://bank.example/files/bonus-terms.pdf")
    assert discover.same_site("https://www.bank.example/a", "https://bank.example")
    assert not discover.same_site("https://other.example/a", "https://bank.example")

    # websites from the government lists
    assert discover.site_root("www.ExampleBank.com") == "https://www.examplebank.com"
    assert discover.site_root("http://www.accentracu.org/") == "https://www.accentracu.org"
    assert discover.site_root("www.jpmorganchase.com") == "https://www.chase.com", "corporate site maps to the consumer site"
    assert discover.site_root("") is None and discover.site_root("n/a") is None

    # scheduling
    now = discover.NOW
    old = {"checked": (now - dt.timedelta(days=8)).isoformat()}
    fresh = {"checked": (now - dt.timedelta(days=1)).isoformat()}
    found = {"checked": (now - dt.timedelta(days=3)).isoformat(), "finds": [{"amt": 300}]}
    assert discover.due({}, None) and discover.due({}, old) and not discover.due({}, fresh), "sites are rechecked weekly"
    assert discover.due({}, found), "sites with a bonus are rechecked every 2 days"

    # a whole site, with the network swapped for canned pages
    pages = {
        "https://bank.example/robots.txt": "User-agent: *\nDisallow: /private/\nSitemap: https://bank.example/sitemap.xml",
        "https://bank.example/sitemap.xml": "<urlset><url><loc>https://bank.example/personal/checking-bonus</loc></url>"
                                            "<url><loc>https://bank.example/private/bonus</loc></url>"
                                            "<url><loc>https://bank.example/about-us</loc></url></urlset>",
        "https://bank.example/": page('<a href="/promo/switch-kit">Switch to us and get $400</a>'),
        "https://bank.example/personal/checking-bonus": CHECKING,
        "https://bank.example/promo/switch-kit": CHECKING,
    }
    fetched = []

    def fake_get(url, **kw):
        fetched.append(url)
        if url not in pages:
            raise discover.urllib.error.URLError("not found")
        return url, pages[url]

    real_get, real_delay = discover.get, discover.PAGE_DELAY
    discover.get, discover.PAGE_DELAY = fake_get, 0
    try:
        import time
        rec = discover.crawl_site({"id": "x", "name": "Example Bank", "site": "https://bank.example"}, None, time.monotonic() + 60)
        assert rec["status"] == "found" and rec["finds"][0]["amt"] == 400, rec
        assert "https://bank.example/private/bonus" not in fetched, "robots.txt is followed"
        assert "https://bank.example/about-us" not in fetched, "unrelated pages are not read"

        def blocked(url, **kw):
            raise discover.Blocked("HTTP 403")
        discover.get = blocked
        rec = discover.crawl_site({"id": "y", "name": "Shy Bank", "site": "https://shy.example"}, None, time.monotonic() + 60)
        assert rec["status"] == "blocked", rec

        # a full run: list carried over from the previous file, results written out
        prev = {"list": {"built": discover.NOW.isoformat(), "states": ["MN"], "retry": [],
                         "items": [{"id": "fdic-1", "name": "Example Bank", "kind": "bank", "site": "https://bank.example", "hq": "MN", "states": ["MN"]}]}}
        discover.get = fake_get
        with tempfile.TemporaryDirectory() as d:
            pp, out = os.path.join(d, "prev.json"), os.path.join(d, "out.json")
            json.dump(prev, open(pp, "w"))
            assert discover.main(["--prev", pp, "--out", out, "--states", "MN", "--minutes", "1", "--workers", "1"]) == 0
            res = json.load(open(out))
            assert res["unverified"] and res["summary"]["finds"] == 1 and res["finds"][0]["bank"] == "Example Bank", res["summary"]
            assert res["finds"][0]["known"] is False and res["summary"]["new_banks"] == 1
    finally:
        discover.get, discover.PAGE_DELAY = real_get, real_delay
    print("all crawler tests passed")


if __name__ == "__main__":
    test()
