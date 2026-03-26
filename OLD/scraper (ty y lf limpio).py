#!/usr/bin/env python3
"""
Scraper de hoteles en venta en España.
Portales activos: Lucas Fox, ThinkSpain.
"""

import re, time, json, urllib.request
from html import unescape
from datetime import date

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
# 1. LUCAS FOX
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

        links = re.findall(r'href="(/es/propiedades/[a-z0-9\-]+/[a-z0-9\-]+)"', html)
        for link in links[:30]:
            if link in seen_urls: continue
            detail = fetch('https://www.lucasfox.es' + link)
            if not detail or not is_hotel(detail[:2000]): continue
            title_m = re.search(r'<h1[^>]*>([^<]{10,100})</h1>', detail)
            price_m = re.search(r'([\d\.]+(?:\.\d{3})*\s*€)', detail)
            loc_m   = re.search(r'(?:ubicacion|location|ciudad)[^>]*>([^<]{3,50})<', detail, re.IGNORECASE)
            desc_m  = re.search(r'<(?:p|div)[^>]*class="[^"]*desc[^"]*"[^>]*>([^<]{20,300})', detail, re.IGNORECASE)
            if title_m:
                add({'title': clean(title_m.group(1)), 'price': clean(price_m.group(1)) if price_m else 'Precio a consultar', 'location': clean(loc_m.group(1)) if loc_m else 'España', 'description': clean(desc_m.group(1)) if desc_m else '', 'url': 'https://www.lucasfox.es' + link, 'source': 'Lucas Fox', 'date': TODAY})
            time.sleep(0.5)
    print(f'  Lucas Fox: {len([r for r in results if r["source"]=="Lucas Fox"])}')

# ══════════════════════════════════════════════════════
# 2. THINKSPAIN
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
        items = re.findall(r'<(?:div|article)[^>]*class="[^"]*(?:property-item|listing-item|search-result)[^"]*"[^>]*>(.*?)</(?:div|article)>', html, re.DOTALL)
        if not items:
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

        prop_links = re.findall(r'href="(https?://www\.thinkspain\.com/property-for-sale/[^"]+)"', html)
        prop_links += ['https://www.thinkspain.com' + l for l in re.findall(r'href="(/property-for-sale/[^"]+)"', html)]
        for link in list(set(prop_links))[:20]:
            if link in seen_urls: continue
            detail = fetch(link)
            if not detail: continue
            title_m = re.search(r'<h1[^>]*>([^<]{10,120})</h1>', detail)
            price_m = re.search(r'([\d\.]+(?:\.\d{3})*\s*€)', detail)
            loc_m   = re.search(r'(?:location|ubicacion|region)["\\s][^>]*>([A-Za-záéíóúñ\s,]{4,60})<', detail, re.IGNORECASE)
            desc_m  = re.search(r'<(?:p|div)[^>]*(?:description|descripcion)[^>]*>([^<]{30,300})', detail, re.IGNORECASE)
            if title_m and is_hotel(title_m.group(1) + detail[:3000]):
                add({'title': clean(title_m.group(1)), 'price': clean(price_m.group(1)) if price_m else 'Precio a consultar', 'location': clean(loc_m.group(1)) if loc_m else 'España', 'description': clean(desc_m.group(1)) if desc_m else '', 'url': link, 'source': 'ThinkSpain', 'date': TODAY})
            time.sleep(0.5)
        time.sleep(1)
    print(f'  ThinkSpain: {len([r for r in results if r["source"]=="ThinkSpain"])}')

# ══════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════
if __name__ == '__main__':
    print(f'\n=== Scraper Hotel Monitor — {TODAY} ===\n')

    scrape_lucasfox()
    scrape_thinkspain()

    print(f'\nTotal anuncios encontrados: {len(results)}')

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
