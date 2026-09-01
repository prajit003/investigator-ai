#!/usr/bin/env python3
"""
Indicators must be right, and must be ABSENT rather than approximate.

The second half matters as much as the first: these are computed from history
the system accumulates itself, so on day one there is nothing to compute from.
A function that returned 50.0 in that situation would put a fabricated RSI in
front of a user, and the price agent would score it as a real reading.

Runs offline. It writes into a throwaway sqlite file, never the real cache.
"""
import os
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
os.environ.setdefault("DATA_MODE", "fixtures")

from feeds import cache  # noqa: E402

# Point the cache at a temp DB BEFORE anything opens the real one.
_TMP = pathlib.Path(tempfile.mkdtemp()) / "test_cache.db"
cache.DB_PATH = _TMP
cache._CONN = None

from feeds import indicators  # noqa: E402

PASSED, FAILED = [], []


def check(label, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f"  — {detail}" if detail and not ok else ""))
    (PASSED if ok else FAILED).append(label)


def seed(symbol, closes):
    for i, c in enumerate(closes):
        cache.record_close(symbol, f"2026-01-{i + 1:02d}", c)


def test_rsi_needs_a_full_window():
    seed("SHORT", [100 + i for i in range(indicators.RSI_PERIOD)])   # one short
    check("RSI is None below period+1 closes", indicators.rsi("SHORT") is None,
          f"got {indicators.rsi('SHORT')} from {cache.close_count('SHORT')} closes")
    check("momentum is None on short history", indicators.momentum("SHORT") is None)
    check("volatility is None on short history", indicators.volatility("SHORT") is None)


def test_rsi_of_a_pure_uptrend_is_100():
    # Every day up, so average loss is zero. Wilder's RSI is exactly 100 here,
    # and this is the boundary the division guard has to survive.
    seed("UPONLY", [100 + i for i in range(30)])
    check("RSI of a monotonic rise is 100", indicators.rsi("UPONLY") == 100.0,
          f"got {indicators.rsi('UPONLY')}")


def test_rsi_matches_a_hand_worked_first_window():
    """
    EXACTLY period+1 closes, so no smoothing runs and the answer is arithmetic
    anyone can check on paper.

    14 deltas alternating +2 / -1, starting with a gain: 7 gains and 7 losses.
    avg_gain = 14/14 = 1.0, avg_loss = 7/14 = 0.5, RS = 2, RSI = 100 - 100/3.
    """
    closes, price = [], 100.0
    for i in range(indicators.RSI_PERIOD + 1):
        closes.append(price)
        price += 2 if i % 2 == 0 else -1
    seed("FIRSTWIN", closes)
    got = indicators.rsi("FIRSTWIN")
    check("RSI over one unsmoothed window is 66.67",
          got is not None and abs(got - 66.67) < 0.01, f"expected 66.67, got {got}")


def test_smoothing_pulls_toward_the_latest_move():
    """
    The same alternation continued to 31 closes must NOT give the same answer:
    Wilder smoothing weights recent deltas, and this series ends on a loss, so
    the smoothed value has to sit below the first-window value. An
    implementation that used a plain moving average would return 66.67 here and
    silently claim to be Wilder's RSI.
    """
    closes, price = [], 100.0
    for i in range(31):
        closes.append(price)
        price += 2 if i % 2 == 0 else -1
    seed("ALT", closes)
    got = indicators.rsi("ALT")
    check("smoothed RSI sits below the unsmoothed window value",
          got is not None and 60.0 < got < 66.67, f"got {got}")


def test_momentum_is_a_fraction_not_a_percent():
    # The price agent's MOMENTUM_STRONG = 0.10 threshold reads 0.18 as +18%.
    # If this ever returned 18.0 the agent would call every stock a strong
    # uptrend, so the SCALE is part of the contract.
    seed("MOM", [100.0] * 1 + [100.0] * (indicators.MOMENTUM_LOOKBACK - 1) + [120.0])
    got = indicators.momentum("MOM")
    check("momentum is a fraction (0.20, not 20.0)", got is not None and abs(got - 0.20) < 0.01,
          f"got {got}")


def test_volatility_is_zero_for_a_flat_series():
    seed("FLAT", [50.0] * 40)
    got = indicators.volatility("FLAT")
    check("volatility of a flat series is 0", got == 0.0, f"got {got}")


def test_coverage_reports_what_is_supportable():
    cov = indicators.coverage("UPONLY")
    check("coverage counts the closes it has", cov["closes"] == 30, f"got {cov}")
    check("coverage says RSI is supportable", cov["rsi"] is True)
    cov = indicators.coverage("NOTHING_HERE")
    check("coverage on an unknown symbol supports nothing",
          cov["closes"] == 0 and not any((cov["rsi"], cov["momentum"], cov["volatility"])))


if __name__ == "__main__":
    print("INDICATORS")
    for fn in (test_rsi_needs_a_full_window, test_rsi_of_a_pure_uptrend_is_100,
               test_rsi_matches_a_hand_worked_first_window,
               test_smoothing_pulls_toward_the_latest_move,
               test_momentum_is_a_fraction_not_a_percent,
               test_volatility_is_zero_for_a_flat_series, test_coverage_reports_what_is_supportable):
        fn()
    print()
    if FAILED:
        print(f"{len(FAILED)} FAILURE(S)\n")
        sys.exit(1)
    print(f"ALL {len(PASSED)} INDICATOR CHECKS PASSED\n")
