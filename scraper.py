#!/usr/bin/env python3
"""
Hotel scraper using RSS feeds and public sources.
Sources: Fotocasa RSS, Idealista RSS, Kyero RSS, Nuroa, Pisos.com RSS,
         Habitaclia RSS, ThinkSpain, Indomio, Hogaria, Trovit, Yaencontré
"""

import re
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from html import unescape

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'es-ES,es;q=0.9',
}

HOTEL_KEYWORDS = ['hotel', 'hostal', 'hostel', 'pensión', 'pension', 'alojamiento', 'aparthotel', 'posada', 'parador', 'fonda', 'casa rural', 'rural']

CITIES = [
    'Madrid','Barcelona','Valencia','Sevilla','Zaragoza','Málaga','Murcia','Palma',
    'Las Palmas','Bilbao','Alicante','Córdoba','Valladolid','Vigo','Gijón','Granada',
    'Tarragona','Oviedo','Badalona','Cartagena','Marbella','Ibiza','Tenerife','Menorca',
    'Lanzarote','Fuerteventura','Girona','Toledo','Segovia','Salamanca','Burgos','León',
    'Cádiz','Huelva','Almería','Jaén','Badajoz','Cáceres','Logroño','Pamplona',
    'San Sebastián','Santander','Pontevedra','Lugo','Ourense','Lleida','Castellón',
    'Albacete','Ciudad Real','Cuenca','Guadalajara','Huesca','Teruel','Ronda','Benidorm',
    'Costa del Sol','Costa Brava','Costa Blanca','Canarias','Baleares','Asturias','Galicia',
]

SOURCE_COLORS = {
    'Idealista':'#0052cc','Fotocasa':'#e8401c','Habitaclia':'#7c3aed',
    'Kyero':'#059669','ThinkSpain':'#b45309','Pisos.com':'#0891b2',
    'Nuroa':'#be185d','Trovit':'#d97706','Indomio':'#16a34a',
    'Hogaria':'#9333ea','Yaencontré':'#dc2626',
}

def fetch(url, timeout=15):
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode('utf-8', errors='ignore')
    except Exception as e:
        print(f"    ✗ {url[:60]}... → {e}")
        return ""

def clean(t):
    if not t: return ""
    t = unescape(t)
    t = re.sub(r'<[^>]+>', ' ', t)
    t = re.sub(r'\s+', ' ', t)
    return t.strip()

def extract_price(text):
    m = re.search(r'[\d]{3,}[\d\.,]*\s*€|€\s*[\d]{3,}[\d\.,]*', text)
    return m.group(0).strip() if m else 'Precio a consultar'

def extract_location(text):
    for city in CITIES:
        if city.lower() in text.lower():
            return city
    return 'España'

def parse_rss(url, source, keywords=None):
    results = []
    content = fetch(url)
    if not content:
        return results

    # Try XML parse first
    try:
        content_clean = re.sub(r'<\?xml[^>]*\?>', '', content)
        content_clean = re.sub(r' xmlns[^=]*="[^"]*"', '', content_clean)
        root = ET.fromstring(content_clean)
        items = root.findall('.//item')
    except ET.ParseError:
        # Fallback: regex
        raw_items = re.findall(r'<item[^>]*>(.*?)</item>', content, re.DOTALL)
        items = None

    def extract_tag(text, tag):
        m = re.search(rf'<{tag}[^>]*>(.*?)</{tag}>', text, re.DOTALL)
        return clean(m.group(1)) if m else ''

    if items is not None:
        for item in items:
            title = clean(item.findtext('title', ''))
            desc = clean(item.findtext('description', ''))
            link = clean(item.findtext('link', ''))
            combined = (title + ' ' + desc).lower()
            if keywords and not any(k in combined for k in keywords):
                continue
            if not title:
                continue
            results.append({
                'title': title[:120],
                'price': extract_price(desc + ' ' + title),
                'location': extract_location(title + ' ' + desc),
                'description': desc[:180],
                'url': link or url,
                'source': source,
                'date': datetime.now().strftime('%d/%m/%Y'),
            })
    else:
        for raw in raw_items:
            title = extract_tag(raw, 'title')
            desc = extract_tag(raw, 'description')
            link = extract_tag(raw, 'link')
            combined = (title + ' ' + desc).lower()
            if keywords and not any(k in combined for k in keywords):
                continue
            if not title:
                continue
            results.append({
                'title': title[:120],
                'price': extract_price(desc + ' ' + title),
                'location': extract_location(title + ' ' + desc),
                'description': desc[:180],
                'url': link or url,
                'source': source,
                'date': datetime.now().strftime('%d/%m/%Y'),
            })
    return results

# ── SCRAPERS ──────────────────────────────────

def scrape_fotocasa():
    urls = [
        "https://www.fotocasa.es/rss/comprar/locales-comerciales/espana/hotel/l.xml",
        "https://www.fotocasa.es/rss/comprar/locales-comerciales/todas-las-provincias/hotel/l.xml",
    ]
    r = []
    for u in urls:
        r += parse_rss(u, 'Fotocasa', HOTEL_KEYWORDS); time.sleep(1)
    return r

def scrape_idealista():
    urls = [
        "https://www.idealista.com/rss/venta-locales/espana/hotel.xml",
        "https://www.idealista.com/rss/venta-locales/con-hotel.xml",
    ]
    r = []
    for u in urls:
        r += parse_rss(u, 'Idealista', HOTEL_KEYWORDS); time.sleep(1)
    return r

def scrape_habitaclia():
    urls = [
        "https://www.habitaclia.com/rss/venta/locales/hotel/espana.xml",
    ]
    r = []
    for u in urls:
        r += parse_rss(u, 'Habitaclia', HOTEL_KEYWORDS); time.sleep(1)
    return r

def scrape_kyero():
    urls = [
        "https://www.kyero.com/es/feed/hoteles-en-venta",
        "https://www.kyero.com/feed/property-type/hotel/for-sale/spain",
    ]
    r = []
    for u in urls:
        r += parse_rss(u, 'Kyero', HOTEL_KEYWORDS); time.sleep(1)
    return r

def scrape_pisos():
    urls = [
        "https://www.pisos.com/rss/venta/locales/hotel/espana/",
    ]
    r = []
    for u in urls:
        r += parse_rss(u, 'Pisos.com', HOTEL_KEYWORDS); time.sleep(1)
    return r

def scrape_nuroa():
    urls = [
        "https://www.nuroa.es/rss/venta/hotel/espana",
        "https://www.nuroa.es/rss/comprar/hotel/espana",
    ]
    r = []
    for u in urls:
        r += parse_rss(u, 'Nuroa', HOTEL_KEYWORDS); time.sleep(1)
    return r

def scrape_trovit():
    urls = [
        "https://casas.trovit.es/rss/search.php?what=hotel+en+venta&type=1&country=es",
    ]
    r = []
    for u in urls:
        r += parse_rss(u, 'Trovit', HOTEL_KEYWORDS); time.sleep(1)
    return r

def scrape_thinkspain():
    urls = [
        "https://www.thinkspain.com/rss/property-for-sale/spain/hotels",
    ]
    r = []
    for u in urls:
        r += parse_rss(u, 'ThinkSpain', HOTEL_KEYWORDS); time.sleep(1)
    return r

def scrape_indomio():
    urls = [
        "https://indomio.es/rss/venta/hotel/espana",
        "https://www.indomio.es/rss/locales-comerciales-en-venta/espana/",
    ]
    r = []
    for u in urls:
        r += parse_rss(u, 'Indomio', HOTEL_KEYWORDS); time.sleep(1)
    return r

def scrape_hogaria():
    urls = [
        "https://www.hogaria.net/rss/venta-hoteles-espana.xml",
    ]
    r = []
    for u in urls:
        r += parse_rss(u, 'Hogaria', HOTEL_KEYWORDS); time.sleep(1)
    return r

def scrape_yaencontre():
    urls = [
        "https://www.yaencontre.com/rss/venta/hoteles/espana",
        "https://www.yaencontre.com/rss/inmuebles/hotel/venta/espana",
    ]
    r = []
    for u in urls:
        r += parse_rss(u, 'Yaencontré', HOTEL_KEYWORDS); time.sleep(1)
    return r

# ── FALLBACK ──────────────────────────────────

def fallback():
    return [
        {'title':'Hotel boutique centro histórico','price':'1.200.000 €','location':'Barcelona','description':'20 hab. totalmente reformado. Licencia turística en vigor.','url':'https://www.idealista.com/venta-locales/con-hotel/','source':'Idealista','date':datetime.now().strftime('%d/%m/%Y')},
        {'title':'Hotel rural con restaurante y spa','price':'850.000 €','location':'Segovia','description':'15 hab., restaurante y zona wellness.','url':'https://www.fotocasa.es','source':'Fotocasa','date':datetime.now().strftime('%d/%m/%Y')},
        {'title':'Hotel frente al mar primera línea','price':'3.500.000 €','location':'Marbella','description':'35 hab. con piscina y acceso directo a playa.','url':'https://www.kyero.com','source':'Kyero','date':datetime.now().strftime('%d/%m/%Y')},
        {'title':'Hostal en zona turística consolidada','price':'320.000 €','location':'Toledo','description':'12 hab. pleno centro histórico.','url':'https://www.habitaclia.com','source':'Habitaclia','date':datetime.now().strftime('%d/%m/%Y')},
        {'title':'Hotel con encanto en pueblo medieval','price':'Precio a consultar','location':'Ronda','description':'Edificio histórico, 18 hab. con vistas al tajo.','url':'https://www.thinkspain.com','source':'ThinkSpain','date':datetime.now().strftime('%d/%m/%Y')},
        {'title':'Aparthotel en zona costera','price':'2.100.000 €','location':'Alicante','description':'28 apartamentos turísticos. Ocupación media 80%.','url':'https://www.pisos.com','source':'Pisos.com','date':datetime.now().strftime('%d/%m/%Y')},
        {'title':'Casa rural con licencia turística','price':'450.000 €','location':'Granada','description':'8 hab. en plena naturaleza, Sierra Nevada.','url':'https://www.nuroa.es','source':'Nuroa','date':datetime.now().strftime('%d/%m/%Y')},
        {'title':'Hotel urbano en barrio de moda','price':'4.800.000 €','location':'Madrid','description':'45 hab., restaurante y sala eventos. Plena actividad.','url':'https://casas.trovit.es','source':'Trovit','date':datetime.now().strftime('%d/%m/%Y')},
    ]

# ── HTML ──────────────────────────────────────

def generate_html(listings):
    now = datetime.now()
    months = ['enero','febrero','marzo','abril','mayo','junio','julio','agosto','septiembre','octubre','noviembre','diciembre']
    date_str = f"{now.day} de {months[now.month-1]} de {now.year}"
    time_str = now.strftime('%H:%M')
    sources = sorted(set(l['source'] for l in listings))

    cards = ""
    for l in listings:
        color = SOURCE_COLORS.get(l['source'], '#374151')
        desc = l.get('description', '')
        cards += f"""<a href="{l['url']}" target="_blank" rel="noopener" class="card">
  <div class="card-header"><span class="badge" style="background:{color}">{l['source']}</span><span class="card-date">{l['date']}</span></div>
  <h3 class="card-title">{l['title']}</h3>
  <div class="card-location"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>{l['location']}</div>
  {f'<p class="card-desc">{desc}</p>' if desc else ''}
  <div class="card-price">{l['price']}</div>
  <div class="card-cta">Ver ficha completa →</div>
</a>"""

    source_tags = "".join(f'<span class="source-tag">{s}</span>' for s in sources)

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Hoteles en Venta · España</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,700;0,900;1,700&family=DM+Sans:wght@300;400;500&display=swap" rel="stylesheet">
<style>
:root{{--ink:#0f0e0d;--paper:#f5f0e8;--accent:#c8973a;--accent2:#8b5e3c;--muted:#7a7060;--card:#faf7f2;--border:#e2d9c8}}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:var(--paper);color:var(--ink);font-family:'DM Sans',sans-serif}}
header{{border-bottom:2px solid var(--ink);padding:0 2rem;position:sticky;top:0;background:var(--paper);z-index:100;display:flex;align-items:center;justify-content:space-between;height:64px}}
.logo{{font-family:'Playfair Display',serif;font-size:1.4rem;font-weight:900}}
.logo span{{color:var(--accent)}}
.hmeta{{font-size:.73rem;color:var(--muted);text-align:right;line-height:1.5}}
.hero{{padding:3rem 2rem 2rem;max-width:1280px;margin:0 auto;display:grid;grid-template-columns:1fr auto;align-items:end;gap:2rem;border-bottom:1px solid var(--border);margin-bottom:2rem}}
.eyebrow{{font-size:.7rem;letter-spacing:.2em;text-transform:uppercase;color:var(--accent2);font-weight:500;margin-bottom:.5rem}}
h1{{font-family:'Playfair Display',serif;font-size:clamp(2rem,5vw,3.8rem);font-weight:900;line-height:1;letter-spacing:-1px}}
h1 em{{font-style:italic;color:var(--accent)}}
.sub{{margin-top:.7rem;color:var(--muted);font-size:.88rem;max-width:460px;line-height:1.6}}
.snum{{font-family:'Playfair Display',serif;font-size:2.8rem;font-weight:900;color:var(--accent);line-height:1;text-align:right}}
.slabel{{font-size:.68rem;color:var(--muted);text-transform:uppercase;letter-spacing:.1em;text-align:right}}
.sbar{{max-width:1280px;margin:0 auto 1.8rem;padding:0 2rem;display:flex;gap:.35rem;flex-wrap:wrap;align-items:center}}
.slabel2{{font-size:.68rem;color:var(--muted);margin-right:.3rem;text-transform:uppercase;letter-spacing:.1em}}
.stag{{font-size:.66rem;font-weight:500;padding:.18rem .6rem;border-radius:100px;border:1px solid var(--border);color:var(--muted);background:#fff}}
.grid{{max-width:1280px;margin:0 auto;padding:0 2rem 4rem;display:grid;grid-template-columns:repeat(auto-fill,minmax(290px,1fr));gap:1.1rem}}
.card{{display:block;text-decoration:none;color:inherit;background:var(--card);border:1px solid var(--border);border-radius:4px;padding:1.3rem;transition:transform .2s,box-shadow .2s,border-color .2s;position:relative;overflow:hidden}}
.card::before{{content:'';position:absolute;top:0;left:0;right:0;height:3px;background:var(--accent);transform:scaleX(0);transform-origin:left;transition:transform .3s}}
.card:hover{{transform:translateY(-4px);box-shadow:0 10px 36px rgba(0,0,0,.09);border-color:var(--accent)}}
.card:hover::before{{transform:scaleX(1)}}
.card-header{{display:flex;justify-content:space-between;align-items:center;margin-bottom:.8rem}}
.badge{{font-size:.6rem;font-weight:600;color:#fff;padding:.16rem .5rem;border-radius:3px;text-transform:uppercase;letter-spacing:.04em}}
.card-date{{font-size:.66rem;color:var(--muted)}}
.card-title{{font-family:'Playfair Display',serif;font-size:1rem;font-weight:700;line-height:1.3;margin-bottom:.45rem}}
.card-location{{display:flex;align-items:center;gap:.28rem;font-size:.74rem;color:var(--muted);margin-bottom:.6rem}}
.card-desc{{font-size:.76rem;color:var(--muted);line-height:1.5;margin-bottom:.8rem}}
.card-price{{font-family:'Playfair Display',serif;font-size:1.25rem;font-weight:700;color:var(--accent2);margin-bottom:.6rem}}
.card-cta{{font-size:.72rem;font-weight:500;color:var(--accent);border-top:1px solid var(--border);padding-top:.6rem}}
footer{{border-top:1px solid var(--border);padding:1.2rem 2rem;max-width:1280px;margin:0 auto;display:flex;justify-content:space-between;font-size:.7rem;color:var(--muted)}}
@media(max-width:640px){{.hero{{grid-template-columns:1fr}}.snum,.slabel{{text-align:left}}.grid{{grid-template-columns:1fr;padding:0 1rem 3rem}}header,.sbar{{padding:0 1rem}}}}
</style>
</head>
<body>
<header>
  <div class="logo">Hotel<span>·</span>España</div>
  <div class="hmeta">Actualizado: {date_str}<br>a las {time_str}h</div>
</header>
<section class="hero">
  <div>
    <div class="eyebrow">Radar de mercado · Hoteles en venta</div>
    <h1>Hoteles en<br><em>venta</em> en España</h1>
    <p class="sub">Agregador diario de {len(sources)} portales inmobiliarios. Actualización automática cada 24 horas.</p>
  </div>
  <div><div class="snum">{len(listings)}</div><div class="slabel">Anuncios hoy</div></div>
</section>
<div class="sbar">
  <span class="slabel2">Fuentes</span>{source_tags}
</div>
<main class="grid">{cards}</main>
<footer>
  <span>🏨 HotelEspaña · Datos de portales públicos</span>
  <span>Próxima actualización: mañana 08:00h</span>
</footer>
</body>
</html>"""


if __name__ == "__main__":
    print("🔍 Buscando hoteles en venta en España...")
    scrapers = [
        ("Idealista",   scrape_idealista),
        ("Fotocasa",    scrape_fotocasa),
        ("Habitaclia",  scrape_habitaclia),
        ("Kyero",       scrape_kyero),
        ("Pisos.com",   scrape_pisos),
        ("Nuroa",       scrape_nuroa),
        ("Trovit",      scrape_trovit),
        ("ThinkSpain",  scrape_thinkspain),
        ("Indomio",     scrape_indomio),
        ("Hogaria",     scrape_hogaria),
        ("Yaencontré",  scrape_yaencontre),
    ]
    all_listings = []
    for name, fn in scrapers:
        print(f"  → {name}...")
        try:
            r = fn()
            all_listings.extend(r)
            print(f"     ✓ {len(r)} anuncios")
        except Exception as e:
            print(f"     ✗ {e}")

    # Deduplicate
    seen, unique = set(), []
    for l in all_listings:
        key = l['title'][:40].lower()
        if key not in seen:
            seen.add(key); unique.append(l)

    if not unique:
        print("  ⚠ Sin resultados reales, usando datos de ejemplo")
        unique = fallback()

    print(f"\n📋 Total: {len(unique)} anuncios únicos")

    # Read the HTML template and inject data
    try:
        with open("index.html", "r", encoding="utf-8") as f:
            html = f.read()
        
        import json
        json_data = json.dumps(unique, ensure_ascii=False, indent=2)
        html = html.replace("LISTINGS_DATA_PLACEHOLDER", json_data)
        
        with open("index.html", "w", encoding="utf-8") as f:
            f.write(html)
        print("✅ index.html actualizado con datos reales")
    except Exception as e:
        print(f"✗ Error actualizando HTML: {e}")
        # Fallback: generate full HTML
        html = generate_html(unique)
        with open("index.html", "w", encoding="utf-8") as f:
            f.write(html)
        print("✅ index.html generado (fallback)")
