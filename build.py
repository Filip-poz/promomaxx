import json, re, sys, collections

import os
SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__))
OUT = sys.argv[2] if len(sys.argv) > 2 else SRC
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

def unit(s):
    m = re.search(r"([\d.,]+)\s*€\s*/\s*(kg|l|pièce|pc|stuk|st|dose|dosis|m)\b", s or "", re.I)
    if not m: return None
    u = m.group(2).lower()
    u = {"pièce":"pc","stuk":"pc","st":"pc","dosis":"dose"}.get(u, u)
    return (float(m.group(1).replace(",", ".")), u)

def deal(p, price):
    p = re.sub(r"\s+", " ", p.replace("_", " ")).strip()
    m = re.match(r"(\d+) ?\+ ?(\d+)", p)
    if m: a, b = int(m[1]), int(m[2]); return b/(a+b), a+b
    m = re.match(r"(\d)(?:ème|e|de) (?:à|a|tegen|aan) -(\d+) ?%", p)
    if m: n = int(m[1]); return int(m[2])/100/n, n
    m = re.match(r"(\d+) = -(\d+) ?%", p)
    if m: return int(m[2])/100, int(m[1])
    m = re.match(r"-([\d.,]+) ?%(?: (?:pour|à l'achat de|voor) (\d+))?", p)
    if m: return float(m[1].replace(",", "."))/100, int(m[2] or 1)
    m = re.match(r"(\d+) (?:produits? |achetés )?(?:pour|voor|=) ?€? ?([\d.,]+) ?€?", p)
    if m:
        n, tot = int(m[1]), float(m[2].replace(",", "."))
        return max(0, 1 - tot/(n*price)), n
    m = re.match(r"- ?€? ?([\d.,]+) ?€?(?: (?:à l'achat de|pour|bij aankoop van) (\d+)?)?", p)
    if m:
        off = float(m[1].replace(",", ".")); n = int(m[2] or 1)
        return min(.9, off/(n*price)), n
    return 0, 1

def pretty(p):
    p = re.sub(r"\s+", " ", p.replace("_", " ")).strip()
    p = re.sub(r"(\d) ?\+ ?(\d) ?(gratuit|gratis)?", r"\1+\2 gratuit", p)
    p = re.sub(r"(\d)(?:ème|e) à ", r"\1e à ", p)
    p = re.sub(r"(\d+) produits? pour €([\d.]+)", lambda m: f"{m[1]} pour {m[2].replace('.', ',')} €", p)
    p = p.replace("-33.34%", "-33%")
    return p.replace("-", "−")

TYPES = [
 ("oeufs","🥚","Œufs",r"\boeufs?\b|œufs?",r"choco|pâques|pâtes|lasagne|nouilles|minuteur"),
 ("kefir","🥛","Kéfir",r"k[ée]fir",None),
 ("yaourt-grec","🥣","Yaourt grec & skyr",r"grec|skyr",r"feta|pita|sauce|tzatziki"),
 ("cottage","🥣","Cottage & fromage frais",r"cottage|fromage frais",None),
 ("mozzarella","🧀","Mozzarella",r"mozzarella",r"pizza|pané|sauce|chips|sticks|peperoncino"),
 ("burrata","🧀","Burrata & stracciatella",r"burrata|stracciatella",None),
 ("parmesan","🧀","Parmesan & grana",r"parmigiano|parmesan|grana padano|pecorino",r"chips|sauce|biscuit|pâtes"),
 ("raclette","🧀","Raclette",r"raclette",None),
 ("gouda","🧀","Gouda & fromage en tranches",r"gouda|tranches|emmental|leerdammer|fromage",r"frais|chèvre|cottage|raclette|burrata|mozzarella|parmigiano|pain|chips|pâtes|sauce|pizza"),
 ("chevre","🧀","Fromage de chèvre",r"chèvre|chavroux",None),
 ("creme","🥛","Crème",r"crème (fraîche|culinaire|entière|liquide|légère|\d)|\bcrème\b.*\d\d ?%|room",r"glacée|dessert|corps|mains|visage|douche|soin|hydrat|chocolat|marrons"),
 ("avoine","🌾","Boisson à l'avoine",r"boisson.*avoine|avoine.*boisson|barista|haver",r"flocons|biscuit|barre|granola"),
 ("beurre","🧈","Beurre & margarine",r"\bbeurre\b|margarine|benecol|pro activ",r"cacahu|biscuit|petit beurre|croissant|cookie|gaufre|sablé|pâte|karité|corps"),
 ("poulet","🍗","Poulet",r"poulet|chicken",r"style|végé|vegan|veggie|plant|soupe|bouillon|chips|pizza|nuggets|bowl|gyoza|dumpling|spring|wings|burger|pasta|salad|protein|curry|wrap|sandwich|croque"),
 ("saumon","🐟","Saumon",r"saumon",None),
 ("poisson","🐟","Poisson blanc",r"cabillaud|\bsole\b|églefin|colin|merlu|poisson",r"soupe|sauce|sticks|fish"),
 ("jambon","🥓","Jambon & charcuterie",r"jambon|prosciutto|serrano|coppa|salami|saucisson|mortadel|chorizo|lomo|fuet|cacciatore|jamón|ardennais",r"pizza|pâtes|croquette"),
 ("lardons","🥓","Lardons",r"lardons|guanciale",None),
 ("saucisses","🌭","Saucisses & chipolatas",r"chipolata|saucisse|boudin",r"végé|plant"),
 ("veggie","🌱","Alternatives végétales",r"végé|vegan|veggie|végétal|plant|falafel|tofu|chick.?n|vuna|vivera|garden gourmet",r"lait|boisson|beurre|margarine"),
 ("pizza","🍕","Pizza",r"pizza",r"sauce|fromage"),
 ("soupe","🍲","Soupe",r"soupe|potage|velouté",r"dumpling"),
 ("plats","🍲","Plats préparés",r"bowl|lasagne|vol-au-vent|vol au vent|bao|dumpling|gyoza|dim sum|spring roll|nuggets|wings|fish stick|curry.*riz|riz.*curry|traiteur",None),
 ("pates","🍝","Pâtes",r"spaghetti|tortiglioni|rigatoni|tortellini|ravioli|fusilli|penne|farfalle|macaroni|maccheroni|linguine|tagliatelle|orzo|gnocchi|bucatini|orecchiette|capellini|casarec|cavatappi|fettuc|pennoni|lumache|puntalette|fedelini|spaghettoni|pâtes",r"sauce|plat|bolognaise|pesto"),
 ("riz","🍚","Riz",r"\briz\b",r"galette|lait|soufflé|crème|curry|scampi|chocolat"),
 ("huile","🫒","Huile d'olive & huile",r"huile",r"corps|cheveux|soin|sèche"),
 ("tomates","🍅","Tomates en conserve & passata",r"passata|pulpe|coulis|tomates pelées|concassées|concentr|purée de tomate|polpa|tomates cerises|datterini|ciliegini",r"sauce"),
 ("sauce-pates","🍝","Sauces pour pâtes & pesto",r"sauce|pesto|sugo|bolognaise|arrabbiata",r"soja|poisson|huître|barbecue|ketchup|chips"),
 ("asiatique","🥥","Coco, curry & cuisine asiatique",r"coco|curry|pad thai|phad thai|ramen|nouilles|sauce.*poisson|huître|combava|keffir|citron vert",r"eau de coco|biscuit|chocolat|douche|shampo|déo|noix de coco râpée|bowl|scampi"),
 ("bonbons","🍬","Bonbons",r"bonbon|haribo|gomm|réglisse|sucette|chamallow|lutti|maoam|fruittella|chupa|frisk|pastilles|trolli|rebelle|fini",None),
 ("noix","🥜","Noix & fruits secs",r"noix|cajou|amande|pistache|cacahu|noisette|pécan|soja grillé|raisins",r"pâte à tartiner|chocolat au lait|beurre|déo|lait|biscuit|barre|douche|granola|candy|party|halloween"),
 ("chips","🥔","Chips",r"chips|tortilla|bugles",None),
 ("tartiner","🍯","Pâte à tartiner, miel & confiture",r"tartiner|nocciolata|cacahu.*(pâte|beurre)|beurre de cacahu|pâte de cacahu|miel|confiture|natù|tartimiel",r"pain d|épices|biscuit|bonbon"),
 ("sucre","🍬","Sucre & édulcorants",r"édulcor|edulcor|stevia|canderel|cankao|sucralose|sucre",r"sans sucre|zero|bonbon|chocolat"),
 ("barres","💪","Barres & protéines",r"barre|\bbar\b|protéin|protein",r"chocolat (noir|au lait) \d|tablette|pâtes|bowl|boisson"),
 ("chocolat","🍫","Chocolat",r"chocolat|côte d'or|galak|milka|kitkat|lion|pick up|kinder",r"boisson|chaud|céréales|pâte à tartiner|cookie|glace|bueno|croissant|donut|biscuit|koek"),
 ("biscuits","🍪","Biscuits",r"biscuit|petit beurre|beukelaer|speculoos|cookie|gaufre|bastogne|zoo|macaron|tarallucci|mulino|baiocchi|abbracci|canestrini|nascondini|pan di stelle|pain d'épices|koek",None),
 ("cafe","☕","Café",r"café|coffee|espresso|capsules|dosettes|grains",r"glacé|liqueur|chocolat|caramel latte"),
 ("the","🍵","Thé, thé glacé & kombucha",r"\bthé\b|ice tea|kombucha|lipton|yogi",None),
 ("cola","🥤","Sodas",r"cola|coke|fanta|sprite|limonade|soda|limonata|aranciata|ginger|pompelmo|vit-hit|sodastream",None),
 ("eau","💧","Eau",r"\beau\b|minérale|spa\b|volvic|pellegrino",r"de coco|toilette|javel|micellaire|parfum|limonata|aranciata"),
 ("jus","🧃","Jus & smoothies",r"\bjus\b|smoothie|swirl|tropicana",None),
 ("biere","🍺","Bières",r"bière|pils|leffe|jupiler|stella|duvel|tripel|karmeliet|chouffe|hoegaarden|corona|vedett|lutgarde|ypra|lefort|victoria|liefmans",None),
 ("spiritueux","🍸","Spiritueux, apéritifs & mocktails",r"\bgin\b|whisky|rhum|vodka|limoncello|fernet|sambuca|bitter|aperitivo|vermouth|martini|porto|cointreau|amaretto|sir james|mocktail|spritz|breezer|liqueur|bourbon",None),
 ("bulles","🥂","Cava, prosecco & champagne",r"cava|prosecco|crémant|champagne|sekt|mousseux|sparkling|brut",r"mocktail|spritz"),
 ("vin","🍷","Vins",r".",None),  # fallback for wine category only
 ("surgeles","❄️","Herbes & légumes surgelés",r"haché|hachée|ciboulette|persil|coriandre|basilic|ail|échalote|cerfeuil|légumes|romanesco|méditerran",r"sauce|pesto|chips|tomate"),
 ("glace","🍨","Glaces",r"glace|ice cream|sorbet|stick|barattolino|bueno",None),
 ("pain","🍞","Pain & viennoiserie",r"pain|baguette|bun|pistolet|sandwich|graankorf|croissant|donut|ardennais|grof",None),
 ("fruits","🍎","Fruits & légumes",r".",None),  # fallback for fresh
 ("papier","🧻","Papier toilette, essuie-tout & mouchoirs",r"papier toilette|toilette|essuie|rouleau|mouchoir",r"nettoy|gel|bloc"),
 ("vaisselle","🍽️","Lave-vaisselle & vaisselle",r"lave-vaisselle|vaisselle|finish|tablettes|capsules lave",None),
 ("lessive","👕","Lessive & adoucissant",r"lessive|adoucissant|détergent|lavage|pods|booster|parfum de linge|ariel|dash|lenor",None),
 ("nettoyant","🧽","Nettoyants & accessoires",r"nettoy|désinfect|lingettes|éponge|serpillière|swiffer|dégraiss|vileda|febreze|ambi pur|mr propre|textile|filtre|cylindre|sodastream",None),
 ("mains","🧼","Savon pour les mains",r"mains|handzeep|savon liquide|pompe",r"crème"),
 ("douche","🚿","Gel douche & bain",r"douche|savon|bain|lavant",r"bouche"),
 ("shampoing","🧴","Shampoing & soins cheveux",r"shampo|après-shampo|conditioner|masque|cheveux|capillaire|démêlant|spray",None),
 ("deo","🌬️","Déodorant",r"déo|anti-transpirant|bodyspray|body spray|transpirant",None),
 ("dentaire","🪥","Dentifrice & soins dentaires",r"dentifrice|brosse|bain de bouche|brossettes|fil dentaire|soft-picks|dentaire|bouche",None),
 ("rasage","🪒","Rasoirs & lames",r"rasoir|lames|rasage",None),
]
TYPE_CAT = {"vin":{"wine"}, "fruits":{"fresh"}}
STAPLES = ["oeufs","kefir","yaourt-grec","cottage","mozzarella","burrata","parmesan","gouda","creme","avoine","beurre","poulet","saumon",
           "jambon","pates","riz","huile","tomates","asiatique","noix","chips","chocolat","tartiner","cafe","the","cola","biere","bulles",
           "papier","vaisselle","lessive","nettoyant","douche","mains","shampoing","deo","dentaire","rasage","fruits","surgeles"]
CTYPE = [(k, e, l, re.compile(r, re.I), re.compile(x, re.I) if x else None) for k, e, l, r, x in TYPES]

NONFOOD_T = {"mains","papier","vaisselle","lessive","nettoyant","douche","shampoing","deo","dentaire","rasage"}
NONFOOD_C = {"household","care"}
def typeof(name, cat):
    nf = cat in NONFOOD_C
    for k, e, l, r, x in CTYPE:
        if (k in NONFOOD_T) != nf: continue
        if k in TYPE_CAT and cat not in TYPE_CAT[k]: continue
        if k == "vin" or k == "fruits":
            return k
        if r.search(name) and not (x and x.search(name)):
            return k
    return None

def clean_name(n):
    n = re.sub(r"\s*\|\s*", " · ", n).strip()
    return n[0].upper() + n[1:] if n else n

items, unparsed = [], collections.Counter()
for p in D["promos"]:
    if not p.get("promo") or p.get("price") is None: continue
    d, q = deal(p["promo"], p["price"])
    if d <= 0: unparsed[p["promo"]] += 1; continue
    cat = refine(D_MAP.get(p["cat"], "pantry"), p["name"])
    items.append(dict(s="d", n=clean_name(p["name"]), b=p["brand"] or "Delhaize", c=cat, p=p["price"], u=p["ppu"] or "", z=p.get("size") or "",
        k="d" + p["code"], pr=pretty(p["promo"]), raw=p["promo"], e=p["end"] or "", d=round(d, 4), q=q,
        img=D["thumbs"].get(p["code"], ""), hb=(p["brand"] == "Delhaize"),
        l="https://www.delhaize.be" + p["url"] if p.get("url") else "https://www.delhaize.be/fr/p/" + p["code"], ns=NS.get(p["code"], "")))
for p in C["promos"]:
    tags = p.get("tags") or ""
    if not tags: continue
    promo = tags.split(" Offre valable")[0].strip()
    h = len(promo) // 2
    if promo[:h].strip() == promo[-h:].strip(): promo = promo[:h].strip()
    m = re.search(r"jusqu.au (\d\d/\d\d)", tags)
    end = m[1] if m else ""
    d, q = deal(promo, p["price"])
    if d <= 0: unparsed[promo] += 1; continue
    cat = refine(C_MAP.get(p["cat"], "pantry"), p["name"])
    key = (p.get("img") or "").replace("https://cdn.carrefour.eu/420_", "").replace(".webp", "")
    brand = p["brand"]
    items.append(dict(s="c", n=clean_name(p["name"]), b=brand, c=cat, p=p["price"], u=p["ppu"] or "", z="",
        k="c" + p["id"], pr=pretty(promo), raw=promo, e=end, d=round(d, 4), q=q, img=CT.get(key, ""),
        hb=bool(re.search(r"carrefour|simpl|no brand|produits blancs|the market", brand, re.I)),
        l=f"https://www.carrefour.be/fr/{p['id']}.html", ns=""))

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

# house brand reference: cheapest unit price per (store, type, unit)
house = collections.defaultdict(list)
for s, src in (("d", D["house"]), ("c", C["house"])):
    for h in src:
        if not h.get("price") or not h.get("ppu"): continue
        if s == "c" and re.search(r"home|baby", h.get("brand", ""), re.I): continue
        un = unit(h["ppu"])
        if not un: continue
        t = typeof(h["name"] + " " + h.get("brand", ""), refine((D_MAP if s == "d" else C_MAP).get(h.get("cat"), "pantry"), h["name"]))
        if not t or t in ("vin", "fruits"): continue
        nb = s == "d" and NS.get(h.get("code"), "") in ("A", "B") and not h.get("promo")
        link = f"https://www.delhaize.be/fr/p/{h['code']}" if s == "d" else f"https://www.carrefour.be/fr/{h['id']}.html"
        house[(s, t, un[1])].append(dict(n=clean_name(h["name"]), p=h["price"], v=un[0], u=un[1], nb=nb, l=link))

import unicodedata
STOP = set("avec sans pour nature natur classic extra bio eco fairtrade pack mini maxi grand grande petit petite pièces piece pieces stuks fresh frais fraîche douce doux original gout goût saveur arôme assortiment selection sélection market carrefour delhaize simpl brand produits blancs bonbon barre chip chocolat sauce pate pates alimentaire confiture douche shampooing tartiner papier brosse dent creme boisson biscuit gaufre glace jambon fromage tranche gel lavant savon liquide tablette noir lait vegetal vegan veggie care protect soft essential women biere beer bouteille canette blonde lavage recharge refill fle bouteille".split())
def toks(n):
    n = unicodedata.normalize("NFD", n.lower()); n = "".join(c for c in n if unicodedata.category(c) != "Mn")
    return {w for w in (v.rstrip("s") for v in re.findall(r"[a-z]{4,}", n)) if w not in STOP and len(w) > 3}
BROAD = {"noix","sauce-pates","plats","biscuits","bonbons","chocolat","barres","spiritueux","vin","douche","shampoing","jambon","veggie",
         "asiatique","gouda","parmesan","tartiner","cola","the","jus","nettoyant","surgeles","pain","glace","soupe","pizza","poulet",
         "biere","bulles","sucre","dentaire","fruits","huile","lessive","creme","beurre"}
FORMS = [re.compile(r, re.I) for r in (r"capsul|nespresso|dolce gusto|tassimo", r"dosette|\bpads?\b|senseo", r"\bgrains?\b|bonen",
         r"brosse|éponge|\bgants?\b", r"hygi[eè]ne|intime|incontinen|adulte", r"mouchoir|tissue", r"sirop", r"vierge",
         r"soluble|instant", r"olive", r"friture|frying|tournesol|colza|arachide", r"lingette", r"pods|capsules? lessive|caps\b",
         r"bio\b", r"sans lactose|lactose free", r"light|0 ?%|zéro|zero")]
def ref_for(x, s, boost=False):
    un = unit(x["u"])
    if not un or not x["t"]: return None
    cands = [h for h in house.get((s, x["t"], un[1]), [])]
    # ignore implausible matches far below or above the promo item's own unit price
    lo, hi = (0.4, 2) if un[1] == "pc" else (0.15, 3)   # "€/pièce" mixes packs and units: stay close
    cands = [h for h in cands if lo*un[0] <= h["v"] <= hi*un[0]]
    # product form must agree (capsules vs ground coffee, olive vs frying oil...)
    xf = [bool(f.search(x["n"])) for f in FORMS]
    cands = [h for h in cands if [bool(f.search(h["n"])) for f in FORMS] == xf]
    if not cands: return None
    pt = toks(x["n"])
    scored = [(len(pt & toks(h["n"])), h) for h in cands]
    best_ov = max(o for o, _ in scored)
    if best_ov == 0 and x["t"] in BROAD: return None
    pool = [h for o, h in scored if o == best_ov]
    eff = lambda h: h["v"]*(0.9 if boost and h["nb"] else 1)
    pool.sort(key=eff)
    h = pool[0]
    r = dict(n=h["n"], p=h["p"], v=h["v"], u=h["u"], l=h["l"])
    if h["nb"]: r["nb"] = 1
    return r

for x in items:
    un = unit(x["u"])
    x["ev"] = round(un[0]*(1-x["d"]), 3) if un else None
    x["uu"] = un[1] if un else ""
    x["ref"] = {s: ref_for(x, s) for s in ("d", "c")}
    rb = ref_for(x, "d", True)
    if rb and x["ref"]["d"] and rb["n"] != x["ref"]["d"]["n"]: x["refb"] = rb
    if x["hb"]:
        for key in ("ref", "refb"):
            if key in x and x[key] and isinstance(x[key], dict):
                tgt = x[key] if key == "refb" else x[key].get(x["s"])
                if tgt and tgt.get("n") == x["n"]:
                    if key == "ref": x["ref"][x["s"]] = None
                    else: del x["refb"]
    del x["raw"]

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
if wk:
    hist[wk] = {x["k"]: [x["p"], x["d"]] for x in items}
    hist = {w: hist[w] for w in sorted(hist)[-12:]}
    try: json.dump(hist, open(HIST_PATH, "w"), separators=(",", ":"))
    except OSError: json.dump(hist, open(f"{OUT}/history.json", "w"), separators=(",", ":"))

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
    '<link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>🏷️</text></svg>">'
    '</head><body style="margin:0">\n' + html + '\n</body></html>\n')
print("items", len(items), "d", sum(x["s"]=="d" for x in items), "c", sum(x["s"]=="c" for x in items))
print("with img", sum(bool(x["img"]) for x in items), "typed", sum(bool(x["t"]) for x in items))
print("with same-store house ref", sum(bool(x["ref"][x["s"]]) for x in items), "any ref", sum(any(x["ref"].values()) for x in items))
print("unparsed", unparsed.most_common(15))
print("untyped sample (first 15)", [x["n"] for x in items if not x["t"]][:15])
print("type counts", collections.Counter(x["t"] for x in items).most_common())
