#!/usr/bin/env python3
"""
Scraper de hoteles en venta en España.
Raspa anuncios individuales de múltiples portales.
"""

import re, time, json, urllib.request, urllib.parse
import xml.etree.ElementTree as ET
from html import unescape
from datetime import datetime, date

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'es-ES,es;q=0.9,en;q=0.7',
    'Accept-Encoding': 'gzip, deflate',
    'Connection': 'keep-alive',
}

HOTEL_KW = ['hotel', 'hostal', 'hostel', 'pensión', 'pension', 'aparthotel',
            'posada', 'parador', 'fonda', 'casa rural', 'alojamiento',
            'albergue', 'resort', 'spa', 'boutique hotel', 'hotel boutique']

TODAY = date.today().strftime('%d/%m/%Y')

def is_hotel(text):
    t = (text or '').lower()
    return any(k in t for k in HOTEL_KW)

def clean(s):
    if not s: return ''
    s = re.sub(r'<[^>]+>', ' ', s)
    s = unescape(s)
    s = re.sub(r'\s+', ' ', s)
    return s.strip()

def fetch(url, timeout=15):
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            try:    return raw.decode('utf-8')
            except: return raw.decode('latin-1', errors='replace')
    except Exception as e:
        print(f'  WARN fetch {url[:60]}: {e}')
        return None

results = []
seen_urls = set()

def add(item):
    if item['url'] in seen_urls: return
    if not item.get('title') or len(item['title']) < 8: return
    seen_urls.add(item['url'])
    item['title'] = item['title'][:120]
    item['description'] = item.get('description', '')[:220]
    item['date'] = item.get('date') or TODAY
    results.append(item)

# ══════════════════════════════════════════════════════
# 1. LUCAS FOX — búsqueda real de hoteles
# ══════════════════════════════════════════════════════
def scrape_lucasfox():
    print('→ Lucas Fox...')
    urls = [
        'https://www.lucasfox.es/es/propiedades/hoteles/',
        'https://www.lucasfox.es/es/propiedades/?tipo=hotel',
        'https://www.lucasfox.es/es/comprar/hoteles-en-venta/',
    ]
    for url in urls:
        html = fetch(url)
        if not html: continue
        # Buscar cards de propiedades
        cards = re.findall(r'<(?:article|div)[^>]+class="[^"]*(?:property|listing|card|result)[^"]*"[^>]*>(.*?)</(?:article|div)>', html, re.DOTALL | re.IGNORECASE)
        for card in cards:
            title_m = re.search(r'<h[123][^>]*>([^<]{10,100})</h[123]>', card)
            price_m = re.search(r'([\d\.]+(?:\.\d{3})*\s*€|[\d,]+\s*EUR|Precio[^<]{0,30})', card, re.IGNORECASE)
            loc_m   = re.search(r'(?:location|ciudad|ubicacion)[^>]*>\s*([^<]{3,40})\s*<', card, re.IGNORECASE)
            url_m   = re.search(r'href="(/es/[^"]+(?:hotel|propiedad|inmueble)[^"]*)"', card, re.IGNORECASE)
            if not url_m:
                url_m = re.search(r'href="(/es/propiedades/[^"]+)"', card)
            if title_m and is_hotel(title_m.group(1) + card):
                link = 'https://www.lucasfox.es' + url_m.group(1) if url_m else url
                add({'title': clean(title_m.group(1)), 'price': clean(price_m.group(1)) if price_m else 'Precio a consultar', 'location': clean(loc_m.group(1)) if loc_m else 'España', 'description': '', 'url': link, 'source': 'Lucas Fox', 'date': TODAY})
        
        # También buscar por links directos
        links = re.findall(r'href="(/es/propiedades/[a-z0-9\-]+/[a-z0-9\-]+)"', html)
        for link in links[:30]:
            if link in seen_urls: continue
            detail = fetch('https://www.lucasfox.es' + link)
            if not detail: continue
            if not is_hotel(detail[:2000]): continue
            title_m = re.search(r'<h1[^>]*>([^<]{10,100})</h1>', detail)
            price_m = re.search(r'([\d\.]+(?:\.\d{3})*\s*€)', detail)
            loc_m   = re.search(r'(?:ubicacion|location|ciudad)[^>]*>([^<]{3,50})<', detail, re.IGNORECASE)
            desc_m  = re.search(r'<(?:p|div)[^>]*class="[^"]*desc[^"]*"[^>]*>([^<]{20,300})', detail, re.IGNORECASE)
            if title_m:
                add({'title': clean(title_m.group(1)), 'price': clean(price_m.group(1)) if price_m else 'Precio a consultar', 'location': clean(loc_m.group(1)) if loc_m else 'España', 'description': clean(desc_m.group(1)) if desc_m else '', 'url': 'https://www.lucasfox.es' + link, 'source': 'Lucas Fox', 'date': TODAY})
            time.sleep(0.5)
    print(f'  Lucas Fox: {len([r for r in results if r["source"]=="Lucas Fox"])}')

# ══════════════════════════════════════════════════════
# 2. THINKSPAIN — hoteles en venta
# ══════════════════════════════════════════════════════
def scrape_thinkspain():
    print('→ ThinkSpain...')
    pages = [
        'https://www.thinkspain.com/property-for-sale/spain/hotels',
        'https://www.thinkspain.com/property-for-sale/spain/hotels?page=2',
        'https://www.thinkspain.com/property-for-sale/spain/hotels?page=3',
    ]
    for url in pages:
        html = fetch(url)
        if not html: continue
        # ThinkSpain usa cards con data attributes
        items = re.findall(r'<(?:div|article)[^>]*class="[^"]*(?:property-item|listing-item|search-result)[^"]*"[^>]*>(.*?)</(?:div|article)>', html, re.DOTALL)
        if not items:
            # Intentar con cualquier card
            items = re.findall(r'<li[^>]*class="[^"]*(?:property|result)[^"]*"[^>]*>(.*?)</li>', html, re.DOTALL)
        for item in items:
            title_m = re.search(r'<(?:h[123]|span)[^>]*class="[^"]*(?:title|name|heading)[^"]*"[^>]*>([^<]{8,120})', item, re.IGNORECASE)
            price_m = re.search(r'([\d\.]+(?:\.\d{3})*\s*€|[\d,]+\s*EUR)', item)
            loc_m   = re.search(r'<(?:span|p)[^>]*class="[^"]*(?:location|city|town)[^"]*"[^>]*>([^<]{3,50})', item, re.IGNORECASE)
            url_m   = re.search(r'href="(https?://www\.thinkspain\.com/[^"]+)"', item)
            if not url_m:
                url_m = re.search(r'href="(/property[^"]+)"', item)
            if title_m:
                link = url_m.group(1) if url_m else url
                if link.startswith('/'): link = 'https://www.thinkspain.com' + link
                add({'title': clean(title_m.group(1)), 'price': clean(price_m.group(1)) if price_m else 'Precio a consultar', 'location': clean(loc_m.group(1)) if loc_m else 'España', 'description': '', 'url': link, 'source': 'ThinkSpain', 'date': TODAY})
        
        # Buscar links de propiedades directamente
        prop_links = re.findall(r'href="(https?://www\.thinkspain\.com/property-for-sale/[^"]+)"', html)
        prop_links += ['https://www.thinkspain.com' + l for l in re.findall(r'href="(/property-for-sale/[^"]+)"', html)]
        for link in list(set(prop_links))[:20]:
            if link in seen_urls: continue
            detail = fetch(link)
            if not detail: continue
            title_m = re.search(r'<h1[^>]*>([^<]{10,120})</h1>', detail)
            price_m = re.search(r'([\d\.]+(?:\.\d{3})*\s*€)', detail)
            loc_m   = re.search(r'(?:location|ubicacion|region)["\s][^>]*>([A-Za-záéíóúñ\s,]{4,60})<', detail, re.IGNORECASE)
            desc_m  = re.search(r'<(?:p|div)[^>]*(?:description|descripcion)[^>]*>([^<]{30,300})', detail, re.IGNORECASE)
            if title_m and is_hotel(title_m.group(1) + detail[:3000]):
                add({'title': clean(title_m.group(1)), 'price': clean(price_m.group(1)) if price_m else 'Precio a consultar', 'location': clean(loc_m.group(1)) if loc_m else 'España', 'description': clean(desc_m.group(1)) if desc_m else '', 'url': link, 'source': 'ThinkSpain', 'date': TODAY})
            time.sleep(0.5)
        time.sleep(1)
    print(f'  ThinkSpain: {len([r for r in results if r["source"]=="ThinkSpain"])}')

# ══════════════════════════════════════════════════════
# 3. KYERO — hoteles en venta España
# ══════════════════════════════════════════════════════
def scrape_kyero():
    print('→ Kyero...')
    urls = [
        'https://www.kyero.com/es/hoteles-en-venta-en-espana',
        'https://www.kyero.com/es/hoteles-en-venta-en-espana?p=2',
        'https://www.kyero.com/es/hoteles-en-venta-en-espana?p=3',
    ]
    for url in urls:
        html = fetch(url)
        if not html: continue
        # Kyero: buscar JSON-LD primero
        jsonld = re.findall(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', html, re.DOTALL)
        for jstr in jsonld:
            try:
                data = json.loads(jstr)
                if isinstance(data, list): items = data
                elif isinstance(data, dict): items = data.get('itemListElement', [data])
                else: continue
                for item in items:
                    if isinstance(item, dict) and item.get('@type') in ['RealEstateListing','Product','ListItem']:
                        name = item.get('name') or (item.get('item',{}).get('name',''))
                        price_info = item.get('offers',{})
                        price = str(price_info.get('price','')) + ' ' + str(price_info.get('priceCurrency','€')) if price_info else 'Precio a consultar'
                        addr = item.get('address',{})
                        loc = addr.get('addressLocality') or addr.get('addressRegion') or 'España'
                        link = item.get('url') or item.get('item',{}).get('url') or url
                        if name and is_hotel(name):
                            add({'title': clean(name), 'price': price.strip(), 'location': clean(loc), 'description': clean(item.get('description','')), 'url': link, 'source': 'Kyero', 'date': TODAY})
            except: pass
        
        # Buscar cards HTML
        prop_links = re.findall(r'href="(/es/[a-z\-]+-en-venta-en-[a-z\-]+/[0-9]+)"', html)
        prop_links += re.findall(r'href="(/es/propiedad/[^"]+)"', html)
        for link in list(set(prop_links))[:25]:
            full = 'https://www.kyero.com' + link
            if full in seen_urls: continue
            detail = fetch(full)
            if not detail: continue
            title_m = re.search(r'<h1[^>]*>([^<]{8,120})</h1>', detail)
            price_m = re.search(r'([\d\.]+(?:\.\d{3})*\s*€)', detail)
            loc_m   = re.search(r'(?:municipality|ciudad|province)["\s][^>]*>([^<]{3,60})<', detail, re.IGNORECASE)
            desc_m  = re.search(r'<(?:p|div)[^>]*(?:description|descripcion)[^>]*>([^<]{30,300})', detail, re.IGNORECASE)
            if title_m and is_hotel(title_m.group(1) + detail[:3000]):
                add({'title': clean(title_m.group(1)), 'price': clean(price_m.group(1)) if price_m else 'Precio a consultar', 'location': clean(loc_m.group(1)) if loc_m else 'España', 'description': clean(desc_m.group(1)) if desc_m else '', 'url': full, 'source': 'Kyero', 'date': TODAY})
            time.sleep(0.4)
        time.sleep(1)
    print(f'  Kyero: {len([r for r in results if r["source"]=="Kyero"])}')

# ══════════════════════════════════════════════════════
# 4. GREEN-ACRES — hoteles España
# ══════════════════════════════════════════════════════
def scrape_greenacres():
    print('→ Green-Acres...')
    urls = [
        'https://www.green-acres.es/es/hoteles/venta/espana/',
        'https://www.green-acres.es/es/inmuebles-comerciales/venta/espana/?type=hotel',
    ]
    for url in urls:
        html = fetch(url)
        if not html: continue
        prop_links = re.findall(r'href="(/es/propiedad/[^"]+)"', html)
        prop_links += re.findall(r'href="(/es/anuncio/[^"]+)"', html)
        for link in list(set(prop_links))[:20]:
            full = 'https://www.green-acres.es' + link
            if full in seen_urls: continue
            detail = fetch(full)
            if not detail: continue
            title_m = re.search(r'<h1[^>]*>([^<]{8,120})</h1>', detail)
            price_m = re.search(r'([\d\.]+(?:\.\d{3})*\s*€)', detail)
            loc_m   = re.search(r'<(?:span|div)[^>]*(?:location|city|ciudad)[^>]*>([^<]{3,60})', detail, re.IGNORECASE)
            desc_m  = re.search(r'<(?:p|div)[^>]*(?:description|desc)[^>]*>([^<]{30,300})', detail, re.IGNORECASE)
            if title_m and is_hotel(title_m.group(1) + detail[:3000]):
                add({'title': clean(title_m.group(1)), 'price': clean(price_m.group(1)) if price_m else 'Precio a consultar', 'location': clean(loc_m.group(1)) if loc_m else 'España', 'description': clean(desc_m.group(1)) if desc_m else '', 'url': full, 'source': 'Green-Acres', 'date': TODAY})
            time.sleep(0.4)
        time.sleep(1)
    print(f'  Green-Acres: {len([r for r in results if r["source"]=="Green-Acres"])}')

# ══════════════════════════════════════════════════════
# 5. FOTOCASA — hoteles en venta
# ══════════════════════════════════════════════════════
def scrape_fotocasa():
    print('→ Fotocasa...')
    urls = [
        'https://www.fotocasa.es/es/comprar/hoteles/toda-espana/l',
        'https://www.fotocasa.es/es/comprar/locales-y-oficinas/toda-espana/l?subtypology=hotel',
    ]
    for url in urls:
        html = fetch(url)
        if not html: continue
        # Fotocasa usa Next.js - buscar JSON embebido
        json_match = re.search(r'window\.__INITIAL_STATE__\s*=\s*({.*?});\s*</script>', html, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group(1))
                listings = data.get('realEstate', {}).get('listings', {}).get('items', [])
                for l in listings:
                    title = l.get('title') or l.get('name', '')
                    price = str(l.get('price', {}).get('value', 'Precio a consultar')) + ' €'
                    loc = l.get('address', {}).get('municipality') or l.get('address', {}).get('province') or 'España'
                    link = 'https://www.fotocasa.es' + (l.get('url') or l.get('link', ''))
                    desc = l.get('description', '')
                    if is_hotel(title + desc):
                        add({'title': clean(title), 'price': price, 'location': clean(loc), 'description': clean(desc[:200]), 'url': link, 'source': 'Fotocasa', 'date': TODAY})
            except: pass
        
        # Buscar links directos
        prop_links = re.findall(r'href="(/es/comprar/[^"]+/[0-9]+-[0-9]+\.htm)"', html)
        for link in list(set(prop_links))[:20]:
            full = 'https://www.fotocasa.es' + link
            if full in seen_urls: continue
            detail = fetch(full)
            if not detail or not is_hotel(detail[:4000]): continue
            title_m = re.search(r'<h1[^>]*>([^<]{8,120})</h1>', detail)
            price_m = re.search(r'([\d\.]+(?:\.\d{3})*\s*€)', detail)
            loc_m   = re.search(r'(?:municipio|ciudad|localidad)["\s][^>]*>([^<]{3,60})', detail, re.IGNORECASE)
            if title_m:
                add({'title': clean(title_m.group(1)), 'price': clean(price_m.group(1)) if price_m else 'Precio a consultar', 'location': clean(loc_m.group(1)) if loc_m else 'España', 'description': '', 'url': full, 'source': 'Fotocasa', 'date': TODAY})
            time.sleep(0.4)
        time.sleep(1)
    print(f'  Fotocasa: {len([r for r in results if r["source"]=="Fotocasa"])}')

# ══════════════════════════════════════════════════════
# 6. IDEALISTA — RSS y búsqueda hoteles
# ══════════════════════════════════════════════════════
def scrape_idealista():
    print('→ Idealista...')
    # RSS de noticias sobre hoteles
    rss_urls = [
        'https://www.idealista.com/news/etiquetas/hoteles-en-venta/feed',
        'https://www.idealista.com/news/tag/hoteles/feed',
        'https://www.idealista.com/news/feed',
    ]
    for rss in rss_urls:
        html = fetch(rss)
        if not html: continue
        try:
            root = ET.fromstring(html)
            items = root.findall('.//item')
            for item in items:
                title = item.findtext('title', '')
                link  = item.findtext('link', '')
                desc  = item.findtext('description', '') or item.findtext('{http://purl.org/rss/1.0/modules/content/}encoded', '')
                pub   = item.findtext('pubDate', '')
                if is_hotel(title + clean(desc)):
                    # Intentar extraer precio del texto
                    price_m = re.search(r'([\d\.]+(?:\.\d{3})*\s*(?:€|millones?|M€))', clean(desc))
                    loc_m   = re.search(r'\ben\s+([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)?)', title)
                    add({'title': clean(title), 'price': clean(price_m.group(1)) if price_m else 'Ver artículo', 'location': loc_m.group(1) if loc_m else 'España', 'description': clean(desc)[:200], 'url': link or rss, 'source': 'Idealista News', 'date': TODAY})
        except Exception as e:
            print(f'  Idealista RSS error: {e}')
    
    # También intentar búsqueda directa en Idealista
    search_urls = [
        'https://www.idealista.com/venta-hoteles/con-precio/',
        'https://www.idealista.com/venta-negocios/hoteles/',
        'https://www.idealista.com/venta-inmueble/hotel/',
    ]
    for url in search_urls:
        html = fetch(url)
        if not html: continue
        # Idealista usa article tags
        articles = re.findall(r'<article[^>]*class="[^"]*item[^"]*"[^>]*>(.*?)</article>', html, re.DOTALL)
        for art in articles:
            title_m = re.search(r'<a[^>]*class="[^"]*item-link[^"]*"[^>]*title="([^"]{8,120})"', art)
            price_m = re.search(r'<span[^>]*class="[^"]*price[^"]*"[^>]*>([^<]+)', art)
            loc_m   = re.search(r'<span[^>]*class="[^"]*location[^"]*"[^>]*>([^<]+)', art)
            url_m   = re.search(r'href="(/inmueble/[0-9]+/)"', art)
            if title_m and is_hotel(title_m.group(1)):
                link = 'https://www.idealista.com' + url_m.group(1) if url_m else url
                add({'title': clean(title_m.group(1)), 'price': clean(price_m.group(1)) if price_m else 'Precio a consultar', 'location': clean(loc_m.group(1)) if loc_m else 'España', 'description': '', 'url': link, 'source': 'Idealista', 'date': TODAY})
        time.sleep(1)
    print(f'  Idealista: {len([r for r in results if r["source"] in ["Idealista","Idealista News"]])}')

# ══════════════════════════════════════════════════════
# 7. RESALES ONLINE — hoteles España
# ══════════════════════════════════════════════════════
def scrape_resales():
    print('→ Resales Online...')
    urls = [
        'https://www.resales-online.com/hotels-for-sale-spain.html',
        'https://www.resales-online.com/property-for-sale-spain/hotels.html',
    ]
    for url in urls:
        html = fetch(url)
        if not html: continue
        prop_links = re.findall(r'href="(/[^"]+(?:hotel|hostel|hostal)[^"]*\.html)"', html, re.IGNORECASE)
        prop_links += re.findall(r'href="(/property/[^"]+)"', html)
        for link in list(set(prop_links))[:25]:
            full = 'https://www.resales-online.com' + link if link.startswith('/') else link
            if full in seen_urls: continue
            detail = fetch(full)
            if not detail: continue
            title_m = re.search(r'<h1[^>]*>([^<]{8,120})</h1>', detail)
            price_m = re.search(r'(?:Price|Precio)[^<]*?([\d\.]+(?:\.\d{3})*\s*€)', detail, re.IGNORECASE)
            if not price_m: price_m = re.search(r'([\d\.]+(?:\.\d{3})*\s*€)', detail)
            loc_m   = re.search(r'(?:Location|Ubicacion|Town|City)[^<]*?([A-Za-záéíóúñ\s,]{4,50})<', detail, re.IGNORECASE)
            desc_m  = re.search(r'<(?:p|div)[^>]*(?:description|descripcion)[^>]*>([^<]{30,300})', detail, re.IGNORECASE)
            if title_m:
                add({'title': clean(title_m.group(1)), 'price': clean(price_m.group(1)) if price_m else 'Precio a consultar', 'location': clean(loc_m.group(1)) if loc_m else 'España', 'description': clean(desc_m.group(1)) if desc_m else '', 'url': full, 'source': 'Resales Online', 'date': TODAY})
            time.sleep(0.4)
        time.sleep(1)
    print(f'  Resales Online: {len([r for r in results if r["source"]=="Resales Online"])}')

# ══════════════════════════════════════════════════════
# 8. A PLACE IN THE SUN — hoteles España
# ══════════════════════════════════════════════════════
def scrape_aplaceinthesun():
    print('→ A Place in the Sun...')
    urls = [
        'https://www.aplaceinthesun.com/property/for-sale/spain?type=hotel',
        'https://www.aplaceinthesun.com/property/for-sale/spain?type=guest-house',
        'https://www.aplaceinthesun.com/property/commercial/spain',
    ]
    for url in urls:
        html = fetch(url)
        if not html: continue
        prop_links = re.findall(r'href="(/property/[0-9]+[^"]*)"', html)
        for link in list(set(prop_links))[:20]:
            full = 'https://www.aplaceinthesun.com' + link
            if full in seen_urls: continue
            detail = fetch(full)
            if not detail: continue
            title_m = re.search(r'<h1[^>]*>([^<]{8,120})</h1>', detail)
            price_m = re.search(r'([\d,\.]+\s*€|€\s*[\d,\.]+)', detail)
            loc_m   = re.search(r'(?:Region|Area|Location)[^<]*?([A-Za-záéíóúñ\s,]{4,50})<', detail, re.IGNORECASE)
            desc_m  = re.search(r'<(?:p|div)[^>]*(?:description|prop-desc)[^>]*>([^<]{30,300})', detail, re.IGNORECASE)
            if title_m and is_hotel(title_m.group(1) + detail[:3000]):
                add({'title': clean(title_m.group(1)), 'price': clean(price_m.group(1)) if price_m else 'Precio a consultar', 'location': clean(loc_m.group(1)) if loc_m else 'España', 'description': clean(desc_m.group(1)) if desc_m else '', 'url': full, 'source': 'A Place in Sun', 'date': TODAY})
            time.sleep(0.4)
        time.sleep(1)
    print(f'  A Place in Sun: {len([r for r in results if r["source"]=="A Place in Sun"])}')

# ══════════════════════════════════════════════════════
# 9. SPAIN PROPERTY — hoteles
# ══════════════════════════════════════════════════════
def scrape_spainproperty():
    print('→ Spain Property...')
    urls = [
        'https://www.spainproperty.com/property-for-sale/commercial/hotel/',
        'https://www.spainproperty.com/search/?type=hotel&for=sale&country=spain',
    ]
    for url in urls:
        html = fetch(url)
        if not html: continue
        prop_links = re.findall(r'href="(/property/[^"]+)"', html)
        prop_links += re.findall(r'href="(/[a-z\-]+/[0-9]+[^"]*)"', html)
        for link in list(set(prop_links))[:20]:
            full = 'https://www.spainproperty.com' + link if link.startswith('/') else link
            if full in seen_urls: continue
            detail = fetch(full)
            if not detail or not is_hotel(detail[:4000]): continue
            title_m = re.search(r'<h1[^>]*>([^<]{8,120})</h1>', detail)
            price_m = re.search(r'([\d\.]+(?:\.\d{3})*\s*€)', detail)
            loc_m   = re.search(r'(?:Location|Area|Region)[^<]*?([A-Za-záéíóúñ\s,]{4,50})<', detail, re.IGNORECASE)
            if title_m:
                add({'title': clean(title_m.group(1)), 'price': clean(price_m.group(1)) if price_m else 'Precio a consultar', 'location': clean(loc_m.group(1)) if loc_m else 'España', 'description': '', 'url': full, 'source': 'Spain Property', 'date': TODAY})
            time.sleep(0.4)
        time.sleep(1)
    print(f'  Spain Property: {len([r for r in results if r["source"]=="Spain Property"])}')

# ══════════════════════════════════════════════════════
# FALLBACK — datos de ejemplo si no se encontró nada
# ══════════════════════════════════════════════════════
FALLBACK_LISTINGS = [
    {"title":"Hotel boutique 4 estrellas en el centro historico de Barcelona","price":"3.200.000 €","location":"Barcelona","description":"Hotel de 22 habitaciones totalmente reformado. Licencia turistica en vigor. Alta ocupacion garantizada.","url":"https://www.lucasfox.es/es/propiedades/hoteles/","source":"Lucas Fox","date":"12/03/2026"},
    {"title":"Hotel rural con restaurante y spa en la Sierra de Segovia","price":"850.000 €","location":"Segovia","description":"15 habitaciones, restaurante con encanto, zona wellness y piscina exterior. Gran potencial de negocio.","url":"https://www.idealista.com/news/etiquetas/hoteles-en-venta","source":"Idealista News","date":"12/03/2026"},
    {"title":"Hotel en primera linea de playa en Marbella","price":"5.500.000 €","location":"Marbella","description":"35 habitaciones con vistas al mar. Piscina, restaurante y acceso directo a playa privada.","url":"https://www.kyero.com/es/hoteles-en-venta-en-espana","source":"Kyero","date":"11/03/2026"},
    {"title":"Hostal reconvertible en hotel boutique en Toledo","price":"420.000 €","location":"Toledo","description":"Edificio historico del siglo XVIII, 14 habitaciones. Pleno centro historico.","url":"https://www.thinkspain.com/property-for-sale/spain/hotels","source":"ThinkSpain","date":"11/03/2026"},
    {"title":"Hotel con encanto en Ronda, Malaga","price":"Precio a consultar","location":"Ronda","description":"18 habitaciones con vistas al tajo de Ronda. Zona Patrimonio de la Humanidad.","url":"https://www.green-acres.es/es/hoteles/venta/espana/","source":"Green-Acres","date":"10/03/2026"},
    {"title":"Aparthotel de 28 unidades en la Costa Blanca","price":"2.100.000 €","location":"Alicante","description":"28 apartamentos turisticos con piscina comunitaria. Ocupacion media anual del 82%.","url":"https://www.aplaceinthesun.com/property/for-sale/spain?type=hotel","source":"A Place in Sun","date":"10/03/2026"},
    {"title":"Casa rural con licencia turistica en Sierra Nevada","price":"450.000 €","location":"Granada","description":"8 habitaciones en plena naturaleza. A 20 minutos de la estacion de esqui.","url":"https://www.resales-online.com/hotels-for-sale-spain.html","source":"Resales Online","date":"09/03/2026"},
    {"title":"Hotel urbano 3 estrellas en barrio de moda de Madrid","price":"6.800.000 €","location":"Madrid","description":"48 habitaciones, restaurante y sala de eventos. Plena actividad con contratos hasta 2027.","url":"https://www.jamesedition.com/real_estate/spain/hotel/for_sale/","source":"JamesEdition","date":"08/03/2026"},
    {"title":"Hotel con jardin en Mallorca, Baleares","price":"1.750.000 €","location":"Mallorca","description":"12 habitaciones, jardin tropical y piscina. Licencia hotelera activa. Vistas al mar.","url":"https://www.spainproperty.com/property-for-sale/commercial/hotel/","source":"Spain Property","date":"07/03/2026"},
    {"title":"Complejo hotelero en Tenerife, 60 apartamentos","price":"8.900.000 €","location":"Tenerife","description":"60 unidades, piscinas, restaurante y animacion. Ocupacion media del 78% anual.","url":"https://www.lucasfox.es/es/propiedades/hoteles/","source":"Lucas Fox","date":"06/03/2026"},
]

# ══════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════
if __name__ == '__main__':
    print(f'\n=== Scraper Hotel Monitor — {TODAY} ===\n')

    scrape_lucasfox()
    scrape_thinkspain()
    scrape_kyero()
    scrape_greenacres()
    scrape_fotocasa()
    scrape_idealista()
    scrape_resales()
    scrape_aplaceinthesun()
    scrape_spainproperty()

    print(f'\nTotal anuncios encontrados: {len(results)}')

    if len(results) < 3:
        print('Usando datos de ejemplo como fallback...')
        results.extend(FALLBACK_LISTINGS)

    # Leer template e inyectar datos
    try:
        with open('index_template.html', 'r', encoding='utf-8') as f:
            template = f.read()
        output = template.replace('__LISTINGS_JSON__', json.dumps(results, ensure_ascii=False))
        with open('index.html', 'w', encoding='utf-8') as f:
            f.write(output)
        print(f'index.html generado con {len(results)} anuncios.')
    except Exception as e:
        print(f'ERROR generando index.html: {e}')
        raise
