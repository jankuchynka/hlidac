# -*- coding: utf-8 -*-
"""
Hlidac aut - Suzuki Swift 4x4 (AllGrip)
Zadani: rok 2017+, benzin, manual, do 110 000 km, do 275 000 Kc (vc. 10% tolerance)
Zdroje: TipCars, Bazos.cz, Bazos.sk, AutoScout24 DE/AT/IT
"""
import json, re, html
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.parse import quote

# ---------- NASTAVENI (uprav v souboru config.json) ----------
try:
    with open("config.json", encoding="utf-8") as _f:
        CFG = json.load(_f)
except Exception:
    CFG = {}

def cfg(key, default):
    v = CFG.get(key, default)
    return default if v in (None, "") else v

ZNACKA      = str(cfg("znacka", "suzuki")).strip().lower()
MODEL       = str(cfg("model", "swift")).strip().lower()
POHON_KW    = [str(x).lower() for x in cfg("pohon_klicova_slova", [])]
PALIVO      = str(cfg("palivo", "benzin")).strip().lower()
YEAR_MIN    = int(cfg("rok_od", 2017))
KM_MAX      = int(cfg("km_do", 110000))
BUDGET      = int(cfg("rozpocet_czk", 275000))
PRICE_MAX   = int(cfg("zobrazit_do_czk", BUDGET))
ALERT_PRICE = int(cfg("upozornit_cena_czk", int(BUDGET*0.8)))
ALERT_KM    = int(cfg("upozornit_km", int(KM_MAX*0.75)))
EUR_CZK     = float(cfg("kurz_eur", 24.5))
MAX_DETAIL  = 30
HLEDANI     = "%s %s%s" % (ZNACKA.capitalize(), MODEL.capitalize(),
                           (" " + POHON_KW[0]) if POHON_KW else "")
EUR_MAX     = int(PRICE_MAX / EUR_CZK)
FUEL_CODE   = {"benzin": "B", "nafta": "D", "diesel": "D", "hybrid": "2", "elektro": "E"}.get(PALIVO, "")

if POHON_KW:
    _pat = "|".join(re.escape(k).replace(r"4x4", r"4\s*[x\u00d7]\s*4") for k in POHON_KW)
    KW_4X4 = re.compile(_pat, re.I)
else:
    KW_4X4 = re.compile(".")   # bez omezeni pohonu
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
      "Accept-Language": "cs,en;q=0.8,de;q=0.7"}

def fetch(url, timeout=30):
    with urlopen(Request(url, headers=UA), timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")

def squash(t):
    t = re.sub(r"<[^>]+>", " ", t or "")
    t = html.unescape(t).replace("\xa0", " ")
    return re.sub(r"\s+", " ", t).strip()

def safe_title(t):
    """vyhodi zbytky HTML atributu, kdyby se do textu dostaly"""
    t = squash(t)
    t = re.sub(r"\S*=\"[^\"]*\"", "", t)
    t = re.sub(r"data-\S+", "", t)
    return re.sub(r"\s+", " ", t).strip(" -|·")

def to_czk(v, cur):
    return None if v is None else (int(v) if cur == "CZK" else int(v * EUR_CZK))

def find_year(text):
    m = re.search(r"(?:r\.?\s?v\.?|rok\s+v[yý]roby|reg\.?|1\.\s*registrace|v\s+provozu\s+od)"
                  r"[^\d]{0,14}(?:\d{1,2}\s*[/.]\s*)?(20[12]\d)", text, re.I)
    if m: return int(m.group(1))
    m = re.search(r"\b(\d{1,2})/(20[12]\d)\b", text)
    if m: return int(m.group(2))
    m = re.search(r"\b(20[12]\d)\b", text)
    return int(m.group(1)) if m else None

def find_km(text):
    cands = []
    for m in re.finditer(r"(?:najeto|najazden[eé]|tachometr|stav\s+tachom[^\d]{0,12})[:\s]*([\d\s.,]{3,12})\s*km",
                         text, re.I):
        cands.append(m.group(1))
    for m in re.finditer(r"(?<![\d/.,])(\d[\d\s.]{2,9})\s*km\b", text, re.I):
        cands.append(m.group(1))
    for c in cands:
        digits = re.sub(r"\D", "", c)
        if digits and 1000 <= int(digits) <= 500_000:
            return int(digits)
    return None

def find_price_czk(text):
    for m in re.finditer(r"(\d[\d\s.]{4,10}?)\s*K[čc]", text):
        digits = re.sub(r"\D", "", m.group(1))
        if len(digits) > 7:      # slepilo se s rokem pred cenou -> vezmi konec
            digits = digits[-6:]
        if digits and 20_000 <= int(digits) <= 5_000_000:
            return int(digits)
    return None

def mk(url, src, country, title, price_czk, price_orig, year, km, img, note=""):
    return {"id": url, "src": src, "country": country, "title": (title or HLEDANI)[:130],
            "price_czk": price_czk, "price_orig": price_orig, "year": year, "km": km,
            "url": url, "img": img or "", "note": note}

results, status = [], {}

def run(name, fn):
    try:
        got = fn()
        results.extend(got)
        status[name] = "OK (%d)" % len(got)
    except Exception as e:
        status[name] = "CHYBA: %s: %s" % (type(e).__name__, str(e)[:70])

# ---------------- TIPCARS ----------------
def slug_title(link):
    m = re.search(r"/([^/]+?)-\d{6,}\.html", link)
    if not m: return HLEDANI
    words = [w for w in m.group(1).split("-") if w]
    out = []
    for w in words:
        if re.fullmatch(r"\d", w) and out and re.fullmatch(r"\d+", out[-1]):
            out[-1] = out[-1] + "." + w      # "1-2" -> "1.2"
        else:
            out.append(w)
    txt = " ".join(out)
    return safe_title(txt[:1].upper() + txt[1:])

def tipcars():
    out = []
    url = "https://www.tipcars.com/%s-%s%s" % (ZNACKA, MODEL, "?vybava=pohon-4x4" if POHON_KW else "")
    page = fetch(url)
    parts = re.split(r'href="((?:https://www\.tipcars\.com)?/[^"]*?-\d{6,}\.html)"', page)
    seen = set()
    for i in range(1, len(parts) - 1, 2):
        href, chunk = parts[i], parts[i + 1][:1200]
        link = href if href.startswith("http") else "https://www.tipcars.com" + href
        if link in seen: continue
        if ZNACKA not in link.lower() or MODEL not in link.lower(): continue
        seen.add(link)
        txt = squash(chunk)
        title = slug_title(link)
        if not KW_4X4.search(title + " " + txt): continue
        price = find_price_czk(txt)
        im = re.search(r'<img[^>]+(?:src|data-src)="([^"]+)"', chunk)
        img = im.group(1) if im else ""
        if img.startswith("//"): img = "https:" + img
        out.append(mk(link, "TipCars", "CZ", title, price,
                      ("%d CZK" % price) if price else "?",
                      find_year(txt), find_km(txt), img))
    return out

# ---------------- BAZOS ----------------
def bazos(domain, country, cur):
    def inner():
        out = []
        base = "https://www.%s" % domain
        for start in (0, 20):
            url = ("%s/search.php?hledat=%s&rubriky=auto&hlokalita=&humkreis=25"
                   "&cenaod=&cenado=&order=&crz=%d" % (base, quote(" ".join([ZNACKA, MODEL] + (POHON_KW[:1] if POHON_KW else []))), start))
            page = fetch(url)
            blocks = page.split('class="inzeraty inzeratyflex"')[1:]
            if not blocks: break
            for b in blocks:
                a = re.search(r'<h2 class="nadpis">\s*<a href="([^"]+)"[^>]*>(.*?)</a>', b, re.S)
                if not a: continue
                href, title = a.group(1), safe_title(a.group(2))
                if MODEL not in title.lower(): continue
                dsc = re.search(r'<div class="popis">(.*?)</div>', b, re.S)
                desc = squash(dsc.group(1)) if dsc else ""
                blob = title + " " + desc
                if not KW_4X4.search(blob): continue
                p = re.search(r'inzeratycena[^>]*>\s*<b>([\d\s.,]+)', b)
                price = int(re.sub(r"\D", "", p.group(1))) if p else None
                im = re.search(r'<img[^>]+src="([^"]+)"', b)
                img = im.group(1) if im else ""
                if img.startswith("//"): img = "https:" + img
                full = href if href.startswith("http") else base + href
                out.append(mk(full, "Bazos %s" % country, country, title,
                              to_czk(price, cur), ("%s %s" % (price, cur)) if price else "?",
                              find_year(blob), find_km(blob), img,
                              "soukromy inzerat - overit VIN"))
        return out
    return inner

# ---------------- AUTOSCOUT24 ----------------
def autoscout(cc):
    def inner():
        out = []
        url = ("https://www.autoscout24.%s/lst/%s/%s"
               "?atype=C&fregfrom=%d&kmto=%d&priceto=%d&fuel=%s&sort=age&desc=1&size=20"
               % (cc, ZNACKA, MODEL, YEAR_MIN, KM_MAX, EUR_MAX, FUEL_CODE))
        page = fetch(url)
        m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', page, re.S)
        if not m:
            raise RuntimeError("na strance nejsou data")
        data = json.loads(m.group(1))
        pp = data.get("props", {}).get("pageProps", {})
        listings = pp.get("listings") or pp.get("results") or []
        for L in listings:
            try:
                blob = json.dumps(L, ensure_ascii=False)
                if not KW_4X4.search(blob): continue
                v = L.get("vehicle", {}) or {}
                title = " ".join(x for x in [v.get("make"), v.get("model"), v.get("modelVersionInput")] if x) \
                        or L.get("title") or HLEDANI
                pr = (L.get("price", {}) or {}).get("priceFormatted") or ""
                pnum = int(re.sub(r"\D", "", pr)) if re.search(r"\d", pr) else None
                tr = L.get("tracking", {}) or {}
                km = tr.get("mileage") or v.get("mileageInKmRaw")
                km = int(km) if km else None
                ym = re.search(r"(20[12]\d)", str(tr.get("firstRegistration") or ""))
                path = L.get("url") or ""
                link = path if path.startswith("http") else "https://www.autoscout24.%s%s" % (cc, path)
                imgs = L.get("images") or []
                img = imgs[0] if imgs and isinstance(imgs[0], str) else ""
                out.append(mk(link, "AutoScout %s" % cc.upper(), cc.upper(), safe_title(title),
                              to_czk(pnum, "EUR"), ("%d EUR" % pnum) if pnum else "?",
                              int(ym.group(1)) if ym else None, km, img))
            except Exception:
                continue
        return out
    return inner

# ---------------- WILLHABEN (AT) ----------------
def willhaben():
    out = []
    # vyhledavani ojetin: model v ceste + fulltext keyword
    url = ("https://www.willhaben.at/iad/gebrauchtwagen/auto/gebrauchtwagenboerse"
           "?make=%s&keyword=%s%%20%s&rows=50"
           % (quote(ZNACKA), quote(MODEL), quote(POHON_KW[0] if POHON_KW else "")))
    page = fetch(url)

    def push(link, title, price_eur, year, km, img):
        if not link.startswith("http"):
            link = "https://www.willhaben.at" + link
        out.append(mk(link, "Willhaben AT", "AT", safe_title(title),
                      to_czk(price_eur, "EUR"), ("%d EUR" % price_eur) if price_eur else "?",
                      year, km, img, ""))

    # 1) pokus: datovy blok (__NEXT_DATA__ nebo podobny JSON se seznamem)
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', page, re.S)
    if not m:
        m = re.search(r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\})\s*</script>', page, re.S)
    if m:
        try:
            data = json.loads(m.group(1))
        except Exception:
            data = None
        if data is not None:
            def walk(o):
                if isinstance(o, dict):
                    yield o
                    for v in o.values(): yield from walk(v)
                elif isinstance(o, list):
                    for v in o: yield from walk(v)
            seen = set()
            for d in walk(data):
                if not isinstance(d, dict): continue
                blob = json.dumps(d, ensure_ascii=False)
                if MODEL not in blob.lower(): continue
                if not KW_4X4.search(blob): continue
                # heuristika: uzel s cenou a odkazem
                link = d.get("seoUrl") or d.get("url") or ""
                if isinstance(link, dict): link = link.get("href", "")
                if not link or "gebrauchtwagen" not in str(link): continue
                if link in seen: continue
                seen.add(link)
                title = d.get("heading") or d.get("description") or d.get("title") or (ZNACKA + " " + MODEL)
                if isinstance(title, dict): title = title.get("value", "")
                price = None
                for pk in ("price", "amount", "priceValue"):
                    pv = d.get(pk)
                    if isinstance(pv, (int, float)): price = int(pv); break
                    if isinstance(pv, dict):
                        for q in ("value", "amount"):
                            if isinstance(pv.get(q), (int, float)):
                                price = int(pv[q]); break
                ym = re.search(r"(20[12]\d)", blob)
                km_m = re.search(r'"mileage"\s*:\s*"?(\d{4,7})', blob) or re.search(r"(\d{4,6})\s*km", blob, re.I)
                img = ""
                gm = re.search(r'"(https://cache\.willhaben\.at[^"]+)"', blob)
                if gm: img = gm.group(1)
                push(link, str(title), price,
                     int(ym.group(1)) if ym else None,
                     int(km_m.group(1)) if km_m else None, img)
        if out:
            return out

    # 2) zaloha: primo z HTML - odkazy na detaily
    seen = set()
    for lm in re.finditer(r'href="(/iad/gebrauchtwagen/d/auto/[^"]*?-\d{6,}/?)"', page):
        link = lm.group(1)
        if link in seen: continue
        if MODEL not in link.lower(): continue
        if not KW_4X4.search(link.replace("-", " ")): continue
        seen.add(link)
        title = link.rsplit("/", 2)[-2].replace("-", " ")
        push(link, title, None, find_year(link.replace("-", " ")), None, "")
    return out

run("TipCars", tipcars)
run("Bazos CZ", bazos("bazos.cz", "CZ", "CZK"))
run("Bazos SK", bazos("bazos.sk", "SK", "EUR"))
run("AutoScout DE", autoscout("de"))
run("AutoScout AT", autoscout("at"))
run("Willhaben AT", willhaben)
run("AutoScout IT", autoscout("it"))
status["Sauto"] = "vypnuto (nacita JS - resit vlastnim hlidanim na Sauto)"

# ---------------- filtr ----------------
def ok(it):
    if it["price_czk"] and it["price_czk"] > PRICE_MAX: return False
    if it["km"] and it["km"] > KM_MAX: return False
    if it["year"] and it["year"] < YEAR_MIN: return False
    return True

results = [r for r in results if ok(r)]

# oznaceni vozu nad rozpoctem
for r in results:
    if r["price_czk"] and r["price_czk"] > BUDGET:
        r["over"] = True
        r["note"] = (r.get("note") + " | " if r.get("note") else "") + "nad rozpocet - k jednani"
    else:
        r["over"] = False

# ---------------- historie ----------------
try:
    with open("docs/data.json", encoding="utf-8") as f:
        old = {c["id"]: c for c in json.load(f).get("cars", [])}
except Exception:
    old = {}

now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
merged, alerts = [], []
for r in results:
    prev = old.get(r["id"])
    r["first_seen"] = prev["first_seen"] if prev else now
    r["new"] = prev is None
    if r["new"] and r["price_czk"] and r["km"] and r["price_czk"] <= ALERT_PRICE and r["km"] <= ALERT_KM:
        alerts.append(r)
    merged.append(r)

merged.sort(key=lambda x: (not x["new"], x["price_czk"] or 9_000_000))

with open("docs/data.json", "w", encoding="utf-8") as f:
    json.dump({"updated": now, "hledani": HLEDANI, "status": status, "cars": merged}, f, ensure_ascii=False, indent=1)

if alerts:
    with open("alert.txt", "w", encoding="utf-8") as f:
        for a in alerts:
            f.write("%s - %s, %s km, %s [%s]\n%s\n\n" %
                    (a["title"], a["price_orig"], a["km"], a["year"], a["src"], a["url"]))

print("Hotovo:", status, "| celkem:", len(merged), "| alertu:", len(alerts))
