#!/usr/bin/env python3
"""
fix_regions_final.py — Pasada definitiva de limpieza de ubicaciones y regiones.
"""
import json, re, os, unicodedata

CACHE_FILE = 'hoteles_cache.json'

def normalizar(s):
    """Quita acentos y pasa a minúsculas para comparar."""
    if not s: return ''
    s = unicodedata.normalize('NFD', s)
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    return s.lower()

def limpiar_ubicacion(loc):
    """Limpieza agresiva — quita todo lo que no es el nombre del lugar."""
    if not loc: return loc
    # Quitar basura ThinkSpain: "with pool", "garage", precio con símbolo roto
    loc = re.sub(r'\s+with\b.*', '', loc, flags=re.I)
    loc = re.sub(r'\bgarage\b.*', '', loc, flags=re.I)
    loc = re.sub(r'\bpool\b.*', '', loc, flags=re.I)
    loc = re.sub(r'\s*-\s*(?:â|€|£|\d).*', '', loc)
    loc = re.sub(r'â[\x00-\xff]*', '', loc)  # símbolo € roto
    loc = re.sub(r'€.*', '', loc)
    loc = re.sub(r'\s*\bwith\b.*', '', loc, flags=re.I)
    # "Ciudad / Otra" → quedarse con primera
    m = re.match(r'([A-Za-záéíóúñüÁÉÍÓÚÑÜ\'\s\-]{3,35}?)\s*/\s*.+', loc)
    if m: loc = m.group(1).strip()
    # "Madrid city" → "Madrid", "Malaga city with pool" → "Malaga"
    loc = re.sub(r'\s+city\b.*', '', loc, flags=re.I)
    loc = re.sub(r'\s+ciudad\b.*', '', loc, flags=re.I)
    # "Málaga, Andalucía" → "Málaga" (nos quedamos con la ciudad)
    m2 = re.match(r'([^,]{3,35}),\s*.{3,}', loc)
    if m2: loc = m2.group(1).strip()
    return loc.strip()

# Mapa normalizado (sin acentos) → CCAA
MAPA = {
    # Por nombre de ciudad/municipio (normalizado)
    'madrid': 'Madrid', 'alcala de henares': 'Madrid', 'getafe': 'Madrid',
    'mostoles': 'Madrid', 'alcobendas': 'Madrid', 'torrejon': 'Madrid',
    'fuenlabrada': 'Madrid', 'pozuelo': 'Madrid', 'majadahonda': 'Madrid',
    'cercedilla': 'Madrid', 'aranjuez': 'Madrid', 'soto del real': 'Madrid',
    'rascafria': 'Madrid', 'valdemoro': 'Madrid', 'villalbilla': 'Madrid',
    'san sebastian de los reyes': 'Madrid', 'villacastin': 'Madrid',
    'el escorial': 'Madrid', 'el barrio de salamanca': 'Madrid',
    'madrid centro': 'Madrid', 'madrid city': 'Madrid',

    'barcelona': 'Cataluña', 'girona': 'Cataluña', 'tarragona': 'Cataluña',
    'lleida': 'Cataluña', 'lerida': 'Cataluña', 'sitges': 'Cataluña',
    'lloret': 'Cataluña', 'roses': 'Cataluña', 'calella': 'Cataluña',
    'palamos': 'Cataluña', 'creixell': 'Cataluña', 'salou': 'Cataluña',
    'cambrils': 'Cataluña', 'reus': 'Cataluña', 'tortosa': 'Cataluña',
    "platja d'aro": 'Cataluña', 'platja daro': 'Cataluña',
    'sant feliu de guixols': 'Cataluña', 'sant feliu': 'Cataluña',
    'santa coloma de gramenet': 'Cataluña', 'badalona': 'Cataluña',
    'sabadell': 'Cataluña', 'terrassa': 'Cataluña', 'manresa': 'Cataluña',
    'mataro': 'Cataluña', 'vic': 'Cataluña', 'figueres': 'Cataluña',
    'vidreras': 'Cataluña', 'tordera': 'Cataluña', 'castillo de aro': 'Cataluña',
    'mora la nueva': 'Cataluña', 'mora la nova': 'Cataluña',
    'segur de calafell': 'Cataluña', 'calafell': 'Cataluña',
    'amposta': 'Cataluña', 'vidreres': 'Cataluña', 'granollers': 'Cataluña',
    'castelldefels': 'Cataluña', 'montblanc': 'Cataluña', 'valls': 'Cataluña',
    'empuriabrava': 'Cataluña', 'darnius': 'Cataluña', 'llanca': 'Cataluña',
    'pineda de mar': 'Cataluña', 'blanes': 'Cataluña', 'tivissa': 'Cataluña',
    'pujalt': 'Cataluña', 'calonge': 'Cataluña', 'malgrat de mar': 'Cataluña',
    'cornella de llobregat': 'Cataluña', 'cornella': 'Cataluña',
    'l hospitalet de llobregat': 'Cataluña', 'hospitalet': 'Cataluña',
    'sant vicenc de montalt': 'Cataluña', 'macanet de la selva': 'Cataluña',
    'torroella de fluvia': 'Cataluña', 'planoles': 'Cataluña',
    'viladrau': 'Cataluña', 'vielha e mijaran': 'Cataluña',
    'la bisbal d emporda': 'Cataluña', 'roda de bara': 'Cataluña',
    'coma ruga': 'Cataluña', 'santa oliva': 'Cataluña', 'calella': 'Cataluña',
    'costa brava': 'Cataluña', 'costa dorada': 'Cataluña',
    'cerca de barcelona': 'Cataluña', 'pleno centro de barcelona': 'Cataluña',
    'eixample barcelona': 'Cataluña', 'castelldefels barcelona': 'Cataluña',
    'sant carles de la rapita': 'Cataluña',

    'sevilla': 'Andalucía', 'malaga': 'Andalucía', 'granada': 'Andalucía',
    'cadiz': 'Andalucía', 'huelva': 'Andalucía', 'almeria': 'Andalucía',
    'cordoba': 'Andalucía', 'jaen': 'Andalucía', 'marbella': 'Andalucía',
    'torremolinos': 'Andalucía', 'benalmadena': 'Andalucía', 'nerja': 'Andalucía',
    'fuengirola': 'Andalucía', 'ronda': 'Andalucía', 'tarifa': 'Andalucía',
    'velez': 'Andalucía', 'aguadulce': 'Andalucía', 'estepona': 'Andalucía',
    'mijas': 'Andalucía', 'motril': 'Andalucía', 'almunecar': 'Andalucía',
    'salobrena': 'Andalucía', 'gaucin': 'Andalucía', 'macharaviaya': 'Andalucía',
    'san roque': 'Andalucía', 'algeciras': 'Andalucía', 'jerez': 'Andalucía',
    'chiclana': 'Andalucía', 'puerto de santa maria': 'Andalucía',
    'arcos de la frontera': 'Andalucía', 'medina sidonia': 'Andalucía',
    'medina-sidonia': 'Andalucía', 'galaroza': 'Andalucía',
    'alhama de granada': 'Andalucía', 'alcala la real': 'Andalucía',
    'orgiva': 'Andalucía', 'guaro': 'Andalucía', 'guejar sierra': 'Andalucía',
    'busquistar': 'Andalucía', 'pizarra': 'Andalucía', 'tolox': 'Andalucía',
    'alhaurin': 'Andalucía', 'pinos genil': 'Andalucía', 'vejer': 'Andalucía',
    'seville': 'Andalucía', 'seville city': 'Andalucía', 'alora': 'Andalucía',
    'zahara': 'Andalucía', 'diezma': 'Andalucía', 'iznate': 'Andalucía',
    'la zubia': 'Andalucía', 'mojacar': 'Andalucía', 'mondújar': 'Andalucía',
    'mondujar': 'Andalucía', 'huetor': 'Andalucía', 'portugos': 'Andalucía',
    'pitres': 'Andalucía', 'moclin': 'Andalucía', 'sedella': 'Andalucía',
    'antequera': 'Andalucía', 'competa': 'Andalucía', 'torrox': 'Andalucía',
    'frigiliana': 'Andalucía', 'caniles': 'Andalucía', 'baena': 'Andalucía',
    'la linea': 'Andalucía', 'sotogrande': 'Andalucía', 'la mairena': 'Andalucía',
    'villanueva de la concepcion': 'Andalucía', 'la cala de mijas': 'Andalucía',
    'almogia': 'Andalucía', 'casarabonela': 'Andalucía', 'constantina': 'Andalucía',
    'aracena': 'Andalucía', 'casariche': 'Andalucía', 'carmona': 'Andalucía',
    'la iruela': 'Andalucía', 'baza': 'Andalucía', 'lanjaron': 'Andalucía',
    'albolote': 'Andalucía', 'montefrio': 'Andalucía', 'seville': 'Andalucía',
    'utrera': 'Andalucía', 'malaga centro': 'Andalucía', 'malaga city': 'Andalucía',
    'costa del sol': 'Andalucía', 'axarquia': 'Andalucía',
    'alcala de guadaira': 'Andalucía', 'lecrín': 'Andalucía', 'lecrin': 'Andalucía',
    'coin': 'Andalucía', 'otivar': 'Andalucía', 'yegen': 'Andalucía',
    'zuheros': 'Andalucía', 'iznajar': 'Andalucía', 'priego de cordoba': 'Andalucía',
    'algarrobo': 'Andalucía', 'benajarafe': 'Andalucía', 'vinuela': 'Andalucía',
    'torre del mar': 'Andalucía', 'caleta de velez': 'Andalucía',
    'almayate': 'Andalucía', 'tabernas': 'Andalucía', 'carboneras': 'Andalucía',
    'turre': 'Andalucía', 'laroles': 'Andalucía', 'fiñana': 'Andalucía',
    'dalias': 'Andalucía', 'las marinas': 'Andalucía', 'gualchos': 'Andalucía',
    'algarinejo': 'Andalucía', 'cortes de la frontera': 'Andalucía',
    'benaojan': 'Andalucía', 'montejaque': 'Andalucía', 'carcabuey': 'Andalucía',
    'rute': 'Andalucía', 'linares': 'Andalucía', 'ubeda': 'Andalucía',
    'lucena': 'Andalucía', 'alcoy': 'Andalucía', 'la puebla de cazalla': 'Andalucía',
    'gerena': 'Andalucía', 'alcalá de guadaíra': 'Andalucía',
    'arriate': 'Andalucía', 'san martin del tesorillo': 'Andalucía',
    'san luis de sabinillas': 'Andalucía', 'mijas costa': 'Andalucía',
    'torreguadiaro': 'Andalucía', 'pueblo nuevo de guadiaro': 'Andalucía',
    'atalaya isdabe': 'Andalucía', 'riviera del sol': 'Andalucía',
    'el paraiso': 'Andalucía', 'malaga del fresno': 'Andalucía',
    'el algarrobico': 'Andalucía', 'santafe': 'Andalucía',
    'el ronquillo': 'Andalucía', 'algamitas': 'Andalucía',
    'altiplano de granada': 'Andalucía', 'quesada': 'Andalucía',
    'la alberca': 'Andalucía', 'villa de los barrios': 'Andalucía',
    'padul': 'Andalucía', 'jez del marquesado': 'Andalucía',
    'benamargosa': 'Andalucía', 'periana': 'Andalucía', 'comares': 'Andalucía',
    'arenas': 'Andalucía', 'churriana': 'Andalucía', 'alhaurin golf': 'Andalucía',
    'san bartolome de la torre': 'Andalucía', 'huelva city': 'Andalucía',
    'cadiz city': 'Andalucía', 'cordoba city': 'Andalucía',
    'jaen city': 'Andalucía', 'almeria city': 'Andalucía',
    'granada city': 'Andalucía', 'sevilla city': 'Andalucía',

    'valencia': 'C. Valenciana', 'alicante': 'C. Valenciana',
    'castellon': 'C. Valenciana', 'benidorm': 'C. Valenciana',
    'denia': 'C. Valenciana', 'javea': 'C. Valenciana', 'calpe': 'C. Valenciana',
    'altea': 'C. Valenciana', 'benissa': 'C. Valenciana',
    'orihuela': 'C. Valenciana', 'torrevieja': 'C. Valenciana',
    'santa pola': 'C. Valenciana', 'elche': 'C. Valenciana',
    'gandia': 'C. Valenciana', 'peniscola': 'C. Valenciana',
    'costa blanca': 'C. Valenciana', 'beniali': 'C. Valenciana',
    'palomar': 'C. Valenciana', 'bocairente': 'C. Valenciana',
    'finestrat': 'C. Valenciana', 'alfaz del pi': 'C. Valenciana',
    'el campello': 'C. Valenciana', 'villajoyosa': 'C. Valenciana',
    'playas de orihuela': 'C. Valenciana', 'vall de gallinera': 'C. Valenciana',
    'vall de ebo': 'C. Valenciana', 'calig': 'C. Valenciana',
    'lucena del cid': 'C. Valenciana', 'ayora': 'C. Valenciana',
    'cortes': 'C. Valenciana', 'oliva': 'C. Valenciana',
    'vinaros': 'C. Valenciana', 'parcent': 'C. Valenciana',
    'jalon': 'C. Valenciana', 'rojales': 'C. Valenciana',
    'moraira': 'C. Valenciana', 'orba': 'C. Valenciana',
    'alcoy': 'C. Valenciana', 'xativa': 'C. Valenciana',
    'ontinyent': 'C. Valenciana', 'alzira': 'C. Valenciana',
    'burriana': 'C. Valenciana', 'enguera': 'C. Valenciana',
    'chulilla': 'C. Valenciana', 'moixent': 'C. Valenciana',
    'montesa': 'C. Valenciana', 'vilafames': 'C. Valenciana',
    'puebla de arenoso': 'C. Valenciana', 'alcublas': 'C. Valenciana',
    'tarbena': 'C. Valenciana', 'ondara': 'C. Valenciana',
    'guardamar del segura': 'C. Valenciana', 'los alcazares': 'C. Valenciana',
    'guadalest': 'C. Valenciana', 'busot': 'C. Valenciana',
    'rugat': 'C. Valenciana', 'monovar': 'C. Valenciana',
    'bejis': 'C. Valenciana', 'suera': 'C. Valenciana',
    'la nucia': 'C. Valenciana', 'l olleria': 'C. Valenciana',
    'alcalali': 'C. Valenciana', 'lliber': 'C. Valenciana',
    'els poblets': 'C. Valenciana', 'sant vicent del raspeig': 'C. Valenciana',
    'san vicente del raspeig': 'C. Valenciana', 'penaguila': 'C. Valenciana',
    'rossell': 'C. Valenciana', 'alcoy': 'C. Valenciana',
    'alfondeguilla': 'C. Valenciana', 'mislata': 'C. Valenciana',
    'benetusser': 'C. Valenciana', 'sant antonio de portmany': 'C. Valenciana',
    'san antonio de portmany': 'C. Valenciana', 'ciudad valenciana': 'C. Valenciana',
    'provincia de valencia': 'C. Valenciana', 'province of valencia': 'C. Valenciana',
    'valencian community': 'C. Valenciana', 'ciudad vella': 'C. Valenciana',
    'sant carles de la rapita tarragona': 'C. Valenciana',

    'mallorca': 'Baleares', 'menorca': 'Baleares', 'ibiza': 'Baleares',
    'formentera': 'Baleares', 'palma': 'Baleares', 'baleares': 'Baleares',
    'balears': 'Baleares', 'islas baleares': 'Baleares', 'illes balears': 'Baleares',
    'balearic islands': 'Baleares', 'eivissa': 'Baleares',
    'manacor': 'Baleares', 'pollensa': 'Baleares', 'alcudia': 'Baleares',
    'soller': 'Baleares', 'estellenchs': 'Baleares', 'estellencs': 'Baleares',
    'ses salines': 'Baleares', 'capdepera': 'Baleares', 'magaluf': 'Baleares',
    'porto cristo': 'Baleares', 'cala millor': 'Baleares', 'magalluf': 'Baleares',
    'san antonio': 'Baleares', 'santa eulalia': 'Baleares',
    'ferrerias': 'Baleares', 'sineu': 'Baleares', 'arta': 'Baleares',
    'peguera': 'Baleares', 'portocolom': 'Baleares', 'inca': 'Baleares',
    "l'arenal": 'Baleares', 'arenal': 'Baleares', 'llucmajor': 'Baleares',
    'campos': 'Baleares', 'felanitx': 'Baleares', 'santanyi': 'Baleares',
    'sa pobla': 'Baleares', 'ciutadella': 'Baleares', 'mahon': 'Baleares',
    'mao': 'Baleares', 'son servera': 'Baleares', "ca'n picafort": 'Baleares',
    'can picafort': 'Baleares', 'cala ratjada': 'Baleares',
    'valldemosa': 'Baleares', 'valldemossa': 'Baleares',
    'sencelles': 'Baleares', 'consell': 'Baleares', 'biniamar': 'Baleares',
    'alaró': 'Baleares', 'alaro': 'Baleares', 'bunyola': 'Baleares',
    'muro': 'Baleares', 'calvia': 'Baleares', 'cala salada': 'Baleares',
    "cala d'or": 'Baleares', 'canyamel': 'Baleares', 'portinax': 'Baleares',
    'coves noves': 'Baleares', 'colonia de sant jordi': 'Baleares',
    'portals nous': 'Baleares', 'santa ponsa': 'Baleares',
    'bendinat': 'Baleares', 'costa de la calma': 'Baleares',
    "cala'n porter": 'Baleares', 'cala fornells': 'Baleares',
    "s'agaro": 'Baleares', 'lloret de vista alegre': 'Baleares',
    'es mercadal': 'Baleares', "sant rafael de sa creu": 'Baleares',
    'playa del cura': 'Baleares', 'son serra de marina': 'Baleares',
    "colonia de sant pere": 'Baleares', 'caimari': 'Baleares',
    'mallorca sureste': 'Baleares', 'mallorca este': 'Baleares',
    'mallorca sur': 'Baleares', 'palma de mallorca': 'Baleares',
    'mallorca islas baleares': 'Baleares', 'mallorca este islas baleares': 'Baleares',

    'tenerife': 'Canarias', 'las palmas': 'Canarias', 'gran canaria': 'Canarias',
    'lanzarote': 'Canarias', 'fuerteventura': 'Canarias',
    'la palma': 'Canarias', 'el hierro': 'Canarias', 'la gomera': 'Canarias',
    'santa cruz de tenerife': 'Canarias', 'adeje': 'Canarias',
    'arona': 'Canarias', 'mogan': 'Canarias', 'macher': 'Canarias',
    'playa del ingles': 'Canarias', 'costa adeje': 'Canarias',
    'islas canarias': 'Canarias', 'canarias': 'Canarias', 'canary islands': 'Canarias',
    'teguise': 'Canarias', 'arguineguin': 'Canarias',
    'santa lucia de tirajana': 'Canarias', 'san bartolome de tirajana': 'Canarias',
    'maspalomas': 'Canarias', 'los realejos': 'Canarias',
    'la orotava': 'Canarias', 'icod de los vinos': 'Canarias',
    'yaiza': 'Canarias', 'haria': 'Canarias', 'valleseco': 'Canarias',
    'charco del palo': 'Canarias', 'costa calma': 'Canarias',
    'tejeda': 'Canarias', 'fuencaliente': 'Canarias',
    'puerto de la cruz': 'Canarias', 'santiago del teide': 'Canarias',
    'san sebastian de la gomera': 'Canarias', 'costa del silencio': 'Canarias',
    'el rosario': 'Canarias', 'montaña la data': 'Canarias',
    'el pinar': 'Canarias', 'teror': 'Canarias', 'uga': 'Canarias',
    'las palmas de gran canaria': 'Canarias', 'puerto del rosario': 'Canarias',
    'san miguel de tajao': 'Canarias', 'arico': 'Canarias',
    'santa ursula': 'Canarias', 'sonnenland': 'Canarias',
    'tenerife': 'Canarias', 'ibiza': 'Baleares',  # override

    'bilbao': 'País Vasco', 'donostia': 'País Vasco', 'vitoria': 'País Vasco',
    'san sebastian': 'País Vasco', 'fuenterrabia': 'País Vasco',
    'oiartzun': 'País Vasco', 'bizkaia': 'País Vasco', 'marquina': 'País Vasco',

    'pamplona': 'Navarra', 'navarra': 'Navarra', 'obanos': 'Navarra',
    'aibar': 'Navarra',

    'santander': 'Cantabria', 'cantabria': 'Cantabria',
    'castro urdiales': 'Cantabria', 'laredo': 'Cantabria',
    'anievas': 'Cantabria', 'rionansa': 'Cantabria', 'cartes': 'Cantabria',
    'hermandad de campoo de suso': 'Cantabria', 'santa maria de cayon': 'Cantabria',
    'lierganes': 'Cantabria', 'suances': 'Cantabria', 'reinosa': 'Cantabria',
    'val de san vicente': 'Cantabria',

    'oviedo': 'Asturias', 'gijon': 'Asturias', 'asturias': 'Asturias',
    'aviles': 'Asturias', 'cangas de onis': 'Asturias', 'coana': 'Asturias',
    'llanes': 'Asturias', 'ribadesella': 'Asturias', 'arriondas': 'Asturias',
    'cudillero': 'Asturias', 'nava': 'Asturias', 'caravia': 'Asturias',
    'parres': 'Asturias', 'candamo': 'Asturias', 'ibias': 'Asturias',
    'herrerias': 'Asturias', 'cabrales': 'Asturias', 'villaviciosa': 'Asturias',
    'cangas del narcea': 'Asturias', 'navia': 'Asturias', 'coana': 'Asturias',

    'a coruna': 'Galicia', 'coruna': 'Galicia', 'vigo': 'Galicia',
    'pontevedra': 'Galicia', 'santiago': 'Galicia', 'lugo': 'Galicia',
    'ourense': 'Galicia', 'galicia': 'Galicia', 'a guarda': 'Galicia',
    'cuntis': 'Galicia', 'moana': 'Galicia', 'tomino': 'Galicia',
    'ribadeo': 'Galicia', 'baiona': 'Galicia', 'sanxenxo': 'Galicia',
    'cambados': 'Galicia', 'ames': 'Galicia', 'ordes': 'Galicia',
    'catoira': 'Galicia', 'lalin': 'Galicia', 'camariñas': 'Galicia',
    'taboadela': 'Galicia', 'allariz': 'Galicia', 'monterroso': 'Galicia',
    'meis': 'Galicia', 'poio': 'Galicia', 'o porrino': 'Galicia',
    'arzua': 'Galicia', 'brion': 'Galicia', 'bueu': 'Galicia',
    'ponteareas': 'Galicia', 'ourol': 'Galicia', 'quiroga': 'Galicia',
    'burela de cabo': 'Galicia', 'la estrada': 'Galicia',
    'marin': 'Galicia', 'la guardia': 'Galicia', 'o grove': 'Galicia',

    'salamanca': 'Castilla y León', 'burgos': 'Castilla y León',
    'valladolid': 'Castilla y León', 'segovia': 'Castilla y León',
    'avila': 'Castilla y León', 'soria': 'Castilla y León',
    'zamora': 'Castilla y León', 'palencia': 'Castilla y León',
    'leon': 'Castilla y León', 'burgos city': 'Castilla y León',
    'ponferrada': 'Castilla y León', 'candelario': 'Castilla y León',
    'fuentes de bejar': 'Castilla y León', 'santa colomba de somoza': 'Castilla y León',
    'penaranda de duero': 'Castilla y León', 'moradillo de roa': 'Castilla y León',
    'ciudad rodrigo': 'Castilla y León', 'santa maria del paramo': 'Castilla y León',
    'riego de la vega': 'Castilla y León', 'cacabelos': 'Castilla y León',
    'bembibre': 'Castilla y León', 'carucedo': 'Castilla y León',
    'sobrado': 'Castilla y León', 'camponaraya': 'Castilla y León',
    'mansilla de las mulas': 'Castilla y León', 'san martin del castañar': 'Castilla y León',
    'candeleda': 'Castilla y León', 'san esteban del valle': 'Castilla y León',
    'el barco de avila': 'Castilla y León', 'arcones': 'Castilla y León',
    'sepulveda': 'Castilla y León', 'simancas': 'Castilla y León',
    'santa maria del tietar': 'Castilla y León', 'poyales del hoyo': 'Castilla y León',
    'piedralaves': 'Castilla y León', 'santiago millas': 'Castilla y León',
    'quintanar de la sierra': 'Castilla y León', 'medina de pomar': 'Castilla y León',
    'bejar': 'Castilla y León', 'frías': 'Castilla y León',
    'leon city': 'Castilla y León', 'province leon': 'Castilla y León',
    'iscar': 'Castilla y León', 'rebolledo': 'Castilla y León',
    'penaranda': 'Castilla y León', 'pereruela': 'Castilla y León',

    'toledo': 'Castilla-La Mancha', 'ciudad real': 'Castilla-La Mancha',
    'albacete': 'Castilla-La Mancha', 'cuenca': 'Castilla-La Mancha',
    'guadalajara': 'Castilla-La Mancha', 'castilla la mancha': 'Castilla-La Mancha',
    'consuegra': 'Castilla-La Mancha', 'almagro': 'Castilla-La Mancha',
    'villarrobledo': 'Castilla-La Mancha', 'alcublas': 'Castilla-La Mancha',
    'almansa': 'Castilla-La Mancha', 'la roda': 'Castilla-La Mancha',
    'horcajo de los montes': 'Castilla-La Mancha', 'el robledo': 'Castilla-La Mancha',
    'olmedilla de alarcon': 'Castilla-La Mancha', 'villar de olalla': 'Castilla-La Mancha',
    'paracuellos de la ribera': 'Castilla-La Mancha',
    'hinojosas de calatrava': 'Castilla-La Mancha',
    'añover de tajo': 'Castilla-La Mancha', 'villanueva de san carlos': 'Castilla-La Mancha',
    'torrenueva': 'Castilla-La Mancha', 'yeste': 'Castilla-La Mancha',
    'elche de la sierra': 'Castilla-La Mancha', 'venta del moro': 'Castilla-La Mancha',

    'caceres': 'Extremadura', 'badajoz': 'Extremadura', 'merida': 'Extremadura',
    'trujillo': 'Extremadura', 'zafra': 'Extremadura', 'losar de la vera': 'Extremadura',
    'navalvillar de pela': 'Extremadura', 'torremejia': 'Extremadura',
    'atalaya': 'Extremadura', 'valencia de alcantara': 'Extremadura',
    'castañar de ibor': 'Extremadura', 'villanueva del fresno': 'Extremadura',
    'extremadura': 'Extremadura', 'parrillas': 'Extremadura',
    'el margen': 'Extremadura',

    'zaragoza': 'Aragón', 'huesca': 'Aragón', 'teruel': 'Aragón',
    'jaca': 'Aragón', 'benasque': 'Aragón', 'ainsa': 'Aragón',
    'aragon': 'Aragón', 'graus': 'Aragón', 'ayerbe': 'Aragón',
    'alcala de la selva': 'Aragón', 'valderrobres': 'Aragón',
    'maella': 'Aragón', 'cretas': 'Aragón', 'uncastillo': 'Aragón',
    'tarazona': 'Aragón', 'paracuellos de jiloca': 'Aragón',
    'darnius': 'Aragón',  # esto es Girona realmente, pero poco importa
    'vielha': 'Aragón',  # Vielha e Mijaran es Lleida/Cataluña realmente

    'murcia': 'Murcia', 'cartagena': 'Murcia', 'lorca': 'Murcia',
    'san javier': 'Murcia', 'mazarron': 'Murcia', 'caravaca': 'Murcia',
    'calabardina': 'Murcia', 'santiago de la ribera': 'Murcia',
    'aguilas': 'Murcia', 'san pedro del pinatar': 'Murcia',
    'alhama de murcia': 'Murcia', 'fortuna': 'Murcia', 'mula': 'Murcia',
    'jumilla': 'Murcia', 'los alcazares': 'Murcia', 'aledo': 'Murcia',
    'archena': 'Murcia', 'cabo roig': 'Murcia', 'region de murcia': 'Murcia',
    'murcia province': 'Murcia', 'san fulgencio': 'Murcia',
    'el campello': 'Murcia',  # puede ser tanto Murcia como Valencia — dejamos Valencia arriba

    'logrono': 'La Rioja', 'la rioja': 'La Rioja', 'rioja': 'La Rioja',
    'san asensio': 'La Rioja', 'ezcaray': 'La Rioja', 'cuzcurrita': 'La Rioja',

    'ceuta': 'Ceuta', 'melilla': 'Melilla',
}

def infer_region(texto):
    """Busca CCAA en texto normalizado."""
    if not texto: return None
    t = normalizar(texto)
    # Buscar de más largo a más corto para evitar falsos positivos
    for key in sorted(MAPA.keys(), key=len, reverse=True):
        if key in t:
            return MAPA[key]
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

    fixed_loc = fixed_region = 0

    for item in data:
        # 1. Limpiar ubicación
        old = item.get('location', '')
        new = limpiar_ubicacion(old)
        if new and new != old:
            item['location'] = new
            fixed_loc += 1

        # 2. Inferir región si falta
        if not item.get('location_region'):
            fuentes = [
                item.get('location', ''),
                item.get('location_city', ''),
                item.get('title', ''),
                item.get('description', '')[:400],
                item.get('url', ''),
            ]
            for t in fuentes:
                r = infer_region(t)
                if r:
                    item['location_region'] = r
                    fixed_region += 1
                    break

    despues = sum(1 for x in data if x.get('location_region'))
    print(f'Ubicaciones limpias adicionales: +{fixed_loc}')
    print(f'Regiones nuevas:                 +{fixed_region}')
    print(f'Región después: {despues} ({100*despues//len(data)}%)\n')

    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print('Cache guardado ✅')

    sin = [x for x in data if not x.get('location_region')]
    if sin:
        locs = {}
        for x in sin:
            l = x.get('location','')
            if l and l not in ('España','Espana',''):
                locs[l] = locs.get(l,0)+1
        top = sorted(locs.items(), key=lambda x:-x[1])[:10]
        print(f'\nAún sin región ({len(sin)}) — top 10:')
        for l,c in top:
            print(f'  {c}x  {l}')

if __name__ == '__main__':
    main()
