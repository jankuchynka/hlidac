# -*- coding: utf-8 -*-
"""
Hlidac aut — Suzuki Swift 4x4 (AllGrip)
Zadani: rok 2017+, benzin, manual, do 110 000 km, do 275 000 Kc (vc. 10% tolerance)
Zdroje: Bazos.cz, Bazos.sk, Sauto.cz, AutoScout24 DE/AT/IT
Vystup: docs/data.json
"""
import json, re, html
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.parse import quote

YEAR_MIN    = 2017
KM_MAX      = 110_000
PRICE_MAX   = 275_000          # Kc
ALERT_PRICE = 210_000
ALERT_KM    = 80_000
EUR_CZK     = 24.5

KW_4X4 = re.compile(r"4\s*[x×]\s*4|allgrip|4wd|awd|allrad|integrale", re.I)
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
      "Accept-Language": "cs,en;q=0.8,de;q=0.7"}

def fetch(url, timeout=30):
    with urlopen(Request(url, headers=UA), timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")

def clean(t):
    return html.unescape(re.sub(r"<[^>]+>", " ", t or "")).replace("\xa0", " ")

def squash(t):
    return re.sub(r"\s+", " ", clean(t)).strip()

def to_czk(v, cur):
    return None if v is None else (int(v) if cur == "CZK" else int(v * EUR_CZK))

def find_year(text):
    m = re.search(r"(?:r\.?\s?v\.?|rok\s+v[ýy]roby|reg\.?|v\s+provozu\s+od)[^\d]{0,12}(?:\d{1,2}[/.])?(20[12]\d)", text, re.I)
    if m: return int(m.group(1))
    m = re.search(r"\b(20[12]\d)\b", text)
    return int(m.group(1)) if m else None

def find_km(text):
    m = re.search(r"(?:najeto|najazden[eé]|tachom[^\d]{0,10}|stav\s+tachometru[^\d]{0,6})[:\s]*([\d\s.,]{3,12})\s*km", text, re.I)
    if not m:
        m = re.search(r"([\d][\d\s.,]{2,10})\s*km\b", text, re.I)
    if not m: return None
    digits = re.sub(r"\D", "", m.group(1))
    if not digits: return None
    km = int(digits)
    return km if 1000 <= km <= 500_000 else None

def mk(url, src, country, title, price_czk, price_orig, year, km, img, note=""):
    return {"id": url, "src": src, "country": country, "title": squash(title)[:130],
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

# ---------------- BAZOS ----------------
def bazos(domain, country, cur):
    def inner():
        out = []
        base = "https://auto.%s" % domain
        for start in (0, 20, 40):
            url = ("%s/search.php?hledat=%s&rubriky=auto&hlokalita=&humkreis=25"
                   "&cenaod=&cenado=&order=&crz=%d" % (base, quote("suzuki swift 4x4"), start))
            page = fetch(url)
            blocks = page.split('class="inzeraty inzeratyflex"')[1:]
            if not blocks: break
            for b in blocks:
                a = re.search(r'<h2 class="nadpis">\s*<a href="([^"]+)"[^>]*>(.*?)</a>', b, re.S)
                if not a: continue
                href, title = a.group(1), squash(a.group(2))
                if "swift" not in title.lower(): continue
                d = re.search(r'<div class="popis">(.*?)</div>', b, re.S)
                desc = squash(d.group(1)) if d else ""
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

# ---------------- SAUTO ----------------
def sauto():
    out = []
    url = ("https://www.sauto.cz/inzerce/osobni/suzuki/swift"
           "?vyrobeno-od=%d&tachometr-do=%d&cena-do=%d&pohon=4x4" % (YEAR_MIN, KM_MAX, PRICE_MAX))
    page = fetch(url)
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', page, re.S)
    if not m:
        raise RuntimeError("na strance nejsou data")
    data = json.loads(m.group(1))

    def walk(o):
        if isinstance(o, dict):
            yield o
            for v in o.values():
                yield from walk(v)
        elif isinstance(o, list):
            for v in o:
                yield from walk(v)

    seen = set()
    for d in walk(data):
        if not isinstance(d, dict): continue
        if "price" not in d: continue
        if not any(k in d for k in ("tachometer", "manufacturing_date", "manufacturer_cb")): continue
        try:
            price = d.get("price")
            price = int(price) if isinstance(price, (int, float)) else None
            if not price: continue
            name = d.get("name") or ""
            if isinstance(name, dict): name = name.get("value", "")
            title = "Suzuki Swift " + squash(str(name))
            km = d.get("tachometer")
            km = int(km) if isinstance(km, (int, float)) else None
            yr = str(d.get("manufacturing_date") or "")
            ym = re.search(r"(20[12]\d)", yr)
            year = int(ym.group(1)) if ym else None
            iid = d.get("id") or d.get("advert_id")
            if not iid: continue
            link = "https://www.sauto.cz/osobni/detail/suzuki/swift/%s" % iid
            if link in seen: continue
            seen.add(link)
            img = ""
            imgs = d.get("images") or d.get("photos") or []
            if imgs and isinstance(imgs, list):
                first = imgs[0]
                if isinstance(first, dict):
                    img = first.get("url") or first.get("full") or ""
                elif isinstance(first, str):
                    img = first
            if img.startswith("//"): img = "https:" + img
            out.append(mk(link, "Sauto", "CZ", title, price, "%d CZK" % price, year, km, img))
        except Exception:
            continue
    return out

# ---------------- AUTOSCOUT24 ----------------
def autoscout(cc):
    def inner():
        out = []
        url = ("https://www.autoscout24.%s/lst/suzuki/swift"
               "?atype=C&fregfrom=%d&kmto=%d&priceto=11000&fuel=B&sort=age&desc=1&size=20"
               % (cc, YEAR_MIN, KM_MAX))
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
                        or L.get("title") or "Suzuki Swift"
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
                out.append(mk(link, "AutoScout %s" % cc.upper(), cc.upper(), title,
                              to_czk(pnum, "EUR"), ("%d EUR" % pnum) if pnum else "?",
                              int(ym.group(1)) if ym else None, km, img))
            except Exception:
                continue
        return out
    return inner

# ---------------- TIPCARS ----------------
def tipcars():
    out = []
    page = fetch("https://www.tipcars.com/suzuki-swift?vybava=pohon-4x4")
    # detailni odkazy na vozy
    parts = re.split(r'<a\s+[^>]*href="([^"]*suzuki-swift[^"]*)"', page)
    seen = set()
    for i in range(1, len(parts) - 1, 2):
        href, chunk = parts[i], parts[i + 1][:1500]
        if "?" in href and "vybava" in href: continue
        link = href if href.startswith("http") else "https://www.tipcars.com" + href
        if link in seen: continue
        txt = squash(chunk)
        pm = re.search(r"([\d][\d\s]{4,9})\s*Kč", txt)
        if not pm: continue
        seen.add(link)
        price = int(re.sub(r"\D", "", pm.group(1)))
        dm = re.search(r"(\d{1,2})/(20[12]\d)", txt)
        year = int(dm.group(2)) if dm else find_year(txt)
        title = "Suzuki Swift " + squash(txt[:70])
        im = re.search(r'<img[^>]+src="([^"]+)"', chunk)
        img = im.group(1) if im else ""
        if img.startswith("//"): img = "https:" + img
        out.append(mk(link, "TipCars", "CZ", title, price, "%d CZK" % price,
                      year, find_km(txt), img))
    return out

run("Bazos CZ", bazos("bazos.cz", "CZ", "CZK"))
run("Bazos SK", bazos("bazos.sk", "SK", "EUR"))
run("Sauto", sauto)
run("TipCars", tipcars)
run("AutoScout DE", autoscout("de"))
run("AutoScout AT", autoscout("at"))
run("AutoScout IT", autoscout("it"))

# ---------------- filtr ----------------
def ok(it):
    if it["price_czk"] and it["price_czk"] > PRICE_MAX: return False
    if it["km"] and it["km"] > KM_MAX: return False
    if it["year"] and it["year"] < YEAR_MIN: return False
    return True

results = [r for r in results if ok(r)]

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
    json.dump({"updated": now, "status": status, "cars": merged}, f, ensure_ascii=False, indent=1)

if alerts:
    with open("alert.txt", "w", encoding="utf-8") as f:
        for a in alerts:
            f.write("%s - %s (%s Kc), %s km, %s [%s]\n%s\n\n" %
                    (a["title"], a["price_orig"], a["price_czk"], a["km"], a["year"], a["src"], a["url"]))

print("Hotovo:", status, "| celkem:", len(merged), "| alertu:", len(alerts))
