#!/usr/bin/env python3
"""
fix_all.py — Limpieza definitiva y completa del cache.
Limpia ubicaciones sucias y asigna región a todos los hoteles posibles.
"""
import json, re, os, unicodedata

CACHE_FILE = 'hoteles_cache.json'

def norm(s):
    """Normaliza texto: sin acentos, minúsculas, sin símbolos raros."""
    if not s: return ''
    s = unicodedata.normalize('NFD', s)
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    s = s.lower()
    s = re.sub(r'[^\w\s,./]', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()

def limpiar(loc):
    """Quita toda la basura que va pegada a la ciudad."""
    if not loc: return ''
    # Símbolo € roto (â¬, â\x82¬, etc.)
    loc = re.sub(r'â[\x00-\xff]{0,2}', '', loc)
    loc = re.sub(r'€.*', '', loc)
    # Todo desde "with", "garage", "pool", " - precio"
    loc = re.sub(r'\s+with\b.*', '', loc, flags=re.I)
    loc = re.sub(r'\bgarage\b.*', '', loc, flags=re.I)
    loc = re.sub(r'\bpool\b.*', '', loc, flags=re.I)
    loc = re.sub(r'\s*-\s*\d.*', '', loc)
    # "Ciudad / Otra" o "Ciudad city" → quedarse con primera parte
    loc = re.sub(r'\s*/\s*.+', '', loc)
    loc = re.sub(r'\s+city\b.*', '', loc, flags=re.I)
    # "Málaga, Andalucía" → "Málaga"
    m = re.match(r'([^,]{3,40}),\s*.{4,}', loc)
    if m: loc = m.group(1)
    return loc.strip()

# Mapa completo normalizado → CCAA
# Clave: texto normalizado (sin acentos, minúsculas)
# Valor: nombre oficial CCAA
MAPA = {k: v for k, v in [
    # Madrid
    ('madrid', 'Madrid'), ('alcala de henares', 'Madrid'), ('getafe', 'Madrid'),
    ('mostoles', 'Madrid'), ('alcobendas', 'Madrid'), ('torrejon', 'Madrid'),
    ('fuenlabrada', 'Madrid'), ('pozuelo', 'Madrid'), ('majadahonda', 'Madrid'),
    ('cercedilla', 'Madrid'), ('aranjuez', 'Madrid'), ('soto del real', 'Madrid'),
    ('rascafria', 'Madrid'), ('valdemoro', 'Madrid'), ('villalbilla', 'Madrid'),
    ('san sebastian de los reyes', 'Madrid'), ('el escorial', 'Madrid'),
    ('villanueva de san carlos', 'Madrid'), ('guadarrama', 'Madrid'),
    ('belmonte de tajo', 'Madrid'), ('anover de tajo', 'Madrid'),
    ('villalbilla', 'Madrid'), ('parets del valles', 'Madrid'),
    ('santa perpetua de mogoda', 'Madrid'), ('iscar', 'Madrid'),
    ('simancas', 'Madrid'), ('el alamo', 'Madrid'), ('villacastin', 'Madrid'),
    ('arcones', 'Madrid'), ('navalvillar de pela', 'Madrid'),

    # Cataluña
    ('barcelona', 'Cataluña'), ('girona', 'Cataluña'), ('tarragona', 'Cataluña'),
    ('lleida', 'Cataluña'), ('lerida', 'Cataluña'), ('sitges', 'Cataluña'),
    ('lloret', 'Cataluña'), ('roses', 'Cataluña'), ('calella', 'Cataluña'),
    ('palamos', 'Cataluña'), ('creixell', 'Cataluña'), ('salou', 'Cataluña'),
    ('cambrils', 'Cataluña'), ('reus', 'Cataluña'), ('tortosa', 'Cataluña'),
    ("platja d'aro", 'Cataluña'), ('platja daro', 'Cataluña'),
    ('sant feliu de guixols', 'Cataluña'), ('sant feliu', 'Cataluña'),
    ('santa coloma de gramenet', 'Cataluña'), ('badalona', 'Cataluña'),
    ('sabadell', 'Cataluña'), ('terrassa', 'Cataluña'), ('manresa', 'Cataluña'),
    ('mataro', 'Cataluña'), ('vic', 'Cataluña'), ('figueres', 'Cataluña'),
    ('vidreres', 'Cataluña'), ('tordera', 'Cataluña'), ('castillo de aro', 'Cataluña'),
    ('mora la nueva', 'Cataluña'), ('mora la nova', 'Cataluña'),
    ('segur de calafell', 'Cataluña'), ('calafell', 'Cataluña'),
    ('empuriabrava', 'Cataluña'), ('llanca', 'Cataluña'), ('blanes', 'Cataluña'),
    ('tivissa', 'Cataluña'), ('pujalt', 'Cataluña'), ('malgrat de mar', 'Cataluña'),
    ('cornella de llobregat', 'Cataluña'), ('cornella', 'Cataluña'),
    ('l hospitalet de llobregat', 'Cataluña'), ('hospitalet', 'Cataluña'),
    ('sant vicenc de montalt', 'Cataluña'), ('macanet de la selva', 'Cataluña'),
    ('torroella', 'Cataluña'), ('planoles', 'Cataluña'), ('viladrau', 'Cataluña'),
    ('la bisbal d emporda', 'Cataluña'), ('roda de bara', 'Cataluña'),
    ('coma ruga', 'Cataluña'), ('costa brava', 'Cataluña'), ('costa dorada', 'Cataluña'),
    ('castelldefels', 'Cataluña'), ('montblanc', 'Cataluña'), ('amposta', 'Cataluña'),
    ('granollers', 'Cataluña'), ('pineda de mar', 'Cataluña'), ('darnius', 'Cataluña'),
    ('sant carles de la rapita', 'Cataluña'), ('calonge', 'Cataluña'),
    ('l ametlla de mar', 'Cataluña'), ('el vendrell', 'Cataluña'),
    ('bellver de cerdanya', 'Cataluña'), ('puigcerda', 'Cataluña'),
    ('llagostera', 'Cataluña'), ("platja d'aiguablava", 'Cataluña'),
    ('grifeu', 'Cataluña'), ('prenafeta', 'Cataluña'), ('el masnou', 'Cataluña'),
    ('botarell', 'Cataluña'), ('morell', 'Cataluña'), ('cataluña', 'Cataluña'),
    ('catalonia', 'Cataluña'), ('montblanch', 'Cataluña'),
    ('vielha e mijaran', 'Cataluña'), ('vielha', 'Cataluña'),
    ('la molina', 'Cataluña'), ('sant aniol de finestres', 'Cataluña'),
    ('masnou maresme', 'Cataluña'), ('gratallops', 'Cataluña'),

    # Andalucía
    ('sevilla', 'Andalucía'), ('malaga', 'Andalucía'), ('granada', 'Andalucía'),
    ('cadiz', 'Andalucía'), ('huelva', 'Andalucía'), ('almeria', 'Andalucía'),
    ('cordoba', 'Andalucía'), ('jaen', 'Andalucía'), ('marbella', 'Andalucía'),
    ('torremolinos', 'Andalucía'), ('benalmadena', 'Andalucía'), ('nerja', 'Andalucía'),
    ('fuengirola', 'Andalucía'), ('ronda', 'Andalucía'), ('tarifa', 'Andalucía'),
    ('velez', 'Andalucía'), ('aguadulce', 'Andalucía'), ('estepona', 'Andalucía'),
    ('mijas', 'Andalucía'), ('motril', 'Andalucía'), ('almunecar', 'Andalucía'),
    ('salobrena', 'Andalucía'), ('gaucin', 'Andalucía'), ('macharaviaya', 'Andalucía'),
    ('san roque', 'Andalucía'), ('algeciras', 'Andalucía'), ('jerez', 'Andalucía'),
    ('chiclana', 'Andalucía'), ('puerto de santa maria', 'Andalucía'),
    ('arcos de la frontera', 'Andalucía'), ('medina sidonia', 'Andalucía'),
    ('medina-sidonia', 'Andalucía'), ('galaroza', 'Andalucía'),
    ('alhama de granada', 'Andalucía'), ('alcala la real', 'Andalucía'),
    ('orgiva', 'Andalucía'), ('guaro', 'Andalucía'), ('guejar sierra', 'Andalucía'),
    ('busquistar', 'Andalucía'), ('pizarra', 'Andalucía'), ('tolox', 'Andalucía'),
    ('alhaurin', 'Andalucía'), ('pinos genil', 'Andalucía'), ('vejer', 'Andalucía'),
    ('seville', 'Andalucía'), ('alora', 'Andalucía'), ('zahara', 'Andalucía'),
    ('diezma', 'Andalucía'), ('iznate', 'Andalucía'), ('la zubia', 'Andalucía'),
    ('mojacar', 'Andalucía'), ('mondujar', 'Andalucía'), ('huetor', 'Andalucía'),
    ('portugos', 'Andalucía'), ('pitres', 'Andalucía'), ('moclin', 'Andalucía'),
    ('sedella', 'Andalucía'), ('antequera', 'Andalucía'), ('competa', 'Andalucía'),
    ('torrox', 'Andalucía'), ('frigiliana', 'Andalucía'), ('caniles', 'Andalucía'),
    ('baena', 'Andalucía'), ('sotogrande', 'Andalucía'), ('la mairena', 'Andalucía'),
    ('almogia', 'Andalucía'), ('casarabonela', 'Andalucía'), ('constantina', 'Andalucía'),
    ('aracena', 'Andalucía'), ('casariche', 'Andalucía'), ('carmona', 'Andalucía'),
    ('la iruela', 'Andalucía'), ('baza', 'Andalucía'), ('lanjaron', 'Andalucía'),
    ('albolote', 'Andalucía'), ('utrera', 'Andalucía'), ('malaga centro', 'Andalucía'),
    ('alcala de guadaira', 'Andalucía'), ('lecrin', 'Andalucía'),
    ('coin', 'Andalucía'), ('otivar', 'Andalucía'), ('yegen', 'Andalucía'),
    ('zuheros', 'Andalucía'), ('iznajar', 'Andalucía'), ('priego de cordoba', 'Andalucía'),
    ('algarrobo', 'Andalucía'), ('benajarafe', 'Andalucía'), ('vinuela', 'Andalucía'),
    ('torre del mar', 'Andalucía'), ('caleta de velez', 'Andalucía'),
    ('almayate', 'Andalucía'), ('tabernas', 'Andalucía'), ('carboneras', 'Andalucía'),
    ('turre', 'Andalucía'), ('laroles', 'Andalucía'), ('gualchos', 'Andalucía'),
    ('algarinejo', 'Andalucía'), ('cortes de la frontera', 'Andalucía'),
    ('benaojan', 'Andalucía'), ('montejaque', 'Andalucía'), ('carcabuey', 'Andalucía'),
    ('rute', 'Andalucía'), ('linares', 'Andalucía'), ('ubeda', 'Andalucía'),
    ('lucena', 'Andalucía'), ('la puebla de cazalla', 'Andalucía'),
    ('gerena', 'Andalucía'), ('arriate', 'Andalucía'), ('san martin del tesorillo', 'Andalucía'),
    ('san luis de sabinillas', 'Andalucía'), ('mijas costa', 'Andalucía'),
    ('torreguadiaro', 'Andalucía'), ('pueblo nuevo de guadiaro', 'Andalucía'),
    ('riviera del sol', 'Andalucía'), ('la cala de mijas', 'Andalucía'),
    ('ativia isdabe', 'Andalucía'), ('axarquia', 'Andalucía'),
    ('playa granada', 'Andalucía'), ('malaga city', 'Andalucía'),
    ('costa del sol', 'Andalucía'), ('costa de sol', 'Andalucía'),
    ('andalucia', 'Andalucía'), ('andalusia', 'Andalucía'),
    ('algamitas', 'Andalucía'), ('altiplano de granada', 'Andalucía'),
    ('villanueva de la concepcion', 'Andalucía'), ('villanueva de tapia', 'Andalucía'),
    ('alhama de murcia', 'Murcia'),  # ←murcia, cuidado
    ('calahonda', 'Andalucía'), ('el ronquillo', 'Andalucía'),
    ('santafe', 'Andalucía'), ('monachil', 'Andalucía'),
    ('torvíscon', 'Andalucía'), ('torvíscon', 'Andalucía'), ('niguelas', 'Andalucía'),
    ('el castillo de las guardas', 'Andalucía'), ('villa de los barrios', 'Andalucía'),
    ('padul', 'Andalucía'), ('cañar', 'Andalucía'), ('alpujarra de la sierra', 'Andalucía'),
    ('dilar', 'Andalucía'), ('huesa', 'Andalucía'), ('hornos el viejo', 'Andalucía'),
    ('quesada', 'Andalucía'), ('la alberca', 'Andalucía'),  # también Salamanca, aquí el contexto manda
    ('jez del marquesado', 'Andalucía'), ('santa brigida', 'Canarias'),
    ('huescar', 'Andalucía'), ('cortes y graena', 'Andalucía'),
    ('zagrilla', 'Andalucía'), ('iznajar', 'Andalucía'),
    ('martin de la jara', 'Andalucía'), ('santa cruz de marchena', 'Andalucía'),
    ('benaocaz', 'Andalucía'), ('benamargosa', 'Andalucía'), ('periana', 'Andalucía'),
    ('comares', 'Andalucía'), ('san bartolome de la torre', 'Andalucía'),
    ('san juan de los terreros', 'Andalucía'), ('torrox costa', 'Andalucía'),
    ('almodovar del rio', 'Andalucía'), ('el algarrobico', 'Andalucía'),
    ('san martin del castañar', 'Andalucía'), ('la herradura', 'Andalucía'),
    ('el puerto de santa maria', 'Andalucía'), ('dalias', 'Andalucía'),
    ('arenas', 'Andalucía'), ('churriana', 'Andalucía'),

    # C. Valenciana
    ('valencia', 'C. Valenciana'), ('alicante', 'C. Valenciana'),
    ('castellon', 'C. Valenciana'), ('benidorm', 'C. Valenciana'),
    ('denia', 'C. Valenciana'), ('javea', 'C. Valenciana'), ('calpe', 'C. Valenciana'),
    ('altea', 'C. Valenciana'), ('benissa', 'C. Valenciana'),
    ('orihuela', 'C. Valenciana'), ('torrevieja', 'C. Valenciana'),
    ('santa pola', 'C. Valenciana'), ('elche', 'C. Valenciana'),
    ('gandia', 'C. Valenciana'), ('peniscola', 'C. Valenciana'),
    ('costa blanca', 'C. Valenciana'), ('beniali', 'C. Valenciana'),
    ('palomar', 'C. Valenciana'), ('bocairente', 'C. Valenciana'),
    ('finestrat', 'C. Valenciana'), ('alfaz del pi', 'C. Valenciana'),
    ('el campello', 'C. Valenciana'), ('villajoyosa', 'C. Valenciana'),
    ('playas de orihuela', 'C. Valenciana'), ('vall de gallinera', 'C. Valenciana'),
    ('vall de ebo', 'C. Valenciana'), ('calig', 'C. Valenciana'),
    ('lucena del cid', 'C. Valenciana'), ('ayora', 'C. Valenciana'),
    ('oliva', 'C. Valenciana'), ('vinaros', 'C. Valenciana'),
    ('parcent', 'C. Valenciana'), ('jalon', 'C. Valenciana'),
    ('rojales', 'C. Valenciana'), ('moraira', 'C. Valenciana'), ('orba', 'C. Valenciana'),
    ('alcoy', 'C. Valenciana'), ('xativa', 'C. Valenciana'),
    ('alzira', 'C. Valenciana'), ('burriana', 'C. Valenciana'),
    ('enguera', 'C. Valenciana'), ('chulilla', 'C. Valenciana'),
    ('moixent', 'C. Valenciana'), ('montesa', 'C. Valenciana'),
    ('vilafames', 'C. Valenciana'), ('puebla de arenoso', 'C. Valenciana'),
    ('tarbena', 'C. Valenciana'), ('ondara', 'C. Valenciana'),
    ('guardamar del segura', 'C. Valenciana'), ('guadalest', 'C. Valenciana'),
    ('busot', 'C. Valenciana'), ('rugat', 'C. Valenciana'),
    ('monovar', 'C. Valenciana'), ('bejis', 'C. Valenciana'),
    ('suera', 'C. Valenciana'), ('la nucia', 'C. Valenciana'),
    ('l olleria', 'C. Valenciana'), ('alcalali', 'C. Valenciana'),
    ('lliber', 'C. Valenciana'), ('els poblets', 'C. Valenciana'),
    ('san vicente del raspeig', 'C. Valenciana'), ('penaguila', 'C. Valenciana'),
    ('rossell', 'C. Valenciana'), ('mislata', 'C. Valenciana'),
    ('benetusser', 'C. Valenciana'), ('sant antonio de portmany', 'C. Valenciana'),
    ('province of valencia', 'C. Valenciana'), ('valencian community', 'C. Valenciana'),
    ('provincia alicante', 'C. Valenciana'), ('les coves de vinroma', 'C. Valenciana'),
    ('alcublas', 'C. Valenciana'), ('venta del moro', 'C. Valenciana'),
    ('cortes', 'C. Valenciana'), ('campello', 'C. Valenciana'),
    ('el vergel', 'C. Valenciana'), ('orihuela costa', 'C. Valenciana'),
    ('jesus pobre', 'C. Valenciana'), ('vall de laguart', 'C. Valenciana'),
    ('l alguena', 'C. Valenciana'), ('san fulgencio', 'C. Valenciana'),
    ('torreblanca', 'C. Valenciana'), ('castello de la plana', 'C. Valenciana'),
    ('favara', 'C. Valenciana'), ('castalla', 'C. Valenciana'),
    ('manilva', 'C. Valenciana'),  # es Málaga! pero dejamos Valencia abajo
    ('cabo roig', 'C. Valenciana'), ('albir', 'C. Valenciana'),

    # Baleares
    ('mallorca', 'Baleares'), ('menorca', 'Baleares'), ('ibiza', 'Baleares'),
    ('formentera', 'Baleares'), ('palma', 'Baleares'), ('baleares', 'Baleares'),
    ('balears', 'Baleares'), ('islas baleares', 'Baleares'), ('illes balears', 'Baleares'),
    ('balearic islands', 'Baleares'), ('eivissa', 'Baleares'),
    ('manacor', 'Baleares'), ('pollensa', 'Baleares'), ('alcudia', 'Baleares'),
    ('soller', 'Baleares'), ('estellenchs', 'Baleares'), ('estellencs', 'Baleares'),
    ('ses salines', 'Baleares'), ('capdepera', 'Baleares'), ('magaluf', 'Baleares'),
    ('porto cristo', 'Baleares'), ('cala millor', 'Baleares'), ('magalluf', 'Baleares'),
    ('san antonio', 'Baleares'), ('santa eulalia', 'Baleares'),
    ('ferrerias', 'Baleares'), ('sineu', 'Baleares'), ('arta', 'Baleares'),
    ('peguera', 'Baleares'), ('portocolom', 'Baleares'), ('inca', 'Baleares'),
    ("l'arenal", 'Baleares'), ('arenal', 'Baleares'), ('llucmajor', 'Baleares'),
    ('campos', 'Baleares'), ('felanitx', 'Baleares'), ('santanyi', 'Baleares'),
    ('sa pobla', 'Baleares'), ('ciutadella', 'Baleares'), ('mahon', 'Baleares'),
    ('mao', 'Baleares'), ('son servera', 'Baleares'), ('can picafort', 'Baleares'),
    ('cala ratjada', 'Baleares'), ('valldemosa', 'Baleares'), ('valldemossa', 'Baleares'),
    ('sencelles', 'Baleares'), ('consell', 'Baleares'), ('biniamar', 'Baleares'),
    ('alaro', 'Baleares'), ('bunyola', 'Baleares'), ('muro', 'Baleares'),
    ('calvia', 'Baleares'), ('cala salada', 'Baleares'), ("cala d'or", 'Baleares'),
    ('canyamel', 'Baleares'), ('portinax', 'Baleares'), ('coves noves', 'Baleares'),
    ('colonia de sant jordi', 'Baleares'), ('portals nous', 'Baleares'),
    ('santa ponsa', 'Baleares'), ('bendinat', 'Baleares'), ('costa de la calma', 'Baleares'),
    ("cala'n porter", 'Baleares'), ('cala fornells', 'Baleares'),
    ('lloret de vista alegre', 'Baleares'), ('es mercadal', 'Baleares'),
    ('son serra de marina', 'Baleares'), ('colonia de sant pere', 'Baleares'),
    ('caimari', 'Baleares'), ('playa del cura', 'Baleares'),
    ('calas de mallorca', 'Baleares'), ("s'illot", 'Baleares'),
    ("s'agaro", 'Baleares'), ('cala ratjada', 'Baleares'),
    ('puigpunyent', 'Baleares'), ('sant llorenc des cardassar', 'Baleares'),
    ('ferreries', 'Baleares'), ('sant lluis', 'Baleares'), ('villacarlos', 'Baleares'),
    ('san jose de la atalaya', 'Baleares'), ('san lorenzo de balafia', 'Baleares'),
    ("sant rafael de sa creu", 'Baleares'), ('coves noves', 'Baleares'),

    # Canarias
    ('tenerife', 'Canarias'), ('las palmas', 'Canarias'), ('gran canaria', 'Canarias'),
    ('lanzarote', 'Canarias'), ('fuerteventura', 'Canarias'),
    ('la palma', 'Canarias'), ('el hierro', 'Canarias'), ('la gomera', 'Canarias'),
    ('santa cruz de tenerife', 'Canarias'), ('adeje', 'Canarias'),
    ('arona', 'Canarias'), ('mogan', 'Canarias'), ('macher', 'Canarias'),
    ('playa del ingles', 'Canarias'), ('costa adeje', 'Canarias'),
    ('islas canarias', 'Canarias'), ('canarias', 'Canarias'), ('canary islands', 'Canarias'),
    ('teguise', 'Canarias'), ('arguineguin', 'Canarias'),
    ('santa lucia de tirajana', 'Canarias'), ('san bartolome de tirajana', 'Canarias'),
    ('maspalomas', 'Canarias'), ('los realejos', 'Canarias'),
    ('la orotava', 'Canarias'), ('icod de los vinos', 'Canarias'),
    ('yaiza', 'Canarias'), ('haria', 'Canarias'), ('valleseco', 'Canarias'),
    ('charco del palo', 'Canarias'), ('costa calma', 'Canarias'),
    ('tejeda', 'Canarias'), ('fuencaliente', 'Canarias'),
    ('puerto de la cruz', 'Canarias'), ('santiago del teide', 'Canarias'),
    ('san sebastian de la gomera', 'Canarias'), ('costa del silencio', 'Canarias'),
    ('el rosario', 'Canarias'), ('montaña la data', 'Canarias'),
    ('el pinar', 'Canarias'), ('teror', 'Canarias'), ('uga', 'Canarias'),
    ('las palmas de gran canaria', 'Canarias'), ('puerto del rosario', 'Canarias'),
    ('san miguel de tajao', 'Canarias'), ('arico', 'Canarias'),
    ('santa ursula', 'Canarias'), ('sonnenland', 'Canarias'), ('tenerife', 'Canarias'),
    ('santa brigida', 'Canarias'), ('puerto santiago', 'Canarias'),
    ('puerto banús', 'Andalucía'),  # Marbella
    ('arona', 'Canarias'), ('santa cruz de tenerife', 'Canarias'),

    # País Vasco
    ('bilbao', 'País Vasco'), ('donostia', 'País Vasco'), ('vitoria', 'País Vasco'),
    ('san sebastian', 'País Vasco'), ('fuenterrabia', 'País Vasco'),
    ('oiartzun', 'País Vasco'), ('bizkaia', 'País Vasco'), ('marquina', 'País Vasco'),

    # Navarra
    ('pamplona', 'Navarra'), ('navarra', 'Navarra'), ('obanos', 'Navarra'),

    # Cantabria
    ('santander', 'Cantabria'), ('cantabria', 'Cantabria'),
    ('castro urdiales', 'Cantabria'), ('laredo', 'Cantabria'),
    ('anievas', 'Cantabria'), ('rionansa', 'Cantabria'), ('cartes', 'Cantabria'),
    ('suances', 'Cantabria'), ('reinosa', 'Cantabria'), ('val de san vicente', 'Cantabria'),

    # Asturias
    ('oviedo', 'Asturias'), ('gijon', 'Asturias'), ('asturias', 'Asturias'),
    ('aviles', 'Asturias'), ('cangas de onis', 'Asturias'), ('coana', 'Asturias'),
    ('llanes', 'Asturias'), ('ribadesella', 'Asturias'), ('arriondas', 'Asturias'),
    ('cudillero', 'Asturias'), ('nava', 'Asturias'), ('caravia', 'Asturias'),
    ('parres', 'Asturias'), ('candamo', 'Asturias'), ('ibias', 'Asturias'),
    ('herrerias', 'Asturias'), ('cabrales', 'Asturias'), ('villaviciosa', 'Asturias'),
    ('cangas del narcea', 'Asturias'), ('navia', 'Asturias'),
    ('arenas de cabrales', 'Asturias'),

    # Galicia
    ('a coruna', 'Galicia'), ('coruna', 'Galicia'), ('vigo', 'Galicia'),
    ('pontevedra', 'Galicia'), ('santiago', 'Galicia'), ('lugo', 'Galicia'),
    ('ourense', 'Galicia'), ('galicia', 'Galicia'), ('a guarda', 'Galicia'),
    ('cuntis', 'Galicia'), ('moana', 'Galicia'), ('tomino', 'Galicia'),
    ('ribadeo', 'Galicia'), ('baiona', 'Galicia'), ('sanxenxo', 'Galicia'),
    ('cambados', 'Galicia'), ('ames', 'Galicia'), ('ordes', 'Galicia'),
    ('catoira', 'Galicia'), ('lalin', 'Galicia'), ('camariñas', 'Galicia'),
    ('taboadela', 'Galicia'), ('allariz', 'Galicia'), ('monterroso', 'Galicia'),
    ('meis', 'Galicia'), ('poio', 'Galicia'), ('o porrino', 'Galicia'),
    ('arzua', 'Galicia'), ('brion', 'Galicia'), ('bueu', 'Galicia'),
    ('ponteareas', 'Galicia'), ('ourol', 'Galicia'), ('quiroga', 'Galicia'),
    ('burela de cabo', 'Galicia'), ('la estrada', 'Galicia'), ('la guardia', 'Galicia'),
    ('o grove', 'Galicia'), ('marin', 'Galicia'), ('chantada', 'Galicia'),
    ('a pobra de trives', 'Galicia'), ('oia', 'Galicia'), ('capmany', 'Galicia'),

    # Castilla y León
    ('salamanca', 'Castilla y León'), ('burgos', 'Castilla y León'),
    ('valladolid', 'Castilla y León'), ('segovia', 'Castilla y León'),
    ('avila', 'Castilla y León'), ('soria', 'Castilla y León'),
    ('zamora', 'Castilla y León'), ('palencia', 'Castilla y León'),
    ('leon', 'Castilla y León'), ('ponferrada', 'Castilla y León'),
    ('candelario', 'Castilla y León'), ('fuentes de bejar', 'Castilla y León'),
    ('santa colomba de somoza', 'Castilla y León'),
    ('penaranda de duero', 'Castilla y León'), ('moradillo de roa', 'Castilla y León'),
    ('ciudad rodrigo', 'Castilla y León'), ('santa maria del paramo', 'Castilla y León'),
    ('riego de la vega', 'Castilla y León'), ('cacabelos', 'Castilla y León'),
    ('bembibre', 'Castilla y León'), ('carucedo', 'Castilla y León'),
    ('sobrado', 'Castilla y León'), ('camponaraya', 'Castilla y León'),
    ('mansilla de las mulas', 'Castilla y León'), ('arcones', 'Castilla y León'),
    ('sepulveda', 'Castilla y León'), ('simancas', 'Castilla y León'),
    ('santa maria del tietar', 'Castilla y León'), ('poyales del hoyo', 'Castilla y León'),
    ('piedralaves', 'Castilla y León'), ('santiago millas', 'Castilla y León'),
    ('quintanar de la sierra', 'Castilla y León'), ('medina de pomar', 'Castilla y León'),
    ('bejar', 'Castilla y León'), ('frias', 'Castilla y León'),
    ('province leon', 'Castilla y León'), ('rebolledo', 'Castilla y León'),
    ('penaranda', 'Castilla y León'), ('pereruela', 'Castilla y León'),
    ('puebla de sanabria', 'Castilla y León'), ('candeleda', 'Castilla y León'),
    ('san esteban del valle', 'Castilla y León'), ('el barco de avila', 'Castilla y León'),

    # Castilla-La Mancha
    ('toledo', 'Castilla-La Mancha'), ('ciudad real', 'Castilla-La Mancha'),
    ('albacete', 'Castilla-La Mancha'), ('cuenca', 'Castilla-La Mancha'),
    ('guadalajara', 'Castilla-La Mancha'), ('castilla la mancha', 'Castilla-La Mancha'),
    ('consuegra', 'Castilla-La Mancha'), ('almagro', 'Castilla-La Mancha'),
    ('villarrobledo', 'Castilla-La Mancha'), ('la roda', 'Castilla-La Mancha'),
    ('horcajo de los montes', 'Castilla-La Mancha'), ('el robledo', 'Castilla-La Mancha'),
    ('olmedilla de alarcon', 'Castilla-La Mancha'), ('villar de olalla', 'Castilla-La Mancha'),
    ('hinojosas de calatrava', 'Castilla-La Mancha'),
    ('villanueva de san carlos', 'Castilla-La Mancha'), ('yeste', 'Castilla-La Mancha'),
    ('elche de la sierra', 'Castilla-La Mancha'), ('almansa', 'Castilla-La Mancha'),
    ('provincia cuenca', 'Castilla-La Mancha'),

    # Extremadura
    ('caceres', 'Extremadura'), ('badajoz', 'Extremadura'), ('merida', 'Extremadura'),
    ('trujillo', 'Extremadura'), ('zafra', 'Extremadura'), ('losar de la vera', 'Extremadura'),
    ('torremejia', 'Extremadura'), ('valencia de alcantara', 'Extremadura'),
    ('castañar de ibor', 'Extremadura'), ('villanueva del fresno', 'Extremadura'),
    ('extremadura', 'Extremadura'), ('parrillas', 'Extremadura'),

    # Aragón
    ('zaragoza', 'Aragón'), ('huesca', 'Aragón'), ('teruel', 'Aragón'),
    ('jaca', 'Aragón'), ('benasque', 'Aragón'), ('ainsa', 'Aragón'),
    ('aragon', 'Aragón'), ('graus', 'Aragón'), ('ayerbe', 'Aragón'),
    ('alcala de la selva', 'Aragón'), ('valderrobres', 'Aragón'),
    ('maella', 'Aragón'), ('cretas', 'Aragón'), ('uncastillo', 'Aragón'),
    ('tarazona', 'Aragón'),

    # Murcia
    ('murcia', 'Murcia'), ('cartagena', 'Murcia'), ('lorca', 'Murcia'),
    ('san javier', 'Murcia'), ('mazarron', 'Murcia'), ('caravaca', 'Murcia'),
    ('calabardina', 'Murcia'), ('santiago de la ribera', 'Murcia'),
    ('aguilas', 'Murcia'), ('san pedro del pinatar', 'Murcia'),
    ('alhama de murcia', 'Murcia'), ('fortuna', 'Murcia'), ('mula', 'Murcia'),
    ('jumilla', 'Murcia'), ('los alcazares', 'Murcia'), ('aledo', 'Murcia'),
    ('archena', 'Murcia'), ('cabo roig', 'Murcia'), ('region de murcia', 'Murcia'),
    ('murcia province', 'Murcia'), ('la manga', 'Murcia'),
    ('vera', 'Murcia'),  # puede ser Almería también

    # La Rioja
    ('logrono', 'La Rioja'), ('la rioja', 'La Rioja'), ('rioja', 'La Rioja'),
    ('san asensio', 'La Rioja'), ('ezcaray', 'La Rioja'), ('cuzcurrita', 'La Rioja'),

    # Ceuta / Melilla
    ('ceuta', 'Ceuta'), ('melilla', 'Melilla'),
]}

def inferir_region(texto):
    t = norm(texto)
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
        new = limpiar(old)
        if new and new != old:
            item['location'] = new
            fixed_loc += 1

        # 2. Añadir región si falta — buscar en varias fuentes
        if not item.get('location_region'):
            fuentes = [
                item.get('location', ''),
                item.get('location_city', ''),
                item.get('title', ''),
                item.get('description', '')[:500],
                item.get('url', ''),
            ]
            for t in fuentes:
                r = inferir_region(t)
                if r:
                    item['location_region'] = r
                    fixed_region += 1
                    break

    despues = sum(1 for x in data if x.get('location_region'))
    print(f'Ubicaciones limpias: +{fixed_loc}')
    print(f'Regiones nuevas:     +{fixed_region}')
    print(f'Región después: {despues} ({100*despues//len(data)}%)\n')

    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print('Cache guardado ✅')

    sin = [x for x in data if not x.get('location_region')]
    if sin:
        locs = {}
        for x in sin:
            l = x.get('location', '')
            if l and l not in ('España', 'Espana', ''):
                locs[l] = locs.get(l, 0) + 1
        top = sorted(locs.items(), key=lambda x: -x[1])[:10]
        print(f'\nSin región ({len(sin)}) — top 10:')
        for l, c in top:
            print(f'  {c}x  {l}')
    else:
        print('\n🎉 100% con región asignada!')

if __name__ == '__main__':
    main()
