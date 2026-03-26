#!/usr/bin/env python3
"""
fix_regions.py — Mejora location y location_region en el cache sin HTTP.

1. Limpia ubicaciones sucias (ThinkSpain con basura pegada)
2. Infiere comunidad autónoma para todas las ubicaciones posibles
3. Guarda el cache actualizado

Uso:
    python fix_regions.py
"""

import json, re, os

CACHE_FILE  = 'hoteles_cache.json'
BACKUP_FILE = 'hoteles_cache_backup_regions.json'

# ── Mapa exhaustivo ciudad/zona → CCAA ────────────────────────────────────────
CCAA_MAP = {
    # Madrid
    'madrid': 'Madrid',
    'alcalá de henares': 'Madrid', 'alcala de henares': 'Madrid',
    'getafe': 'Madrid', 'leganés': 'Madrid', 'leganes': 'Madrid',
    'móstoles': 'Madrid', 'mostoles': 'Madrid', 'alcobendas': 'Madrid',
    'torrejón': 'Madrid', 'torrejon': 'Madrid', 'fuenlabrada': 'Madrid',
    'pozuelo': 'Madrid', 'majadahonda': 'Madrid', 'las rozas': 'Madrid',
    'cercedilla': 'Madrid', 'navacerrada': 'Madrid', 'manzanares': 'Madrid',
    'aranjuez': 'Madrid', 'collado villalba': 'Madrid',

    # Cataluña
    'barcelona': 'Cataluña', 'girona': 'Cataluña', 'tarragona': 'Cataluña',
    'lleida': 'Cataluña', 'lérida': 'Cataluña', 'lerida': 'Cataluña',
    'sitges': 'Cataluña', 'lloret': 'Cataluña', 'roses': 'Cataluña',
    'calella': 'Cataluña', 'palamos': 'Cataluña', 'palamós': 'Cataluña',
    'creixell': 'Cataluña', 'salou': 'Cataluña', 'cambrils': 'Cataluña',
    'reus': 'Cataluña', 'valls': 'Cataluña', 'tortosa': 'Cataluña',
    'costa dorada': 'Cataluña', 'costa brava': 'Cataluña',
    'platja d\'aro': 'Cataluña', 'platja daro': 'Cataluña',
    'sant feliu de guixols': 'Cataluña', 'sant feliu': 'Cataluña',
    'santa coloma de gramenet': 'Cataluña', 'badalona': 'Cataluña',
    'sabadell': 'Cataluña', 'terrassa': 'Cataluña', 'manresa': 'Cataluña',
    'mataró': 'Cataluña', 'mataro': 'Cataluña', 'vic': 'Cataluña',
    'figueres': 'Cataluña', 'empúries': 'Cataluña', 'empuriabrava': 'Cataluña',
    'vidreras': 'Cataluña', 'tordera': 'Cataluña', 'castillo de aro': 'Cataluña',
    'sant marti barcelona': 'Cataluña', 'mora la nueva': 'Cataluña',
    'costa brava': 'Cataluña', 'costa dorada': 'Cataluña',

    # Andalucía
    'sevilla': 'Andalucía', 'málaga': 'Andalucía', 'malaga': 'Andalucía',
    'granada': 'Andalucía', 'cádiz': 'Andalucía', 'cadiz': 'Andalucía',
    'huelva': 'Andalucía', 'almería': 'Andalucía', 'almeria': 'Andalucía',
    'córdoba': 'Andalucía', 'cordoba': 'Andalucía', 'jaén': 'Andalucía', 'jaen': 'Andalucía',
    'marbella': 'Andalucía', 'torremolinos': 'Andalucía', 'benalmadena': 'Andalucía',
    'nerja': 'Andalucía', 'fuengirola': 'Andalucía', 'ronda': 'Andalucía',
    'tarifa': 'Andalucía', 'velez': 'Andalucía', 'vélez': 'Andalucía',
    'aguadulce': 'Andalucía', 'estepona': 'Andalucía', 'mijas': 'Andalucía',
    'motril': 'Andalucía', 'almuñécar': 'Andalucía', 'almunecar': 'Andalucía',
    'salobreña': 'Andalucía', 'salobrena': 'Andalucía',
    'gaucin': 'Andalucía', 'macharaviaya': 'Andalucía',
    'san roque': 'Andalucía', 'la línea': 'Andalucía', 'algeciras': 'Andalucía',
    'jerez': 'Andalucía', 'chiclana': 'Andalucía', 'puerto de santa maría': 'Andalucía',
    'arcos de la frontera': 'Andalucía', 'medina-sidonia': 'Andalucía',
    'medina sidonia': 'Andalucía', 'galaroza': 'Andalucía',
    'alhama de granada': 'Andalucía', 'alcalá la real': 'Andalucía',
    'órgiva': 'Andalucía', 'orgiva': 'Andalucía', 'guaro': 'Andalucía',
    'guejar sierra': 'Andalucía', 'busquistar': 'Andalucía',
    'pizarra': 'Andalucía', 'costa del sol': 'Andalucía',
    'torrevieja': 'Andalucía',  # ojo, es Valencia — lo ponemos abajo
    'málaga city': 'Andalucía', 'malaga city': 'Andalucía',
    'andalucia': 'Andalucía', 'andalucía': 'Andalucía', 'andalusia': 'Andalucía',
    'mondújar': 'Andalucía', 'mondujar': 'Andalucía',
    'huétor-tájar': 'Andalucía', 'huetor tajar': 'Andalucía',
    'pórtugos': 'Andalucía', 'pitres': 'Andalucía',

    # C. Valenciana
    'valencia': 'C. Valenciana', 'alicante': 'C. Valenciana',
    'castellón': 'C. Valenciana', 'castellon': 'C. Valenciana',
    'benidorm': 'C. Valenciana', 'denia': 'C. Valenciana', 'dénia': 'C. Valenciana',
    'jávea': 'C. Valenciana', 'javea': 'C. Valenciana',
    'calpe': 'C. Valenciana', 'calp': 'C. Valenciana',
    'altea': 'C. Valenciana', 'benissa': 'C. Valenciana',
    'orihuela': 'C. Valenciana', 'torrevieja': 'C. Valenciana',
    'santa pola': 'C. Valenciana', 'elche': 'C. Valenciana', 'elx': 'C. Valenciana',
    'gandía': 'C. Valenciana', 'gandia': 'C. Valenciana',
    'peñíscola': 'C. Valenciana', 'peniscola': 'C. Valenciana',
    'costa blanca': 'C. Valenciana',
    'beniali': 'C. Valenciana', 'palomar': 'C. Valenciana',
    'bocairente': 'C. Valenciana', 'bocairent': 'C. Valenciana',
    'finestrat': 'C. Valenciana', 'alfaz del pi': 'C. Valenciana',
    'el campello': 'C. Valenciana', 'villajoyosa': 'C. Valenciana',
    'playas de orihuela': 'C. Valenciana',
    'vall de gallinera': 'C. Valenciana', 'vall de ebo': 'C. Valenciana',
    'calig': 'C. Valenciana', 'lucena del cid': 'C. Valenciana',
    'ayora': 'C. Valenciana', 'cortes': 'C. Valenciana',
    'valencia/valència': 'C. Valenciana',

    # Baleares
    'mallorca': 'Baleares', 'menorca': 'Baleares', 'ibiza': 'Baleares',
    'formentera': 'Baleares', 'palma': 'Baleares', 'baleares': 'Baleares',
    'balears': 'Baleares', 'islas baleares': 'Baleares', 'illes balears': 'Baleares',
    'balears illes': 'Baleares',
    'manacor': 'Baleares', 'pollensa': 'Baleares', 'pollença': 'Baleares',
    'alcudia': 'Baleares', 'alcúdia': 'Baleares', 'sóller': 'Baleares', 'soller': 'Baleares',
    'estellenchs': 'Baleares', 'estellencs': 'Baleares',
    'ses salines': 'Baleares', 'capdepera': 'Baleares', 'magaluf': 'Baleares',
    'porto cristo': 'Baleares', 'cala millor': 'Baleares',
    'san antonio': 'Baleares', 'santa eulalia': 'Baleares',
    'ferrerias': 'Baleares', 'ferreries': 'Baleares',
    'mallorca sureste': 'Baleares', 'mallorca este': 'Baleares',
    'palma de mallorca': 'Baleares',

    # Canarias
    'tenerife': 'Canarias', 'las palmas': 'Canarias', 'gran canaria': 'Canarias',
    'lanzarote': 'Canarias', 'fuerteventura': 'Canarias',
    'la palma': 'Canarias', 'el hierro': 'Canarias', 'la gomera': 'Canarias',
    'santa cruz de tenerife': 'Canarias', 'adeje': 'Canarias',
    'arona': 'Canarias', 'mogán': 'Canarias', 'mogan': 'Canarias',
    'playa de las américas': 'Canarias', 'costa adeje': 'Canarias',
    'islas canarias': 'Canarias', 'canarias': 'Canarias',
    'mácher': 'Canarias', 'macher': 'Canarias',

    # País Vasco
    'bilbao': 'País Vasco', 'san sebastián': 'País Vasco', 'donostia': 'País Vasco',
    'vitoria': 'País Vasco', 'gasteiz': 'País Vasco',
    'guipúzcoa': 'País Vasco', 'guipuzcoa': 'País Vasco',
    'vizcaya': 'País Vasco', 'bizkaia': 'País Vasco', 'álava': 'País Vasco',

    # Navarra
    'pamplona': 'Navarra', 'navarra': 'Navarra', 'iruña': 'Navarra',

    # Cantabria
    'santander': 'Cantabria', 'cantabria': 'Cantabria',
    'castro urdiales': 'Cantabria', 'laredo': 'Cantabria',

    # Asturias
    'oviedo': 'Asturias', 'gijón': 'Asturias', 'gijon': 'Asturias',
    'asturias': 'Asturias', 'avilés': 'Asturias', 'aviles': 'Asturias',
    'cangas de onís': 'Asturias', 'cangas de onis': 'Asturias',
    'coaña': 'Asturias', 'coana': 'Asturias',

    # Galicia
    'a coruña': 'Galicia', 'coruña': 'Galicia', 'vigo': 'Galicia',
    'pontevedra': 'Galicia', 'santiago': 'Galicia', 'lugo': 'Galicia',
    'ourense': 'Galicia', 'galicia': 'Galicia',
    'a guarda': 'Galicia', 'cuntis': 'Galicia', 'moana': 'Galicia',
    'tomino': 'Galicia', 'tomiño': 'Galicia', 'ribadeo': 'Galicia',

    # Castilla y León
    'salamanca': 'Castilla y León', 'burgos': 'Castilla y León',
    'valladolid': 'Castilla y León', 'segovia': 'Castilla y León',
    'ávila': 'Castilla y León', 'avila': 'Castilla y León',
    'soria': 'Castilla y León', 'zamora': 'Castilla y León',
    'palencia': 'Castilla y León', 'león': 'Castilla y León', 'leon': 'Castilla y León',
    'burgos city': 'Castilla y León',

    # Castilla-La Mancha
    'toledo': 'Castilla-La Mancha', 'ciudad real': 'Castilla-La Mancha',
    'albacete': 'Castilla-La Mancha', 'cuenca': 'Castilla-La Mancha',
    'guadalajara': 'Castilla-La Mancha',

    # Extremadura
    'cáceres': 'Extremadura', 'caceres': 'Extremadura', 'badajoz': 'Extremadura',
    'mérida': 'Extremadura', 'merida': 'Extremadura',

    # Aragón
    'zaragoza': 'Aragón', 'huesca': 'Aragón', 'teruel': 'Aragón',
    'jaca': 'Aragón', 'benasque': 'Aragón',

    # Murcia
    'murcia': 'Murcia', 'cartagena': 'Murcia', 'lorca': 'Murcia',
    'san javier': 'Murcia', 'mazarrón': 'Murcia', 'mazarron': 'Murcia',
    'caravaca de la cruz': 'Murcia', 'caravaca': 'Murcia',
    'calabardina': 'Murcia', 'santiago de la ribera': 'Murcia',

    # La Rioja
    'logroño': 'La Rioja', 'logrono': 'La Rioja', 'la rioja': 'La Rioja',

    # Ceuta / Melilla
    'ceuta': 'Ceuta', 'melilla': 'Melilla',
}

def clean_location(loc, source):
    """Limpia ubicaciones sucias especialmente de ThinkSpain."""
    if not loc: return loc
    # Quitar basura ThinkSpain: "with pool", "garage", precio, etc.
    loc = re.sub(r'\s+with\b.*', '', loc, flags=re.I)
    loc = re.sub(r'\s*-\s*[â€¬€\d].*', '', loc)
    loc = re.sub(r'\s*[â€¬€]\s*[\d,. ]+.*', '', loc)
    loc = re.sub(r'\bgarage\b.*', '', loc, flags=re.I)
    loc = re.sub(r'\bpool\b.*', '', loc, flags=re.I)
    loc = re.sub(r'â[\x82¬¬].*', '', loc)
    loc = re.sub(r'\s+$', '', loc)
    # Quitar ciudad / Calp → quedarse con primera parte
    loc = re.sub(r'\s*/\s*\w+\s+city\b', '', loc, flags=re.I)
    # "Alicante / Alacant city" → "Alicante"
    m = re.match(r'([A-Za-záéíóúñüÁÉÍÓÚÑÜ][^/]+?)\s*/\s*.+', loc)
    if m: loc = m.group(1).strip()
    return loc.strip()

def infer_region(text):
    """Infiere CCAA buscando en el texto (insensible a mayúsculas/acentos)."""
    if not text: return None
    t = text.lower().strip()
    # Buscar coincidencias de más larga a más corta para evitar falsos positivos
    candidates = sorted(CCAA_MAP.keys(), key=len, reverse=True)
    for key in candidates:
        if key in t:
            return CCAA_MAP[key]
    return None

def main():
    if not os.path.exists(CACHE_FILE):
        print(f'ERROR: No se encuentra {CACHE_FILE}')
        return

    with open(CACHE_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)

    print(f'Cache cargado: {len(data)} hoteles')

    # Backup
    with open(BACKUP_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f'Backup en {BACKUP_FILE}')

    # Stats antes
    antes_region = sum(1 for x in data if x.get('location_region'))
    print(f'\nRegión antes: {antes_region} ({100*antes_region//len(data)}%)')

    fixed_loc   = 0
    fixed_region = 0

    for item in data:
        source = item.get('source', '')
        old_loc = item.get('location', '')

        # 1. Limpiar ubicación sucia
        new_loc = clean_location(old_loc, source)
        if new_loc != old_loc and new_loc:
            item['location'] = new_loc
            fixed_loc += 1

        # 2. Intentar inferir región desde múltiples fuentes
        if not item.get('location_region'):
            # Buscar en: location limpia, location_city, título, descripción
            search_texts = [
                item.get('location', ''),
                item.get('location_city', ''),
                item.get('title', ''),
                item.get('description', '')[:200],
                item.get('url', ''),
            ]
            for text in search_texts:
                region = infer_region(text)
                if region:
                    item['location_region'] = region
                    fixed_region += 1
                    break

        # 3. Si tiene location_city pero no location limpia, usar location_city
        if item.get('location_city') and (
            not item.get('location') or
            item.get('location') in ('España', 'Espana', '')
        ):
            item['location'] = item['location_city']

    # Stats después
    despues_region = sum(1 for x in data if x.get('location_region'))
    despues_loc = sum(1 for x in data if x.get('location') not in ('España','Espana','',None))

    print(f'\nUbicaciones limpias:  +{fixed_loc}')
    print(f'Regiones añadidas:    +{fixed_region}')
    print(f'\nRegión después: {despues_region} ({100*despues_region//len(data)}%)')
    print(f'Ubicación válida:     {despues_loc} ({100*despues_loc//len(data)}%)')

    # Guardar
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f'\nCache guardado en {CACHE_FILE} ✅')

    # Ver las que siguen sin región (para mejorar en el futuro)
    sin = [x for x in data if not x.get('location_region')]
    locs_sin = {}
    for x in sin:
        loc = x.get('location','')
        if loc and loc not in ('España','Espana',''):
            locs_sin[loc] = locs_sin.get(loc,0) + 1
    if locs_sin:
        print(f'\nAún sin región ({len(sin)} hoteles) — top ubicaciones:')
        for loc, cnt in sorted(locs_sin.items(), key=lambda x: -x[1])[:20]:
            print(f'  {cnt:3d}x  {loc}')

if __name__ == '__main__':
    main()
