# Chartle

**One real chart. Forty bars. Everyone gets the same one.**

A daily trading game. You see 60 bars of a real price series with the name
stripped off, then you trade the next 40 one bar at a time — up to 2x long or
2x short. At the end you find out what you were trading.

```bash
python build_data.py          # fetch prices -> data/charts.json  (~3 min)
python -m http.server 8421    # then open http://localhost:8421
```

No dependencies, no build step, no backend. `build_data.py` is stdlib-only and
the game is a single static `index.html`.

---

## Why this shape

The Wordle engine has three parts, and this has all three:

1. **One shared instance per day.** Everyone gets the same chart, so everyone
   can argue about the same chart. Losing feels like a bad draw, not like being
   bad at it.
2. **A share card that spoils nothing.** Ten squares, one per four bars, green
   if that stretch made money.
3. **A reveal.** *"This was BABA, Oct–Dec 2022."* That line is the marketing —
   it's the bit people screenshot.

What Wordle doesn't have, and this does: a real skill ceiling. Position sizing,
transaction costs, and drawdown mean good players stay for streaks and stats
long after the novelty goes.

## Rules

- Position: `2x short · 1x short · flat · 1x long · 2x long`, held into the next bar.
- Changing position costs **5bp** of equity, so flip-flopping bleeds you.
- **Win condition:** beat buy & hold. That keeps your streak alive.
- Keyboard: <kbd>1</kbd>–<kbd>5</kbd> position, <kbd>space</kbd> advance, <kbd>A</kbd> auto.
- One puzzle a day, saved mid-game — refreshing won't let you re-roll a bad start.
- Practice mode gives unlimited random charts and doesn't touch your stats.

## Auto mode

Rather than clicking through 40 bars, hit **Auto** and they run on a timer while
you keep changing position. Speed cycles 0.5× / 1× / 2× / 4× (2400ms down to
300ms per bar). It pauses on its own when the run ends, when any dialog opens,
and when the tab is hidden.

The tick is driven by `setInterval` reading the wall clock, not
`requestAnimationFrame` — rAF stalls whenever the page isn't compositing, which
silently freezes the run in a background tab.

## Difficulty

Changes which pool the daily chart is drawn from. Everyone on the same
difficulty still gets the same chart, so scores stay comparable.

Each chart is scored on two textures computed from the bundled OHLC at load:
realised volatility, and **wick-to-range ratio** — the share of each bar's range
that isn't body, i.e. how much rejection and whipsaw there is.

Both are converted to z-scores before being summed. That detail matters: wick
ratio only spans about 0.45–0.55 while volatility spans an order of magnitude,
so adding them raw let volatility decide everything and hard mode came out with
*no more wicks than easy* (0.4977 vs 0.4942). Standardised, they separate
properly:

| | wick ratio | volatility |
|---|---|---|
| Easy (122 charts) | 0.462 | 0.037 |
| Hard (122 charts) | **0.528** | **0.060** |

Normal is the full 366-chart set, unchanged from the original game.

## Studies and drawing

Toggle **SMA 20 / SMA 50 / EMA 20 / Bollinger(20, 2)** under *Study*. All are
computed only over revealed bars — they never peek at what hasn't printed.

Drawing tools: trendline (drag), horizontal level (click), freehand, plus undo
and clear. Drawings are stored in **chart space — bar index and price — not
pixels**, so they stay pinned to the level you drew them at when the y-axis
rescales underneath them. Verified against GME, where the played section runs
24.9× above the setup high: the stored price held exactly while the axis went
from [77, 195] to [0, 5030] and the drawing re-projected accordingly.

Drawings persist per puzzle and difficulty.

## The data

`build_data.py` pulls 20 years of daily OHLC from Yahoo for ~60 liquid tickers,
slices 100-bar windows, and rebases each to 100 at the first open so the price
level can't give the ticker away.

Two details that matter more than they look:

**Windows are picked for interest, then rebalanced by outcome.** Scoring purely
on volatility silently selects for crashes — the first build came out at a
median buy & hold of **−6.68%**, which would have made the game trivial (sit
flat, beat the benchmark, win every day). The set is now stratified into
rising/sideways/falling buckets:

```
buy&hold over the played section: median +0.02%  mean +9.12%
  147 rising · 73 sideways · 146 falling
```

**Percentiles are precomputed, not invented.** For every chart the builder runs
1,200 random position paths through the *same* equity function the browser uses,
and stores the return distribution. "Beat 75% of random traders" is measured
against that chart, not a guess. `verify_math.py`-style cross-checks confirmed
the browser and the builder agree to 0.000000pp on an identical position
sequence — if those two ever drift, every rank the game shows becomes a lie.

366 puzzles ≈ one year. Re-run `build_data.py` to extend or refresh; bump
`TARGET_PUZZLES` for more.

## Deploying to Cloudflare Pages

Static site, no build step, no server. Two commands.

### One-time setup

You need a free Cloudflare account and Node (already installed if `npx` works).

### Deploy

```bash
python build_data.py
```

```bash
python make_dist.py
```

```bash
npx wrangler pages deploy dist --project-name=chartle
```

The first `wrangler` run opens a browser to authorise your Cloudflare account.
If the project doesn't exist yet it offers to create it — accept, and pick
`main` as the production branch.

You get `https://chartle.pages.dev`. Every later deploy also gets its own
immutable preview URL, so you can hand someone a specific build.

### Why `dist/` and not the repo root

`wrangler pages deploy` uploads *everything* in the directory you point it at.
Aim it at the repo root and you publish `build_data.py`, the README, and any
stray files. `make_dist.py` copies only `index.html`, `data/` and `_headers`.

### Updating

Re-run the last two commands. To refresh the puzzle set, re-run all three.

```bash
python make_dist.py && npx wrangler pages deploy dist --project-name=chartle
```

### Caching

`_headers` ships with the build and sets the policy that matters:

| path | policy | why |
|---|---|---|
| `/`, `/index.html` | `max-age=0, must-revalidate` | a redeploy has to reach people who already played today |
| `/data/*` | `max-age=3600, stale-while-revalidate=604800` | the puzzle set only changes when you rebuild; the daily rotation is client-side |

Payload is small once compressed — Pages serves gzip/brotli automatically:

```
charts.json  1057 KB raw -> 379 KB gzip
index.html     43 KB raw ->  13 KB gzip
```

### Custom domain

Cloudflare dashboard → Workers & Pages → chartle → Custom domains → *Set up a
domain*. If the domain is already on Cloudflare, DNS is wired automatically.

### Git integration instead?

Possible, but awkward here: this lives inside a large mixed repo, so you'd have
to set *Root directory* to `chartle` and give Pages a build command that runs
Python to produce `dist/`. Direct upload avoids all of that, and the dataset
build wants to run on your machine anyway — it makes ~60 outbound calls to
Yahoo.

### A note before you point traffic at it

The whole puzzle set ships to the client, so tomorrow's chart is readable in
`charts.json` by anyone who opens devtools. Fine at launch — Wordle shipped the
same way for a year — but if the game gets popular, move to serving one day's
chart from a Pages Function.

## What's deliberately not here yet

- **A real leaderboard.** Needs a backend. Wordle launched without accounts and
  so should this; local stats and share cards are enough to find out whether
  anyone cares.
- **Server-side answer hiding.** The whole puzzle set ships to the client, so a
  determined player can read tomorrow's chart out of the JSON. That's the same
  trade Wordle made for a year. Move to a per-day fetch if it becomes a problem.

---

## How to promote it

The game is the marketing. Everything below is about getting the first thousand
people to see one result card.

### 1. Post results, never links

The thing that spreads is a score, not a URL. Seed the share card into places
where people already argue about charts:

- **r/wallstreetbets, r/Daytrading, r/algotrading, r/investing** — post your own
  bad score. Self-deprecation travels; promotion gets removed.
- **FinTwit / X.** Reply to chart-posting accounts with your card. The format is
  instantly legible to anyone who knows Wordle.
- **Discord/Slack trading servers.** These are where daily-habit games actually
  take root, because someone posts their score every morning and the rest of the
  channel has to answer.

### 2. Make the reveal the hook

*"You just traded NVDA through March 2020"* is a better headline than anything
you could write about the game. Lean on it:

- Weekly "hardest chart of the week" post with the reveal and what everyone got.
- Charts with a famous event in them (COVID crash, GME, SVB week) will get
  screenshotted far more than a random 2015 window.

### 3. Aim at the people who teach this

Trading educators, university finance societies, and CFA/quant study groups need
a free interactive teaching tool. One professor using it in a lecture is worth
more than a viral post, because it comes back every semester. Offer a
**classroom mode** — fixed chart, shared link, everyone's scores compared.

### 4. Build the thing people ask for

Watch what gets requested and ship it fast: crypto mode, forex mode,
head-to-head, survival mode (keep trading until you blow up). Survival is the
one most likely to go viral, because "I lasted 34 charts" is a better brag than
a single day's return.

### Monetisation, honestly

Games like this monetise weakly per user and scale on volume. Realistic:

| | |
|---|---|
| Pro tier ~$4/mo | unlimited practice, full history archive, personal edge analytics |
| Cosmetics | chart themes, card styles |
| Sponsorship | brokers and data vendors want exactly this audience |

Do not expect this to pay rent. Expect it to be the most shareable thing you can
build alone, and the best possible portfolio piece for anything quant-adjacent —
which, for you, is probably worth more than the subscription revenue.

### The one metric to watch

**Day-2 return rate.** If people don't come back tomorrow, nothing else you do
to the game matters. Everything above is downstream of that number.
