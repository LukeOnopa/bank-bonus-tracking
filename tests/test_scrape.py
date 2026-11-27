"""Offline tests for the scraper using small pages shaped like the real ones.
Run: python tests/test_scrape.py"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import scrape  # noqa: E402

DOC = """<html><body><div class="entry-content">
<h2>Best Checking Account Bonuses</h2>
<h3>Chase $900 Checking Bonus</h3>
<p><a href="https://accounts.chase.com/x">Direct link to offer</a></p>
<p>Get $900 when you make $10,000 in total direct deposits within 90 days. Valid through 1/27/2027.</p>
<ul><li><a href="https://www.doctorofcredit.com/chase-900/">Read our full post</a></li><li>Soft pull</li><li>No credit card funding</li></ul>
<h3>Wells Fargo $500 Checking Bonus</h3>
<p>Requires $1,000 in direct deposits within 90 days.</p>
<ul><li>Soft pull</li></ul>
<h3>Schwab $250/$500/$1,000 Checking Bonus</h3>
<p>Transfer $25k/$50k/$100k. No direct deposit required.</p>
<h3>Brand New Bank $350 Checking Bonus</h3>
<p>Make 2 direct deposits of $500 within 60 days and 10 debit card purchases.</p>
<ul><li>Soft pull</li></ul>
<h2>Best Saving Account Bonuses</h2>
<h3>Ally $200 Savings Bonus</h3><p>Deposit $10,000.</p>
<h2>Best State Specific Bonuses</h2>
<h3>BMO $650 - AZ, CA, CO, FL, IL, WI</h3>
<p>$1,000+ in direct deposits per month.</p>
<h3>Hometown Credit Union $300 Checking Bonus - MN Only</h3>
<p>No direct deposit required. Complete 15 debit transactions within 90 days. Offer ends December 31, 2026.</p>
<h3>Acme Bank $400 Business Checking</h3><p>Business.</p>
</div></body></html>"""

FS_ITEMS = [("1", "HSBC", "3,000", "No DD (tiered) | $50/mo fee", "Premier offer."),
            ("2", "Chase", "3,000", "No DD (tiered) | 12mo cooldown | $35/mo fee", "Private client."),
            ("10", "BMO", "600", "$1,000+/mo DD in 210 days | 12mo cooldown | $0 monthly fee", "BMO is offering..."),
            ("11", "Huntington", "600", "$500 DD in 90 days (tiered) | 24mo cooldown | $10/mo fee", "Huntington..."),
            ("19", "Wells Fargo", "500", "$1,000 DD in 90 days | 12mo cooldown | $15/mo fee", "This offer is no longer available."),
            ("40", "Fat Stacks Only CU", "275", "$750 DD in 60 days + 8 transactions | 18mo cooldown | $0 monthly fee", "Available through March 31, 2027."),
            ("41", "Acme Biz", "500", "No DD + 5 tx", "A business checking bonus.")]
FS_ITEMS += [(str(50 + i), f"Filler Bank {i}", "200", "$500 DD in 60 days | $0 monthly fee", "Filler.") for i in range(20)]
FS = "<html><body><main>" + "".join(
    f'<div class="card"><h3><span>{r}</span> <span>{n}</span><span>${a}</span></h3><p>{s}</p><p>{d} <a href="/blog/{n.lower().replace(" ", "-")}-bonus">Review →</a></p></div>'
    for r, n, a, s, d in FS_ITEMS) + "</main></body></html>"


def test():
    d = {o["b"]: o for o in scrape.parse_doc(DOC)}
    assert set(d) == {"Chase", "Wells Fargo", "Schwab", "Brand New Bank", "BMO", "Hometown Credit Union"}, set(d)
    assert d["Chase"]["amt"] == 900 and d["Chase"]["dd"] == 10000 and d["Chase"]["win"] == 90 and d["Chase"]["st"] == "ALL"
    assert d["Chase"]["exp"] == "2027-01-27" and d["Chase"]["url"].startswith("https://accounts.chase.com")
    assert d["Schwab"]["amt"] == 1000 and d["Schwab"]["dd"] == 0
    assert d["BMO"]["st"] == ["AZ", "CA", "CO", "FL", "IL", "WI"] and d["BMO"]["mdd"] == 1000
    h = d["Hometown Credit Union"]
    assert h["st"] == ["MN"] and h["dd"] == 0 and h["tx"] == 15 and h["exp"] == "2026-12-31", h
    assert d["Brand New Bank"]["tx"] == 10 and d["Brand New Bank"]["win"] == 60 and d["Brand New Bank"]["dd"] == 1000

    f = {o["b"]: o for o in scrape.parse_fs(FS)}
    assert "Wells Fargo" not in f, "ended offers must be skipped"
    assert "Acme Biz" not in f, "business offers must be skipped"
    assert f["BMO"]["mdd"] == 1000 and f["BMO"]["cd"] == 12 and f["BMO"]["win"] == 210 and f["BMO"]["fee"] == "None"
    assert f["Huntington"]["cd"] == 24 and f["Huntington"]["dd"] == 500
    fo = f["Fat Stacks Only CU"]
    assert fo["dd"] == 750 and fo["tx"] == 8 and fo["cd"] == 18 and fo["exp"] == "2027-03-31" and fo["url"].endswith("fat-stacks-only-cu-bonus"), fo
    assert len(f) >= scrape.MIN_FS

    curated = [{"id": "bmo", "b": "BMO", "amt": 600, "st": ["IL"], "cd": 12},
               {"id": "wf", "b": "Wells Fargo", "amt": 500, "st": "ALL", "cd": 12},
               {"id": "hunt", "b": "Huntington", "amt": 600, "st": ["OH"], "cd": None},
               {"id": "gone", "b": "Vanished Bank", "amt": 300, "st": "ALL", "cd": None},
               {"id": "chase-total", "b": "Chase", "amt": 400, "st": "ALL"}, {"id": "chase-900", "b": "Chase", "amt": 900, "st": "ALL"}]
    prev = [{"id": "gone", "seen": "2026-11-01", "first": "2026-10-01"}, {"id": "bmo", "amt": 600, "first": "2026-09-01"},
            {"id": "auto-old-cu-250", "b": "Old CU", "amt": 250, "auto": 1, "seen": "2020-01-01"}]
    out = {o["id"]: o for o in scrape.merge(curated, list(d.values()) + list(f.values()), prev, ["x"])}
    assert out["bmo"]["amt"] == 650 and out["bmo"]["prevAmt"] == 600 and out["bmo"]["seen"] == scrape.TODAY, out["bmo"]
    assert out["bmo"]["st"] == ["IL"], "curated states must win"
    assert out["bmo"]["first"] == "2026-09-01"
    assert out["hunt"]["cd"] == 24, "fill missing churn rule from Fat Stacks"
    assert out["gone"]["seen"] == "2026-11-01", "unlisted offer keeps its last-seen date"
    assert out["chase-total"]["amt"] == 400 and out["chase-900"]["amt"] == 900, "multi-offer banks keep curated amounts"
    autos = {o["b"]: o for o in out.values() if o.get("auto")}
    assert "Brand New Bank" in autos and "Hometown Credit Union" in autos and "Fat Stacks Only CU" in autos, set(autos)
    assert autos["Hometown Credit Union"]["st"] == ["MN"] and autos["Hometown Credit Union"]["t"] == "cu"
    assert "Old CU" not in autos, "auto offers unseen for >14 days are dropped"
    assert "HSBC" in autos and "Schwab" in autos
    print("all scraper tests passed")


if __name__ == "__main__":
    test()
