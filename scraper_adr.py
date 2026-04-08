#!/usr/bin/env python3
"""
scraper_adr.py — Benchmark ADR por municipio × categoría
Extrae precios medios de Booking.com para cada municipio del cache.
Corre independiente del scraper diario, 1 vez al mes.
Genera: adr_benchmark.json
"""

import json, re, time, random, unicodedata, os
from datetime import datetime

# ── Dependencias ──────────────────────────────────────────────────────────────
try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    import subprocess, sys
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'requests', 'beautifulsoup4', 'lxml'])
    import requests
    from bs4 import BeautifulSoup

# ── Configuración ─────────────────────────────────────────────────────────────
CACHE_FILE     = 'hoteles_cache.json'
OUTPUT_FILE    = 'adr_benchmark.json'
DELAY_MIN      = 2.5   # segundos entre requests
DELAY_MAX      = 5.0
MAX_RETRIES    = 2
REQUEST_TIMEOUT= 15

HEADERS_LIST = [
    {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept-Language': 'es-ES,es;q=0.9,en;q=0.8',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
    },
    {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        'Accept-Language': 'es,en-US;q=0.7,en;q=0.3',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
    },
    {
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept-Language': 'es-ES,es;q=0.8',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
    },
]

# ── Normalización de nombres ──────────────────────────────────────────────────
def normalizar(texto):
    """Convierte 'Alhaurín el Grande' → 'alhaurin-el-grande'"""
    if not texto:
        return ''
    # Quitar acentos
    texto = unicodedata.normalize('NFD', texto)
    texto = ''.join(c for c in texto if unicodedata.category(c) != 'Mn')
    # Minúsculas, espacios → guiones
    texto = texto.lower().strip()
    texto = re.sub(r'[^a-z0-9\s-]', '', texto)
    texto = re.sub(r'[\s]+', '-', texto)
    texto = re.sub(r'-+', '-', texto).strip('-')
    return texto

def variantes(municipio_norm):
    """Genera variantes del nombre para probar si falla la primera"""
    variantes_list = [municipio_norm]
    # Sin artículos comunes
    for art in ['-el-', '-la-', '-los-', '-las-', '-de-', '-del-', '-de-la-', '-de-los-']:
        if art in municipio_norm:
            variantes_list.append(municipio_norm.replace(art, '-'))
    # Solo primera palabra
    primera = municipio_norm.split('-')[0]
    if primera != municipio_norm and len(primera) > 3:
        variantes_list.append(primera)
    return variantes_list

# ── Extracción de precios de Booking ─────────────────────────────────────────
def extraer_precios_booking(html, municipio_orig):
    """
    Extrae precio medio por categoría de estrellas de una página de ciudad de Booking.
    Booking muestra frases como:
    'los hoteles de 3 estrellas cuestan X € de media'
    'On average, 3-star hotels in X cost $Y per night'
    """
    soup = BeautifulSoup(html, 'lxml')
    text = soup.get_text(' ', strip=True)
    precios = {}

    # Patrones en español e inglés que Booking usa en sus páginas de ciudad
    patrones = [
        # ES: "hoteles de 3 estrellas cuestan 95 € de media"
        r'hoteles?\s+de\s+(\d)\s+estrellas?\s+(?:en\s+\S+\s+)?(?:tienen\s+un\s+precio\s+(?:medio\s+)?de|cuestan?)\s+([\d,.]+)\s*€',
        # ES: "precio medio de un hotel de 3 estrellas es de 95 €"
        r'precio\s+medio\s+(?:de\s+)?(?:un\s+)?hotel(?:es?)?\s+de\s+(\d)\s+estrellas?\s+(?:en\s+\S+\s+)?(?:es\s+de\s+|cuesta\s+)([\d,.]+)\s*€',
        # EN: "3-star hotels in X cost $95 per night" / "cost €95"
        r'(\d)-star\s+hotels?\s+(?:in\s+\S+\s+)?cost\s+(?:around\s+)?(?:\$|€|£)([\d,]+)',
        # EN: "average price for a 3-star hotel ... is $95"
        r'average\s+price\s+(?:per\s+night\s+)?for\s+(?:a\s+)?(\d)-star\s+hotel[^$€£\d]*(?:\$|€|£)([\d,]+)',
        # EN: "3-star hotels cost $95 per night on average"  
        r'(\d)-star\s+hotels?\s+(?:in\s+\S+\s+)?(?:are|cost)\s+(?:around\s+)?(?:\$|€|£)([\d,]+)',
    ]

    for patron in patrones:
        matches = re.findall(patron, text, re.IGNORECASE)
        for match in matches:
            try:
                stars = int(match[0])
                precio_str = match[1].replace(',', '').replace('.', '')
                precio = int(precio_str)
                if 1 <= stars <= 5 and 20 <= precio <= 2000:
                    if str(stars) not in precios:
                        precios[str(stars)] = precio
                        print(f'    ★{stars}: {precio}€')
            except:
                continue

    # Si no encontramos con patrones de texto, buscar en atributos data o JSON-LD
    if not precios:
        # Buscar en scripts JSON de la página
        for script in soup.find_all('script', type='application/json'):
            try:
                data = json.loads(script.string)
                data_str = json.dumps(data)
                matches = re.findall(r'"stars":\s*(\d).*?"price":\s*([\d.]+)', data_str)
                for m in matches:
                    stars, precio = int(m[0]), int(float(m[1]))
                    if 1 <= stars <= 5 and 20 <= precio <= 2000:
                        if str(stars) not in precios:
                            precios[str(stars)] = precio
            except:
                continue

    return precios

def fetch_booking_city(municipio_orig, session):
    """Intenta obtener precios de Booking para un municipio con varias variantes de URL"""
    muni_norm = normalizar(municipio_orig)
    if not muni_norm or len(muni_norm) < 2:
        return None

    urls_a_probar = []
    for v in variantes(muni_norm):
        urls_a_probar.append(f'https://www.booking.com/city/es/{v}.es.html')
        urls_a_probar.append(f'https://www.booking.com/city/es/{v}.en-gb.html')

    for url in urls_a_probar[:4]:  # max 4 intentos por municipio
        for intento in range(MAX_RETRIES):
            try:
                headers = random.choice(HEADERS_LIST)
                r = session.get(url, headers=headers, timeout=REQUEST_TIMEOUT, allow_redirects=True)

                if r.status_code == 404:
                    break  # Esta variante no existe, probar siguiente
                if r.status_code == 429:
                    print(f'  Rate limit en {url}, esperando 30s...')
                    time.sleep(30)
                    continue
                if r.status_code != 200:
                    time.sleep(DELAY_MIN)
                    continue

                # Verificar que es una página de ciudad válida (no redirect a home)
                if 'booking.com/city/' not in r.url and municipio_orig.lower()[:4] not in r.url.lower():
                    break

                precios = extraer_precios_booking(r.text, municipio_orig)
                if precios:
                    return precios

                # Si la página cargó pero no hay precios estructurados,
                # puede que sea un municipio pequeño sin datos suficientes
                if r.status_code == 200 and len(r.text) > 5000:
                    return {}  # Página existe pero sin datos de precio por estrella

                break

            except requests.exceptions.ConnectionError:
                time.sleep(DELAY_MIN * 2)
                continue
            except Exception as e:
                print(f'  Error {url}: {e}')
                break

        time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

    return None

# ── Lógica principal ──────────────────────────────────────────────────────────
def main():
    print(f'\n{"="*60}')
    print(f'SCRAPER ADR BENCHMARK — {datetime.now().strftime("%d/%m/%Y %H:%M")}')
    print(f'{"="*60}\n')

    # Cargar cache de hoteles
    if not os.path.exists(CACHE_FILE):
        print(f'ERROR: No se encuentra {CACHE_FILE}')
        return

    with open(CACHE_FILE, 'r', encoding='utf-8') as f:
        cache = json.load(f)

    print(f'Cache cargado: {len(cache)} hoteles')

    # Cargar benchmark existente (para no repetir municipios ya scrapeados)
    benchmark_existente = {}
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
            data_existente = json.load(f)
            benchmark_existente = data_existente.get('municipios', {})
        print(f'Benchmark existente: {len(benchmark_existente)} municipios ya scrapeados')

    # Extraer municipios únicos limpios del cache
    municipios_raw = set()
    for h in cache:
        loc = (h.get('location') or '').strip()
        if loc and len(loc) <= 40 and not loc.isupper() and not any(c.isdigit() for c in loc[:3]):
            municipios_raw.add(loc)

    print(f'Municipios únicos en cache: {len(municipios_raw)}')

    # Filtrar los que ya tenemos (salvo que el scrape fue hace más de 25 días)
    ultimo_update = data_existente.get('updated', '') if benchmark_existente else ''
    force_refresh = False
    if ultimo_update:
        try:
            dias = (datetime.now() - datetime.strptime(ultimo_update, '%Y-%m-%d')).days
            force_refresh = dias > 25
            if force_refresh:
                print(f'Último update hace {dias} días → refrescando todo')
        except:
            pass

    municipios_a_scrapear = []
    for m in sorted(municipios_raw):
        key = normalizar(m)
        if force_refresh or key not in benchmark_existente:
            municipios_a_scrapear.append(m)

    print(f'Municipios a scrapear ahora: {len(municipios_a_scrapear)}')
    print()

    # Resultado final
    benchmark = dict(benchmark_existente)  # Mantener los ya scrapeados
    ok, sin_datos, errores = 0, 0, 0

    session = requests.Session()

    for i, municipio in enumerate(municipios_a_scrapear, 1):
        key = normalizar(municipio)
        print(f'[{i}/{len(municipios_a_scrapear)}] {municipio} ({key})')

        precios = fetch_booking_city(municipio, session)

        if precios is None:
            print(f'  → No encontrado en Booking')
            errores += 1
            benchmark[key] = {'fuente': 'no_encontrado', 'ts': datetime.now().strftime('%Y-%m-%d')}
        elif precios == {}:
            print(f'  → Página existe pero sin datos de precio por estrella')
            sin_datos += 1
            benchmark[key] = {'fuente': 'sin_datos', 'ts': datetime.now().strftime('%Y-%m-%d')}
        else:
            print(f'  → OK: {precios}')
            ok += 1
            benchmark[key] = {
                'municipio': municipio,
                'precios': precios,  # {"3": 95, "4": 130, "5": 220}
                'fuente': 'booking',
                'ts': datetime.now().strftime('%Y-%m-%d')
            }

        # Guardar progreso cada 20 municipios
        if i % 20 == 0:
            _guardar(benchmark, OUTPUT_FILE)
            print(f'\n  [Progreso guardado: {i}/{len(municipios_a_scrapear)}]\n')

        # Delay entre requests
        time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

    # Guardar resultado final
    _guardar(benchmark, OUTPUT_FILE)

    print(f'\n{"="*60}')
    print(f'COMPLETADO')
    print(f'  OK con precios:  {ok}')
    print(f'  Sin datos:       {sin_datos}')
    print(f'  No encontrados:  {errores}')
    print(f'  Total en benchmark: {len(benchmark)}')
    print(f'  Guardado en: {OUTPUT_FILE}')
    print(f'{"="*60}\n')

def _guardar(benchmark, output_file):
    output = {
        'updated': datetime.now().strftime('%Y-%m-%d'),
        'fuente': 'Booking.com páginas de ciudad — precio medio por categoría',
        'municipios': benchmark
    }
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

if __name__ == '__main__':
    main()
