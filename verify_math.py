#!/usr/bin/env python3
"""Guard the one invariant that makes the score honest.

The browser computes your return in JavaScript; the percentile table was built
by simulate() in Python. If those two ever disagree, every "beat 75% of random
traders" the game prints is wrong. This replays a fixed position sequence
through the Python side and checks it against a value captured from the browser.

    python verify_math.py
"""

import json
import os
import sys

from build_data import PLAY_BARS, SETUP_BARS, simulate

HERE = os.path.dirname(os.path.abspath(__file__))

# Captured from the browser by running, on chart 221:
#   for(const p of SEQ){ setPos(p); step(); }  ->  (S.equity-1)*100
CHART_ID = 221
SEQ = [-2, -2, 0, 0, -1, 2, 0, 0, 0, 1, -2, 0, 1, 2, -2, -2, -1, 0, -2, -1,
       1, 2, -2, 0, 2, 1, 1, 2, 2, -1, -2, 0, -2, 1, 1, 0, 1, 1, -1, -1]
BROWSER_RETURN = -17.1030


def main():
    path = os.path.join(HERE, "data", "charts.json")
    if not os.path.exists(path):
        print("data/charts.json missing - run build_data.py first")
        return 1
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    chart = next((c for c in data["charts"] if c["id"] == CHART_ID), None)
    if chart is None:
        print(f"chart #{CHART_ID} not in this build - regenerate the reference values")
        return 1

    closes = [b[3] for b in chart["ohlc"][SETUP_BARS - 1: SETUP_BARS + PLAY_BARS]]
    py = simulate(closes, SEQ) * 100
    drift = abs(py - BROWSER_RETURN)

    rev = chart["reveal"]
    print(f"chart          #{CHART_ID}  {rev['ticker']} {rev['from']}-{rev['to']}")
    print(f"python         {py:+.4f}%")
    print(f"browser        {BROWSER_RETURN:+.4f}%")
    print(f"drift          {drift:.6f} pp")

    bh = (closes[-1] / closes[0] - 1) * 100
    print(f"buy&hold       stored {chart['buyhold']:+.2f}%  recomputed {bh:+.2f}%")

    ok = drift < 0.001 and abs(bh - chart["buyhold"]) < 0.01
    print("\n" + ("PASS - browser and builder agree" if ok else "FAIL - engines disagree"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
