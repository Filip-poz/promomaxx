"""Pure promo logic: offer arithmetic, product families, product forms and house-brand matching.

No file I/O here so tests can feed small fixtures. build.py does the reading and writing.
"""
import re, unicodedata

# ---------------------------------------------------------------- offers
# One model for every offer: buy `q` packs of the regular price `p`, pay `tot`.
# Derived: per-pack price tot/q and discount 1 - tot/(q*p) against the same quantity at regular price.
# Anything we cannot read reliably comes back with ok=False and no derived numbers.

APO = r"l['’`]? ?"          # "l'achat", "l' achat", "l’achat"
MAX_PLAUSIBLE = 0.75        # above this the parse is more likely wrong than the deal real

def _num(s):
    return float(s.replace(",", "."))

def _clean_offer(text):
    t = re.sub(r"\s+", " ", (text or "").replace("_", " ")).strip()
    h = len(t) // 2   # Carrefour repeats the label: "2 + 2 gratuits 2 + 2 gratuits"
    if h and t[:h].strip() == t[h:].strip():
        t = t[:h].strip()
    return t

def eur_fr(v):
    s = f"{v:.2f}".replace(".", ",")
    return s[:-3] if s.endswith(",00") else s

def parse_offer(text, price):
    """-> dict(ok, kind, q, tot, label, raw[, why, tier, mix])"""
    raw = _clean_offer(text)
    t = raw.lower()
    out = dict(ok=False, kind="unknown", q=1, tot=None, label=raw, raw=raw)
    if not raw:
        out["why"] = "offre vide"; return out
    if re.search(r"livraison", t):
        out.update(kind="nonprice", why="avantage en ligne, pas une réduction en magasin"); return out
    if not price or price <= 0:
        out["why"] = "prix habituel inconnu"; return out
    p = price
    m = re.match(r"^(\d+) ?\+ ?(\d+)(?: ?(?:gratuits?|gratis)+)?$", t)
    if m:
        a, b = int(m[1]), int(m[2])
        out.update(kind="nplusm", q=a + b, tot=a * p, label=f"{a}+{b} gratuit" + ("s" if b > 1 else ""))
    m = None if out["kind"] != "unknown" else re.match(r"^(\d+) ?(?:ème|eme|e|de) (?:à|a) -? ?(\d+(?:[.,]\d+)?) ?%$", t)
    if m:
        n, pc = int(m[1]), _num(m[2]) / 100
        out.update(kind="nth", q=n, tot=(n - 1) * p + p * (1 - pc), label=f"{n}e à −{eur_fr(pc*100)} %")
    m = None if out["kind"] != "unknown" else re.match(r"^(\d+) ?= ?-(\d+(?:[.,]\d+)?) ?%((?: ?\| ?\d+ ?= ?-\d+(?:[.,]\d+)? ?%)*)$", t)
    if m:   # tiered "2 = -20% | 4 = -30%": the first tier is what you must buy at minimum
        n, pc = int(m[1]), _num(m[2]) / 100
        tiers = re.findall(r"(\d+) ?= ?-(\d+(?:[.,]\d+)?) ?%", m[3] or "")
        out.update(kind="tier", q=n, tot=n * p * (1 - pc), label=f"−{eur_fr(pc*100)} % à l'achat de {n}" if n > 1 else f"−{eur_fr(pc*100)} %")
        if tiers:
            out["tier"] = " · ".join(f"−{eur_fr(_num(b))} % à l'achat de {a}" for a, b in tiers)
    m = None if out["kind"] != "unknown" else re.match(r"^-? ?(\d+(?:[.,]\d+)?) ?%(?: (?:pour|à " + APO + r"achat de) (\d+)(?: produits?)?)?$", t)
    if m:
        pc, n = _num(m[1]) / 100, int(m[2] or 1)
        out.update(kind="pct", q=n, tot=n * p * (1 - pc), label=f"−{eur_fr(pc*100)} %" + (f" à l'achat de {n}" if n > 1 else ""))
    m = None if out["kind"] != "unknown" else re.match(r"^(\d+) ?(?:produits?|achetés)? ?(?:pour|=) ?€? ?(\d+(?:[.,]\d+)?) ?€?$", t)
    if m:
        n, x = int(m[1]), _num(m[2])
        out.update(kind="for", q=n, tot=x, label=(f"{n} pour {eur_fr(x)} €" if n > 1 else f"{eur_fr(x)} € au lieu de {eur_fr(p)} €"))
    m = None if out["kind"] != "unknown" else re.match(r"^- ?€? ?(\d+(?:[.,]\d+)?) ?€?(?: à " + APO + r"achat de (\d+)(?: produits?)?)?$", t)
    if m:
        x, n = _num(m[1]), int(m[2] or 1)
        out.update(kind="off", q=n, tot=n * p - x, label=f"−{eur_fr(x)} €" + (f" à l'achat de {n}" if n > 1 else ""))
    if out["kind"] == "unknown":
        out["why"] = "conditions non reconnues"; return out
    d = 1 - out["tot"] / (out["q"] * p)
    if d <= 0:
        out.update(ok=False, why="pas moins cher que le prix habituel"); return out
    if d > MAX_PLAUSIBLE:
        out.update(ok=False, why=f"remise calculée de {round(d*100)} %, invraisemblable"); return out
    tot = round(out["tot"] + 1e-9, 2)   # half-up, like a till: 3.885 -> 3.89
    out.update(ok=True, tot=tot, d=round(1 - tot / (out["q"] * p), 4), pe=round(tot / out["q"], 4))
    # "3 produits pour 5 €", "à l'achat de 3 produits": the offer may cover a mix of products.
    # We price it as q identical packs and say so.
    if out["q"] > 1 and (re.search(r"produits|achetés|à " + APO + "achat", t) or out["kind"] in ("nplusm", "nth", "tier", "for", "off")):
        out["mix"] = 1
    return out

def basket_total(offer, price, n):
    """Pay for n packs: complete offer bundles at the offer price, the rest at regular price (prudent)."""
    if not offer.get("ok"):
        return round(n * price, 2), 0
    q = offer["q"]
    full, rest = divmod(n, q)
    return round(full * offer["tot"] + rest * price, 2), rest

# ---------------------------------------------------------------- units
def unit(s):
    m = re.search(r"([\d.,]+)\s*€\s*/\s*(kg|l|pièce|pc|stuk|st|dose|dosis|m)\b", s or "", re.I)
    if not m: return None
    u = m.group(2).lower()
    u = {"pièce": "pc", "stuk": "pc", "st": "pc", "dosis": "dose"}.get(u, u)
    try:
        return (_num(m.group(1)), u)
    except ValueError:
        return None

# ---------------------------------------------------------------- families
# Composite foods: an ingredient named in a dish never makes the dish an ingredient reference.
DISH = re.compile(r"\bwraps?\b|sandwich|panini|tramezz|"
                  r"\bsalade\b|quiche|croque|gratin|\bplats?\b|bowl|pizza|tarte|feuillet|burger|nuggets|bruschett|risotto|arrabbiata|"
                  r"carbonara|bolognaise|soupe|velouté|potage|traiteur|bon appétit|sushi|pok[eé]\b|croquette|empanada|samoussa|\bwok\b|"
                  r"tapas|\bdip\b|tartinade|rillettes|mousse de|cake|bagel|focaccia|crêpe|hachis|parmentier|moussaka|cannelloni|"
                  r"tortiglioni .*(?:&|lardons)|spaghetti .*(?:&|bolo)|roulé|feuilleté|\bpain\b|biscuit|cracker|chips|snack|"
                  r"apéro|bouchées|gyoza|dumpling|dim sum|bao\b|spring roll|nems?\b|samosa|kebab|tacos|fajita|enchilada|"
                  r"\bsauce\b|pesto|vol.au.vent|wings|schnitzel|cordon|farci|garni|cuisiné|repas|\bsalad|lasagne (?:bolo|traiteur|légumes|saumon|épinards)", re.I)
FILLED = re.compile(r"ravioli|tortellini|cappelletti|girasoli|agnolotti|mezzelune|fagottini|lasagne|cannelloni", re.I)
INGREDIENT = {"oeufs","kefir","yaourt-grec","cottage","mozzarella","burrata","parmesan","raclette","gouda","chevre","creme","avoine",
              "beurre","poulet","saumon","poisson","jambon","lardons","riz","huile","tomates","noix","pates"}

TYPES = [
 # key, emoji, label, include regex, exclude regex
 ("oeufs","🥚","Œufs",r"\boeufs?\b|œufs?",r"choco|pâques|pâtes|lasagne|nouilles|minuteur|kinder|surprise|mayonnaise"),
 ("kefir","🥛","Kéfir",r"k[ée]fir",None),
 ("yaourt-grec","🥣","Yaourt grec & skyr",r"\bgrecs?\b|grecque|\bgreek\b|skyr",r"feta|pita|sauce|tzatziki|salade|olive"),
 ("burrata","🧀","Burrata & stracciatella",r"burrata|stracciatella",r"glace|gelato|chocolat|yaourt|grecque|skyr"),
 ("cottage","🥣","Cottage & fromage frais",r"cottage|fromage frais|maquée|plattekaas|fromage blanc|philadelphia|st môret|boursin|faisselle|quark",r"glace|dessert"),
 ("mozzarella","🧀","Mozzarella",r"mozzarella",r"pané|sticks|peperoncino|bites"),
 ("parmesan","🧀","Parmesan & grana",r"parmigiano|parmesan|grana padano|pecorino",r"biscuit|crackers?"),
 ("raclette","🧀","Raclette",r"raclette",r"appareil|grill|four"),
 ("chevre","🧀","Fromage de chèvre",r"chèvre|chavroux",None),
 ("gouda","🧀","Gouda & fromage en tranches",r"gouda|emmental|leerdammer|maasdam|cheddar|comté|brie|camembert|\bfromage\b",r"frais|chèvre|cottage|raclette|burrata|mozzarella|parmigiano|blanc|végé|vegan|veggie|style"),
 ("creme","🥛","Crème",r"crème (fraîche|culinaire|entière|liquide|légère|épaisse|à fouetter|cuisine|\d)|\bcrème\b.*\d\d ?%|\broom\b|mascarpone",r"glacée|dessert|corps|mains|visage|douche|soin|hydrat|chocolat|marrons|brûlée|caramel|vanille|pâtissière|solaire|anti|\bspf\b|gorgonzola"),
 ("avoine","🌾","Boisson à l'avoine",r"boisson.*avoine|avoine.*boisson|barista|haver|\boat\b|oatly",r"flocons|biscuit|barre|granola|porridge|cookie"),
 ("beurre","🧈","Beurre & margarine",r"\bbeurre\b|margarine|minarine|benecol|pro activ|becel|\bbutter\b",r"cacahu|biscuit|petit beurre|croissant|cookie|gaufre|sablé|pâte|karité|corps|cacao|peanut|cajou|amande|brioche|poulet|sauce|yaourt|drink|boisson"),
 ("poulet","🍗","Poulet",r"poulet|chicken|\bdinde\b",r"style|végé|vegan|veggie|plant|chick.?n|bouillon|spring|protein"),
 ("saumon","🐟","Saumon",r"saumon|salmon",r"chat|chien|croquettes"),
 ("poisson","🐟","Poisson blanc",r"cabillaud|\bsole\b|églefin|colin|merlu|lieu noir|\bpoisson\b",r"sticks|fish|chat|chien|huître"),
 ("lardons","🥓","Lardons",r"lardons|guanciale",r"style|végé|vegan|sauce"),
 ("jambon","🥓","Jambon & charcuterie",r"jambon|prosciutto|serrano|coppa|salami|saucisson|mortadel|chorizo|lomo|fuet|cacciatore|jamón|cerreta|pancetta|bresaola|filet de saxe|filet d'anvers",r"croquette|chips|style|végé|vegan"),
 ("saucisses","🌭","Saucisses & chipolatas",r"chipolata|saucisse|boudin|merguez",r"végé|plant|vegan|style"),
 ("veggie","🌱","Alternatives végétales",r"végé|vegan|veggie|végétal|plant|falafel|tofu|chick.?n|vuna|vivera|garden gourmet|style\b",r"lait|boisson|beurre|margarine|crème|yaourt|huile"),
 ("pizza","🍕","Pizza",r"pizza",r"sauce|fromage|four|pelle"),
 ("soupe","🍲","Soupe",r"soupe|potage|velouté|bouillon",r"dumpling|cube"),
 ("pates","🍝","Pâtes",r"spaghett|tortiglioni|rigatoni|tortellini|ravioli|fusilli|penne|farfalle|macaroni|maccheroni|linguine|tagliatelle|orzo|gnocchi|bucatini|orecchiette|capellini|casarec|cavatappi|fettuc|pennoni|lumache|puntalette|fedelini|girasoli|cappelletti|conchiglie|\bpâtes\b|pasta\b",r"sauce|plats?\b|bolognaise|pesto|arrabbiata|carbonara|lardons|&|gratin|salade|salad|traiteur|courgette|légume"),
 ("plats","🍲","Plats préparés",r"bowl|lasagne|vol-au-vent|vol au vent|bao\b|dumpling|gyoza|dim sum|spring roll|nuggets|wings|fish stick|curry|traiteur|wraps?\b|plats?\b|\bmaaltijd|parmentier|moussaka|cannelloni|hachis|risotto|arrabbiata|carbonara|bolognaise|chili con|tajine|couscous royal|paella",r"pâte de curry|curry paste|poudre"),
 ("riz","🍚","Riz",r"\briz\b|basmati|jasmin rice",r"galette|lait|soufflé|crème|scampi|chocolat|céréales|croustillant|vinaigre|nouilles|feuilles|pudding|gaufrettes|vermicelle"),
 ("huile","🫒","Huile d'olive & huile",r"\bhuile\b",r"corps|cheveux|soin|sèche|argan|massage|bébé|thon|sardine|maquereau|anchois|tomates séchées|artichaut"),
 ("tomates","🍅","Tomates en conserve & passata",r"passata|pulpe|coulis|tomates pelées|concassées|concentr|purée de tomate|polpa|tomates cerises|datterini|ciliegini",r"sauce|jus de"),
 ("sauce-pates","🍝","Sauces pour pâtes & pesto",r"sauce|pesto|sugo|bolognaise|arrabbiata",r"soja|poisson|huître|barbecue|ketchup|chips|mayonnaise|piquante|sriracha|wok|teriyaki|salade|vinaigrette"),
 ("asiatique","🥥","Coco, curry & cuisine asiatique",r"\bcoco\b|lait de coco|crème de coco|curry|pad thai|phad thai|ramen|nouilles|noodles|sauce.*poisson|huître|combava|soja|teriyaki|sriracha|wok",r"eau de coco|biscuit|chocolat|douche|shampo|déo|râpée|bowl|scampi|bounty|yaourt|boisson"),
 ("bonbons","🍬","Bonbons",r"bonbon|haribo|gomm|réglisse|sucette|chamallow|lutti|maoam|fruittella|chupa|frisk|pastilles|trolli|rebelle|mentos|tic tac",None),
 ("noix","🥜","Noix & fruits secs",r"\bnoix\b|cajou|amandes?\b|pistaches?|cacahu|noisettes?\b|pécan|soja grillé|raisins secs|mélange (?:de noix|apéro|étudiant)",r"pâte à tartiner|chocolat|cacao|beurre|déo|lait|biscuit|barre|douche|granola|candy|party|halloween|coco|muscade|huile|glace|boisson|crème|yaourt|céréales|muesli"),
 ("chips","🥔","Chips",r"\bchips\b|tortilla|bugles|pringles|doritos|nachos?\b",r"wrap|galettes? de"),
 ("tartiner","🍯","Pâte à tartiner, miel & confiture",r"tartiner|nocciolata|nutella|beurre de cacahu|pâte de cacahu|peanut butter|\bmiel\b|confiture|natù|tartimiel|choco ?pasta",r"pain d|épices|biscuit|bonbon|moutarde|fromage|douche|shampo|barres?\b|protéin|protein|croissant|donut|fourr|couque|gaufre|céréales|granola|noix grill|yaourt"),
 ("sucre","🍬","Sucre & édulcorants",r"édulcor|edulcor|stevia|canderel|cankao|sucralose|\bsucre\b",r"sans sucre|zero|bonbon|chocolat|gaufre|tarte"),
 ("barres","💪","Barres & protéines",r"\bbarres?\b|\bbars?\b|protéin|protein",r"chocolat (noir|au lait) \d|tablette|pâtes|bowl|boisson|yaourt|skyr"),
 ("chocolat","🍫","Chocolat",r"chocolat|côte d'or|galak|milka|kitkat|\blion\b|kinder|lindt|toblerone",r"boisson|chaud|céréales|cereals|pâte à tartiner|cookie|glace|bueno|croissant|donut|biscuit|koek|lait\b.*\d ?l|pain|muffin|brownie|gaufrette|wafer|pick ?up|granola"),
 ("biscuits","🍪","Biscuits",r"biscuit|gaufrette|pick ?up|petit beurre|beukelaer|speculoos|cookie|gaufre|bastogne|\bzoo\b|macaron|tarallucci|mulino|baiocchi|abbracci|canestrini|nascondini|pan di stelle|pain d'épices|koek",None),
 ("cafe","☕","Café",r"\bcaf[ée]\b|coffee|espresso|nespresso|dolce gusto|senseo|ristretto|lungo",r"glacé|liqueur|chocolat|caramel latte|cornet|glace|biscuit|boisson végétale|crème|cuillère|machine|tasse|tiramisu|bonbon"),
 ("the","🍵","Thé, thé glacé & kombucha",r"\bthé\b|ice ?tea|kombucha|lipton|yogi|infusion|tisane",r"théière|sirop|machine"),
 ("cola","🥤","Sodas & sirops",r"\bcola\b|coca|\bcoke\b|pepsi|fanta|sprite|\blimonade\b|lemonade|\bsoda\b|limonata|aranciata|ginger|pompelmo|vit-hit|tonic\b|\bsirop\b|\bsyrup\b|7 ?up|orangina|schweppes|lemon lime",r"chocolat|bonbon|chips|cylindre|cylinder|gin\b|rhum|rum|whisky|vodka|\bcake\b"),
 ("eau","💧","Eau",r"\beau\b|minérale|\bspa\b|volvic|pellegrino|evian|chaudfontaine|vittel",r"de coco|toilette|javel|micellaire|parfum|limonata|aranciata|déminéralisée|de rose|fleur d'oranger"),
 ("jus","🧃","Jus & smoothies",r"\bjus\b|smoothie|swirl|tropicana|innocent",None),
 ("biere","🍺","Bières",r"bière|\bpils\b|leffe|jupiler|stella|duvel|tripel|karmeliet|chouffe|hoegaarden|corona|vedett|lutgarde|ypra|lefort|victoria|liefmans|heineken|grimbergen|affligem|westmalle|chimay|orval|kriek|\bipa\b",None),
 ("spiritueux","🍸","Spiritueux, apéritifs & mocktails",r"\bgin\b|whisky|rhum|\brum\b|vodka|limoncello|fernet|sambuca|bitter|aperitivo|vermouth|martini|porto|cointreau|amaretto|sir james|mocktail|spritz|breezer|liqueur|bourbon|tequila|triple sec|disaronno|g&t|paloma|mojito|sapphire|tanqueray|cognac",None),
 ("bulles","🥂","Cava, prosecco & champagne",r"cava\b|prosecco|crémant|champagne|sekt|mousseux|sparkling|\bbrut\b|spumante",r"mocktail|spritz|0 ?%|sans alcool|non alcool"),
 ("vin","🍷","Vins",r".",None),  # fallback for wine category only
 ("surgeles","❄️","Herbes & légumes surgelés",r"haché|hachée|ciboulette|persil|coriandre|basilic|\bail\b|échalote|cerfeuil|légumes|romanesco|méditerran|épinards|haricots|petits pois|brocoli",r"sauce|pesto|chips|tomate|viande|boeuf|porc|poulet"),
 ("glace","🍨","Glaces",r"glace|ice cream|sorbet|\bstick\b|barattolino|bueno|magnum|cornet|gelato",None),
 ("pain","🍞","Pain & viennoiserie",r"pain|baguette|\bbuns?\b|pistolet|sandwich|graankorf|croissant|donut|ardennais|grof|brioche|wrap|tortilla",None),
 ("fruits","🍎","Fruits & légumes",r".",None),  # fallback for fresh
 # non-food: deodorant and dental before hair care and laundry ("spray", "booster" are not enough to say shampoo or detergent)
 ("deo","🌬️","Déodorant",r"déo|\bdeo|anti-?transpirant|bodyspray|body spray|spray (?:pour le )?corp",None),
 ("dentaire","🪥","Dentifrice & soins dentaires",r"dentifrice|brosse à dents|brosses? à dent|bain de bouche|brossettes|fil dentaire|soft-picks|dentaire|\bdents?\b|oral-?b|sensodyne|colgate|signal",None),
 ("rasage","🪒","Rasoirs & lames",r"rasoir|lames|rasage|gillette|wilkinson",None),
 ("papier","🧻","Papier toilette, essuie-tout & mouchoirs",r"papier toilette|papier hygiénique|toilette|essuie|rouleau|mouchoir|tissues?\b",r"nettoy|gel|bloc|eau de|essuie-glace|raclette|canard|wc"),
 ("vaisselle","🍽️","Lave-vaisselle & vaisselle",r"lave-?vaisselle|vaisselle|vaiselle|\bfinish\b|tablettes|capsules lave|dreft|\bpril\b|fairy|sun\b.*(?:tablet|caps|gel)",r"beauty|déo|deo|éponge|gants?\b|brosse"),
 ("lessive","👕","Lessive & adoucissant",r"lessive|adoucissant|assouplissant|détergent|lavages?\b|\bpods\b|parfum de linge|perles de parfum|ariel|\bdash\b|lenor|persil|omo\b|skip\b|dixan|unstoppables|washing",r"vaisselle|vaiselle|lave-vaisselle|voiture|mains|textile"),
 ("nettoyant","🧽","Nettoyants & accessoires",r"nettoy|désinfect|lingettes|éponge|lavette|serpill|swiffer|dégraiss|vileda|febreze|ambi pur|mr propre|textile|filtre|cylindre|cylinder|sodastream|javel|wc\b|détartr|vitres|sols\b|multi-?usages?",None),
 ("mains","🧼","Savon pour les mains",r"mains|handzeep|savon liquide|pompe",r"crème|gants?"),
 ("douche","🚿","Gel douche & bain",r"douche|savon|\bbain\b|lavant",r"bouche|serviette"),
 ("shampoing","🧴","Shampoing & soins cheveux",r"shampo|après-shampo|conditioner|masque cheveux|masq capillaire|masque\b|cheveux|capillaire|démêl|anti-noeuds|anti-mêlage|gliss|elsève|elseve|pantene|head ?& ?shoulders|garnier fructis|ogx|\bshampoo",r"brosse|peigne|sèche|lisseur|coloration"),
]
CTYPE = [(k, e, l, re.compile(r, re.I), re.compile(x, re.I) if x else None) for k, e, l, r, x in TYPES]
NONFOOD_T = {"mains","papier","vaisselle","lessive","nettoyant","douche","shampoing","deo","dentaire","rasage"}
NONFOOD_C = {"household","care"}
DAIRY = {"dairy"}
# a family only accepts products from plausible retailer categories (blocks "Romanesco Parmesan" in vegetables,
# wraps in ready meals, a wine called "Pecorino", ice cream with coffee...)
TYPE_CAT = {
 "vin":{"wine"}, "fruits":{"fresh"},
 "kefir":DAIRY, "yaourt-grec":DAIRY, "cottage":DAIRY, "mozzarella":DAIRY, "burrata":DAIRY, "parmesan":DAIRY,
 "raclette":DAIRY, "chevre":DAIRY, "gouda":DAIRY, "creme":DAIRY, "beurre":DAIRY, "oeufs":{"dairy","fresh"},
 "avoine":{"dairy","drinks"},
 "poulet":{"meat","frozen"}, "saumon":{"meat","frozen"}, "poisson":{"meat","frozen"}, "jambon":{"meat"},
 "lardons":{"meat"}, "saucisses":{"meat","frozen"},
 "riz":{"pantry"}, "huile":{"pantry"}, "tomates":{"pantry"}, "sauce-pates":{"pantry","dairy","ready"},
 "pates":{"pantry","dairy","ready","fresh"}, "asiatique":{"pantry","ready"},
 "cafe":{"drinks"}, "the":{"drinks"}, "cola":{"drinks"}, "eau":{"drinks"}, "jus":{"drinks","fresh"},
 "biere":{"beer","drinks"}, "spiritueux":{"beer","drinks","wine"}, "bulles":{"wine","drinks","beer"},
 "chips":{"snacks","pantry"}, "noix":{"snacks","pantry","fresh"},
 "papier":{"household","care"}, "vaisselle":{"household"}, "lessive":{"household"}, "nettoyant":{"household"},
 "deo":{"care"}, "dentaire":{"care"}, "rasage":{"care"}, "shampoing":{"care"}, "douche":{"care"}, "mains":{"care","household"},
}

def norm(s):
    s = unicodedata.normalize("NFD", s.lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")

def is_dish(name):
    return bool(DISH.search(name))

def _blocked(k, name, dish):
    if k not in INGREDIENT: return False
    return dish or (k != "pates" and bool(FILLED.search(name)))

def typeof(name, cat):
    nf = cat in NONFOOD_C
    dish = is_dish(name)
    for k, e, l, r, x in CTYPE:
        if (k in NONFOOD_T) != nf: continue
        if k in TYPE_CAT and cat not in TYPE_CAT[k]: continue
        if k in ("vin", "fruits"):
            return k
        if _blocked(k, name, dish): continue
        if r.search(name) and not (x and x.search(name)):
            return k
    return None

# ---------------------------------------------------------------- product forms
# Within a family, products only compare when every dimension agrees. A dimension with default None means
# "unknown form": such a product gets no reference at all (no comparison beats a wrong one).
FLAV = r"fraise|vanille|myrtille|framboise|fruits|citron|mangue|pêche|cerise|coco|miel|stracciatella|chocolat|caramel|banane|abricot|passion|pomme|poire|cassis|ananas|rhubarbe|figue|muesli|granola|speculoos|noisette|café|amande|grenade|kiwi|orange"
FORMS = {
 "oeufs": [([("cuits", r"cuit|\bdurs?\b|pic ?nic|mimosa|écalés"), ("crus", r".")], None)],
 "cafe": [([("caps", r"\bcaps\b|capsul|nespresso|dolce gusto|tassimo|\bcups?\b|\bk-?fee"), ("pads", r"\bpads?\b|dosettes?|senseo"),
           ("soluble", r"soluble|instant"), ("boisson", r"latte|frapp|ice coffee|glacé|cappuccino|boisson|prêt à boire"),
           ("grains", r"\bgrains?\b|bonen|beans"), ("moulu", r"moulu|gemalen|ground|filtre")], None),
          ([("dolcegusto", r"dolce gusto"), ("tassimo", r"tassimo"), ("std", r".")], None),
          ([("lait", r"cappuccino|latte|chococino|macchiato|au lait|flat white|cortado"), ("noir", r".")], None)],
 "vaisselle": [([("spray", r"spray"), ("sel", r"\bsel\b|rinçage|nettoyant machine|entretien|désodorisant"),
                ("lv-gel", r"gel.*lave|lave.*gel|\bgel\b"),
                ("lv-tabs", r"tablet|caps|capsul|quantum|ultimate|all ?in ?1|tabs|\bx ?\d+\b|\d+ ?x\b|lave-?vaisselle|finish"),
                ("main", r"liquide|dreft|fairy|pril|maxpower|quickwash|vaisselle|vaiselle")], None)],
 "lessive": [([("parfum", r"parfum de linge|perles"), ("caps", r"pods|capsul|caps\b|discs"), ("poudre", r"poudre"),
              ("detachant", r"détachant|vanish|booster|oxi"), ("liquide", r"washing|lessive|liquide de lavage|détergent"),
              ("adoucissant", r"adoucissant|assouplissant|softener|lenor"), ("liquide", r"liquide|\bgel\b|lavages?\b")], None)],
 "riz": [([("cuit", r"micro-?ondes|\bprêt|express|\b\d ?min|(?<!pré)cuit\b|pouch|sachet cuisson rapide|à réchauffer"),
          ("risotto", r"arborio|risotto|carnaroli"), ("parfume", r"basmati|jasmin|thaï|thai\b"), ("complet", r"complet|brun|integral"),
          ("sec", r"\briz\b")], None)],
 "huile": [([("olive-ve", r"vierge|virgin"), ("olive", r"olive"), ("friture", r"friture|frying|tournesol|colza|arachide|frit|wok|végétale|pépins"),
            ], None)],
 "cola": [([("sirop", r"sirop|syrup"), ("cola", r"\bcola\b|coca|\bcoke\b|pepsi(?!.*(?:lime|lemon|orange))"),
           ("tonic", r"tonic|ginger|bitter lemon"), ("soda", r".")], None),
          ([("canette", r"canette|boite|boîte|\bcans?\b|33 ?cl|330 ?ml|25 ?cl|250 ?ml|15 ?x|\d+ ?x ?\d+ ?(?:cl|ml)"), ("bouteille", r".")], None),
          ([("zero", r"zero|zéro|light|diet|sans sucre|no sugar|max\b"), ("sucre", r".")], None)],
 "the": [([("glace", r"ice ?tea|thé glacé|iced|\bpet\b|\d ?(?:cl|l)\b|\bcan\b|\d+ ?ml"), ("kombucha", r"kombucha"), ("infusion", r"infusion|tisane|rooibos|camomille|verveine"), ("the", r"thé|\btea\b|yogi|lipton")], None)],
 "mozzarella": [([("bufala", r"bufala|buffl"), ("rapee", r"râp|rapé|grated|cubes|pizza|shred|julienne"), ("boule", r".")], None)],
 "parmesan": [([("parmigiano", r"parmigiano|parmesan|reggiano"), ("grana", r"grana"), ("pecorino", r"pecorino")], None),
              ([("rape", r"râp|rapé|grated|pétales|copeaux|scaglie|flocons|frais 3 ?x"), ("bloc", r".")], None)],
 "burrata": [([("burrata", r"burrata"), ("stracciatella", r"stracciatella")], None)],
 "cottage": [([("cottage", r"cottage"), ("blanc", r"maquée|faisselle|quark|plattekaas|fromage blanc"),
              ("frais", r"fromage frais|philadelphia|st môret|boursin|tartiner")], None)],
 "raclette": [([("tranches", r"tranch"), ("bloc", r".")], None)],
 "creme": [([("liquide", r"liquide|culinaire|cuisine|fouetter|entière|légère|\broom\b|\d\d ?%"), ("epaisse", r"épaisse|fraîche|crème"), ("mascarpone", r"mascarpone")], None),
           ([("legere", r"\b(?:[5-9]|1\d|2[0-4])(?:[.,]\d)? ?%|légère|light|allégée"), ("entiere", r".")], None)],
 "beurre": [([("marg", r"margarine|minarine|benecol|pro activ|becel|plant|végétal|tartiner|halvarine"), ("beurre", r"beurre|butter")], None)],
 "avoine": [([("barista", r"barista"), ("boisson", r".")], None)],
 "poulet": [([("tranches", r"tranch|charcut|rôti cuit|fumé|\bcuit\b|haché cuit|blanc de (?:poulet|dinde)"), ("hache", r"haché"),
             ("cuisse", r"cuisse|pilon|drumstick|ailes|ailerons"), ("entier", r"entier|\bpoulet fermier\b$"),
             ("filet", r"filet|escalope|blanc|émincé|aiguillette|lanières|brochette|suprême")], None)],
 "saumon": [([("fume", r"fum"), ("filet", r"filet|pavé|dos|portion|steak|tranche|frais|atlantique")], None)],
 "poisson": [([("pane", r"pané|panure|meunière|beignet"), ("filet", r".")], None)],
 "lardons": [([("italien", r"guanciale|pancetta"), ("lardons", r".")], None)],
 "jambon": [([("cuit", r"saucisson de jambon|saucisson cuit|biggie|jambon cuit|\bcuit\b|cotto"), ("sec", r"salami|saucisson|chorizo|fuet|cacciatore|lomo|coppa|mortadel|pancetta|bresaola|filet de saxe|filet d'anvers"),
             ("cru", r"cru|serrano|prosciutto|parme|jamón|ibérique|ardenn|fumé|cerreta|bayonne|forêt|crudo|speck|\bsecs?\b|séché"),
             ("cuit", r"cuit|cotto|york|blanc|jambon|braisé|torchon")], None)],
 "pates": [([("farcies", r"ravioli|tortellini|cappelletti|girasoli|agnolotti|mezzelune|fagottini|\bfarci"), ("gnocchi", r"gnocchi"),
            ("fraiches", r"fraîch|fresh|frais\b"), ("sans-gluten", r"sans gluten|gluten free"),
            ("completes", r"complet|integral|whole|épeautre|lentilles|pois chiche"), ("seches", r".")], None)],
 "tomates": [([("concentre", r"concentr"), ("passata", r"passata|coulis|purée|passée|tamisée"),
              ("pulpe", r"pulpe|concass|polpa|morceaux|\bdés\b|cubes"), ("entieres", r"pelées|entières|cerises|datterini|ciliegini")], None)],
 "yaourt-grec": [([("skyr", r"skyr"), ("grec", r".")], None), ([("arome", FLAV), ("nature", r".")], None)],
 "kefir": [([("arome", FLAV), ("nature", r".")], None)],
 "gouda": [([("rape", r"râp|rapé|grated"), ("tranches", r"tranch|slices|plak"), ("bloc", r".")], None)],
 "chips": [([("mais", r"tortilla|nacho|bugles|doritos|maïs"), ("tuiles", r"pringles|tuiles|soufflé|crackers"), ("pdt", r".")], None),
           ([("paprika", r"paprika"), ("bbq", r"bbq|barbecue"), ("poivre", r"poivre|pepper"), ("fromage", r"fromage|cheese|nacho"),
             ("chili", r"chili|piment|spicy"), ("vinaigre", r"vinaigre|vinegar"), ("ketchup", r"ketchup"), ("?", r"burger|pickle|bolognese|truffe|oignon|onion|herbes|crème|korean|thai|wasabi"),
             ("nature", r"nature|naturel|\bsel\b|salé|salted|salt|classic|original|roasted")], None)],
 "noix": [([("melange", r"mélange|melange|\bmix\b|cocktail|raisin|apéro|étudiant"), ("pistache", r"pistache"), ("cajou", r"cajou"), ("amande", r"amande"), ("cacahuete", r"cacahu|arachide"), ("noisette", r"noisette"),
           ("pecan", r"pécan|pecan"), ("macadamia", r"macadamia"), ("soja", r"soja"),
           ("noix", r"\bnoix\b")], None),
          ([("patisserie", r"effil|poudre|moulu|hach|émond|bâtonnet"), ("nature", r"nature|naturel|non sal|crue|blanch"), ("aromatise", r".")], None)],
 "chocolat": [([("blanc", r"chocolat blanc|\bblanc\b|white"), ("noir", r"noir|dark|fondant|extra bitter|\d\d ?%"), ("lait", r"lait|milk")], None),
              ([("garni", r"noisette|amande|praliné|caramel|framboise|fruit|nougat|coco|\briz\b|cereal|céréale|biscuit|menthe|orange|\bsel\b|fourr|truff|café|avocat|vanille|banane|&|cacahu|speculoos|crisp|mini"),
                ("tablette", r".")], None)],
 "tartiner": [([("cacahuete-choco", r"(?=.*(?:cacahu|peanut))(?=.*(?:cacao|choco))"), ("miel", r"\bmiel\b"),
                ("confiture", r"confiture|gelée|marmelade|natù(?!.*(?:cacahu|noisette|tartiner))"), ("cacahuete", r"cacahu|peanut"),
               ("choco", r"choco|noisette|nocciolata|nutella|tartiner|pasta")], None)],
 "bulles": [([("champagne", r"champagne"), ("mousseux", r".")], None)],
 "papier": [([("mouchoirs", r"mouchoir|tissue|zakdoek"), ("essuie", r"essuie|keuken|cuisine"), ("toilette", r"toilette|wc|rouleau")], None)],
 "shampoing": [([("sec", r"\bsec\b|dry shampoo"), ("apres", r"après|apres|conditioner|démêl|baume"), ("masque", r"masque|masq|mask"),
                ("soin", r"spray|sérum|serum|huile|sans rinçage|lotion|anti-noeuds|anti-mêlage|leave"), ("shampoing", r"shampo")], None)],
 "deo": [([("roll", r"roll|bille"), ("stick", r"stick|baume"), ("spray", r"spray|aérosol|atomiseur|deospray|bodyspray|\d+ ?ml")], None)],
 "dentaire": [([("recharge", r"brossettes|recharges?\b|têtes?\b|\bio\b"), ("inter", r"soft-picks|interdent|fil dentaire|flosser"), ("brosse", r"brosse|bosse|brush"), ("bain", r"bain de bouche|mouthwash|listerine"),
               ("dentifrice", r"dentifrice|dentrifice|toothpaste|sérum|gel")], None)],
 "rasage": [([("lames", r"lames|recharge|cartouche"), ("mousse", r"mousse|gel|crème|baume|after"), ("rasoir", r"rasoir|razor")], None)],
 "asiatique": [([("coco", r"lait de coco|crème de coco|coco milk|\bcoco\b"), ("nouilles", r"nouilles|ramen|noodles|udon|soba"),
                ("pate", r"pâte|paste"), ("sauce", r"sauce|soja|teriyaki|sriracha")], None)],
 "biere": [([("sans", r"(?<![\d,.])0[.,]\d ?%|(?<![\d,.])0 ?%|0[.,]0\b|sans alcool|alcoholvrij|alcohol free|\bfree\b"), ("biere", r".")], None)],
}
CFORMS = {t: [([(lab, re.compile(rx, re.I)) for lab, rx in opts], dflt) for opts, dflt in dims] for t, dims in FORMS.items()}

UNIT_FORM = {("the", "the", "l"): "glace", ("the", "infusion", "l"): "glace"}   # Lipton "Peach · Can" priced per litre is a drink

def form_of(t, name, u=None):
    """Form label for a product within its family. '' = family has no form split, None = form unknown."""
    if not t or t not in CFORMS: return ""
    parts = []
    for opts, dflt in CFORMS[t]:
        lab = next((lab for lab, rx in opts if rx.search(name)), dflt)
        if lab is None or lab == "?": return None
        parts.append(UNIT_FORM.get((t, lab, u), lab))
    return "|".join(parts)

FORM_LABEL = {"caps":"capsules","pads":"dosettes","soluble":"soluble","grains":"grains","moulu":"moulu","boisson":"boisson prête à boire",
              "lv-tabs":"tablettes lave-vaisselle","lv-gel":"gel lave-vaisselle","main":"liquide vaisselle","spray":"spray","sel":"sel / rinçage",
              "adoucissant":"adoucissant","parfum":"parfum de linge","poudre":"poudre","liquide":"liquide","detachant":"détachant",
              "risotto":"riz à risotto","parfume":"riz parfumé","complet":"riz complet","sec":"sec",
              "olive-ve":"olive vierge extra","olive":"olive","friture":"friture","sirop":"sirop","cola":"cola","tonic":"tonic","soda":"soda",
              "zero":"sans sucre","sucre":"sucré","glace":"thé glacé","kombucha":"kombucha","infusion":"infusion","the":"thé",
              "bufala":"bufala","rapee":"râpée","boule":"boule","parmigiano":"parmigiano","grana":"grana padano","pecorino":"pecorino",
              "rape":"râpé","bloc":"morceau","burrata":"burrata","stracciatella":"stracciatella","blanc":"fromage blanc","frais":"fromage frais",
              "epaisse":"crème épaisse","mascarpone":"mascarpone","marg":"margarine","beurre":"beurre","barista":"barista",
              "tranches":"tranches","hache":"haché","cuisse":"cuisses","entier":"entier","filet":"filet","fume":"fumé","pane":"pané",
              "cru":"cru","cuit":"cuit","farcies":"pâtes farcies","fraiches":"pâtes fraîches","sans-gluten":"sans gluten","completes":"complètes",
              "seches":"pâtes sèches","concentre":"concentré","passata":"passata","pulpe":"pulpe","entieres":"tomates entières",
              "skyr":"skyr","grec":"yaourt grec","arome":"aromatisé","nature":"nature","mais":"maïs","tuiles":"tuiles","pdt":"pomme de terre",
              "miel":"miel","confiture":"confiture","cacahuete":"cacahuète","cacahuete-choco":"cacahuète-chocolat","gnocchi":"gnocchi","italien":"guanciale / pancetta","lardons":"lardons","cuits":"cuits","crus":"crus","dolcegusto":"Dolce Gusto","tassimo":"Tassimo","std":"","lait":"au lait","noir":"","canette":"canettes","bouteille":"bouteille","paprika":"paprika","bbq":"barbecue","poivre":"poivre","fromage":"fromage","chili":"piquant","vinaigre":"vinaigre","ketchup":"ketchup","pistache":"pistaches","cajou":"cajou","amande":"amandes","noisette":"noisettes","pecan":"pécan","macadamia":"macadamia","soja":"soja","melange":"mélange","noix":"noix","patisserie":"pâtisserie","aromatise":"assaisonnées","garni":"garni","legere":"légère","entiere":"entière","tablette":"tablette","recharge":"brossettes","inter":"interdentaire","choco":"pâte chocolat","champagne":"champagne","mousseux":"mousseux",
              "mouchoirs":"mouchoirs","essuie":"essuie-tout","toilette":"papier toilette","apres":"après-shampoing","masque":"masque",
              "soin":"soin cheveux","shampoing":"shampoing","roll":"roll-on","stick":"stick","brosse":"brosse","bain":"bain de bouche",
              "dentifrice":"dentifrice","lames":"lames","mousse":"mousse / gel","rasoir":"rasoir","coco":"lait de coco","nouilles":"nouilles",
              "pate":"pâte","sauce":"sauce","sans":"sans alcool","biere":"bière"}

# generic attributes that must agree in every family
ATTRS = [re.compile(r, re.I) for r in (r"\bbio\b|organic", r"sans lactose|lactose free|lactofree", r"light|allégé|(?<![\d,.])0 ?%|zéro|zero|sans sucre",
         r"hygi[eè]ne|intime|incontinen", r"sans gluten|gluten free", r"végan|vegan|végétal|plant", r"lait cru")]

# ---------------------------------------------------------------- house-brand matching
STOP = set("avec sans pour nature natur classic classique extra bio eco fairtrade pack mini maxi grand grande petit petite pieces piece stuks "
           "fresh frais fraiche douce doux original gout saveur arome assortiment selection market carrefour delhaize simpl brand "
           "produits blancs bonbon barre chip chocolat sauce pate pates alimentaire confiture douche shampooing tartiner papier brosse "
           "dent creme boisson biscuit gaufre glace jambon fromage tranche gel lavant savon liquide tablette noir lait vegetal vegan "
           "veggie care protect soft essential women biere beer bouteille canette blonde lavage recharge refill bouteille qualite filiere "
           "kwaliteitsketen trattoria".split())
STOP |= {w.rstrip("s") for w in STOP}
BROAD = {"noix","sauce-pates","plats","biscuits","bonbons","chocolat","barres","spiritueux","vin","douche","shampoing","jambon","veggie",
         "asiatique","gouda","tartiner","cola","the","jus","nettoyant","surgeles","pain","glace","soupe","pizza","biere","bulles",
         "sucre","dentaire","fruits","lessive","chevre","eau","deo","mains"}

# families too heterogeneous for a fair house-brand comparison (a spring roll is not a wrap, leeks are not soup)
NO_COMPARE = {"plats", "soupe", "pain", "pizza", "veggie", "glace", "vin", "fruits", "spiritueux"}

def toks(n):
    return {w for w in (v.rstrip("s") for v in re.findall(r"[a-z]{4,}", norm(n))) if w not in STOP and len(w) > 3}

def comparable(x, h):
    """Why house product h is not a valid reference for promo x (None = valid)."""
    if h.get("code") and h.get("code") == x.get("code"): return "même produit"
    if h["t"] != x["t"]: return "famille"
    if x["f"] is None or h["f"] is None: return "format inconnu"
    if h["f"] != x["f"]: return "format"
    if h["u"] != x["uu"]: return "unité"
    if h["dish"] != x["dish"]: return "plat préparé"
    if [bool(a.search(h["n"])) for a in ATTRS] != [bool(a.search(x["n"])) for a in ATTRS]: return "attribut"
    lo, hi = (0.4, 2.0) if x["uu"] == "pc" else (0.15, 3.0)   # "€/pièce" mixes packs and units: stay close
    if not (lo * x["v"] <= h["v"] <= hi * x["v"]): return "prix unitaire hors plage"
    return None

def match_ref(x, cands, boost=False):
    """Cheapest valid house-brand reference for promo x among cands (same store), or None.
    x: dict(n, t, f, uu, v, dish[, code]); cands: dicts(n, t, f, u, v, dish, nb[, code])."""
    if not x.get("t") or x.get("f") is None or not x.get("v") or x["t"] in NO_COMPARE: return None
    ok = [h for h in cands if comparable(x, h) is None]
    if not ok: return None
    pt = toks(x["n"])
    scored = [(len(pt & toks(h["n"])), h) for h in ok]
    best = max(o for o, _ in scored)
    if best == 0 and x["t"] in BROAD: return None   # broad family: needs a shared meaningful word
    pool = [h for o, h in scored if o == best]
    pool.sort(key=lambda h: h["v"] * (0.9 if boost and h.get("nb") else 1))
    return pool[0]

# ---------------------------------------------------------------- display names (presentation only, never used for matching)
# Conservative clean-up: the retailer wording stays available in the details. Nothing is guessed:
# capitals are only lowered for words the corpus itself writes in lowercase, sizes are only moved, never changed.
SIZE_END = re.compile(r"\s+((?:\d+\s*[x×]\s*)?\d+(?:[.,]\d+)?\s*(?:kg|gr|g|ml|cl|dl|l)\b\.?)\s*$", re.I)
ACRO = {"dop": "DOP", "igp": "IGP", "aop": "AOP", "aoc": "AOC", "doc": "DOC", "docg": "DOCG", "xl": "XL", "xxl": "XXL", "bbq": "BBQ", "uht": "UHT"}

def fmt_size(z):
    """'340G' -> '340 g', '4X115g' -> '4 × 115 g', '350 gr' -> '350 g', '14 pc' -> '14 pièces', '1.5L' -> '1,5 l'."""
    z = re.sub(r"\s+", " ", (z or "").strip().rstrip("."))
    if not z: return ""
    m = re.fullmatch(r"(\+/- ?)?(?:(\d+)\s*[x×]\s*)?(\d+(?:[.,]\d+)?)\s*([a-zè]+)", z, re.I)
    if not m: return z
    approx, n, v, u = m.groups()
    u = {"gr": "g", "pc": "pièces", "pcs": "pièces", "st": "pièces"}.get(u.lower(), u.lower())
    if u == "pièces" and v == "1": u = "pièce"
    return f"{'± ' if approx else ''}{n + ' × ' if n else ''}{v.replace('.', ',')} {u}"

def name_vocab(names):
    """Words the retailers themselves write in lowercase somewhere (not as first word), at least twice."""
    c = {}
    for n in names:
        for w in re.findall(r"[^\W\d_][\w'’-]*", n)[1:]:
            if w.islower(): c[w] = c.get(w, 0) + 1
    return {w for w, k in c.items() if k >= 2}

def _word(w, lead, vocab, shouting):
    lw = w.lower()
    if lw in ACRO: return ACRO[lw]
    if shouting and len(w) >= 4 and w.isupper() and w.isalpha():   # all-caps title: PENNONI LISCI -> Pennoni lisci
        return w.capitalize() if lead else lw
    return w

def display_name(name, vocab=frozenset(), strip_size=False):
    """-> (title, size_moved_out). A '·' segment whose first word the retailers write in lowercase elsewhere
    reads as a continuation and is joined ('Jambon · Fumé' -> 'Jambon fumé'); other wording is left as is."""
    name = re.sub(r"\s+", " ", name or "").strip()
    size = ""
    if strip_size:
        m = SIZE_END.search(name)
        if m and m.start() > 0:
            size, name = fmt_size(m.group(1)), name[:m.start()].strip(" ,-·")
    words = re.findall(r"[^\W\d_]+", name)
    shouting = sum(w.isupper() and len(w) > 1 for w in words) > len(words) / 2
    segs = []
    for s in (p.strip() for p in name.split("·")):
        if s and (not segs or s.casefold() != segs[-1].casefold()): segs.append(s)   # "Chips · Chips"
    segs = [[_word(w, i == 0 and j == 0, vocab, shouting) for j, w in enumerate(s.split(" "))] for i, s in enumerate(segs)]
    cont = lambda w: w.islower() or (w[:1].isupper() and w[1:].islower() and w.lower() in vocab)
    if len(segs) > 1 and all(cont(ws[0]) for ws in segs[1:]):   # all or nothing, so the title reads one way
        for ws in segs[1:]: ws[0] = ws[0].lower()
        t = " ".join(" ".join(ws) for ws in segs)
    else:
        t = " · ".join(" ".join(ws) for ws in segs)
    return (t[:1].upper() + t[1:], size)

# what one "unit" of the offer is, only when the product text says it
CONTAINER = [("canette", "canettes"), ("bouteille", "bouteilles"), ("bocal", "bocaux"), ("tube", "tubes"), ("sachet", "sachets"),
             ("boîte", "boîtes"), ("brique", "briques"), ("barquette", "barquettes"), ("flacon", "flacons"), ("pot", "pots")]
MULTI = re.compile(r"\b\d+\s*[x×]\s*\d+(?:[.,]\d+)?\s*(?:kg|gr|g|ml|cl|l)\b|\bpack\b", re.I)
PIECES = re.compile(r"\b([2-9]|\d{2,})\s*(?:pc|pcs|pièces?|pieces?|rouleaux|capsules|dosettes|lingettes|doses|lames|x)(?![\w])", re.I)

def pack_noun(name, size=""):
    """(singular, plural) for one pack of the offer, or None when the text does not say (the page then says 'unité')."""
    txt = f"{name} {size}"
    if MULTI.search(txt): return ("pack", "packs")
    if PIECES.search(txt): return ("paquet", "paquets")
    low = norm(name)
    for sg, pl in CONTAINER:
        if re.search(rf"\b(?:{norm(sg)}|{norm(pl)})\b", low): return (sg, pl)
    return None
