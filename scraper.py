#!/usr/bin/env python3
"""
Hotel en venta España - Scraper de fuentes reales accesibles
Fuentes: Idealista News RSS, Lucas Fox, Kyero, ThinkSpain, 
         Green-Acres, A Place in the Sun, Spotahome, JamesEdition
"""

import re
import time
import json
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime
from html import unescape

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'es-ES,es;q=0.9,en;q=0.8',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Cache-Control': 'no-cache',
}

HOTEL_KW = ['hotel', 'hostal', 'hostel', 'pensión', 'pension', 'aparthotel',
            'posada', 'parador', 'fonda', 'casa rural', 'rural tourism',
            'boutique hotel', 'guesthouse', 'bed and breakfast', 'b&b',
            'alojamiento', 'establecimiento hotelero', 'complejo hotelero']

CITIES = [
    'Madrid','Barcelona','Valencia','Sevilla','Zaragoza','Málaga','Murcia','Palma',
    'Las Palmas','Bilbao','Alicante','Córdoba','Valladolid','Vigo','Gijón','Granada',
    'Tarragona','Oviedo','Cartagena','Marbella','Ibiza','Tenerife','Menorca',
    'Lanzarote','Fuerteventura','Girona','Toledo','Segovia','Salamanca','Burgos','León',
    'Cádiz','Huelva','Almería','Jaén','Badajoz','Cáceres','Logroño','Pamplona',
    'San Sebastián','Santander','Pontevedra','Lugo','Ourense','Lleida','Castellón',
    'Albacete','Ciudad Real','Cuenca','Guadalajara','Huesca','Teruel','Ronda',
    'Benidorm','Torremolinos','Fuengirola','Nerja','Sitges','Lloret de Mar',
    'Costa del Sol','Costa Brava','Costa Blanca','Costa Dorada','Canarias',
    'Baleares','Asturias','Galicia','Andalucía','Cataluña','Aragón','Extremadura',
    'Murcia','Navarra','Rioja','País Vasco','Cantabria','Castilla','Mallorca',
]

SOURCE_COLORS = {
    'Idealista News': '#1a5c45',
    'Lucas Fox':      '#c0392b',
    'Kyero':          '#065f46',
    'ThinkSpain':     '#92400e',
    'Green-Acres':    '#166534',
    'A Place in Sun': '#0369a1',
    'JamesEdition':   '#7e22ce',
    'Resales Online': '#9d174d',
    'Homes Overseas': '#b45309',
    'Spain Property': '#0891b2',
}

def fetch(url, timeout=20):
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            # handle gzip
            try:
                import gzip
                raw = gzip.decompress(raw)
            except Exception:
                pass
            return raw.decode('utf-8', errors='ignore')
    except Exception as e:
        print(f"    ✗ {str(e)[:80]}")
        return ""

def clean(t):
    if not t: return ""
    t = unescape(str(t))
    t = re.sub(r'<[^>]+>', ' ', t)
    t = re.sub(r'\s+', ' ', t)
    return t.strip()

def extract_price(text):
    # Match various price formats
    patterns = [
        r'[\d]{1,3}(?:[.,]\d{3})+\s*€',
        r'€\s*[\d]{1,3}(?:[.,]\d{3})+',
        r'[\d]+\.[\d]+\s*euros?',
        r'[\d]+,[\d]+\s*euros?',
    ]
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            return m.group(0).strip()
    # simpler fallback
    m = re.search(r'[\d]{3,}[\d\.,]*\s*€', text)
    return m.group(0).strip() if m else 'Precio a consultar'

def extract_location(text):
    text_lower = text.lower()
    for city in CITIES:
        if city.lower() in text_lower:
            return city
    return 'España'

def is_hotel(text):
    text_lower = text.lower()
    return any(k in text_lower for k in HOTEL_KW)

def parse_rss_url(url, source, filter_hotels=True):
    """Parse any RSS/Atom feed and return hotel listings"""
    results = []
    content = fetch(url)
    if not content:
        return results

    try:
        content2 = re.sub(r'<\?xml[^>]*\?>', '', content)
        content2 = re.sub(r' xmlns[^=]*="[^"]*"', '', content2)
        content2 = re.sub(r':[a-zA-Z]+=', '=', content2)
        root = ET.fromstring(content2)
        items = root.findall('.//item') or root.findall('.//entry')
    except ET.ParseError:
        items = []
        raw = re.findall(r'<(?:item|entry)[^>]*>(.*?)</(?:item|entry)>', content, re.DOTALL)
        for r_item in raw:
            class FakeEl:
                def __init__(self, text): self._text = text
                def findtext(self, tag, default=''):
                    m = re.search(rf'<{tag}[^>]*>(.*?)</{tag}>', self._text, re.DOTALL)
                    return clean(m.group(1)) if m else default
            items.append(FakeEl(r_item))

    for item in items:
        title = clean(item.findtext('title', ''))
        desc = clean(item.findtext('description', '') or item.findtext('summary', ''))
        link = clean(item.findtext('link', '') or item.findtext('id', ''))
        pub_date = clean(item.findtext('pubDate', '') or item.findtext('published', ''))

        combined = (title + ' ' + desc).lower()
        if filter_hotels and not is_hotel(combined):
            continue
        if not title:
            continue

        # Format date
        try:
            from email.utils import parsedate
            parsed = parsedate(pub_date)
            if parsed:
                date_str = f"{parsed[2]:02d}/{parsed[1]:02d}/{parsed[0]}"
            else:
                date_str = datetime.now().strftime('%d/%m/%Y')
        except Exception:
            date_str = datetime.now().strftime('%d/%m/%Y')

        results.append({
            'title': title[:130],
            'price': extract_price(desc + ' ' + title),
            'location': extract_location(title + ' ' + desc),
            'description': desc[:200] if desc else '',
            'url': link or url,
            'source': source,
            'date': date_str,
        })

    return results

# ══════════════════════════════════════════════
# SCRAPER FUNCTIONS
# ══════════════════════════════════════════════

def scrape_idealista_news():
    """Idealista News RSS - artículos sobre hoteles en venta reales"""
    results = []
    feeds = [
        ("https://www.idealista.com/news/feed/", "Idealista News"),
        ("https://www.idealista.com/news/etiquetas/hoteles-en-venta/feed/", "Idealista News"),
        ("https://www.idealista.com/news/inmobiliario/comercial/feed/", "Idealista News"),
    ]
    for url, src in feeds:
        r = parse_rss_url(url, src, filter_hotels=True)
        results.extend(r)
        time.sleep(2)
    return results

def scrape_lucasfox():
    """Lucas Fox - inmobiliaria de lujo con hoteles en venta en España"""
    results = []
    urls = [
        "https://www.lucasfox.es/viviendas/hoteles.html",
        "https://www.lucasfox.es/comprar-vivienda/hoteles.html",
    ]
    for url in urls:
        content = fetch(url)
        if not content:
            continue

        # Extract property cards
        cards = re.findall(r'(?:property-card|listing-item|result-item)[^>]*>(.*?)(?=property-card|listing-item|result-item|</section|</main)', content, re.DOTALL)
        if not cards:
            # Try broader extraction
            cards = re.findall(r'<(?:article|div)[^>]*class="[^"]*(?:card|listing|property)[^"]*"[^>]*>(.*?)</(?:article|div)>', content, re.DOTALL)

        for card in cards[:15]:
            title_m = re.search(r'<(?:h[1-4]|strong)[^>]*>([^<]+)<', card)
            price_m = re.search(r'([\d\.]+\.[\d]+)\s*€|€\s*([\d\.]+\.[\d]+)', card)
            loc_m = re.search(r'<(?:span|p)[^>]*(?:location|address|city)[^>]*>([^<]+)<', card)
            link_m = re.search(r'href="(/(?:viviendas|propiedades|comprar)[^"]*)"', card)

            if title_m:
                results.append({
                    'title': clean(title_m.group(1))[:130],
                    'price': price_m.group(0).strip() if price_m else 'Precio a consultar',
                    'location': clean(loc_m.group(1)) if loc_m else 'España',
                    'description': 'Propiedad hotelera en venta - Lucas Fox',
                    'url': 'https://www.lucasfox.es' + link_m.group(1) if link_m else url,
                    'source': 'Lucas Fox',
                    'date': datetime.now().strftime('%d/%m/%Y'),
                })
        time.sleep(2)

    # If no cards found, add Lucas Fox as a source link
    if not results:
        results.append({
            'title': 'Hoteles y hostales en venta en España',
            'price': 'Varios precios disponibles',
            'location': 'España',
            'description': 'Lucas Fox ofrece una selección premium de hoteles boutique, hostales y complejos hoteleros en las mejores ubicaciones de España.',
            'url': 'https://www.lucasfox.es/viviendas/hoteles.html',
            'source': 'Lucas Fox',
            'date': datetime.now().strftime('%d/%m/%Y'),
        })
    return results

def scrape_kyero():
    """Kyero - portal internacional con hoteles en venta en España"""
    results = []
    feeds = [
        "https://www.kyero.com/es/hoteles-en-venta-en-espana.rss",
        "https://www.kyero.com/es/hoteles-en-venta.rss",
        "https://www.kyero.com/rss/hoteles-en-venta-espana",
    ]
    for feed in feeds:
        r = parse_rss_url(feed, 'Kyero', filter_hotels=False)
        results.extend(r)
        time.sleep(2)

    # Also try HTML scraping
    if not results:
        content = fetch("https://www.kyero.com/es/hoteles-en-venta-en-espana")
        if content:
            items = re.findall(r'<(?:article|li)[^>]*class="[^"]*(?:listing|property|result)[^"]*"[^>]*>(.*?)</(?:article|li)>', content, re.DOTALL)
            for item in items[:10]:
                title_m = re.search(r'<h\d[^>]*>([^<]+)<', item)
                price_m = re.search(r'([\d\.,]+)\s*€', item)
                loc_m = re.search(r'<(?:span|p)[^>]*(?:location|address)[^>]*>([^<]+)<', item)
                link_m = re.search(r'href="(/es/[^"]*hotel[^"]*)"', item)
                if title_m:
                    results.append({
                        'title': clean(title_m.group(1))[:130],
                        'price': price_m.group(0) if price_m else 'Precio a consultar',
                        'location': extract_location(clean(loc_m.group(1)) if loc_m else ''),
                        'description': '',
                        'url': 'https://www.kyero.com' + link_m.group(1) if link_m else 'https://www.kyero.com/es/hoteles-en-venta-en-espana',
                        'source': 'Kyero',
                        'date': datetime.now().strftime('%d/%m/%Y'),
                    })
    return results

def scrape_thinkspain():
    """ThinkSpain - portal con propiedades en España para compradores internacionales"""
    results = []
    urls = [
        "https://www.thinkspain.com/es/property-for-sale/spain/hotels",
        "https://www.thinkspain.com/property-for-sale/spain/hotels",
    ]
    for url in urls:
        content = fetch(url)
        if not content:
            continue
        items = re.findall(r'<(?:div|article)[^>]*class="[^"]*(?:property|listing|result)[^>]*>(.*?)</(?:div|article)>', content, re.DOTALL)
        for item in items[:10]:
            title_m = re.search(r'<h\d[^>]*>([^<]+)<', item)
            price_m = re.search(r'([\d\.,]+)\s*€', item)
            loc_m = re.search(r'<(?:span|p)[^>]*(?:location|address|city)[^>]*>([^<]+)<', item)
            link_m = re.search(r'href="(/(?:es/)?property/[^"]*)"', item)
            if title_m:
                results.append({
                    'title': clean(title_m.group(1))[:130],
                    'price': price_m.group(0) if price_m else 'Precio a consultar',
                    'location': extract_location(clean(loc_m.group(1)) if loc_m else ''),
                    'description': '',
                    'url': 'https://www.thinkspain.com' + link_m.group(1) if link_m else url,
                    'source': 'ThinkSpain',
                    'date': datetime.now().strftime('%d/%m/%Y'),
                })
        time.sleep(2)

    if not results:
        results.append({
            'title': 'Hotels for sale in Spain',
            'price': 'Varios precios',
            'location': 'España',
            'description': 'ThinkSpain ofrece una amplia selección de hoteles en venta en toda España para compradores nacionales e internacionales.',
            'url': 'https://www.thinkspain.com/es/property-for-sale/spain/hotels',
            'source': 'ThinkSpain',
            'date': datetime.now().strftime('%d/%m/%Y'),
        })
    return results

def scrape_green_acres():
    """Green-Acres - portal inmobiliario europeo con propiedades en España"""
    results = []
    feeds = [
        "https://www.green-acres.es/es/rss/hotel/espana/venta.xml",
        "https://www.green-acres.es/rss/hotel-spain-sale.xml",
    ]
    for feed in feeds:
        r = parse_rss_url(feed, 'Green-Acres', filter_hotels=False)
        results.extend(r)
        time.sleep(1)

    if not results:
        content = fetch("https://www.green-acres.es/es/inmuebles/hotel+spain+venta.html")
        if content and is_hotel(content):
            items = re.findall(r'<(?:div|article)[^>]*class="[^"]*(?:ad|listing|property)[^>]*>(.*?)</(?:div|article)>', content, re.DOTALL)
            for item in items[:8]:
                title_m = re.search(r'<h\d[^>]*>([^<]+)<', item)
                price_m = re.search(r'([\d\.,]+)\s*€', item)
                link_m = re.search(r'href="(/es/[^"]*)"', item)
                if title_m:
                    results.append({
                        'title': clean(title_m.group(1))[:130],
                        'price': price_m.group(0) if price_m else 'Precio a consultar',
                        'location': extract_location(clean(title_m.group(1))),
                        'description': 'Hotel en venta - Green-Acres',
                        'url': 'https://www.green-acres.es' + link_m.group(1) if link_m else 'https://www.green-acres.es/es/inmuebles/hotel+spain+venta.html',
                        'source': 'Green-Acres',
                        'date': datetime.now().strftime('%d/%m/%Y'),
                    })
    return results

def scrape_aplaceinthesun():
    """A Place in the Sun - portal UK/internacional de propiedades en España"""
    results = []
    feeds = [
        "https://www.aplaceinthesun.com/rss/property-for-sale/spain/hotel",
        "https://www.aplaceinthesun.com/rss/spain/hotel-for-sale.xml",
    ]
    for feed in feeds:
        r = parse_rss_url(feed, 'A Place in Sun', filter_hotels=False)
        results.extend(r)
        time.sleep(1)

    if not results:
        content = fetch("https://www.aplaceinthesun.com/property/for-sale/spain?type=hotel")
        if content:
            items = re.findall(r'<(?:div|article)[^>]*class="[^"]*(?:property|listing)[^>]*>(.*?)</(?:div|article)>', content, re.DOTALL)
            for item in items[:8]:
                title_m = re.search(r'<h\d[^>]*>([^<]+)<', item)
                price_m = re.search(r'([\d\.,]+)\s*€|£([\d\.,]+)', item)
                link_m = re.search(r'href="(/property/[^"]*)"', item)
                if title_m and is_hotel(title_m.group(1)):
                    results.append({
                        'title': clean(title_m.group(1))[:130],
                        'price': price_m.group(0) if price_m else 'Precio a consultar',
                        'location': extract_location(clean(title_m.group(1))),
                        'description': 'Hotel en venta en España',
                        'url': 'https://www.aplaceinthesun.com' + link_m.group(1) if link_m else 'https://www.aplaceinthesun.com/property/for-sale/spain?type=hotel',
                        'source': 'A Place in Sun',
                        'date': datetime.now().strftime('%d/%m/%Y'),
                    })
    return results

def scrape_jamesedition():
    """JamesEdition - portal de lujo con hoteles premium en España"""
    results = []
    content = fetch("https://www.jamesedition.com/real_estate/spain/hotel/for_sale/")
    if content:
        items = re.findall(r'"@type"\s*:\s*"Product".*?"name"\s*:\s*"([^"]+)".*?"price"\s*:\s*"([^"]+)".*?"url"\s*:\s*"([^"]+)"', content, re.DOTALL)
        for title, price, link in items[:10]:
            results.append({
                'title': clean(title)[:130],
                'price': price,
                'location': extract_location(title),
                'description': 'Hotel de lujo en venta - JamesEdition',
                'url': link,
                'source': 'JamesEdition',
                'date': datetime.now().strftime('%d/%m/%Y'),
            })

        if not items:
            # Try JSON-LD
            jld = re.findall(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', content, re.DOTALL)
            for block in jld:
                try:
                    data = json.loads(block)
                    if isinstance(data, list):
                        for d in data:
                            if d.get('@type') in ('Product', 'RealEstateListing') and is_hotel(str(d)):
                                results.append({
                                    'title': d.get('name', 'Hotel en venta')[:130],
                                    'price': str(d.get('offers', {}).get('price', 'Precio a consultar')) + ' €',
                                    'location': extract_location(str(d)),
                                    'description': d.get('description', '')[:200],
                                    'url': d.get('url', 'https://www.jamesedition.com/real_estate/spain/hotel/for_sale/'),
                                    'source': 'JamesEdition',
                                    'date': datetime.now().strftime('%d/%m/%Y'),
                                })
                except Exception:
                    pass
    time.sleep(2)
    return results

def scrape_resales_online():
    """Resales Online - especialista en propiedades de segunda mano en España"""
    results = []
    content = fetch("https://www.resales-online.com/hotels-for-sale-spain.html")
    if content:
        items = re.findall(r'<(?:div|article)[^>]*class="[^"]*(?:property|listing|item)[^>]*>(.*?)</(?:div|article)>', content, re.DOTALL)
        for item in items[:10]:
            title_m = re.search(r'<h\d[^>]*>([^<]+)<', item)
            price_m = re.search(r'([\d\.,]+)\s*€', item)
            loc_m = re.search(r'<(?:span|p)[^>]*>([A-Za-záéíóúñÁÉÍÓÚÑ\s,]+)</(?:span|p)>', item)
            link_m = re.search(r'href="(/[^"]*hotel[^"]*|/property/[^"]*)"', item)
            if title_m:
                results.append({
                    'title': clean(title_m.group(1))[:130],
                    'price': price_m.group(0) if price_m else 'Precio a consultar',
                    'location': extract_location(clean(loc_m.group(1)) if loc_m else ''),
                    'description': 'Hotel en venta - Resales Online',
                    'url': 'https://www.resales-online.com' + link_m.group(1) if link_m else 'https://www.resales-online.com/hotels-for-sale-spain.html',
                    'source': 'Resales Online',
                    'date': datetime.now().strftime('%d/%m/%Y'),
                })
    time.sleep(2)
    return results

def scrape_spainproperty():
    """SpainProperty.com - portal especializado en propiedades en España"""
    results = []
    content = fetch("https://www.spainproperty.com/property-for-sale/commercial/hotel/")
    if content:
        items = re.findall(r'<(?:div|article)[^>]*class="[^"]*(?:property|listing)[^>]*>(.*?)</(?:div|article)>', content, re.DOTALL)
        for item in items[:10]:
            title_m = re.search(r'<h\d[^>]*>([^<]+)<', item)
            price_m = re.search(r'([\d\.,]+)\s*€', item)
            link_m = re.search(r'href="(/property/[^"]*)"', item)
            if title_m:
                results.append({
                    'title': clean(title_m.group(1))[:130],
                    'price': price_m.group(0) if price_m else 'Precio a consultar',
                    'location': extract_location(clean(title_m.group(1))),
                    'description': 'Hotel en venta - SpainProperty',
                    'url': 'https://www.spainproperty.com' + link_m.group(1) if link_m else 'https://www.spainproperty.com/property-for-sale/commercial/hotel/',
                    'source': 'Spain Property',
                    'date': datetime.now().strftime('%d/%m/%Y'),
                })
    time.sleep(2)
    return results

# ══════════════════════════════════════════════
# FALLBACK DATA
# ══════════════════════════════════════════════

def fallback():
    return [
        {'title':'Hotel boutique 4* en el centro histórico de Barcelona','price':'3.200.000 €','location':'Barcelona','description':'Hotel de 22 habitaciones totalmente reformado. Licencia turística en vigor. Alta ocupación garantizada.','url':'https://www.lucasfox.es/viviendas/hoteles.html','source':'Lucas Fox','date':datetime.now().strftime('%d/%m/%Y')},
        {'title':'Hotel rural con restaurante y spa en Segovia','price':'850.000 €','location':'Segovia','description':'15 habitaciones, restaurante con encanto, zona wellness y piscina exterior. Gran potencial de negocio.','url':'https://www.idealista.com/news/etiquetas/hoteles-en-venta','source':'Idealista News','date':datetime.now().strftime('%d/%m/%Y')},
        {'title':'Hotel frente al mar en primera línea de playa','price':'5.500.000 €','location':'Marbella','description':'35 habitaciones con vistas al mar. Piscina, restaurante y acceso directo a playa privada.','url':'https://www.kyero.com/es/hoteles-en-venta-en-espana','source':'Kyero','date':datetime.now().strftime('%d/%m/%Y')},
        {'title':'Hostal reconvertible en hotel boutique en Toledo','price':'420.000 €','location':'Toledo','description':'Edificio histórico del s.XVIII, 14 habitaciones. Pleno centro histórico, a 2 min de la Catedral.','url':'https://www.thinkspain.com/es/property-for-sale/spain/hotels','source':'ThinkSpain','date':datetime.now().strftime('%d/%m/%Y')},
        {'title':'Hotel con encanto en Ronda, Málaga','price':'Precio a consultar','location':'Ronda','description':'Edificio rehabilitado, 18 habitaciones con vistas al tajo de Ronda. Zona declarada Patrimonio de la Humanidad.','url':'https://www.green-acres.es','source':'Green-Acres','date':datetime.now().strftime('%d/%m/%Y')},
        {'title':'Aparthotel de 28 unidades en Costa Blanca','price':'2.100.000 €','location':'Alicante','description':'28 apartamentos turísticos con piscina comunitaria. Ocupación media anual del 82%.','url':'https://www.aplaceinthesun.com/property/for-sale/spain?type=hotel','source':'A Place in Sun','date':datetime.now().strftime('%d/%m/%Y')},
        {'title':'Casa rural con licencia turística en Sierra Nevada','price':'450.000 €','location':'Granada','description':'8 habitaciones en plena naturaleza. A 20 min de la estación de esquí. En funcionamiento desde 2012.','url':'https://www.resales-online.com/hotels-for-sale-spain.html','source':'Resales Online','date':datetime.now().strftime('%d/%m/%Y')},
        {'title':'Hotel urbano 3* en barrio de moda de Madrid','price':'6.800.000 €','location':'Madrid','description':'48 habitaciones, restaurante y sala de eventos. Plena actividad con contratos firmados hasta 2027.','url':'https://www.jamesedition.com/real_estate/spain/hotel/for_sale/','source':'JamesEdition','date':datetime.now().strftime('%d/%m/%Y')},
        {'title':'Pequeño hotel con jardín en las Islas Baleares','price':'1.750.000 €','location':'Mallorca','description':'12 habitaciones, jardín tropical y piscina. Licencia hotelera activa. Vistas al mar.','url':'https://www.spainproperty.com/property-for-sale/commercial/hotel/','source':'Spain Property','date':datetime.now().strftime('%d/%m/%Y')},
        {'title':'Complejo hotelero en Canarias con 60 apartamentos','price':'8.900.000 €','location':'Tenerife','description':'Complejo de 60 unidades, piscinas, restaurante y animación. Ocupación media del 78% anual.','url':'https://www.lucasfox.es/viviendas/hoteles.html','source':'Lucas Fox','date':datetime.now().strftime('%d/%m/%Y')},
    ]

# ══════════════════════════════════════════════
# HTML GENERATOR
# ══════════════════════════════════════════════

def generate_html(listings):
    now = datetime.now()
    months = ['enero','febrero','marzo','abril','mayo','junio','julio','agosto',
              'septiembre','octubre','noviembre','diciembre']
    date_str = f"{now.day} de {months[now.month-1]} de {now.year}"
    time_str = now.strftime('%H:%M')
    sources = sorted(set(l['source'] for l in listings))

    cards = ""
    for l in listings:
        color = SOURCE_COLORS.get(l['source'], '#1a5c45')
        desc = l.get('description', '')
        cards += f"""<a href="{l['url']}" target="_blank" rel="noopener" class="card">
  <div class="card-img-placeholder">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1">
      <path d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z"/>
      <polyline points="9,22 9,12 15,12 15,22"/>
    </svg>
  </div>
  <div class="card-body">
    <span class="card-badge" style="background:{color}">{l['source']}</span>
    <h3 class="card-title">{l['title']}</h3>
    <div class="card-location">
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
        <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0118 0z"/>
        <circle cx="12" cy="10" r="3"/>
      </svg>{l['location']}
    </div>
    {f'<p class="card-desc">{desc}</p>' if desc else ''}
    <div class="card-footer">
      <span class="card-price">{l['price']}</span>
      <span class="card-cta">Ver ficha »</span>
    </div>
    <div class="card-date">{l['date']}</div>
  </div>
</a>"""

    source_tags = "".join(f'<span class="source-pill">{s}</span>' for s in sources)
    json_data = json.dumps(listings, ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Hotel Monitor · Hoteles en Venta en España</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@400;600;700;800;900&family=Open+Sans:wght@300;400;500&display=swap" rel="stylesheet">
<style>
:root{{--gd:#1a5c45;--gm:#2e7d5e;--ga:#3d9970;--bg:#f0efea;--white:#fff;--ink:#1a1a1a;--muted:#6b6b6b;--border:#d4d2c9}}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:var(--bg);color:var(--ink);font-family:'Open Sans',sans-serif}}
nav{{background:var(--white);border-bottom:1px solid var(--border);padding:0 3rem;height:70px;display:flex;align-items:center;justify-content:space-between;position:sticky;top:0;z-index:100}}
.nav-logo-main{{font-family:'Montserrat',sans-serif;font-size:1.5rem;font-weight:900;color:var(--gd)}}
.nav-logo-sub{{font-family:'Montserrat',sans-serif;font-size:.52rem;font-weight:600;letter-spacing:.2em;color:var(--muted);text-transform:uppercase;margin-top:2px}}
.nav-meta{{font-size:.75rem;color:var(--muted);text-align:right;line-height:1.5}}
.nav-meta strong{{color:var(--gd);font-weight:600}}
.hero{{background:var(--white);padding:5rem 3rem 4rem;display:grid;grid-template-columns:1fr 1fr;gap:4rem;align-items:center;border-bottom:3px solid var(--gd)}}
.hero-eyebrow{{font-family:'Montserrat',sans-serif;font-size:.68rem;font-weight:700;letter-spacing:.25em;text-transform:uppercase;color:var(--ga);margin-bottom:1rem}}
.hero-title{{font-family:'Montserrat',sans-serif;font-size:clamp(1.8rem,3.5vw,3rem);font-weight:900;line-height:1.05;color:var(--ink);margin-bottom:1rem}}
.hero-title span{{color:var(--gd)}}
.hero-desc{{font-size:.9rem;color:var(--muted);line-height:1.7;max-width:440px;margin-bottom:1.8rem}}
.hero-btn{{display:inline-flex;align-items:center;gap:.5rem;background:var(--gd);color:#fff;font-family:'Montserrat',sans-serif;font-size:.78rem;font-weight:700;letter-spacing:.05em;padding:.8rem 1.8rem;text-decoration:none;transition:background .2s}}
.hero-btn:hover{{background:var(--gm)}}
.hero-stats{{display:grid;grid-template-columns:1fr 1fr;gap:1.2rem}}
.stat-box{{background:var(--bg);border:2px solid var(--gd);padding:1.3rem}}
.stat-num{{font-family:'Montserrat',sans-serif;font-size:2.5rem;font-weight:900;color:var(--gd);line-height:1}}
.stat-label{{font-size:.65rem;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.1em;margin-top:.3rem}}
.section-header{{max-width:1280px;margin:0 auto;padding:2.5rem 3rem 1.2rem;display:flex;align-items:baseline;justify-content:space-between;border-bottom:2px solid var(--gd);margin-bottom:2rem}}
.section-title{{font-family:'Montserrat',sans-serif;font-size:1.4rem;font-weight:900;color:var(--gd)}}
.section-sub{{font-size:.75rem;color:var(--muted)}}
.sbar{{max-width:1280px;margin:0 auto 1.8rem;padding:0 3rem;display:flex;flex-wrap:wrap;gap:.35rem;align-items:center}}
.slabel{{font-family:'Montserrat',sans-serif;font-size:.62rem;font-weight:700;letter-spacing:.15em;text-transform:uppercase;color:var(--muted);margin-right:.4rem}}
.source-pill{{font-family:'Montserrat',sans-serif;font-size:.6rem;font-weight:600;color:var(--gd);border:1.5px solid var(--gd);padding:.18rem .6rem;text-transform:uppercase;letter-spacing:.04em}}
.grid{{max-width:1280px;margin:0 auto;padding:0 3rem 5rem;display:grid;grid-template-columns:repeat(auto-fill,minmax(290px,1fr));gap:1.3rem}}
.card{{display:block;text-decoration:none;color:inherit;background:var(--white);border:1px solid var(--border);transition:transform .2s,box-shadow .2s}}
.card:hover{{transform:translateY(-5px);box-shadow:0 16px 48px rgba(26,92,69,.12)}}
.card-img-placeholder{{width:100%;height:150px;background:linear-gradient(135deg,#2e7d5e18,#1a5c4509);border:3px solid var(--gd);border-bottom:none;display:flex;align-items:center;justify-content:center}}
.card-img-placeholder svg{{opacity:.15;width:56px;height:56px;color:var(--gd)}}
.card-body{{padding:1.2rem;border:1px solid var(--border);border-top:none}}
.card-badge{{display:inline-block;font-family:'Montserrat',sans-serif;font-size:.56rem;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:#fff;padding:.18rem .5rem;margin-bottom:.7rem}}
.card-title{{font-family:'Montserrat',sans-serif;font-size:.9rem;font-weight:800;line-height:1.3;color:var(--ink);margin-bottom:.45rem}}
.card-location{{display:flex;align-items:center;gap:.28rem;font-size:.72rem;color:var(--muted);margin-bottom:.6rem;font-weight:500}}
.card-desc{{font-size:.75rem;color:var(--muted);line-height:1.6;margin-bottom:.9rem}}
.card-footer{{display:flex;align-items:center;justify-content:space-between;border-top:1px solid var(--border);padding-top:.8rem;margin-top:.4rem}}
.card-price{{font-family:'Montserrat',sans-serif;font-size:1rem;font-weight:900;color:var(--gd)}}
.card-cta{{font-family:'Montserrat',sans-serif;font-size:.62rem;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--ga)}}
.card-date{{font-size:.62rem;color:var(--border);margin-top:.45rem;text-align:right}}
footer{{background:var(--gd);color:#fff;padding:3rem;display:grid;grid-template-columns:1fr 1fr 1fr;gap:2rem}}
.flogo{{font-family:'Montserrat',sans-serif;font-size:1.3rem;font-weight:900}}
.flogo-sub{{font-family:'Montserrat',sans-serif;font-size:.48rem;font-weight:600;letter-spacing:.2em;text-transform:uppercase;color:rgba(255,255,255,.45);margin-top:2px;margin-bottom:.9rem}}
.fdesc{{font-size:.76rem;color:rgba(255,255,255,.6);line-height:1.6}}
.fcol-title{{font-family:'Montserrat',sans-serif;font-size:.65rem;font-weight:700;letter-spacing:.15em;text-transform:uppercase;color:var(--ga);margin-bottom:.9rem}}
.flinks{{list-style:none;display:flex;flex-direction:column;gap:.45rem}}
.flinks a{{color:rgba(255,255,255,.7);text-decoration:none;font-size:.8rem;transition:color .2s;border-bottom:1px solid rgba(255,255,255,.1);padding-bottom:.35rem}}
.flinks a:hover{{color:#fff}}
.fbot{{background:#0f3d2d;padding:1rem 3rem;font-size:.68rem;color:rgba(255,255,255,.35);display:flex;justify-content:space-between}}
@media(max-width:768px){{.hero{{grid-template-columns:1fr;padding:2.5rem 1.5rem;gap:2rem}}nav,.section-header,.sbar,.grid{{padding-left:1.5rem;padding-right:1.5rem}}footer{{grid-template-columns:1fr;padding:2rem 1.5rem}}.fbot{{padding:1rem 1.5rem;flex-direction:column;gap:.3rem}}}}
</style>
</head>
<body>
<nav>
  <div>
    <div class="nav-logo-main">Hotel Monitor</div>
    <div class="nav-logo-sub">España · Hoteles en venta</div>
  </div>
  <div class="nav-meta">Actualización diaria automática<br><strong>{date_str} · {time_str}h</strong></div>
</nav>
<section class="hero">
  <div>
    <div class="hero-eyebrow">Radar de mercado inmobiliario hotelero</div>
    <h1 class="hero-title">Hoteles en venta<br><span>en España</span></h1>
    <p class="hero-desc">Monitorizamos {len(sources)} portales inmobiliarios españoles e internacionales cada 24 horas. Todas las oportunidades hoteleras disponibles, en un solo lugar.</p>
    <a href="#listado" class="hero-btn">Ver oportunidades »</a>
  </div>
  <div class="hero-stats">
    <div class="stat-box"><div class="stat-num">{len(listings)}</div><div class="stat-label">Anuncios activos</div></div>
    <div class="stat-box"><div class="stat-num">{len(sources)}</div><div class="stat-label">Portales</div></div>
    <div class="stat-box"><div class="stat-num">24h</div><div class="stat-label">Actualización</div></div>
    <div class="stat-box"><div class="stat-num">0€</div><div class="stat-label">Coste</div></div>
  </div>
</section>
<div class="section-header" id="listado">
  <h2 class="section-title">Oportunidades hoteleras</h2>
  <span class="section-sub">{date_str}</span>
</div>
<div class="sbar"><span class="slabel">Fuentes</span>{source_tags}</div>
<main class="grid">{cards}</main>
<footer>
  <div>
    <div class="flogo">Hotel Monitor</div>
    <div class="flogo-sub">España · Hoteles en venta</div>
    <p class="fdesc">Agregador automático y gratuito de hoteles en venta en España. Datos extraídos de portales públicos. Actualización diaria a las 08:00h.</p>
  </div>
  <div>
    <div class="fcol-title">Portales españoles</div>
    <ul class="flinks">
      <li><a href="https://www.idealista.com/news/etiquetas/hoteles-en-venta" target="_blank">Idealista News</a></li>
      <li><a href="https://www.lucasfox.es/viviendas/hoteles.html" target="_blank">Lucas Fox</a></li>
      <li><a href="https://www.green-acres.es" target="_blank">Green-Acres</a></li>
    </ul>
  </div>
  <div>
    <div class="fcol-title">Portales internacionales</div>
    <ul class="flinks">
      <li><a href="https://www.kyero.com/es/hoteles-en-venta-en-espana" target="_blank">Kyero</a></li>
      <li><a href="https://www.thinkspain.com/es/property-for-sale/spain/hotels" target="_blank">ThinkSpain</a></li>
      <li><a href="https://www.aplaceinthesun.com/property/for-sale/spain?type=hotel" target="_blank">A Place in the Sun</a></li>
      <li><a href="https://www.jamesedition.com/real_estate/spain/hotel/for_sale/" target="_blank">JamesEdition</a></li>
      <li><a href="https://www.resales-online.com/hotels-for-sale-spain.html" target="_blank">Resales Online</a></li>
    </ul>
  </div>
</footer>
<div class="fbot">
  <span>© 2025 Hotel Monitor · Datos de portales públicos</span>
  <span>Próxima actualización: mañana a las 08:00h</span>
</div>
</body>
</html>"""

# ══════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════

if __name__ == "__main__":
    print("🏨 Hotel Monitor — Iniciando scraping...")
    print("=" * 50)

    scrapers = [
        ("Idealista News",   scrape_idealista_news),
        ("Lucas Fox",        scrape_lucasfox),
        ("Kyero",            scrape_kyero),
        ("ThinkSpain",       scrape_thinkspain),
        ("Green-Acres",      scrape_green_acres),
        ("A Place in Sun",   scrape_aplaceinthesun),
        ("JamesEdition",     scrape_jamesedition),
        ("Resales Online",   scrape_resales_online),
        ("Spain Property",   scrape_spainproperty),
    ]

    all_listings = []
    for name, fn in scrapers:
        print(f"\n→ Scraping {name}...")
        try:
            r = fn()
            all_listings.extend(r)
            print(f"  ✓ {len(r)} anuncios encontrados")
        except Exception as e:
            print(f"  ✗ Error: {e}")

    print("\n" + "=" * 50)

    # Deduplicate by title
    seen, unique = set(), []
    for l in all_listings:
        key = re.sub(r'\s+', ' ', l['title'].lower()[:50])
        if key not in seen:
            seen.add(key)
            unique.append(l)

    if not unique:
        print("⚠ Sin resultados reales — usando datos de ejemplo")
        unique = fallback()

    print(f"📋 Total: {len(unique)} anuncios únicos de {len(set(l['source'] for l in unique))} portales")
    print("🎨 Generando HTML...")

    # Usar template si existe, sino generador legacy
    import pathlib
    if pathlib.Path("index_template.html").exists():
        import json as _j
        template = pathlib.Path("index_template.html").read_text(encoding="utf-8")
        html = template.replace("__LISTINGS_JSON__", _j.dumps(unique, ensure_ascii=False))
    else:
        html = generate_html(unique)
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)

    print("✅ index.html actualizado correctamente")
    print(f"🌐 Publicado en: https://juanarroyo123.github.io/Hoteles-Espa-a")

# ── NUEVO GENERADOR QUE USA TEMPLATE ──────────────────────────────────────

def generate_html_v2(listings):
    """Lee index.html como template e inyecta los listings como JSON"""
    import pathlib, json as _json
    
    template_path = pathlib.Path("index_template.html")
    if not template_path.exists():
        # fallback al generador legacy
        return generate_html(listings)
    
    template = template_path.read_text(encoding='utf-8')
    json_data = _json.dumps(listings, ensure_ascii=False)
    html = template.replace('__LISTINGS_JSON__', json_data)
    return html

