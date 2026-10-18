import json, re, sys, os, collections
from promo import parse_offer, unit, typeof, form_of, is_dish, match_ref, TYPES, FORM_LABEL, NO_COMPARE, display_name, name_vocab, fmt_size, pack_noun

# python3 build.py [data-dir] [out-dir] [--rewrite-history]
# history.json only gets a new snapshot for a new scrape date; rebuilding the page never touches it
# unless --rewrite-history is given (e.g. to store corrected discounts for the current week).
ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
REWRITE_HIST = "--rewrite-history" in sys.argv
SRC = ARGS[0] if ARGS else os.path.dirname(os.path.abspath(__file__))
OUT = ARGS[1] if len(ARGS) > 1 else SRC
D = json.load(open(f"{SRC}/delhaize-fr.json"))
C = json.load(open(f"{SRC}/carrefour-fr.json"))
CT = json.load(open(f"{SRC}/carrefour-photos.json"))
NS = json.load(open(f"{SRC}/delhaize-nutriscore.json"))

CATS = {  # key: (emoji, label)
 "fresh":("🥬","Fruits & légumes"), "meat":("🥩","Viande, poisson & veggie"), "dairy":("🧀","Crèmerie & fromage"),
 "ready":("🍲","Plats préparés & soupes"), "bakery":("🥖","Pain & viennoiserie"), "pantry":("🫙","Épicerie salée"),
 "snacks":("🥜","Chips & noix"), "sweet":("🍫","Épicerie sucrée"), "frozen":("❄️","Surgelés"),
 "drinks":("☕","Boissons & café"), "beer":("🍺","Bières & spiritueux"), "wine":("🍷","Vins & bulles"),
 "household":("🧽","Entretien"), "care":("🧴","Hygiène & soins")}
D_MAP = {"v2FRU":"fresh","v2MEA":"meat","v2DAI":"dairy","v2CON":"ready","v2APE":"snacks","v2BAK":"bakery","v2SWE":"sweet",
         "v2SAL":"pantry","v2CAN":"pantry","v2FRO":"frozen","v2SPE":"dairy","v2WIN":"wine","v2DRI":"drinks","V2ALC":"beer",
         "v2CLE":"household","v2NON":"household","v2HYG":"care"}
C_MAP = {"ros002":"dairy","ros003":"fresh","ros004":"meat","ros005":"snacks","ros006":"ready","ros007":"meat","ros008":"bakery",
         "ros009":"sweet","ros010":"sweet","ros011":"pantry","ros013":"pantry","ros014":"sweet","ros015":"frozen","ros016":"drinks",
         "ros017":"care","ros018":"care","ros019":"household","ros022":"meat"}

def refine(cat, name):
    n = name.lower()
    if re.search(r"\bchips\b|tortilla|bugles|cacahu|noix|cajou|amande|pistache|pécan|mélange apéro", n) and cat in ("pantry","fresh","sweet","snacks"): return "snacks"
    if re.search(r"café|capsules|dosettes|espresso", n) and cat in ("sweet","pantry"): return "drinks"
    if re.search(r"\bjus\b|smoothie|swirl", n) and cat in ("fresh","dairy"): return "drinks"
    if cat == "drinks":
        if re.search(r"prosecco|vin |rouge|blanc|négroamaro|negroamaro|trebbiano|severino|75 ?cl", n): return "wine"
        if re.search(r"bière|pils|leffe|jupiler|stella|limoncello|fernet|sambuca|bitter|aperitivo|\bgin\b|whisky|rhum|vodka", n): return "beer"
    if cat == "fresh" and re.search(r"soupe|velouté|potage", n): return "ready"
    if cat == "fresh" and re.search(r"pêches|cocktail de fruits|passata|pulpe|tomates|artichauts", n) and re.search(r"\d+ ?g|sirop|jus", n): return "pantry"
    if cat == "meat" and re.search(r"burrata|fromage|mozzarella", n): return "dairy"
    if cat == "meat" and re.search(r"nocciolata|tartiner", n): return "sweet"
    return cat

STAPLES = ["oeufs","kefir","yaourt-grec","cottage","mozzarella","burrata","parmesan","gouda","creme","avoine","beurre","poulet","saumon",
           "jambon","pates","riz","huile","tomates","asiatique","noix","chips","chocolat","tartiner","cafe","the","cola","biere","bulles",
           "papier","vaisselle","lessive","nettoyant","douche","mains","shampoing","deo","dentaire","rasage","fruits","surgeles"]

def clean_name(n):
    n = re.sub(r"\s*\|\s*", " · ", n).strip()
    return n[0].upper() + n[1:] if n else n

items, skipped = [], collections.Counter()
def add(s, p, offer_text, code, brand, cat, end, img, hb, link, ns, size):
    o = parse_offer(offer_text, p["price"])
    if o["kind"] == "nonprice" or (o["kind"] == "unknown" and not o["raw"]) or o["raw"].lower() == "nouveau":
        skipped[o["raw"] or "(vide)"] += 1; return
    name = clean_name(p["name"])
    x = dict(s=s, n=name, b=brand, c=cat, p=p["price"], u=p.get("ppu") or "", z=size, k=s + code, code=code,
             pr=o["label"], raw=o["raw"], e=end, ok=1 if o["ok"] else 0, q=o["q"], img=img, hb=hb, l=link, ns=ns)
    if o["ok"]:
        x.update(tot=o["tot"], pe=o["pe"], d=o["d"])
        if o.get("mix"): x["mix"] = 1
        if o.get("tier"): x["tier"] = o["tier"]
    else:
        x.update(q=1, d=None, why=o.get("why", ""))
    items.append(x)

for p in D["promos"]:
    if p.get("price") is None or not p.get("promo"): continue
    add("d", p, p["promo"], p["code"], p["brand"] or "Delhaize", refine(D_MAP.get(p["cat"], "pantry"), p["name"]), p["end"] or "",
        D["thumbs"].get(p["code"], ""), p["brand"] == "Delhaize",
        "https://www.delhaize.be" + p["url"] if p.get("url") else "https://www.delhaize.be/fr/p/" + p["code"], NS.get(p["code"], ""), p.get("size") or "")
for p in C["promos"]:
    tags = p.get("tags") or ""
    if not tags or p.get("price") is None: continue
    m = re.search(r"jusqu.au (\d\d/\d\d)", tags)
    key = (p.get("img") or "").replace("https://cdn.carrefour.eu/420_", "").replace(".webp", "")
    add("c", p, tags.split(" Offre valable")[0], p["id"], p["brand"], refine(C_MAP.get(p["cat"], "pantry"), p["name"]), m[1] if m else "",
        CT.get(key, ""), bool(re.search(r"carrefour|simpl|no brand|produits blancs|the market", p["brand"], re.I)),
        f"https://www.carrefour.be/fr/{p['id']}.html", "", "")

# de-duplicate identical rows
seen, uniq = set(), []
for x in items:
    k = (x["s"], x["n"], x["p"], x["pr"])
    if k in seen: continue
    seen.add(k); uniq.append(x)
items = uniq
# stable id per product (basket, hidden items and history survive weekly refreshes)
kc = collections.Counter()
for x in items:
    kc[x["k"]] += 1
    if kc[x["k"]] > 1: x["k"] += f"-{kc[x['k']]}"

for x in items:
    x["t"] = typeof(x["n"] + " " + x["b"], x["c"])
    un = unit(x["u"])
    x["f"] = form_of(x["t"], x["n"] + " " + x["b"], un[1] if un else None)
    x["dish"] = is_dish(x["n"])
    x["v"], x["uu"] = (un if un else (None, ""))
    x["ev"] = round(x["v"] * x["pe"] / x["p"], 3) if un and x["ok"] else None

# display-only title, pack size and pack noun (matching above and below keeps the retailer name in x["n"])
VOCAB = name_vocab([x["n"] for x in items] + [h["name"] for h in D["house"] + C["house"]])
for x in items:
    dn, sz = display_name(x["n"], VOCAB, strip_size=not x["z"])
    if dn != x["n"]: x["dn"] = dn
    x["z"] = fmt_size(x["z"]) if x["z"] else sz
    pk = pack_noun(x["n"], x["z"])
    if pk: x["pk"] = list(pk)

# house-brand references, per store, typed and formed like the promos
house = {"d": [], "c": []}
for s, src in (("d", D["house"]), ("c", C["house"])):
    for h in src:
        if not h.get("price") or not h.get("ppu"): continue
        if s == "c" and re.search(r"home|baby", h.get("brand", ""), re.I): continue
        un = unit(h["ppu"])
        if not un: continue
        nm = h["name"] + " " + h.get("brand", "")
        t = typeof(nm, refine((D_MAP if s == "d" else C_MAP).get(h.get("cat"), "pantry"), h["name"]))
        if not t or t in ("vin", "fruits"): continue
        code = h["code"] if s == "d" else h["id"]
        house[s].append(dict(n=clean_name(h["name"]), p=h["price"], v=un[0], u=un[1], t=t, f=form_of(t, nm, un[1]), dish=is_dish(h["name"]),
            code=code, nb=s == "d" and NS.get(code, "") in ("A", "B") and not h.get("promo"),
            l=f"https://www.delhaize.be/fr/p/{code}" if s == "d" else f"https://www.carrefour.be/fr/{code}.html"))
by_type = collections.defaultdict(list)
for s in house:
    for h in house[s]: by_type[(s, h["t"])].append(h)

def out_ref(h):
    if not h: return None
    r = dict(n=h["n"], p=h["p"], v=h["v"], u=h["u"], l=h["l"])
    if h["nb"]: r["nb"] = 1
    return r

for x in items:
    x["fl"] = " · ".join(FORM_LABEL.get(f, f) for f in (x["f"] or "").split("|") if f) if x["f"] else ""
    x["ref"] = {s: out_ref(match_ref(x, by_type[(s, x["t"])])) for s in ("d", "c")}
    rb = match_ref(x, by_type[("d", x["t"])], boost=True)
    if rb and x["ref"]["d"] and rb["n"] != x["ref"]["d"]["n"]: x["refb"] = out_ref(rb)
    # why there is no same-store reference (shown as "Pas de comparaison fiable")
    if not x["ref"][x["s"]]:
        x["nr"] = ("type" if not x["t"] else "nocmp" if x["t"] in NO_COMPARE else "unit" if not x["v"] else "form" if x["f"] is None else "none")
    del x["code"], x["dish"]
    if x["f"] is None: x["f"] = ""
    if not x["ref"]["d"] and not x["ref"]["c"]: x["ref"] = {}

# history: one compact snapshot per week in <data-dir>/history.json -> "new this week", "often on promo", "base price up"
wk = (D.get("pulled") or "")[:10]
HIST_PATH = f"{SRC}/history.json"
try: hist = json.load(open(HIST_PATH))
except (OSError, ValueError): hist = {}
prevs = sorted((w for w in hist if w < wk), reverse=True)[:4]
for x in items:
    if not prevs: break
    if x["k"] not in hist[prevs[0]]: x["nw"] = 1
    seen_w = [hist[w][x["k"]] for w in prevs if x["k"] in hist[w]]
    if len(seen_w) >= 3: x["hx"] = len(seen_w)
    if any(x["p"] > old[0] * 1.03 for old in seen_w): x["up"] = 1
if wk and (wk not in hist or REWRITE_HIST):
    hist[wk] = {x["k"]: [x["p"], x["d"] or 0] for x in items}
    hist = {w: hist[w] for w in sorted(hist)[-12:]}
    try: json.dump(hist, open(HIST_PATH, "w"), separators=(",", ":"))
    except OSError: json.dump(hist, open(f"{OUT}/history.json", "w"), separators=(",", ":"))
    print("history: snapshot", wk, "written")
else:
    print("history: unchanged (snapshot", wk, "already stored; --rewrite-history to replace it)")

# non-perishables worth stocking up on at >= 33 % off
STOCK = ["papier","vaisselle","lessive","nettoyant","douche","mains","shampoing","deo","dentaire","rasage","pates","riz","huile",
         "tomates","asiatique","sauce-pates","cafe","the","chocolat","noix","tartiner","sucre","biere","bulles","vin","spiritueux",
         "cola","eau","bonbons","biscuits","barres","chips"]
# category of each family (for the essentials editor), from this week's promos then house-brand lists
tcat = {}
for t in {x["t"] for x in items if x["t"]}:
    tcat[t] = collections.Counter(x["c"] for x in items if x["t"] == t).most_common(1)[0][0]
tcat.update({"poulet": "meat", "saumon": "meat", "poisson": "meat"})

types_out = {k: [e, l] for k, e, l, *_ in TYPES}
out = dict(items=items, cats=CATS, types=types_out, staples=STAPLES, stock=STOCK, tcat=tcat, hist=bool(prevs), pulled=D.get("pulled"))
json.dump(out, open(f"{OUT}/data.json", "w"), ensure_ascii=False, separators=(",", ":"))
tpl = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "template-fr.html")).read()
html = tpl.replace("__DATA__", json.dumps(out, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/"))
open(f"{OUT}/promo-board.html", "w", encoding="utf-8").write(html)  # claude.ai artifact (adds its own <head>)
open(f"{OUT}/index.html", "w", encoding="utf-8").write(  # standalone web page (GitHub Pages)
    '<!doctype html>\n<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
    '<meta name="description" content="Promos de la semaine Delhaize et Carrefour Market comparées aux marques maison.">'
    '<link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>🛒</text></svg>">'
    '</head><body style="margin:0">\n' + html + '\n</body></html>\n')
print("items", len(items), "d", sum(x["s"]=="d" for x in items), "c", sum(x["s"]=="c" for x in items))
print("with img", sum(bool(x["img"]) for x in items), "typed", sum(bool(x["t"]) for x in items))
print("with same-store house ref", sum(bool(x["ref"].get(x["s"])) for x in items), "any ref", sum(bool(x["ref"]) for x in items))
print("offer not interpreted", collections.Counter(x["raw"] for x in items if not x["ok"]).most_common(10))
print("skipped (not a price offer)", skipped.most_common(10))
print("untyped sample (first 15)", [x["n"] for x in items if not x["t"]][:15])
print("type counts", collections.Counter(x["t"] for x in items).most_common())
