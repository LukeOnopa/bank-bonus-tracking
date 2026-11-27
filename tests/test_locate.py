"""Offline tests for filling in where an offer is available (scripts/locate.py).
Run: python tests/test_locate.py"""
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import locate  # noqa: E402
from scrape import norm  # noqa: E402


def test():
    assert locate.name_states("City National Bank VA, WV, OH") == ["OH", "VA", "WV"]
    assert locate.name_states("Unitus Community Credit Union OR & WA") == ["OR", "WA"]
    assert locate.name_states("BMI Federal Credit Union") is None and locate.name_states("Bank of New Hampshire") is None
    assert locate.state_hint({"url": "https://www.fatstacksacademy.com/blog/town-bank-wi-checking-bonus"}) == {"WI"}
    assert locate.state_hint({"url": "https://example.com/blog/credit-union-of-oregon-or-checking"}) == set(), "'or' is a word, not Oregon"
    assert locate.own_domains({"url": "https://www.fatstacksacademy.com/x", "offerUrl": "https://www.bell.bank/promo"}) == {"bell.bank"}

    # Doctor of Credit names limited offers' states at the start of the address
    doc = lambda slug: {"url": f"https://www.doctorofcredit.com/{slug}/"}  # noqa: E731
    assert locate.article_states(doc("wi-il-onlyheritage-credit-union-100-checking-bonus")) == ["IL", "WI"]
    assert locate.article_states(doc("il-only-u-of-i-community-credit-union-150-checking-bonus")) == ["IL"]
    assert locate.article_states(doc("mi-portland-federal-credit-union-100-referral-bonus")) is None, "no 'only': just a hint"
    assert locate.article_states({"url": "https://www.fatstacksacademy.com/blog/il-only-bank"}) is None

    # the bank's website from the bonus article's links
    from scrape import link_matches_bank
    art = '<a href="https://www.facebook.com/x">f</a> <a href="https://www.peoplesbankmt.com/checking-bonus">Apply</a> <a href="https://www.chase.com/">Chase</a>'
    got = locate.article_domains({"b": "Peoples Bank", "url": "https://www.fatstacksacademy.com/blog/peoples-bank-checking-bonus"}, lambda u: art, link_matches_bank)
    assert got == {"peoplesbankmt.com"}, got
    assert locate.article_domains({"b": "X", "url": "https://www.doctorofcredit.com/best-bank-account-bonuses/"}, lambda u: art, link_matches_bank) == set(), "the roundup page links to every bank"

    peoples = [{"NAME": "Peoples Bank", "STALP": s, "WEBADDR": f"www.peoples{s.lower()}.com", "CERT": i} for i, s in enumerate(["WA", "OH", "IA"])]
    site = lambda c: c["WEBADDR"]  # noqa: E731
    assert locate.pick(peoples, {"b": "Peoples Bank"}, norm, "NAME", site, "STALP") == (None, None), "a shared name stays unknown"
    c, how = locate.pick(peoples, {"b": "Peoples Bank", "url": "https://x.com/blog/peoples-bank-ia-checking-bonus"}, norm, "NAME", site, "STALP")
    assert c["STALP"] == "IA" and how == "name+state"
    c, how = locate.pick(peoples, {"b": "Peoples Bank", "offerUrl": "https://promo.peoplesoh.com/get300"}, norm, "NAME", site, "STALP")
    assert c["STALP"] == "OH" and how == "website"
    bell = [{"NAME": "Bell Bank", "STALP": "ND", "WEBADDR": "www.bell.bank", "CERT": 1}, {"NAME": "Beal Bank USA", "STALP": "NV", "WEBADDR": "", "CERT": 2}]
    assert locate.pick(bell, {"b": "Bell Bank"}, norm, "NAME", site, "STALP")[0]["CERT"] == 1, "fuzzy search results are filtered to the exact name"

    # caching: a fresh earlier answer is reused without any lookup; a stale one is looked up again
    calls = []
    real = locate.locate_one
    locate.locate_one = lambda o, n: calls.append(o["b"]) or {"st": ["MN"], "stSrc": "branches", "stInst": "X", "stHow": "name"}
    try:
        today = dt.date(2026, 11, 27)
        v = locate.VERSION
        prev = [{"id": "a", "st": ["ND"], "stSrc": "branches", "stOn": "2026-11-20", "stVer": v}, {"id": "b", "stOn": "2026-11-20", "stVer": v},
                {"id": "c", "stOn": "2026-09-01", "stVer": v}, {"id": "f", "st": ["IA"], "stSrc": "hq", "stOn": "2026-11-26"}]
        offers = [{"id": k, "b": k.upper(), "st": "?"} for k in "abcdf"] + [{"id": "e", "b": "E", "st": ["TX"]}]
        found, looked = locate.locate(offers, prev, norm, today=today)
        assert offers[0]["st"] == ["ND"], "cached answer reused"
        assert offers[1]["st"] == "?", "a recent 'not found' isn't retried"
        assert calls == ["C", "D", "F"] and looked == 3 and found == 4, (calls, looked, found)  # F: cached by an older version, redone
        assert offers[5]["st"] == ["TX"], "known states are left alone"
    finally:
        locate.locate_one = real
    print("all locate tests passed")


if __name__ == "__main__":
    test()
