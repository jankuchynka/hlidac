# -*- coding: utf-8 -*-
"""
Hlídač aut — Suzuki Swift 4x4 (AllGrip), 2017+, benzín, do 110 000 km, do 275 000 Kč
Prochází: Bazoš.cz, Bazos.sk, Sauto.cz, TipCars, AutoScout24 (DE/AT/IT)
Výstup: docs/data.json (čte ho stránka docs/index.html)
Výjimečné nabídky: zapíše do alert.txt (workflow z toho udělá GitHub Issue -> e-mail)
"""
import json, re, sys, time, html
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.parse import quote

# ---------- ZADÁNÍ ----------
YEAR_MIN   = 2017
KM_MAX     = 110_000          # 100 000 + 10% tolerance
PRICE_MAX  = 275_000          # Kč, 250 000 + 10% tolerance
ALERT_PRICE = 210_000         # výjimečná nabídka: cena pod…
ALERT_KM    = 80_000          # …a nájezd pod
EUR_CZK    = 24.5
KW_4X4     = re.compile(r"4\s*[x×]\s*4|allgrip|4wd|awd|allrad|napęd\s*4|integrale", re.I)

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
      "Accept-Language": "cs,en;q=0.8,de;q=0.7"}

def fetch(url, timeout=25):
    req = Request(url, headers=UA)
    with urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")

def norm_price_czk(val, cur):
    if not val: return None
    v = int(val)
    return v if cur == "CZK" else int(v * EUR_CZK)

def clean(t):
    return html.unescape(re.sub(r"\s+", " ", t or "")).strip()

def mk(id_, src, country, title, price_czk, price_orig, year, km, url, img, note=""):
    return {"id": id_, "src": src, "country": country, "title": clean(title)[:120],
            "price_czk": price_czk, "price_orig": price_orig, "year": year, "km": km,
            "url": url, "img": img, "note": note}

results, status = [], {}

def run(name, fn):
    try:
        items = fn()
        results.extend(items)
        status[name] = f"OK ({len(items)})"
    except Exception as e:
        status[name] = f"CHYBA: {type(e).__name__}: {str(e)[:80]}"

# ---------- BAZOŠ (CZ + SK) ----------
def bazos(domain, country, cur):
    def inner():
        out = []
        for offset in (0, 20):
            u = f"https://auto.{domain}/{('' if offset==0 else str(offset)+'/')}?hledat={quote('suzuki swift')}&cenado={PRICE_MAX if cur=='CZK' else 11000}"
            page = fetch(u)
            # bloky inzerátů
            for m in re.finditer(r'<div class="inzeraty inzeratyflex">(.*?)</div>\s*</div>\s*</div>', page, re.S):
                b = m.group(1)
                a = re.search(r'<h2 class="nadpis">\s*<a href="([^"]+)">(.*?)</a>', b, re.S)
                if not a: continue
                href, title = a.group(1), clean(re.sub(r"<[^>]+>", "", a.group(2)))
                if "swift" not in title.lower(): continue
                desc_m = re.search(r'<div class="popis">(.*?)</div>', b, re.S)
                desc = clean(re.sub(r"<[^>]+>", "", desc_m.group(1))) if desc_m else ""
                if not KW_4X4.search(title + " " + desc): continue
                pm = re.search(r'inzeratycena[^>]*>\s*<b>([\d\s]+)', b)
                price = int(re.sub(r"\D", "", pm.group(1))) if pm else None
                im = re.search(r'<img[^>]+src="([^"]+)"', b)
                ym = re.search(r"\b(20[12]\d)\b", title + " " + desc)
                km_m = re.search(r"(\d[\d\s]{1,6})\s*(?:km|tkm)", desc, re.I)
                km = int(re.sub(r"\D", "", km_m.group(1))) if km_m else None
                url = href if href.startswith("http") else f"https://auto.{domain}{href}"
                out.append(mk(url, f"Bazoš {country}", country, title,
                              norm_price_czk(price, cur), f"{price} {cur}" if price else "?",
                              int(ym.group(1)) if ym else None, km, url,
                              im.group(1) if im else "", "soukromý inzerát – prověřit VIN!"))
        return out
    return inner

# ---------- SAUTO ----------
def sauto():
    out = []
    u = ("https://www.sauto.cz/inzerce/osobni/suzuki/swift"
         f"?vyrobeno-od={YEAR_MIN}&tachometr-do={KM_MAX}&cena-do={PRICE_MAX}&pohon=4x4")
    page = fetch(u)
    nd = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', page, re.S)
    if nd:
        try:
            data = json.loads(nd.group(1))
            txt = json.dumps(data)
            # projdeme všechny objekty vypadající jako inzerát
            for adv in re.finditer(r'\{[^{}]*"name"\s*:\s*"([^"]*[Ss]wift[^"]*)"[^{}]*\}', txt):
                pass  # struktura se liší, spolehlivější je fallback níže
        except Exception:
            pass
    # fallback: odkazy na detaily
    seen = set()
    for m in re.finditer(r'href="(/osobni/detail/suzuki/swift/[^"]+)"', page):
        url = "https://www.sauto.cz" + m.group(1)
        if url in seen: continue
        seen.add(url)
        out.append(mk(url, "Sauto", "CZ", "Suzuki Swift (detail na Sauto)", None, "?",
                      None, None, url, "", "doplnit údaje z detailu"))
    return out

# ---------- TIPCARS ----------
def tipcars():
    out = []
    u = f"https://www.tipcars.com/hledam/ojete-vozy/suzuki/swift/?cena_do={PRICE_MAX}&rok_od={YEAR_MIN}&km_do={KM_MAX}"
    page = fetch(u)
    seen = set()
    for m in re.finditer(r'href="(https?://www\.tipcars\.com/[^"]*suzuki[^"]*swift[^"]*\.html)"', page):
        url = m.group(1)
        if url in seen: continue
        seen.add(url)
        out.append(mk(url, "TipCars", "CZ", "Suzuki Swift (detail na TipCars)", None, "?",
                      None, None, url, "", "doplnit údaje z detailu"))
    return out

# ---------- AUTOSCOUT24 (DE / AT / IT) ----------
def autoscout(cc):
    def inner():
        out = []
        u = (f"https://www.autoscout24.{cc}/lst/suzuki/swift"
             f"?atype=C&fregfrom={YEAR_MIN}&kmto={KM_MAX}&priceto=11000&fuel=B&sort=age&desc=1&size=20")
        page = fetch(u)
        nd = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', page, re.S)
        if not nd: raise RuntimeError("nenalezen datový blok")
        data = json.loads(nd.group(1))
        listings = (data.get("props", {}).get("pageProps", {}).get("listings")
                    or data.get("props", {}).get("pageProps", {}).get("results") or [])
        for L in listings:
            try:
                title = " ".join(filter(None, [L.get("vehicle", {}).get("make"),
                                               L.get("vehicle", {}).get("model"),
                                               L.get("vehicle", {}).get("modelVersionInput")])) or L.get("title", "Swift")
                blob = json.dumps(L, ensure_ascii=False)
                if not KW_4X4.search(blob): continue
                price = (L.get("price", {}) or {}).get("priceFormatted") or ""
                pnum = int(re.sub(r"\D", "", price)) if re.search(r"\d", price) else None
                km_s = (L.get("tracking", {}) or {}).get("mileage") or (L.get("vehicle", {}) or {}).get("mileageInKmRaw")
                km = int(km_s) if km_s else None
                yr = (L.get("tracking", {}) or {}).get("firstRegistration") or ""
                ym = re.search(r"(20[12]\d)", str(yr))
                path = L.get("url") or ""
                url = path if path.startswith("http") else f"https://www.autoscout24.{cc}{path}"
                imgs = L.get("images") or []
                img = imgs[0] if imgs and isinstance(imgs[0], str) else ""
                out.append(mk(url, f"AutoScout {cc.upper()}", cc.upper(), title,
                              norm_price_czk(pnum, "EUR"), f"{pnum} €" if pnum else "?",
                              int(ym.group(1)) if ym else None, km, url, img))
            except Exception:
                continue
        return out
    return inner

run("Bazoš CZ", bazos("bazos.cz", "CZ", "CZK"))
run("Bazoš SK", bazos("bazos.sk", "SK", "EUR"))
run("Sauto",    sauto)
run("TipCars",  tipcars)
run("AutoScout DE", autoscout("de"))
run("AutoScout AT", autoscout("at"))
run("AutoScout IT", autoscout("it"))

# ---------- filtr limitů (kde známe čísla) ----------
def within(it):
    if it["price_czk"] and it["price_czk"] > PRICE_MAX: return False
    if it["km"] and it["km"] > KM_MAX: return False
    if it["year"] and it["year"] < YEAR_MIN: return False
    return True
results = [r for r in results if within(r)]

# ---------- sloučení s historií ----------
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

merged.sort(key=lambda x: (not x["new"], x["price_czk"] or 9e9))

with open("docs/data.json", "w", encoding="utf-8") as f:
    json.dump({"updated": now, "status": status, "cars": merged}, f, ensure_ascii=False, indent=1)

if alerts:
    with open("alert.txt", "w", encoding="utf-8") as f:
        for a in alerts:
            f.write(f"🔥 {a['title']} — {a['price_orig']} ({a['price_czk']:,} Kč), "
                    f"{a['km']:,} km, {a['year']} [{a['src']}]\n{a['url']}\n\n".replace(",", " "))

print("Hotovo:", {k: v for k, v in status.items()}, "| celkem:", len(merged), "| alertů:", len(alerts))
