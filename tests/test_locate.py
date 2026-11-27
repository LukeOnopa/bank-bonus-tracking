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
        prev = [{"id": "a", "st": ["ND"], "stSrc": "branches", "stOn": "2026-11-20"}, {"id": "b", "stOn": "2026-11-20"}, {"id": "c", "stOn": "2026-09-01"}]
        offers = [{"id": k, "b": k.upper(), "st": "?"} for k in "abcd"] + [{"id": "e", "b": "E", "st": ["TX"]}]
        found, looked = locate.locate(offers, prev, norm, today=today)
        assert offers[0]["st"] == ["ND"], "cached answer reused"
        assert offers[1]["st"] == "?", "a recent 'not found' isn't retried"
        assert calls == ["C", "D"] and looked == 2 and found == 3, (calls, looked, found)
        assert offers[4]["st"] == ["TX"], "known states are left alone"
    finally:
        locate.locate_one = real
    print("all locate tests passed")


if __name__ == "__main__":
    test()
