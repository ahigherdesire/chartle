#!/usr/bin/env python3
"""Build the Chartle puzzle set from real daily price history.

Pulls OHLC from Yahoo, slices 100-bar windows (60 setup + 40 playable), rebases
each so the price level can't give the ticker away, and precomputes a
random-trader return distribution so the end screen can rank the player honestly.

    python build_data.py              # ~50 tickers -> data/charts.json
    python build_data.py --quick      # small run for testing

Stdlib only.
"""

import argparse
import json
import math
import os
import random
import statistics
import sys
import time
import urllib.error
import urllib.request

SETUP_BARS = 60          # history the player sees before trading
PLAY_BARS = 40           # bars they trade through
WINDOW = SETUP_BARS + PLAY_BARS
STEP = 45                # stride between candidate windows in one series
COST_BPS = 5             # per unit of position change, matches the game
N_SIMS = 1200            # random strategies per chart, for the percentile table
TARGET_PUZZLES = 366
SEED = 20260810

TICKERS = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "NFLX", "AMD", "INTC",
    "IBM", "ORCL", "CSCO", "QCOM", "TXN", "AVGO", "CRM", "ADBE", "PYPL", "SHOP",
    "UBER", "ABNB", "COIN", "PLTR", "SNAP", "ZM", "ROKU", "GME", "F", "GM",
    "BA", "DAL", "CCL", "XOM", "CVX", "OXY", "SLB", "JPM", "GS", "BAC",
    "WMT", "COST", "NKE", "SBUX", "MCD", "DIS", "PFE", "MRNA", "JNJ", "UNH",
    "SPY", "QQQ", "IWM", "GLD", "SLV", "USO", "TLT", "ARKK", "BABA", "NIO",
]

UA = {"User-Agent": "Mozilla/5.0 (compatible; chartle-builder/1.0)"}


def fetch(ticker, rng="20y"):
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
           f"?range={rng}&interval=1d")
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read())
    res = data["chart"]["result"][0]
    ts = res["timestamp"]
    q = res["indicators"]["quote"][0]
    meta = res.get("meta", {})
    bars = []
    for i in range(len(ts)):
        o, h, l, c = q["open"][i], q["high"][i], q["low"][i], q["close"][i]
        if None in (o, h, l, c) or o <= 0 or c <= 0:
            continue
        bars.append((ts[i], o, h, l, c))
    return bars, meta.get("shortName") or meta.get("longName") or ticker


def simulate(closes, positions, cost_bps=COST_BPS):
    """Equity path for a position sequence. positions[i] is held into bar i+1."""
    equity, prev = 1.0, 0.0
    for i, pos in enumerate(positions):
        ret = closes[i + 1] / closes[i] - 1.0
        equity *= (1.0 + pos * ret)
        equity *= (1.0 - abs(pos - prev) * cost_bps / 10000.0)
        prev = pos
    return equity - 1.0


def random_distribution(closes, rng):
    """What a coin-flipping trader would score on this chart."""
    out = []
    choices = (-2, -1, 0, 1, 2)
    for _ in range(N_SIMS):
        pos, seq = 0, []
        for _ in range(PLAY_BARS):
            # Persist positions rather than redrawing each bar - a trader who
            # flips every bar is destroyed by costs and makes the bar too low.
            if rng.random() < 0.25:
                pos = rng.choice(choices)
            seq.append(pos)
        out.append(simulate(closes, seq))
    out.sort()

    def pct(p):
        return round(out[min(len(out) - 1, int(p / 100 * len(out)))] * 100, 2)

    return {"p25": pct(25), "p50": pct(50), "p75": pct(75),
            "p90": pct(90), "p95": pct(95), "p99": pct(99)}


def interestingness(window):
    """Prefer windows that actually move, and that aren't a single straight line."""
    closes = [b[4] for b in window]
    play = closes[SETUP_BARS - 1:]
    rets = [play[i + 1] / play[i] - 1 for i in range(len(play) - 1)]
    vol = statistics.pstdev(rets) if len(rets) > 1 else 0
    total = abs(play[-1] / play[0] - 1)
    # Reward movement and volatility, but penalise a pure one-way ramp so the
    # set isn't all "buy and hold wins".
    straightness = total / (sum(abs(r) for r in rets) + 1e-9)
    return (vol * 60) + (total * 1.5) - (straightness * 0.8)


def build(quick=False):
    rng = random.Random(SEED)
    tickers = TICKERS[:8] if quick else TICKERS
    candidates = []

    for n, tk in enumerate(tickers, 1):
        try:
            bars, name = fetch(tk)
        except (urllib.error.URLError, urllib.error.HTTPError, KeyError,
                IndexError, ValueError) as e:
            print(f"  [{n}/{len(tickers)}] {tk:<6} skipped ({type(e).__name__})")
            continue
        if len(bars) < WINDOW + 10:
            print(f"  [{n}/{len(tickers)}] {tk:<6} skipped (only {len(bars)} bars)")
            continue

        made = 0
        for start in range(0, len(bars) - WINDOW, STEP):
            w = bars[start:start + WINDOW]
            pc = [b[4] for b in w[SETUP_BARS - 1:]]
            candidates.append({"ticker": tk, "name": name, "window": w,
                               "score": interestingness(w),
                               "bh": (pc[-1] / pc[0] - 1) * 100})
            made += 1
        print(f"  [{n}/{len(tickers)}] {tk:<6} {len(bars):>5} bars -> {made} windows")
        time.sleep(0.4)

    if not candidates:
        print("no data fetched")
        return 1

    print(f"\n{len(candidates)} candidate windows; selecting {TARGET_PUZZLES}")

    # Balance the set by outcome. Selecting purely on "interestingness" favours
    # high-volatility windows, which in equities means crashes - and a set where
    # buy & hold usually loses makes the game trivial (just sit flat and win).
    # Stratify so up, down and sideways charts are all well represented.
    buckets = {
        "up":   ([c for c in candidates if c["bh"] > 3], int(TARGET_PUZZLES * 0.40)),
        "down": ([c for c in candidates if c["bh"] < -3], int(TARGET_PUZZLES * 0.40)),
        "flat": ([c for c in candidates if -3 <= c["bh"] <= 3], int(TARGET_PUZZLES * 0.20)),
    }
    per_cap = max(3, TARGET_PUZZLES // max(1, len(set(c["ticker"] for c in candidates))) + 3)
    picked, used = [], {}
    for label, (pool, quota) in buckets.items():
        pool.sort(key=lambda c: -c["score"])
        took = 0
        for c in pool:
            if took >= quota:
                break
            if used.get(c["ticker"], 0) >= per_cap:
                continue
            picked.append(c)
            used[c["ticker"]] = used.get(c["ticker"], 0) + 1
            took += 1
        print(f"  {label:<5} {len(pool):>4} available -> took {took}")

    # Top up from whatever is left if a bucket came up short.
    if len(picked) < TARGET_PUZZLES:
        chosen = {id(c) for c in picked}
        for c in sorted(candidates, key=lambda c: -c["score"]):
            if len(picked) >= TARGET_PUZZLES:
                break
            if id(c) in chosen or used.get(c["ticker"], 0) >= per_cap:
                continue
            picked.append(c)
            used[c["ticker"]] = used.get(c["ticker"], 0) + 1

    rng.shuffle(picked)

    charts = []
    for i, c in enumerate(picked):
        w = c["window"]
        base = w[0][1]  # rebase on first open so the price level reveals nothing
        k = 100.0 / base
        ohlc = [[round(b[1] * k, 2), round(b[2] * k, 2),
                 round(b[3] * k, 2), round(b[4] * k, 2)] for b in w]
        closes = [b[4] for b in w[SETUP_BARS - 1:]]
        bh = round((closes[-1] / closes[0] - 1) * 100, 2)
        charts.append({
            "id": i,
            "ohlc": ohlc,
            "buyhold": bh,
            "rand": random_distribution(closes, rng),
            "reveal": {
                "ticker": c["ticker"],
                "name": c["name"],
                "from": time.strftime("%b %Y", time.gmtime(w[SETUP_BARS - 1][0])),
                "to": time.strftime("%b %Y", time.gmtime(w[-1][0])),
            },
        })
        if (i + 1) % 25 == 0:
            print(f"  simulated {i + 1}/{len(picked)}")

    out = {
        "version": 1,
        "setup_bars": SETUP_BARS,
        "play_bars": PLAY_BARS,
        "cost_bps": COST_BPS,
        "built": time.strftime("%Y-%m-%d"),
        "charts": charts,
    }
    os.makedirs("data", exist_ok=True)
    path = os.path.join("data", "charts.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, separators=(",", ":"))

    size = os.path.getsize(path)
    tick_n = len(set(c["reveal"]["ticker"] for c in charts))
    print(f"\nwrote {path}  ({len(charts)} puzzles, {tick_n} tickers, "
          f"{size / 1024:.0f} KB)")
    bhs = [c["buyhold"] for c in charts]
    up = sum(1 for b in bhs if b > 3)
    dn = sum(1 for b in bhs if b < -3)
    print(f"buy&hold over the played section: median {statistics.median(bhs):+.2f}%  "
          f"mean {statistics.mean(bhs):+.2f}%")
    print(f"  {up} rising · {len(bhs) - up - dn} sideways · {dn} falling")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    a = ap.parse_args()
    sys.exit(build(quick=a.quick))
