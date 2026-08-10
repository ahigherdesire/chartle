#!/usr/bin/env python3
"""Assemble the deployable site into dist/.

`wrangler pages deploy` uploads everything in the directory you point it at, so
pointing it at the repo root would publish build_data.py, the README and any
stray files. This copies only what the browser actually needs.

    python make_dist.py
    npx wrangler pages deploy dist --project-name=chartle
"""

import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(HERE, "dist")

FILES = ["index.html", "_headers"]
DIRS = ["data"]


def main():
    missing = [f for f in FILES if not os.path.exists(os.path.join(HERE, f))]
    if not os.path.exists(os.path.join(HERE, "data", "charts.json")):
        missing.append("data/charts.json (run build_data.py first)")
    if missing:
        print("missing:")
        for m in missing:
            print("  -", m)
        return 1

    if os.path.exists(DIST):
        shutil.rmtree(DIST)
    os.makedirs(DIST)

    for f in FILES:
        shutil.copy2(os.path.join(HERE, f), os.path.join(DIST, f))
    for d in DIRS:
        shutil.copytree(os.path.join(HERE, d), os.path.join(DIST, d))

    total = 0
    print(f"dist/ ->")
    for root, _, files in os.walk(DIST):
        for f in sorted(files):
            p = os.path.join(root, f)
            size = os.path.getsize(p)
            total += size
            print(f"  {size/1024:>8.1f} KB  {os.path.relpath(p, DIST)}")
    print(f"  {'-'*8}")
    print(f"  {total/1024:>8.1f} KB  total (Pages serves this gzipped/brotli)")
    print("\nnext:  npx wrangler pages deploy dist --project-name=chartle")
    return 0


if __name__ == "__main__":
    sys.exit(main())
