"""Offline tests for using the bonus roundup articles as a reference (scripts/reference.py).
Run: python tests/test_reference.py"""
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import reference  # noqa: E402
from scrape import link_matches_bank  # noqa: E402

FS = """<html><body><article><h1>Bell Bank $100 Checking Bonus</h1>
<p>Deposit window: 60 days. Make 10 debit card transactions.</p>
<h3>Eligibility</h3><p>Availability: MN, ND, AZ Lifetime limit: one bonus per customer ChexSystems sensitivity: Unknown</p>
<p><a href="/go/bell-bank-100-checking-2026">Open account →</a> Valid through April 30, 2099</p>
<p><a href="https://www.fatstacksacademy.com/blog/other">Other bonuses</a></p></article></body></html>"""
DOC = """<html><body><div class="entry-content"><p>Availability: Must live in Illinois or Wisconsin Direct deposit required: No
Expiration date: 12/31/2024</p><p><a href="https://www.heritagecu.org/free-checking.html">Direct link to offer</a></p></div></body></html>"""


def test():
    assert reference.states_from("MN, ND, AZ") == ["AZ", "MN", "ND"]
    assert reference.states_from("Must live in Illinois or Wisconsin") == ["IL", "WI"]
    assert reference.states_from("West Virginia and Virginia") == ["VA", "WV"], "'west virginia' isn't also counted as just Virginia's name"
    assert reference.states_from("Nationwide") == "ALL" and reference.states_from("Champaign county residents") is None

    resolve = {"https://www.fatstacksacademy.com/go/bell-bank-100-checking-2026": "https://bell.bank/checking/100"}.get
    r = reference.read_article("https://www.fatstacksacademy.com/blog/bell-bank-checking-bonus", FS, "Bell Bank", link_matches_bank, resolve)
    assert r["st"] == ["AZ", "MN", "ND"] and r["offerUrl"] == "https://bell.bank/checking/100" and r["exp"] == "2099-04-30" and r["src"] == "Fat Stacks", r
    r = reference.read_article("https://www.doctorofcredit.com/wi-il-heritage/", DOC, "Heritage Credit Union", link_matches_bank, lambda u: None)
    assert r["st"] == ["IL", "WI"] and r["offerUrl"] == "https://www.heritagecu.org/free-checking.html" and r["exp"] == "2024-12-31", r
    assert reference.article_of({"url": "https://www.doctorofcredit.com/best-bank-account-bonuses/"}) is None, "the roundup page itself isn't an article"

    today = dt.date(2026, 11, 27)
    # roundup states are set aside; the federal branch states win and the roundup is the cross-check
    o = {"auto": 1, "b": "Bell Bank", "st": ["MN", "ND", "AZ"], "url": "https://www.fatstacksacademy.com/blog/bell-bank-checking-bonus"}
    reference.set_aside_roundup_states([o])
    assert o["st"] == "?" and o["stRoundup"] == ["MN", "ND", "AZ"]
    o.update(st=["AZ", "ID", "MN", "ND"], stSrc="branches", stSite="https://www.bell.bank", ref={"src": "Fat Stacks", "st": ["AZ", "MN", "ND"], "exp": "2026-10-31"})
    reference.settle(o, today)
    assert o["st"] == ["AZ", "ID", "MN", "ND"] and o["stCheck"] == {"src": "Fat Stacks", "st": ["AZ", "MN", "ND"], "agrees": False}, o
    assert o["url"] == "https://www.bell.bank", "the card links to the bank, not the article"
    assert o["refExpired"] == "2026-10-31" and "exp" not in o, "a recent past end date is flagged, not used"
    # nationwide in the article stays nationwide; no federal match falls back to the article's list
    o = {"auto": 1, "st": ["MN"], "stSrc": "branches", "ref": {"src": "Doctor of Credit", "st": "ALL", "exp": "2021-08-31"}}
    reference.settle(o, today)
    assert o["st"] == "ALL" and "refExpired" not in o, "an old article date isn't treated as the offer ending"
    assert o["natSrc"] == "Doctor of Credit", "the article that confirms nationwide is named"
    o = {"auto": 1, "st": "?", "stRoundup": ["IL", "WI"], "url": "https://www.doctorofcredit.com/x/"}
    reference.settle(o, today)
    assert o["st"] == ["IL", "WI"] and o["stSrc"] == "article" and o["url"] is None, o
    o = {"st": ["CA"], "url": "https://www.chase.com"}  # hand-researched offers are left alone
    reference.settle(o, today)
    assert o == {"st": ["CA"], "url": "https://www.chase.com"}
    # "Anywhere in the US" needs proof
    from scrape import norm
    assert reference.page_says_nationwide("This offer is available nationwide to new customers.")
    assert reference.page_says_nationwide("Open an account online from anywhere in the U.S.")
    assert not reference.page_says_nationwide("Use 40,000 fee-free ATMs nationwide."), "ATMs don't count"
    assert not reference.page_says_nationwide("Visit one of our branches in all 50 states."), "branches don't count"
    offers = [{"id": "a", "b": "Chase", "st": "ALL"}, {"id": "b", "b": "SoFi", "st": "ALL", "ref": {"src": "Fat Stacks", "st": "ALL"}},
              {"id": "c", "b": "Varo", "st": "ALL", "check": {"nationwide": True}}, {"id": "d", "b": "Bell Bank", "st": "ALL", "stSrc": "article"},
              {"id": "e", "b": "Navy Federal", "st": "ALL", "natSrc": "Navy Federal's membership page"}, {"id": "f", "b": "X", "st": ["MN"]}]
    reference.gate_nationwide(offers, [{"src": "doc", "b": "Chase", "st": "ALL"}, {"src": "fs", "b": "Bell Bank", "st": "ALL"}], norm)
    assert [o.get("natSrc") for o in offers[:3]] == ["Doctor of Credit", "Fat Stacks", "bank"]
    assert offers[3]["st"] == "?" and offers[3]["stWasAll"] and "stSrc" not in offers[3], "unconfirmed nationwide falls back to the federal lookup"
    assert offers[4]["st"] == "ALL", "a hand-confirmed source in curated.json counts"
    assert offers[5]["st"] == ["MN"]
    online = [{"b": "Varo", "st": "ALL", "t": "fin"}, {"b": "Example Bank", "st": "ALL", "t": "bank", "req": "Open this online-only checking account"},
              {"b": "Capital One", "st": "ALL", "t": "bank", "req": "Open a 360 Checking account"}]
    reference.gate_nationwide(online, [], norm)
    assert [o.get("natSrc") for o in online[:2]] == ["online", "online"] and online[2]["st"] == "?", online
    print("all reference tests passed")


if __name__ == "__main__":
    test()
