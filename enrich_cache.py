#!/usr/bin/env python3
"""
enrich_cache.py — Enriquece el cache de hoteles con datos estructurados.

Para cada hotel sin datos (rooms, beds, m2, stars), entra en la ficha
individual y extrae:
  - rooms       → número de habitaciones
  - beds        → número de camas
  - m2          → metros cuadrados construidos
  - stars       → categoría en estrellas
  - location    → ubicación limpia (ciudad, región)

Guarda progreso cada BATCH_SIZE hoteles para no perder nada si se corta.

Uso:
    pip install requests beautifulsoup4 lxml
    python enrich_cache.py

    # Solo enriquecer ciertos portales:
    python enrich_cache.py --sources ThinkSpain LuxuryEstate

    # Modo test (solo primeros N):
    python enrich_cache.py --limit 20
"""

import json, re, time, argparse, os, sys
from html import unescape

import requests
from bs4 import BeautifulSoup

# ── Configuración ──────────────────────────────────────────────────────────────
CACHE_FILE   = 'hoteles_cache.json'
BACKUP_FILE  = 'hoteles_cache_backup.json'
BATCH_SIZE   = 50        # guardar progreso cada N hoteles procesados
DELAY        = 1.2       # segundos entre peticiones (ser respetuoso)
TIMEOUT      = 15        # timeout por petición
MAX_RETRIES  = 2

HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/122.0.0.0 Safari/537.36'
    ),
    'Accept-Language': 'es-ES,es;q=0.9,en;q=0.8',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
}

# Mapa de comunidades autónomas para normalizar ubicaciones
CCAA_MAP = {
    'madrid': 'Madrid',
    'barcelona': 'Cataluña', 'girona': 'Cataluña', 'tarragona': 'Cataluña', 'lleida': 'Cataluña',
    'sevilla': 'Andalucía', 'málaga': 'Andalucía', 'malaga': 'Andalucía',
    'granada': 'Andalucía', 'cádiz': 'Andalucía', 'cadiz': 'Andalucía',
    'huelva': 'Andalucía', 'almería': 'Andalucía', 'almeria': 'Andalucía',
    'córdoba': 'Andalucía', 'cordoba': 'Andalucía', 'jaén': 'Andalucía', 'jaen': 'Andalucía',
    'valencia': 'C. Valenciana', 'alicante': 'C. Valenciana', 'castellón': 'C. Valenciana', 'castellon': 'C. Valenciana',
    'murcia': 'Murcia',
    'zaragoza': 'Aragón', 'aragon': 'Aragón', 'huesca': 'Aragón', 'teruel': 'Aragón',
    'mallorca': 'Baleares', 'menorca': 'Baleares', 'ibiza': 'Baleares', 'baleares': 'Baleares', 'palma': 'Baleares',
    'tenerife': 'Canarias', 'las palmas': 'Canarias', 'gran canaria': 'Canarias', 'lanzarote': 'Canarias', 'fuerteventura': 'Canarias',
    'bilbao': 'País Vasco', 'san sebastián': 'País Vasco', 'vitoria': 'País Vasco',
    'pamplona': 'Navarra', 'navarra': 'Navarra',
    'santander': 'Cantabria', 'cantabria': 'Cantabria',
    'oviedo': 'Asturias', 'gijón': 'Asturias', 'asturias': 'Asturias',
    'a coruña': 'Galicia', 'coruña': 'Galicia', 'vigo': 'Galicia', 'pontevedra': 'Galicia',
    'santiago': 'Galicia', 'lugo': 'Galicia', 'ourense': 'Galicia',
    'salamanca': 'Castilla y León', 'burgos': 'Castilla y León', 'valladolid': 'Castilla y León',
    'león': 'Castilla y León', 'leon': 'Castilla y León', 'segovia': 'Castilla y León',
    'ávila': 'Castilla y León', 'avila': 'Castilla y León', 'soria': 'Castilla y León',
    'zamora': 'Castilla y León', 'palencia': 'Castilla y León',
    'toledo': 'Castilla-La Mancha', 'ciudad real': 'Castilla-La Mancha', 'albacete': 'Castilla-La Mancha',
    'cuenca': 'Castilla-La Mancha', 'guadalajara': 'Castilla-La Mancha',
    'cáceres': 'Extremadura', 'caceres': 'Extremadura', 'badajoz': 'Extremadura',
    'logroño': 'La Rioja', 'la rioja': 'La Rioja',
    'la palma': 'Canarias', 'el hierro': 'Canarias', 'la gomera': 'Canarias',
}

# ── Helpers ────────────────────────────────────────────────────────────────────
def clean(s):
    if not s: return ''
    s = re.sub(r'<[^>]+>', ' ', str(s))
    s = unescape(s)
    return re.sub(r'\s+', ' ', s).strip()

def get_html(url, retries=MAX_RETRIES):
    for attempt in range(retries + 1):
        try:
            r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            if r.status_code == 200:
                return r.text
            elif r.status_code in (403, 429, 503):
                print(f'    [{r.status_code}] bloqueado: {url[:60]}')
                time.sleep(5)
        except Exception as e:
            if attempt < retries:
                time.sleep(2)
    return None

def extract_number(s):
    """Extrae el primer número entero de un texto."""
    if not s: return None
    m = re.search(r'(\d[\d.,]*)', str(s).replace('.', '').replace(',', '.'))
    if m:
        try: return int(float(m.group(1)))
        except: pass
    return None

def infer_region(location_text):
    """Infiere la comunidad autónoma a partir del texto de ubicación."""
    t = (location_text or '').lower()
    for key, val in CCAA_MAP.items():
        if key in t:
            return val
    return None

def needs_enrichment(item):
    """True si el item le faltan datos que podríamos enriquecer."""
    return (
        not item.get('rooms') and
        not item.get('beds') and
        not item.get('m2')
    )

# ── Extractor genérico por patrones de texto ──────────────────────────────────
def extract_from_text(text):
    """
    Extrae rooms, beds, m2, stars de cualquier texto usando regex.
    Funciona como fallback para portales sin estructura clara.
    """
    result = {}
    t = text.lower()

    # Habitaciones
    patterns_rooms = [
        r'(\d+)\s*(?:habitaciones?|rooms?|chambres?|bedrooms?)',
        r'(?:habitaciones?|rooms?)[\s:]+(\d+)',
        r'(\d+)\s*habs?\b',
    ]
    for pat in patterns_rooms:
        m = re.search(pat, t)
        if m:
            v = int(m.group(1))
            if 1 <= v <= 500:
                result['rooms'] = v
                break

    # Camas
    patterns_beds = [
        r'(\d+)\s*(?:camas?|beds?|literas?)',
        r'(?:camas?|beds?)[\s:]+(\d+)',
    ]
    for pat in patterns_beds:
        m = re.search(pat, t)
        if m:
            v = int(m.group(1))
            if 1 <= v <= 1000:
                result['beds'] = v
                break

    # M²
    patterns_m2 = [
        r'(\d[\d.,]*)\s*m[²2](?:\s*(?:construidos?|útiles?|totales?|built)?)',
        r'superficie[\s:]*(\d[\d.,]*)',
        r'(\d[\d.,]*)\s*metros?\s*cuadrados?',
    ]
    for pat in patterns_m2:
        m = re.search(pat, t)
        if m:
            try:
                v = int(float(m.group(1).replace('.','').replace(',','.')))
                if 20 <= v <= 100000:
                    result['m2'] = v
                    break
            except: pass

    # Estrellas
    patterns_stars = [
        r'(\d)\s*(?:estrellas?|stars?)\b',
        r'hotel\s+(\d)\s*\*',
        r'(\d)\s*\*\s*(?:hotel|hostal)',
        r'categoría\s*(\d)',
    ]
    for pat in patterns_stars:
        m = re.search(pat, t)
        if m:
            v = int(m.group(1))
            if 1 <= v <= 5:
                result['stars'] = v
                break

    return result

# ── Extractores por portal ─────────────────────────────────────────────────────

def enrich_thinkspain(item):
    """
    ThinkSpain: habitaciones y precio están en el título.
    La ubicación también está en el título pero con basura pegada.
    La ficha tiene tabla de características con m², dormitorios, baños.
    """
    result = {}
    title = item.get('title', '')

    # 1. Habitaciones desde el título (sin HTTP)
    m = re.search(r'(\d+)\s*(?:habitaciones?|bedrooms?|rooms?|habs?)\b', title, re.I)
    if m:
        v = int(m.group(1))
        if 1 <= v <= 500:
            result['rooms'] = v

    # 2. Precio desde el título: "... - â¬ 490,000" (â¬ es € con encoding roto)
    if not item.get('price') or 'consultar' in item.get('price', '').lower():
        # Buscar número después del símbolo de euro (roto o no)
        m_price = re.search(r'(?:â[\x82¬¬]|€|EUR)\s*([\d,. ]+)', title)
        if not m_price:
            m_price = re.search(r'-([\s]*)?([\d,]+(?:\.\d{3})*(?:,\d+)?)\s*(?:â[\x82¬¬]|€)?$', title)
        if m_price:
            raw = re.sub(r'[^\d]', '', m_price.group(1) if m_price.lastindex == 1 else m_price.group(2))
            if len(raw) >= 4:
                val = int(raw)
                # ThinkSpain usa 490,000 (coma = miles) → 490000
                if val < 1000:
                    val *= 1000  # "490" → 490.000 (raro, pero por si acaso)
                result['price_extracted'] = f'{val:,} €'.replace(',', '.')

    # 3. Ubicación limpia desde el título
    # Patrón: "N habitaciones Hotel en venta in CIUDAD with..." o "in CIUDAD -"
    m_loc = re.search(
        r'\bin\s+([A-Za-záéíóúñüÁÉÍÓÚÑÜ][A-Za-záéíóúñüÁÉÍÓÚÑÜ\s\-]{1,40?})\s*(?:with\b|\(|-\s*[€â]|\s*$)',
        title, re.I
    )
    if m_loc:
        city_raw = m_loc.group(1).strip().rstrip('-').strip()
        # Limpiar si hay provincia entre paréntesis: "Aguadulce (Almeria)" → ciudad=Aguadulce, prov=Almeria
        m_prov = re.match(r'(.+?)\s*\((.+?)\)', city_raw)
        if m_prov:
            city_raw = m_prov.group(1).strip()
            prov_hint = m_prov.group(2).strip()
        else:
            prov_hint = ''

        if city_raw and city_raw.lower() not in ['spain', 'españa']:
            result['location_city'] = city_raw.title()
            region = infer_region(city_raw + ' ' + prov_hint)
            if region:
                result['location_region'] = region

    # 4. Entrar en la ficha para m², estrellas y mejorar ubicación
    html = get_html(item['url'])
    if not html:
        return result

    soup = BeautifulSoup(html, 'lxml')
    full_text = soup.get_text(' ', strip=True)

    # Características estructuradas
    features_text = ''
    for container in soup.find_all(['ul', 'div', 'table'],
                                    class_=re.compile(r'feature|detail|spec|propert|info|characteristic|bedroom|bathroom', re.I)):
        features_text += ' ' + container.get_text(' ', strip=True)

    combined = features_text + ' ' + full_text
    extracted = extract_from_text(combined)

    # Aplicar solo campos no obtenidos antes
    for k, v in extracted.items():
        if k not in result:
            result[k] = v

    # Mejorar región con info de la ficha si no la tenemos
    if not result.get('location_region'):
        region = infer_region(combined[:2000])
        if region:
            result['location_region'] = region

    return result


def enrich_luxuryestate(item):
    """
    LuxuryEstate: la ficha tiene un bloque de datos estructurados
    con 'Dormitorios', 'Baños', 'Superficie' en etiquetas dl/dt/dd o ul.
    """
    result = {}
    html = get_html(item['url'])
    if not html:
        return result

    soup = BeautifulSoup(html, 'lxml')

    # Buscar pares label→valor en dt/dd, li, o divs con clase
    def find_value_near_label(label_pattern, text):
        m = re.search(
            label_pattern + r'[:\s]*(\d[\d.,]*)',
            text, re.I
        )
        if m:
            try: return int(float(m.group(1).replace(',','.')))
            except: pass
        return None

    full_text = soup.get_text(' ', strip=True)

    # Habitaciones / dormitorios
    for pat in [r'(?:dormitorios?|habitaciones?|bedrooms?|rooms?)\D{0,15}(\d+)',
                r'(\d+)\s*(?:dormitorios?|habitaciones?|bedrooms?)']:
        m = re.search(pat, full_text, re.I)
        if m:
            v = int(m.group(1))
            if 1 <= v <= 500:
                result['rooms'] = v
                break

    # Camas
    for pat in [r'(?:camas?|beds?)\D{0,10}(\d+)', r'(\d+)\s*(?:camas?|beds?)']:
        m = re.search(pat, full_text, re.I)
        if m:
            v = int(m.group(1))
            if 1 <= v <= 1000:
                result['beds'] = v
                break

    # M²
    for pat in [r'(\d[\d.,]*)\s*m[²2]', r'superficie[\s:]*(\d[\d.,]*)']:
        m = re.search(pat, full_text, re.I)
        if m:
            try:
                v = int(float(m.group(1).replace('.','').replace(',','.')))
                if 20 <= v <= 100000:
                    result['m2'] = v
                    break
            except: pass

    # Estrellas
    m = re.search(r'(\d)\s*(?:estrellas?|stars?|\*)', full_text, re.I)
    if m:
        v = int(m.group(1))
        if 1 <= v <= 5:
            result['stars'] = v

    # Ubicación desde meta og:locality o address
    meta_city = soup.find('meta', property='og:locality') or soup.find('meta', attrs={'name': 'city'})
    if meta_city:
        city = meta_city.get('content', '').strip()
        if city:
            result['location_city'] = city
            region = infer_region(city)
            if region:
                result['location_region'] = region

    # Fallback: extraer de la URL "hotel-for-sale-sietamo" → Sietamo
    if not result.get('location_city'):
        m_url = re.search(r'hotel-for-sale-(.+)$', item['url'])
        if m_url:
            city = m_url.group(1).replace('-', ' ').title()
            result['location_city'] = city
            region = infer_region(city)
            if region:
                result['location_region'] = region

    return result


def enrich_idealista(item):
    """
    Idealista: la ficha tiene características en ul.details-property_features
    o en spans con clases específicas.
    """
    result = {}
    html = get_html(item['url'])
    if not html:
        return result

    soup = BeautifulSoup(html, 'lxml')
    full_text = soup.get_text(' ', strip=True)

    # Idealista tiene "XX hab." en el bloque de características
    extracted = extract_from_text(full_text)
    result.update(extracted)

    # Ubicación desde el título o breadcrumb
    breadcrumb = soup.find(class_=re.compile(r'breadcrumb|location', re.I))
    if breadcrumb:
        crumbs = [c.strip() for c in breadcrumb.get_text(' / ').split('/') if c.strip()]
        if len(crumbs) >= 2:
            result['location_city'] = crumbs[-2].strip()
            region = infer_region(' '.join(crumbs))
            if region:
                result['location_region'] = region

    return result


def enrich_generic(item):
    """
    Extractor genérico para portales sin estructura específica:
    HotelSeVende, NegociosEnVenta, Lucas Fox, Engel & Völkers, Oi Real Estate.
    """
    result = {}
    html = get_html(item['url'])
    if not html:
        return result

    soup = BeautifulSoup(html, 'lxml')
    full_text = soup.get_text(' ', strip=True)

    extracted = extract_from_text(full_text)
    result.update(extracted)

    # Intentar ubicación desde meta tags
    for meta_name in ['og:locality', 'geo.placename', 'city']:
        meta = soup.find('meta', property=meta_name) or soup.find('meta', attrs={'name': meta_name})
        if meta:
            city = meta.get('content', '').strip()
            if city and city.lower() not in ['spain', 'españa']:
                result['location_city'] = city
                region = infer_region(city)
                if region:
                    result['location_region'] = region
                break

    # Región desde la ubicación actual del item si no la encontramos
    if not result.get('location_region') and item.get('location'):
        region = infer_region(item['location'])
        if region:
            result['location_region'] = region

    return result


# ── Dispatcher por portal ──────────────────────────────────────────────────────
ENRICHERS = {
    'ThinkSpain':     enrich_thinkspain,
    'LuxuryEstate':   enrich_luxuryestate,
    'Idealista':      enrich_idealista,
    'HotelSeVende':   enrich_generic,
    'NegociosEnVenta':enrich_generic,
    'Lucas Fox':      enrich_generic,
    'Engel & Völkers':enrich_generic,
    'Oi Real Estate': enrich_generic,
}

# ── Main ───────────────────────────────────────────────────────────────────────
# ── Limpieza de ubicaciones sin HTTP ──────────────────────────────────────────
def clean_location_thinkspain(loc):
    """
    Limpia la ubicación de ThinkSpain que viene con basura:
    'Creixell with pool garage - â¬ 490,000' -> 'Creixell'
    """
    if not loc: return loc
    loc = re.sub(r'\s+with\b.*', '', loc, flags=re.I)
    loc = re.sub(r'\s*-\s*[â€¬€\d].*', '', loc)
    loc = re.sub(r'\s*[â€¬€]\s*[\d,. ]+.*', '', loc)
    loc = re.sub(r'\s*\(.*?\)', '', loc)
    return loc.strip().title()


def clean_all_locations(data):
    """Limpia ubicaciones mal formadas en todo el cache (sin HTTP)."""
    fixed = 0
    for item in data:
        if item.get('source') == 'ThinkSpain':
            old = item.get('location', '')
            new = clean_location_thinkspain(old)
            if new and new != old:
                item['location'] = new
                fixed += 1
            if not item.get('location_region') and new:
                region = infer_region(new)
                if region:
                    item['location_region'] = region
        if not item.get('location_region') and item.get('location'):
            region = infer_region(item['location'])
            if region:
                item['location_region'] = region
    return fixed


def main():
    parser = argparse.ArgumentParser(description='Enriquece el cache de hoteles')
    parser.add_argument('--sources', nargs='+', help='Solo procesar estos portales')
    parser.add_argument('--limit', type=int, help='Limitar a N hoteles (para test)')
    parser.add_argument('--force', action='store_true', help='Re-enriquecer aunque ya tengan datos')
    args = parser.parse_args()

    # Cargar cache
    if not os.path.exists(CACHE_FILE):
        print(f'ERROR: No se encuentra {CACHE_FILE}')
        sys.exit(1)

    with open(CACHE_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)

    print(f'Cache cargado: {len(data)} hoteles')

    # Paso 0: Limpiar ubicaciones sin HTTP (ThinkSpain y región para todos)
    fixed_locs = clean_all_locations(data)
    print(f'Ubicaciones limpiadas: {fixed_locs}')

    # Extraer habitaciones desde títulos ThinkSpain (sin HTTP)
    import re as _re
    fixed_rooms = 0
    for item in data:
        if item.get('source') == 'ThinkSpain' and not item.get('rooms'):
            m = _re.search(r'(\d+)\s*(?:habitaciones?|bedrooms?|rooms?|habs?)\b', item.get('title',''), _re.I)
            if m:
                v = int(m.group(1))
                if 1 <= v <= 500:
                    item['rooms'] = v
                    fixed_rooms += 1
        # Extraer precio de ThinkSpain desde título
        if item.get('source') == 'ThinkSpain' and ('consultar' in item.get('price','').lower()):
            m_p = _re.search(r'(?:â[\x82¬¬]|€|EUR)\s*([\d,. ]+)', item.get('title',''))
            if m_p:
                raw = _re.sub(r'[^\d]', '', m_p.group(1))
                if len(raw) >= 4:
                    val = int(raw)
                    item['price'] = f'{val:,} €'.replace(',', '.')
                    fixed_rooms += 1  # reutilizar contador

    print(f'Habitaciones/precios extraídos de títulos: {fixed_rooms}')

    # Guardar mejoras sin-HTTP inmediatamente
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print('Cache guardado con mejoras rápidas.\n')

    # Backup
    with open(BACKUP_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f'Backup guardado en {BACKUP_FILE}')

    # Filtrar qué procesar
    to_process = []
    for item in data:
        source = item.get('source', '')
        if args.sources and source not in args.sources:
            continue
        if not args.force and not needs_enrichment(item):
            continue
        if source not in ENRICHERS:
            continue
        to_process.append(item)

    if args.limit:
        to_process = to_process[:args.limit]

    # Stats iniciales
    from collections import Counter
    sources_count = Counter(x.get('source') for x in to_process)
    print(f'\nHoteles a enriquecer: {len(to_process)}')
    for src, cnt in sources_count.most_common():
        print(f'  {src}: {cnt}')
    print()

    # Procesar
    enriched = 0
    failed   = 0
    skipped  = 0

    # Índice para acceso rápido
    cache_index = {item['url']: i for i, item in enumerate(data)}

    for idx, item in enumerate(to_process, 1):
        url    = item['url']
        source = item.get('source', '?')
        enricher = ENRICHERS.get(source)

        print(f'[{idx}/{len(to_process)}] {source} — {url[:65]}')

        try:
            new_data = enricher(item)

            if new_data:
                # Aplicar al item en el cache original
                cache_idx = cache_index.get(url)
                if cache_idx is not None:
                    for k, v in new_data.items():
                        if k == 'price_extracted':
                            # Solo actualizar precio si era "Precio a consultar"
                            if 'consultar' in data[cache_idx].get('price','').lower():
                                data[cache_idx]['price'] = v
                        elif v is not None:
                            # No sobreescribir datos existentes excepto si están vacíos
                            if not data[cache_idx].get(k):
                                data[cache_idx][k] = v

                    # Resumen de lo encontrado
                    found = [f'{k}={v}' for k,v in new_data.items() if v is not None and k != 'price_extracted']
                    if found:
                        print(f'  ✅ {", ".join(found)}')
                        enriched += 1
                    else:
                        print(f'  ⚪ Sin datos nuevos')
                        skipped += 1
            else:
                print(f'  ⚪ Sin respuesta')
                skipped += 1

        except Exception as e:
            print(f'  ❌ Error: {e}')
            failed += 1

        # Guardar progreso cada BATCH_SIZE
        if idx % BATCH_SIZE == 0:
            with open(CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f'\n  💾 Progreso guardado ({idx}/{len(to_process)})\n')

        time.sleep(DELAY)

    # Guardado final
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # Estadísticas finales
    print(f'\n{"="*50}')
    print(f'ENRIQUECIMIENTO COMPLETADO')
    print(f'{"="*50}')
    print(f'  Enriquecidos con datos: {enriched}')
    print(f'  Sin datos nuevos:       {skipped}')
    print(f'  Errores:                {failed}')
    print()

    # Coverage tras el enriquecimiento
    rooms_ok = sum(1 for x in data if x.get('rooms'))
    beds_ok  = sum(1 for x in data if x.get('beds'))
    m2_ok    = sum(1 for x in data if x.get('m2'))
    stars_ok = sum(1 for x in data if x.get('stars'))
    reg_ok   = sum(1 for x in data if x.get('location_region'))
    total    = len(data)

    print(f'Coverage final del cache ({total} hoteles):')
    print(f'  Habitaciones:  {rooms_ok:4d} ({100*rooms_ok//total}%)')
    print(f'  Camas:         {beds_ok:4d} ({100*beds_ok//total}%)')
    print(f'  M²:            {m2_ok:4d} ({100*m2_ok//total}%)')
    print(f'  Estrellas:     {stars_ok:4d} ({100*stars_ok//total}%)')
    print(f'  Región:        {reg_ok:4d} ({100*reg_ok//total}%)')
    print(f'\nCache guardado en {CACHE_FILE}')
    print(f'Backup disponible en {BACKUP_FILE}')


if __name__ == '__main__':
    main()
