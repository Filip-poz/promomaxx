import json, os, sys, datetime

# python3 gate.py [data-dir] [out-dir]  ->  exit 0 if this week's build is safe to publish, 1 otherwise.
# Run after build.py. Compares the built board (out-dir/data.json) with the previous snapshot in history.json.
# Carrefour Market folders vary a lot in size (225 vs 380 tagged promos in Oct/Nov 2026), so it gets a
# looser bar: 50 % of last week or at least 150 promos.
ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
SRC = ARGS[0] if ARGS else os.path.dirname(os.path.abspath(__file__))
OUT = ARGS[1] if len(ARGS) > 1 else f"{SRC}/docs"
FILES = ["delhaize-fr.json", "delhaize-nutriscore.json", "carrefour-fr.json", "carrefour-photos.json"]

data = json.load(open(f"{OUT}/data.json"))
hist = json.load(open(f"{SRC}/history.json"))
wk = (data.get("pulled") or "")[:10]
prev = max((w for w in hist if w < wk), default=None)
fails, today = [], datetime.date.today()

for f in FILES:
    d = datetime.date.fromtimestamp(os.path.getmtime(f"{SRC}/{f}"))
    if d != today: fails.append(f"{f} is from {d}, not today")
if not wk: fails.append("no scrape date (pulled) in the build")
elif wk not in hist: fails.append(f"history has no snapshot for {wk}")

for s, name, ratio, floor in (("d", "Delhaize", .6, None), ("c", "Carrefour", .5, 150)):
    items = [x for x in data["items"] if x["s"] == s]
    n, img = len(items), sum(1 for x in items if x.get("img"))
    last = sum(1 for k in hist[prev] if k.startswith(s)) if prev else 0
    share = n / last if last else 1
    photos = img / n if n else 0
    print(f"{name}: {n} promos (last week {last}, {share:.0%}), photos {img}/{n} ({photos:.0%})")
    if n < 50: fails.append(f"{name}: only {n} promos")
    if last and share < ratio and not (floor and n >= floor):
        fails.append(f"{name}: {n} promos is {share:.0%} of last week ({last})")
    if photos < .8: fails.append(f"{name}: photos {photos:.0%}")

print("GATE " + ("PASS" if not fails else "FAIL: " + "; ".join(fails)))
sys.exit(1 if fails else 0)
