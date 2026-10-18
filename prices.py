"""Long-term price database: one snapshot per scrape week in prices/<date>.json, never pruned.

Each snapshot holds every product seen that week (promo items at their regular price, plus the house-brand
reference lists): {k: [price, unit_price, unit, cat, family, discount]}. k = store + product code, the same id the
board uses. Names live in prices/products.json (latest name wins).

Report: python3 prices.py [data-dir] [--since YYYY-MM-DD] [--csv out.csv] [--brief]
Index = Jevons (geometric mean of price ratios) over products present in both weeks, chained week to week.
Ratios outside 0.5-2x are treated as pack changes or scrape errors and ignored.
"""
import collections, csv, glob, json, math, os, sys

LO, HI = 0.5, 2.0
STORE = {"d": "Delhaize", "c": "Carrefour"}


def snapshot(rows):
    """rows: dicts with k, p, v, u, c, t, d, n, b. Promo rows win over house rows for the same k (they carry d)."""
    snap, names = {}, {}
    for r in rows:
        try: p = round(float(r["p"]), 2)
        except (TypeError, ValueError): continue
        if p <= 0: continue
        if r["k"] in snap and not r.get("d"): continue
        snap[r["k"]] = [p, r.get("v"), r.get("u") or "", r.get("c") or "", r.get("t") or "", r.get("d") or 0]
        names[r["k"]] = [r.get("n") or "", r.get("b") or ""]
    return snap, names


def record(data_dir, week, rows):
    """Write prices/<week>.json if that week is new. Returns True when written."""
    if not week: return False
    d = os.path.join(data_dir, "prices")
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, f"{week}.json")
    if os.path.exists(path): return False
    snap, names = snapshot(rows)
    json.dump(snap, open(path, "w"), ensure_ascii=False, separators=(",", ":"))
    pp = os.path.join(d, "products.json")
    try: prod = json.load(open(pp))
    except (OSError, ValueError): prod = {}
    for k, nb in names.items():
        prod[k] = nb + [prod[k][2] if k in prod else week]  # [name, brand, first seen]
    json.dump(prod, open(pp, "w"), ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return True


def load(data_dir):
    weeks = {}
    for f in sorted(glob.glob(os.path.join(data_dir, "prices", "????-??-??.json"))):
        weeks[os.path.basename(f)[:10]] = json.load(open(f))
    return weeks


def ratios(a, b, keep=lambda k, row: True):
    out = {}
    for k, row in b.items():
        if k in a and keep(k, row):
            r = row[0] / a[k][0]
            if LO <= r <= HI: out[k] = r
    return out


def geo(rs):
    return math.exp(sum(math.log(r) for r in rs) / len(rs)) if rs else None


def chain(weeks, keep=lambda k, row: True):
    """[(week, index, n_common)] with the first week at 100."""
    ws = sorted(weeks)
    if not ws: return []
    out, idx = [(ws[0], 100.0, len(weeks[ws[0]]))], 100.0
    for w0, w1 in zip(ws, ws[1:]):
        rs = ratios(weeks[w0], weeks[w1], keep)
        g = geo(rs.values())
        if g: idx *= g
        out.append((w1, idx, len(rs)))
    return out


def by_store(s): return lambda k, row: k.startswith(s)
def by_cat(s, c): return lambda k, row: k.startswith(s) and row[3] == c


def report(data_dir, since=None, brief=False):
    weeks = load(data_dir)
    if since: weeks = {w: v for w, v in weeks.items() if w >= since}
    ws = sorted(weeks)
    lines = [f"Base de prix: {len(ws)} semaine(s)" + (f", {ws[0]} -> {ws[-1]}" if ws else "")]
    if len(ws) < 2:
        if ws: lines.append(f"{len(weeks[ws[-1]])} produits dans la dernière semaine. Il faut au moins 2 semaines pour un indice.")
        return "\n".join(lines)
    prod = {}
    try: prod = json.load(open(os.path.join(data_dir, "prices", "products.json")))
    except (OSError, ValueError): pass
    a, b = weeks[ws[0]], weeks[ws[-1]]
    for s, label in STORE.items():
        ch = chain(weeks, by_store(s))
        last = weeks[ws[-2]]
        wk = geo(ratios(last, b, by_store(s)).values())
        lines.append(f"{label}: indice {ch[-1][1]:.1f} (base 100 au {ws[0]}), "
                     f"{(wk - 1) * 100:+.1f} % sur la dernière semaine ({ch[-1][2]} produits comparés)")
    if brief: return "\n".join(lines)
    lines.append("\nPar rayon (indice chaîné, base 100):")
    cats = sorted({row[3] for v in weeks.values() for row in v.values() if row[3]})
    for s, label in STORE.items():
        parts = []
        for c in cats:
            ch = chain(weeks, by_cat(s, c))
            if ch[-1][2] >= 5: parts.append(f"{c} {ch[-1][1]:.1f}")
        lines.append(f"  {label}: " + ", ".join(parts))
    rs = ratios(a, b)
    mv = sorted(rs.items(), key=lambda kv: kv[1])
    nm = lambda k: (prod.get(k, ["?"])[0])[:50]
    lines.append(f"\nPlus fortes hausses depuis {ws[0]}:")
    lines += [f"  {STORE[k[0]]:9} {nm(k):50} {a[k][0]:.2f} -> {b[k][0]:.2f} ({(r - 1) * 100:+.0f} %)" for k, r in mv[::-1][:10] if r > 1]
    lines.append("Plus fortes baisses:")
    lines += [f"  {STORE[k[0]]:9} {nm(k):50} {a[k][0]:.2f} -> {b[k][0]:.2f} ({(r - 1) * 100:+.0f} %)" for k, r in mv[:10] if r < 1]
    shrink = [k for k in set(a) & set(b) if a[k][1] and b[k][1] and a[k][2] == b[k][2]
              and abs(b[k][0] - a[k][0]) < 0.01 and b[k][1] > a[k][1] * 1.03]
    if shrink:
        lines.append("Réduflation possible (même prix, prix au kilo en hausse):")
        lines += [f"  {STORE[k[0]]:9} {nm(k):50} {a[k][1]:.2f} -> {b[k][1]:.2f} €/{b[k][2]}" for k in shrink[:10]]
    return "\n".join(lines)


def summary(weeks, prod, families=(), top=10, fam_cap=300, recent=4):
    """Compact trend data for the board's "Tendances" tab (the full DB never goes into the page).
    w: weeks; idx/n: chained index and products compared per store; cats: {cat: {store: series or None}};
    s: {k: [name, brand, family, unit, prices aligned on w (None = not seen)]} for movers and changed items of `families`;
    up/down: [k, ratio] first vs last price seen (last seen in the `recent` latest weeks); shrink: [k, v0, v1, price]."""
    ws = sorted(weeks)
    out = dict(w=ws, idx={}, n={}, cats={}, s={}, up=[], down=[], shrink=[])
    if not ws: return out
    r1 = lambda x: round(x, 1)
    for s in STORE:
        ch = chain(weeks, by_store(s))
        out["idx"][s] = [r1(i) for _, i, _ in ch]
        out["n"][s] = ch[-1][2] if len(ch) > 1 else sum(k.startswith(s) for k in weeks[ws[-1]])
    cats = sorted({row[3] for v in weeks.values() for row in v.values() if row[3]})
    for c in cats:
        e = {}
        for s in STORE:
            ch = chain(weeks, by_cat(s, c))
            e[s] = [r1(i) for _, i, _ in ch] if len(ch) > 1 and min(n for _, _, n in ch[1:]) >= 5 else None
        if any(e.values()): out["cats"][c] = e
    obs = collections.defaultdict(list)  # k -> [(week index, row)]
    for i, w in enumerate(ws):
        for k, row in weeks[w].items(): obs[k].append((i, row))
    live = [k for k, o in obs.items() if len(o) >= 2 and o[-1][0] >= len(ws) - recent]
    mv = {}
    for k in live:
        r = obs[k][-1][1][0] / obs[k][0][1][0]
        if LO <= r <= HI and abs(r - 1) >= 0.005: mv[k] = r
    srt = sorted(mv.items(), key=lambda kv: kv[1])
    out["up"] = [[k, round(r, 4)] for k, r in srt[::-1][:top] if r > 1]
    out["down"] = [[k, round(r, 4)] for k, r in srt[:top] if r < 1]
    for k in live:
        (_, a), (_, b) = obs[k][0], obs[k][-1]
        if a[1] and b[1] and a[2] == b[2] and abs(b[0] - a[0]) < 0.01 and b[1] > a[1] * 1.03:
            out["shrink"].append([k, a[1], b[1], b[0]])
    out["shrink"].sort(key=lambda x: -x[2] / x[1])
    out["shrink"] = out["shrink"][:top]
    fam = set(families)
    keep = [k for k, _ in out["up"] + out["down"]] + [x[0] for x in out["shrink"]]
    keep += sorted((k for k in mv if obs[k][-1][1][4] in fam and k not in keep), key=lambda k: -abs(mv[k] - 1))[:fam_cap]
    for k in keep:
        p = [None] * len(ws)
        for i, row in obs[k]: p[i] = row[0]
        last = obs[k][-1][1]
        out["s"][k] = (prod.get(k) or ["", ""])[:2] + [last[4], last[2], p]
    return out


def to_csv(data_dir, path):
    weeks, prod = load(data_dir), {}
    try: prod = json.load(open(os.path.join(data_dir, "prices", "products.json")))
    except (OSError, ValueError): pass
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["semaine", "magasin", "id", "nom", "marque", "rayon", "famille", "prix", "prix_unitaire", "unite", "remise_promo"])
        for wk, snap in sorted(weeks.items()):
            for k, (p, v, u, c, t, d) in sorted(snap.items()):
                n, b = (prod.get(k) or ["", ""])[:2]
                w.writerow([wk, STORE.get(k[0], k[0]), k, n, b, c, t, p, v if v is not None else "", u, d or ""])


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = sys.argv[1:]
    data_dir = args[0] if args and os.path.isdir(args[0]) else os.path.dirname(os.path.abspath(__file__))
    since = flags[flags.index("--since") + 1] if "--since" in flags else None
    if "--csv" in flags:
        out = flags[flags.index("--csv") + 1]
        to_csv(data_dir, out); print("csv:", out)
    else:
        print(report(data_dir, since, brief="--brief" in flags))
