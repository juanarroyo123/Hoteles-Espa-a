#!/usr/bin/env python3
"""
fix_regions2.py — Segunda pasada de limpieza de ubicaciones y regiones.
Corre después de fix_regions.py para limpiar los casos que quedaron.
"""
import json, re, os

CACHE_FILE  = 'hoteles_cache.json'

# Municipios pequeños + variantes con basura → CCAA
EXTRA_MAP = {
    # Andalucía — municipios pequeños
    'tolox': 'Andalucía', 'alhaurin': 'Andalucía', 'alhaurín': 'Andalucía',
    'pinos genil': 'Andalucía', 'vejer de la frontera': 'Andalucía',
    'vejer': 'Andalucía', 'seville': 'Andalucía', 'seville city': 'Andalucía',
    'alora': 'Andalucía', 'álora': 'Andalucía',
    'zahara de la sierra': 'Andalucía', 'zahara': 'Andalucía',
    'diezma': 'Andalucía', 'iznate': 'Andalucía', 'la zubia': 'Andalucía',
    'mojacar': 'Andalucía', 'mojácar': 'Andalucía',
    'guejar sierra': 'Andalucía', 'güéjar sierra': 'Andalucía',
    'guaro': 'Andalucía', 'macharaviaya': 'Andalucía',
    'gaucin': 'Andalucía', 'gaucín': 'Andalucía',
    'san roque': 'Andalucía', 'almuñécar': 'Andalucía', 'almunecar': 'Andalucía',
    'busquistar': 'Andalucía', 'órgiva': 'Andalucía', 'orgiva': 'Andalucía',
    'pitres': 'Andalucía', 'pórtugos': 'Andalucía', 'mondújar': 'Andalucía',
    'huétor': 'Andalucía', 'huetor': 'Andalucía',
    'pizarra': 'Andalucía', 'estepona': 'Andalucía',
    'alcalá la real': 'Andalucía', 'alhama de granada': 'Andalucía',
    'galaroza': 'Andalucía', 'arcos de la frontera': 'Andalucía',
    'medina-sidonia': 'Andalucía', 'medina sidonia': 'Andalucía',
    'puerto de santa maría': 'Andalucía', 'el puerto': 'Andalucía',
    'chiclana': 'Andalucía', 'salobreña': 'Andalucía', 'salobrena': 'Andalucía',
    'motril': 'Andalucía', 'nerja': 'Andalucía', 'frigiliana': 'Andalucía',
    'competa': 'Andalucía', 'torrox': 'Andalucía', 'ronda': 'Andalucía',
    'tarifa': 'Andalucía', 'los barrios': 'Andalucía', 'algeciras': 'Andalucía',
    'la línea': 'Andalucía', 'linea de la concepcion': 'Andalucía',
    'mijas': 'Andalucía', 'fuengirola': 'Andalucía', 'benalmadena': 'Andalucía',
    'benalmádena': 'Andalucía', 'torremolinos': 'Andalucía', 'marbella': 'Andalucía',

    # Baleares — municipios pequeños
    'sineu': 'Baleares', 'arta': 'Baleares', 'artà': 'Baleares',
    'peguera': 'Baleares', 'portocolom': 'Baleares', 'inca': 'Baleares',
    'l\'arenal': 'Baleares', 'arenal': 'Baleares', 'llucmajor': 'Baleares',
    'campos': 'Baleares', 'felanitx': 'Baleares', 'santanyí': 'Baleares',
    'santanyi': 'Baleares', 'alcudia': 'Baleares', 'alcúdia': 'Baleares',
    'pollensa': 'Baleares', 'pollença': 'Baleares', 'sa pobla': 'Baleares',
    'estellenchs': 'Baleares', 'estellencs': 'Baleares',
    'ses salines': 'Baleares', 'capdepera': 'Baleares', 'magaluf': 'Baleares',
    'porto cristo': 'Baleares', 'cala millor': 'Baleares',
    'san antonio': 'Baleares', 'sant antonio': 'Baleares',
    'santa eulalia': 'Baleares', 'santa eulàlia': 'Baleares',
    'ferrerias': 'Baleares', 'ferreries': 'Baleares', 'ciutadella': 'Baleares',
    'es mercadal': 'Baleares', 'mahon': 'Baleares', 'maó': 'Baleares',

    # C. Valenciana — municipios pequeños
    'oliva': 'C. Valenciana', 'vinaros': 'C. Valenciana', 'vinaròs': 'C. Valenciana',
    'parcent': 'C. Valenciana', 'jalon': 'C. Valenciana', 'jalón': 'C. Valenciana',
    'finestrat': 'C. Valenciana', 'alfaz del pi': 'C. Valenciana',
    'el campello': 'C. Valenciana', 'villajoyosa': 'C. Valenciana',
    'altea': 'C. Valenciana', 'calpe': 'C. Valenciana', 'calp': 'C. Valenciana',
    'denia': 'C. Valenciana', 'dénia': 'C. Valenciana',
    'jávea': 'C. Valenciana', 'javea': 'C. Valenciana',
    'benissa': 'C. Valenciana', 'bocairente': 'C. Valenciana', 'bocairent': 'C. Valenciana',
    'vall de gallinera': 'C. Valenciana', 'vall de ebo': 'C. Valenciana',
    'calig': 'C. Valenciana', 'lucena del cid': 'C. Valenciana',
    'ayora': 'C. Valenciana', 'cortes': 'C. Valenciana',
    'benidorm': 'C. Valenciana', 'santa pola': 'C. Valenciana',
    'torrevieja': 'C. Valenciana', 'playas de orihuela': 'C. Valenciana',
    'orihuela': 'C. Valenciana', 'gandía': 'C. Valenciana', 'gandia': 'C. Valenciana',
    'palomar': 'C. Valenciana', 'beniali': 'C. Valenciana',

    # Murcia
    'calabardina': 'Murcia', 'mazarrón': 'Murcia', 'mazarron': 'Murcia',
    'caravaca': 'Murcia', 'san javier': 'Murcia', 'santiago de la ribera': 'Murcia',
    'cartagena': 'Murcia', 'lorca': 'Murcia', 'águilas': 'Murcia',

    # Cataluña
    'vidreras': 'Cataluña', 'tordera': 'Cataluña', 'castillo de aro': 'Cataluña',
    'sant feliu de guixols': 'Cataluña', 'sant feliu': 'Cataluña',
    'platja d\'aro': 'Cataluña', 'platja daro': 'Cataluña',
    'santa coloma de gramenet': 'Cataluña', 'badalona': 'Cataluña',
    'mora la nueva': 'Cataluña', 'mora la nova': 'Cataluña',
    'segur de calafell': 'Cataluña', 'calafell': 'Cataluña',
    'roses': 'Cataluña', 'palamos': 'Cataluña', 'palamós': 'Cataluña',
    'creixell': 'Cataluña', 'lloret': 'Cataluña', 'sitges': 'Cataluña',
    'salou': 'Cataluña', 'cambrils': 'Cataluña', 'amposta': 'Cataluña',
    'vidreres': 'Cataluña',

    # Galicia
    'a guarda': 'Galicia', 'a guarda': 'Galicia', 'cuntis': 'Galicia',
    'moana': 'Galicia', 'tomino': 'Galicia', 'tomiño': 'Galicia',
    'ribadeo': 'Galicia', 'baiona': 'Galicia', 'bayona': 'Galicia',
    'cambados': 'Galicia', 'sanxenxo': 'Galicia',

    # Asturias
    'cangas de onís': 'Asturias', 'cangas de onis': 'Asturias',
    'coaña': 'Asturias', 'llanes': 'Asturias', 'ribadesella': 'Asturias',

    # Canarias
    'adeje': 'Canarias', 'mogán': 'Canarias', 'mogan': 'Canarias',
    'mácher': 'Canarias', 'macher': 'Canarias',
    'arona': 'Canarias', 'granadilla': 'Canarias',

    # Aragón
    'jaca': 'Aragón', 'benasque': 'Aragón', 'ainsa': 'Aragón',

    # Castilla y León
    'burgos city': 'Castilla y León',

    # Variantes en inglés / mayúsculas de regiones completas
    'andalusia': 'Andalucía', 'andalucia': 'Andalucía', 'andalucía': 'Andalucía',
    'galicia': 'Galicia', 'catalonia': 'Cataluña', 'cataluña': 'Cataluña',
    'costa blanca': 'C. Valenciana', 'costa brava': 'Cataluña',
    'costa del sol': 'Andalucía', 'costa dorada': 'Cataluña',
    'costa de la luz': 'Andalucía',
    'islas baleares': 'Baleares', 'illes balears': 'Baleares',
    'islas canarias': 'Canarias', 'canary islands': 'Canarias',
    'balearic islands': 'Baleares',
}

def clean_location_aggressive(loc):
    """Limpieza agresiva de ubicaciones con basura pegada."""
    if not loc: return loc
    # Quitar todo desde "with", "garage", " - €", precio
    loc = re.sub(r'\s+with\b.*', '', loc, flags=re.I)
    loc = re.sub(r'\bgarage\b.*', '', loc, flags=re.I)
    loc = re.sub(r'\bpool\b.*', '', loc, flags=re.I)
    loc = re.sub(r'\s*-\s*(?:â|€|£|\d).*', '', loc)
    loc = re.sub(r'â[\x82¬¬\x80-\xff].*', '', loc)
    loc = re.sub(r'€.*', '', loc)
    # "Ciudad / Otra ciudad" → quedarse con la primera
    m = re.match(r'([A-Za-záéíóúñüÁÉÍÓÚÑÜ][^/]{2,30}?)\s*/\s*.+', loc)
    if m: loc = m.group(1).strip()
    # "Madrid city" → "Madrid"
    loc = re.sub(r'\bcity\b', '', loc, flags=re.I).strip()
    # Quitar comas y texto tras provincia conocida: "Málaga, Andalucía" → "Málaga"
    # (mantenemos la ciudad, la región la inferimos)
    m2 = re.match(r'([^,]{3,30}),\s*.+', loc)
    if m2: loc = m2.group(1).strip()
    return loc.strip()

def infer_region_v2(text):
    """Busca región en texto usando mapa ampliado."""
    if not text: return None
    t = text.lower().strip()
    # Primero buscar en mapa extra (municipios pequeños)
    for key in sorted(EXTRA_MAP.keys(), key=len, reverse=True):
        if key in t:
            return EXTRA_MAP[key]
    return None

def main():
    if not os.path.exists(CACHE_FILE):
        print(f'ERROR: No se encuentra {CACHE_FILE}')
        return

    with open(CACHE_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)

    print(f'Cache: {len(data)} hoteles')
    antes = sum(1 for x in data if x.get('location_region'))
    print(f'Región antes: {antes} ({100*antes//len(data)}%)\n')

    fixed_loc = 0
    fixed_region = 0

    for item in data:
        # 1. Limpiar ubicación si aún tiene basura
        old_loc = item.get('location', '')
        new_loc = clean_location_aggressive(old_loc)
        if new_loc and new_loc != old_loc:
            item['location'] = new_loc
            fixed_loc += 1

        # 2. Añadir región si falta
        if not item.get('location_region'):
            texts = [
                item.get('location', ''),
                item.get('location_city', ''),
                item.get('title', ''),
                item.get('description', '')[:300],
            ]
            for t in texts:
                region = infer_region_v2(t)
                if region:
                    item['location_region'] = region
                    fixed_region += 1
                    break

    despues = sum(1 for x in data if x.get('location_region'))
    print(f'Ubicaciones limpias adicionales: +{fixed_loc}')
    print(f'Regiones nuevas añadidas:        +{fixed_region}')
    print(f'Región después: {despues} ({100*despues//len(data)}%)\n')

    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f'Cache guardado ✅')

    # Ver lo que queda sin región
    sin = [x for x in data if not x.get('location_region')]
    locs_sin = {}
    for x in sin:
        loc = x.get('location', '')
        if loc and loc not in ('España', 'Espana', ''):
            locs_sin[loc] = locs_sin.get(loc, 0) + 1
    if locs_sin:
        top = sorted(locs_sin.items(), key=lambda x: -x[1])[:15]
        print(f'\nAún sin región ({len(sin)} hoteles) — top:')
        for loc, cnt in top:
            print(f'  {cnt:3d}x  {loc}')

if __name__ == '__main__':
    main()
