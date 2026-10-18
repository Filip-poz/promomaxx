"""Regression tests for offer arithmetic, classification and house-brand matching.

Run: python3 -m pytest tests -q
Small inline fixtures only (no scrape files, no images).
"""
import json, os, subprocess, sys
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from promo import parse_offer, basket_total, typeof, form_of, is_dish, match_ref, unit  # noqa: E402


# ---------------------------------------------------------------- offers
@pytest.mark.parametrize("text,price,q,tot,d", [
    ("1+1 gratis", 4.00, 2, 4.00, 0.5),
    ("1+1_gratis", 4.00, 2, 4.00, 0.5),
    ("2+1 Gratis", 3.00, 3, 6.00, 0.3333),
    ("2 + 2 gratuits 2 + 2 gratuits", 2.03, 4, 4.06, 0.5),          # Carrefour repeats its label
    ("3 + 3 gratuits", 1.00, 6, 3.00, 0.5),
    ("2ème à -50%", 2.59, 2, 3.89, 0.249),                          # 2.59 + 1.295, rounded like a till
    ("3ème à -60% 3ème à -60%", 5.00, 3, 12.00, 0.2),
    ("3 produits pour €5.5", 2.00, 3, 5.50, 0.0833),
    ("2 achetés = 5€ 2 achetés = 5€", 3.49, 2, 5.00, 0.2837),
    ("1 produit pour €2.99", 3.59, 1, 2.99, 0.1671),
    ("-25%", 2.00, 1, 1.50, 0.25),
    ("-15%_pour 3", 2.00, 3, 5.10, 0.15),
    ("-3€ à l'achat de 2 -3€ à l'achat de 2", 19.99, 2, 36.98, 0.075),
    ("-2€ -2€", 17.99, 1, 15.99, 0.1112),
    ("2 = -20% |_4 = -30%", 2.15, 2, 3.44, 0.2),
])
def test_offer_formats(text, price, q, tot, d):
    o = parse_offer(text, price)
    assert o["ok"], o
    assert o["q"] == q
    assert o["tot"] == pytest.approx(tot, abs=0.005)
    assert o["d"] == pytest.approx(d, abs=0.001)
    assert o["pe"] == pytest.approx(o["tot"] / q, abs=1e-4)


def test_sodastream_euro_off_for_three():
    # "€6.99 off when buying 3": 3 x 6.99 = 20.97, pay 13.98, i.e. 4.66 each and 33.33 % off. It used to show ~90 %.
    o = parse_offer("- €6.99 à l' achat de 3 produits", 6.99)
    assert o["ok"] and o["kind"] == "off"
    assert o["q"] == 3
    assert o["tot"] == pytest.approx(13.98)
    assert o["pe"] == pytest.approx(4.66)
    assert o["d"] == pytest.approx(0.3333, abs=1e-4)
    assert o["mix"] == 1                                  # may cover several products: assumption is made explicit
    assert o["label"] == "−6,99 € à l'achat de 3"


def test_bundle_discount_never_applied_to_one_item():
    # same text, the quantity must come from the offer, not default to 1
    for text in ("- €6.99 à l'achat de 3 produits", "- €6.99 à l’achat de 3 produits", "-6,99€ à l'achat de 3"):
        assert parse_offer(text, 6.99)["q"] == 3, text


def test_tier_keeps_next_level_as_information():
    o = parse_offer("1 = -15% |_2 = -25%", 4.89)
    assert o["q"] == 1 and o["d"] == pytest.approx(0.15, abs=1e-3)
    assert "−25 % à l'achat de 2" in o["tier"]


@pytest.mark.parametrize("text,price,kind", [
    ("Nouveau", 3.0, "unknown"),
    ("Prix choc en magasin", 3.0, "unknown"),
    ("2produits = livraison gratuite", 9.99, "nonprice"),
    ("", 3.0, "unknown"),
])
def test_unknown_offers_make_no_claim(text, price, kind):
    o = parse_offer(text, price)
    assert not o["ok"] and o["kind"] == kind
    assert "d" not in o and o["tot"] is None


def test_implausible_discount_is_rejected_not_clamped():
    o = parse_offer("- €10 à l' achat de 1 produit", 9.99)     # more than the price
    assert not o["ok"] and "d" not in o
    o = parse_offer("5 pour 1€", 3.00)                         # 93 % off: a misread, not a deal
    assert not o["ok"] and "invraisemblable" in o["why"]
    o = parse_offer("1 produit pour €9.9", 9.85)               # not cheaper than regular
    assert not o["ok"]


def test_basket_total_prices_incomplete_bundles_at_regular_price():
    o = parse_offer("1+1 gratis", 4.00)
    assert basket_total(o, 4.00, 2) == (4.00, 0)
    assert basket_total(o, 4.00, 1) == (4.00, 1)               # does not qualify
    assert basket_total(o, 4.00, 3) == (8.00, 1)               # one bundle + one at regular price
    soda = parse_offer("- €6.99 à l' achat de 3 produits", 6.99)
    assert basket_total(soda, 6.99, 6) == (27.96, 0)
    assert basket_total(parse_offer("bizarre", 2.0), 2.0, 2) == (4.0, 0)


def test_unit_parsing():
    assert unit("15,89 €/l") == (15.89, "l")
    assert unit("0,36 €/pc") == (0.36, "pc")
    assert unit("5,99 €/pièce") == (5.99, "pc")
    assert unit("0,20 €/dose") == (0.20, "dose")
    assert unit("") is None and unit("prix au poids") is None


# ---------------------------------------------------------------- classification
@pytest.mark.parametrize("name,cat,not_t", [
    ("Bon Appétit! Wraps Saumon Fumé, Concombre & Fromage Frais 210 g Carrefour", "ready", "cottage"),
    ("Bon Appétit! Wraps Saumon Fumé, Concombre & Fromage Frais 210 g Carrefour", "dairy", "cottage"),
    ("Trattoria Ravioli Burrata, Pesto & Mortadella Bologna 250 g Carrefour", "ready", "burrata"),
    ("Trattoria Ravioli Burrata, Pesto & Mortadella Bologna 250 g Carrefour", "dairy", "burrata"),
    ("Tortiglioni Arrabbiata Lardons & Grana Padano 400 g Carrefour", "dairy", "parmesan"),
    ("Tortiglioni Arrabbiata Lardons & Grana Padano 400 g Carrefour", "ready", "pates"),
    ("Romanesco · Parmesan Delhaize", "frozen", "parmesan"),
    ("Spray vaiselle · Citron Dreft", "household", "shampoing"),
    ("Deospray · Beauty finish Dove", "care", "shampoing"),
    ("Chocolat chaud · Bomb duo marshmallow", "drinks", "cola"),
    ("Bun · Multigrains · Sans lactose", "bakery", "cafe"),
    ("Dentifrice · sérum · booster blanchissant", "care", "lessive"),
    ("Yaourt à boire · Fraise Benecol", "dairy", "beurre"),
    ("Cornet Vanille Café Delhaize", "frozen", "cafe"),
    ("Extra Yaourt à la Grecque Stracciatella 4 x 150 g", "dairy", "burrata"),
])
def test_classification_mistakes(name, cat, not_t):
    assert typeof(name, cat) != not_t


@pytest.mark.parametrize("name,cat,t", [
    ("Spray vaisselle · Recharge · Citron Dreft", "household", "vaisselle"),
    ("Déodorant spray · Advanced care Dove", "care", "deo"),
    ("Shampooing · Classic Head & Shoulders", "care", "shampoing"),
    ("Cottage cheese nature 200 g", "dairy", "cottage"),
    ("Burrata 250 g", "dairy", "burrata"),
    ("Parmigiano Reggiano Râpé Frais 60 g", "dairy", "parmesan"),
    ("Sirop · Pepsi zero Sodastream", "drinks", "cola"),
    ("Riz · Précuit · Grain long", "pantry", "riz"),
    ("Pasta Lasagne N°112 500 g", "pantry", "pates"),
])
def test_classification_positive(name, cat, t):
    assert typeof(name, cat) == t


@pytest.mark.parametrize("t,a,b", [
    ("cafe", "Café · Classic · Pads", "Café · Mild · Moulu"),
    ("cafe", "Café · Santorini · Caps", "Café · Moulu · Dessert"),
    ("cafe", "Café · Espresso 08 · Dolce Gusto capsules", "Café · Magnifico · 20 Caps"),
    ("cafe", "Café · Cappuccino · Caps", "Café · Lungo · Caps"),
    ("vaisselle", "MaxPower Liquide Vaisselle 450ml", "Expert Tablettes Lave Vaisselle 30 x 15 g"),
    ("vaisselle", "Spray vaisselle · Fresh", "Liquide vaisselle · Menthe"),
    ("lessive", "Adoucissant Fresh Air 50 lavages", "Liquide Lessive Color, 30 Lavages"),
    ("lessive", "Perles De Parfum 240g Lenor", "Assouplissant Lenor 55 Lavages"),
    ("lessive", "Washing Liquid + Touch of Lenor Unstoppables", "Adoucissant 55 Lavages"),
    ("cola", "Sirop · Pepsi zero", "Pepsi Zero 1.5 L"),
    ("cola", "Zero Sugar 15x330ml Boite", "Classic' Cola Zero 1.5 L"),
    ("riz", "Riz basmati micro-ondes 2 min 250 g", "Riz basmati 1 kg"),
    ("huile", "Huile d'olive · Extra vierge", "Huile · Friture · Fine"),
    ("mozzarella", "Mozzarella · Râpée", "Mozzarella 125 g"),
    ("parmesan", "Parmigiano Reggiano Râpé Frais 60 g", "Parmigiano Reggiano 24 mois 200g"),
    ("jambon", "Selection Chiffonnade de Jambon Sec Fumé 100 g", "Classic' Jambon Cuit au Goût Fumé 150 g"),
    ("noix", "Pistaches · Poivre et sel", "Cacahuètes · Poivre-Sel"),
    ("creme", "Crème · 20% M.G.", "Crème · Entière · 35%"),
    ("the", "Thé vert · Energy · 17S · Bio", "Ice Tea au goût de pêche 4x250ml"),
])
def test_forms_that_must_not_compare(t, a, b):
    fa, fb = form_of(t, a), form_of(t, b)
    assert fa is None or fb is None or fa != fb, (fa, fb)


def test_unit_tells_ice_tea_from_tea_bags():
    assert form_of("the", "Peach · Can", "l") == "glace"
    assert form_of("the", "Thé · Bedtime · 17S", "kg") == "the"


def test_unknown_form_means_no_form():
    assert form_of("cafe", "Café · Saveur citrouille") is None
    assert form_of("chips", "Chips · Bolognese") is None
    assert form_of("oeufs", "Oeufs · Larges") == "crus"


# ---------------------------------------------------------------- house-brand matching
def item(name, cat, ppu, code="X1", brand=""):
    full = name + " " + brand
    t = typeof(full, cat)
    v, u = unit(ppu)
    return dict(n=name, t=t, f=form_of(t, full, u), uu=u, v=v, dish=is_dish(name), code=code)

def house(name, cat, ppu, code, brand="Carrefour", nb=False):
    full = name + " " + brand
    t = typeof(full, cat)
    v, u = unit(ppu)
    return dict(n=name, t=t, f=form_of(t, full, u), u=u, v=v, dish=is_dish(name), code=code, nb=nb)


def test_prepared_meals_are_never_ingredient_references():
    wraps = house("Bon Appétit! Wraps Saumon Fumé, Concombre & Fromage Frais 210 g", "ready", "19,05 €/kg", "H1")
    ravioli = house("Trattoria Ravioli Burrata, Pesto & Mortadella Bologna 250 g", "ready", "14,00 €/kg", "H2")
    pasta = house("Tortiglioni Arrabbiata Lardons & Grana Padano 400 g", "ready", "15,00 €/kg", "H3")
    pool = [wraps, ravioli, pasta]
    cottage = item("Fromage frais Philadelphia 200 g", "dairy", "12,00 €/kg")
    burrata = item("Burrata 250 g", "dairy", "15,96 €/kg")
    parm = item("Grana Padano DOP 200 g", "dairy", "27,50 €/kg")
    for x in (cottage, burrata, parm):
        assert x["t"] is not None
        assert match_ref(x, [h for h in pool if h["t"] == x["t"]] + pool) is None


def test_valid_reference_is_found_and_cheapest_same_form():
    x = item("Burrata di Latte di Bufala 400 g", "dairy", "25,00 €/kg")
    good = house("Extra Burrata 285 g", "dairy", "16,60 €/kg", "H1")
    cheaper_wrong_form = house("Stracciatella 200 g", "dairy", "12,00 €/kg", "H2")
    assert match_ref(x, [good, cheaper_wrong_form])["code"] == "H1"


def test_capsules_never_compared_with_ground_coffee():
    caps = item("Café · Santorini · Caps", "drinks", "88,27 €/kg")
    ground = house("Café · Moulu · Dessert", "drinks", "11,35 €/kg", "H1", "Delhaize")
    assert match_ref(caps, [ground]) is None


def test_dish_liquid_never_compared_with_tablets():
    liq = item("MaxPower Liquide Vaisselle 450ml", "household", "10,87 €/l")
    tabs = house("Expert Tablettes Lave Vaisselle 30 x 15 g", "household", "0,11 €/dose", "H1")
    tabs_l = dict(tabs, u="l")   # even if the unit happened to agree, the form does not
    assert match_ref(liq, [tabs, tabs_l]) is None


def test_house_brand_promo_does_not_beat_itself():
    # a house-brand mozzarella on promo: its own regular price is not a "house brand" to beat
    x = item("Mozzarella 125 g", "dairy", "10,00 €/kg", code="05555")
    itself = house("Mozzarella 125 g", "dairy", "10,00 €/kg", "05555")
    assert match_ref(x, [itself]) is None
    other = house("Mozzarella 200 g", "dairy", "5,52 €/kg", "06666")
    r = match_ref(x, [itself, other])
    assert r["code"] == "06666"


def test_unknown_unit_or_form_gives_no_reference():
    h = house("Café · Moulu · Dessert", "drinks", "11,35 €/kg", "H1", "Delhaize")
    no_unit = dict(item("Café · Mild · Moulu", "drinks", "9,98 €/kg"), v=None, uu="")
    unknown_form = item("Café · Saveur citrouille & épices", "drinks", "40,00 €/kg")
    assert match_ref(no_unit, [h]) is None
    assert match_ref(unknown_form, [h]) is None


def test_implausible_unit_price_gap_rejected_for_pieces():
    x = item("Essuie-Tout · Xtra Power", "household", "1,90 €/pc")
    far = house("Essuie-tout · 2 rouleaux", "household", "0,40 €/pc", "H1")
    assert match_ref(x, [far]) is None


def test_broad_family_needs_a_shared_word():
    x = item("Zero Sugar Orange 1.5L PET", "drinks", "1,53 €/l")
    cola = house("Classic' Cola Zero 1.5 L", "drinks", "0,70 €/l", "H1")
    assert match_ref(x, [cola]) is None


def test_nutriboost_only_reorders_eligible_references():
    x = item("Huile d'olive · Extra vierge", "pantry", "17,70 €/l")
    a = house("Huile d'Olive · Extra Vierge · Bio", "pantry", "15,00 €/l", "H1", "Delhaize")    # bio: attribute differs
    b = house("Huile d'Olive · Extra Vierge", "pantry", "15,96 €/l", "H2", "Delhaize", nb=True)
    c = house("Huile d'Olive Vierge Extra 1 L", "pantry", "15,50 €/l", "H3", "Delhaize")
    assert match_ref(x, [a, b, c])["code"] == "H3"
    assert match_ref(x, [a, b, c], boost=True)["code"] == "H2"      # 15.96 x 0.9 < 15.50


# ---------------------------------------------------------------- build on tiny fixtures
def _fixtures(d, pulled="2026-10-18T07:00:00Z", hist=None):
    D = {"pulled": pulled, "thumbs": {}, "promos": [
        {"code": "S1", "name": "Sirop | Pepsi zero", "brand": "Sodastream", "cat": "v2DRI", "price": 6.99, "ppu": "15,89 €/l",
         "size": "44 cl", "promo": "- €6.99 à l' achat de 3 produits", "end": "28/10", "url": ""},
        {"code": "M1", "name": "Mozzarella | Boule", "brand": "Delhaize", "cat": "v2DAI", "price": 1.25, "ppu": "10,00 €/kg",
         "size": "125 gr", "promo": "2ème à -50%", "end": "28/10", "url": ""},
        {"code": "W1", "name": "Mystère | Bocal", "brand": "Marque", "cat": "v2SAL", "price": 3.0, "ppu": "", "size": "",
         "promo": "Prix choc", "end": "28/10", "url": ""},
    ], "house": [
        {"code": "M1", "name": "Mozzarella | Boule", "price": 1.25, "ppu": "10,00 €/kg", "cat": "v2DAI", "promo": "2ème à -50%"},
    ]}
    C = {"promos": [], "house": []}
    for n, j in (("delhaize-fr", D), ("carrefour-fr", C), ("carrefour-photos", {}), ("delhaize-nutriscore", {})):
        json.dump(j, open(os.path.join(d, n + ".json"), "w"))
    if hist is not None:
        json.dump(hist, open(os.path.join(d, "history.json"), "w"))

def _build(src, out, *flags):
    subprocess.run([sys.executable, os.path.join(ROOT, "build.py"), str(src), str(out), *flags], check=True, capture_output=True)
    return {x["k"]: x for x in json.load(open(os.path.join(out, "data.json")))["items"]}


def test_build_end_to_end(tmp_path):
    _fixtures(tmp_path)
    items = _build(tmp_path, tmp_path)
    soda, mozz, odd = items["dS1"], items["dM1"], items["dW1"]
    assert (soda["q"], soda["tot"], soda["d"]) == (3, 13.98, 0.3333)
    assert soda["ev"] == pytest.approx(10.593, abs=0.001)          # 15.89 €/l x 4.66 / 6.99
    assert soda["mix"] == 1
    # house-brand promo, only house reference is itself -> no reference, so no "beats house brand" claim possible
    assert mozz["hb"] and not (mozz["ref"] or {}).get("d") and mozz["nr"] == "none"
    # unknown offer kept, original text shown, nothing derived
    assert odd["ok"] == 0 and odd["d"] is None and "tot" not in odd and odd["raw"] == "Prix choc"
    html = open(os.path.join(tmp_path, "index.html")).read()
    assert "__DATA__" not in html and "<!doctype html>" in html


def test_rebuild_does_not_touch_existing_history(tmp_path):
    old = {"2026-10-11": {"dS1": [6.99, 0.1]}, "2026-10-18": {"dS1": [6.99, 0.9]}}
    _fixtures(tmp_path, hist=old)
    _build(tmp_path, tmp_path)
    assert json.load(open(tmp_path / "history.json")) == old          # same scrape date: untouched
    _build(tmp_path, tmp_path, "--rewrite-history")
    assert json.load(open(tmp_path / "history.json"))["2026-10-18"]["dS1"] == [6.99, 0.3333]
    _fixtures(tmp_path, pulled="2026-10-25T07:00:00Z")
    _build(tmp_path, tmp_path)
    assert "2026-10-25" in json.load(open(tmp_path / "history.json"))  # new week: snapshot added
