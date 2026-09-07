#!/usr/bin/env python3
"""
Scraper de LICENCIAS TURÍSTICAS OFICIALES — registro por Comunidad Autónoma.

A diferencia de scraper.py (que scrapea anuncios de venta en portales
inmobiliarios y corre a diario), este script descarga datos ABIERTOS
OFICIALES de organismos públicos — no cambia cada día, así que basta con
correrlo de vez en cuando (igual que scraper_adr.py, que corre 1x/mes).

Cada Comunidad Autónoma tiene su propio portal de datos abiertos, con su
propio formato de columnas — por eso cada fuente tiene su propia función
de descarga + "traductor" a nuestro esquema común FIJO:

    destino, provincia, municipio, tipo, categoria, registro, nombre,
    direccion, cp, hab, plazas

Estas son las columnas OBLIGATORIAS en todas las comunidades — si una
fuente no publica algún campo (p.ej. Madrid no da habitaciones/plazas),
esa columna se queda vacía para esos registros, pero SIEMPRE existe con
ese nombre exacto. No se añaden columnas extra por fuente.

Salida: licencias.json en la raíz del repo.

Estado de las fuentes (ir ampliando esta lista según se vayan añadiendo):
  ✅ Madrid       — CSV directo, confirmado
  ⏳ Andalucía    — API JSON, mapeo sin confirmar todavía (pendiente de prueba)
  ⏳ Resto de CCAA — pendientes, se añaden una a una
"""
import csv
import io
import json
import re
import sys
import time
import unicodedata

import requests

# ══════════════════════════════════════════════════════
# Destinos objetivo — misma lista que PRIORIDAD_DEFECTO en index_template.html
# (mantener sincronizadas ambas listas si se edita una de las dos)
# ══════════════════════════════════════════════════════
DESTINOS_OBJETIVO = [
    'Fuerteventura', 'Gran Canaria', 'Lanzarote', 'Madrid', 'Sevilla', 'Tenerife',
    'Barcelona', 'Benidorm', 'Bilbao', 'Malaga', 'San Sebastian',
    'Granada', 'Salou', 'Torremolinos', 'Valencia',
]


def normalizar(s):
    """minúsculas, sin tildes, sin espacios sobrantes — para comparar texto
    de forma robusta sin depender de mayúsculas/acentos de cada fuente."""
    if not s:
        return ''
    s = str(s).lower().strip()
    s = ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')
    return s


_DESTINOS_NORM = {normalizar(d): d for d in DESTINOS_OBJETIVO}


def calcular_destino(municipio):
    """Devuelve el nombre del destino objetivo si el municipio coincide
    EXACTO (mismo criterio que usa la fórmula VLOOKUP en el Excel), o ''
    si no está en la lista de destinos que nos interesan."""
    return _DESTINOS_NORM.get(normalizar(municipio), '')



HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept-Language': 'es-ES,es;q=0.9',
}


def clean(s):
    if s is None:
        return ''
    return re.sub(r'\s+', ' ', str(s)).strip()


def reparar_mojibake(s):
    """Algunos portales de datos abiertos publican ciertas celdas con el
    texto codificado en UTF-8 DOS VECES (p.ej. 'TURÃ\x8dSTICOS' en vez de
    'TURÍSTICOS') — es un fallo del propio origen de datos, no de cómo
    nosotros decodificamos la respuesta (el resto del fichero decodifica
    bien). Se revierte re-codificando como latin1 (recupera los bytes
    UTF-8 originales) y volviendo a decodificar como UTF-8. Si el texto
    no está afectado, esto lanza una excepción o no cambia nada raro —
    en ese caso nos quedamos con el original tal cual."""
    if not s or 'Ã' not in s and '\x8d' not in s and '\x8c' not in s:
        return s
    try:
        reparado = s.encode('latin1').decode('utf-8')
        return reparado
    except (UnicodeDecodeError, UnicodeEncodeError):
        return s


def clave_normalizada(k):
    """Normaliza un nombre de columna de CSV/JSON de forma robusta: quita
    saltos de línea internos (algunos portales, como el de Castilla-La
    Mancha, publican cabeceras tipo 'Tipo\\nEstablecimiento'), colapsa
    espacios repetidos, y aplica la normalización habitual (minúsculas,
    sin tildes)."""
    return normalizar(clean(k))


def descargar_texto(url, encoding_probable='utf-8', reintentos=4, timeout=30):
    """Descarga un recurso de datos abiertos con reintentos. Devuelve el
    texto decodificado, o None si falla tras todos los intentos.

    CONFIRMADO con un run real: Andalucía (175.000 registros, un archivo
    grande) falló del todo un día porque el servidor tuvo un mal momento
    (timeout + conexión reiniciada) y solo teníamos 2 intentos con 3s de
    pausa — insuficiente para un problema pasajero del lado del servidor.
    Subimos a 4 intentos con espera CRECIENTE (3s, 6s, 12s) en vez de
    fija, dando más margen para que el servidor se recupere."""
    session = requests.Session()
    for intento in range(reintentos):
        try:
            r = session.get(url, headers=HEADERS, timeout=timeout)
            if r.status_code == 200:
                # Los portales de datos abiertos a veces mandan mal la
                # cabecera de encoding. Cascada: el declarado -> windows-1252
                # (frecuentísimo en CSVs de administraciones españolas más
                # antiguas, y windows-1252 casi nunca lanza error porque
                # acepta cualquier byte, así que si el declarado falla esto
                # suele arreglarlo de verdad) -> utf-8 con reemplazo como
                # último recurso, ya sabiendo que saldrán '�' sueltos.
                try:
                    return r.content.decode(encoding_probable)
                except UnicodeDecodeError:
                    try:
                        return r.content.decode('windows-1252')
                    except UnicodeDecodeError:
                        return r.content.decode('utf-8', errors='replace')
            else:
                print(f'  [{url[:70]}] status {r.status_code}')
        except Exception as e:
            if intento < reintentos - 1:
                espera = 3 * (2 ** intento)  # 3s, 6s, 12s...
                print(f'  [{url[:70]}] intento {intento + 1}/{reintentos} '
                      f'falló ({e}), reintentando en {espera}s...')
                time.sleep(espera)
            else:
                print(f'  [{url[:70]}] fallo tras {reintentos} intentos: {e}')
    return None


# ══════════════════════════════════════════════════════
# MADRID — Registro de Empresas Turísticas de la Comunidad de Madrid
# Fuente: datos.comunidad.madrid — CSV directo, confirmado por búsqueda.
# ══════════════════════════════════════════════════════
def descargar_madrid():
    print('\n→ Comunidad de Madrid...')
    url = ('https://datos.comunidad.madrid/catalogo/dataset/'
           'ef437c50-5b26-4843-92c3-d8eef5507fac/resource/'
           '260e80ac-2062-41f6-9f96-4902675b1078/download/'
           'alojamientos_turisticos.csv')

    texto = descargar_texto(url)
    if not texto:
        print('  Madrid: 0 registros (fallo de descarga)')
        return []

    try:
        # Los CSV de datos.comunidad.madrid suelen usar ';' como separador
        # (estándar en portales CKAN españoles) — probamos ambos por si acaso.
        muestra = texto[:2000]
        separador = ';' if muestra.count(';') > muestra.count(',') else ','
        lector = csv.DictReader(io.StringIO(texto), delimiter=separador)

        print(f'  [DIAGNÓSTICO] Separador detectado: {separador!r}')
        print(f'  [DIAGNÓSTICO] Columnas reales del CSV: {lector.fieldnames}')

        registros = []
        for fila in lector:
            # Normalizamos las claves: minúsculas, y quitamos el BOM
            # (\ufeff) que suele venir pegado al nombre de la primera
            # columna en CSVs exportados desde Windows/Excel.
            fila_norm = {clean(k).lower().lstrip('\ufeff'): v for k, v in fila.items()}

            # Columnas REALES confirmadas para Madrid (distinto de lo que
            # supusimos al principio):
            #   alojamiento_tipo, categoria, denominacion, via_tipo,
            #   via_nombre, numero, bloque, portal, escalera, planta,
            #   puerta, cdpostal, localidad, signatura
            # Este registro NO trae cadena/email/web/teléfono/habitaciones/
            # plazas — el registro turístico de Madrid solo publica estos
            # campos, así que esos quedan vacíos a propósito (no es un bug).

            # La dirección viene troceada en varias columnas — la unimos.
            partes_direccion = [
                clean(fila_norm.get('via_tipo')),
                clean(fila_norm.get('via_nombre')),
                clean(fila_norm.get('numero')),
            ]
            direccion = ' '.join(p for p in partes_direccion if p)
            extra = []
            if clean(fila_norm.get('bloque')):   extra.append(f"Bloque {clean(fila_norm.get('bloque'))}")
            if clean(fila_norm.get('portal')):   extra.append(f"Portal {clean(fila_norm.get('portal'))}")
            if clean(fila_norm.get('escalera')): extra.append(f"Esc. {clean(fila_norm.get('escalera'))}")
            if clean(fila_norm.get('planta')):   extra.append(f"Planta {clean(fila_norm.get('planta'))}")
            if clean(fila_norm.get('puerta')):   extra.append(f"Puerta {clean(fila_norm.get('puerta'))}")
            if extra:
                direccion += ', ' + ', '.join(extra)

            municipio = clean(fila_norm.get('localidad') or 'MADRID').upper()

            registros.append({
                'destino': calcular_destino(municipio),
                'provincia': 'MADRID',
                'municipio': municipio,
                'tipo': clean(fila_norm.get('alojamiento_tipo')),
                'categoria': clean(fila_norm.get('categoria')),
                'registro': clean(fila_norm.get('signatura')),
                'nombre': clean(fila_norm.get('denominacion')),
                'direccion': direccion,
                'cp': clean(fila_norm.get('cdpostal')),
                'hab': '',      # no viene en este registro
                'plazas': '',   # no viene en este registro
            })

        print(f'  Madrid: {len(registros)} registros procesados')
        if registros:
            print(f'  Ejemplo primera fila: {registros[0]}')
        return registros

    except Exception as e:
        print(f'  Error procesando CSV de Madrid: {e}')
        return []


# ══════════════════════════════════════════════════════
# ANDALUCÍA — OpenRTA (Registro de Turismo de Andalucía)
# Fuente: datos.juntadeandalucia.es — API REST oficial en JSON.
# OJO: no pude comprobar yo mismo el formato exacto de los campos (el
# archivo es grande, mi herramienta no consiguió descargarlo) — mapeo
# a ciegas con nombres de campo razonables + diagnóstico, igual que
# hicimos al principio con Madrid. Es más que probable que haga falta
# un ajuste con datos reales tras la primera prueba.
# ══════════════════════════════════════════════════════
def descargar_andalucia():
    print('\n→ Andalucía (OpenRTA)...')
    url_json = 'https://datos.juntadeandalucia.es/api/v0/openrta/all?format=json'
    url_csv_zip = 'https://datos.juntadeandalucia.es/api/v0/openrta/all?format=csv'

    texto = descargar_texto(url_json, timeout=120)  # es el archivo más grande de todos, más margen aún

    if not texto:
        # PLAN B: la misma fuente también se publica como un CSV
        # comprimido en ZIP (confirmado en datos.gob.es) desde el MISMO
        # servidor. Si el fallo era una intermitencia puntual del
        # endpoint JSON en concreto (generado al vuelo) en vez de una
        # caída general del servidor, un ZIP estático tiene alguna
        # posibilidad más de aguantar. No es una fuente distinta de
        # verdad, así que si el servidor está caído de raíz esto
        # tampoco va a funcionar -- pero cuesta poco intentarlo.
        print('  El JSON falló del todo. Probando el CSV/ZIP como plan B...')
        registros_csv = _descargar_andalucia_csv_zip(url_csv_zip)
        if registros_csv:
            return registros_csv
        print('  Andalucía: 0 registros (fallo de descarga en ambos formatos)')
        return []

    try:
        datos = json.loads(texto)

        # La API puede devolver la lista directamente, o envuelta en una
        # clave tipo 'result'/'data'/'items'/'records' — probamos varias.
        if isinstance(datos, dict):
            for clave in ('result', 'data', 'items', 'records', 'openrta'):
                if clave in datos and isinstance(datos[clave], list):
                    datos = datos[clave]
                    break

        if not isinstance(datos, list) or not datos:
            print(f'  [DIAGNÓSTICO] Estructura del JSON no reconocida. '
                  f'Tipo: {type(datos)}. Primeros 500 caracteres: {texto[:500]}')
            print('  Andalucía: 0 registros')
            return []

        print(f'  [DIAGNÓSTICO] Campos reales del primer registro: {list(datos[0].keys())}')
        print(f'  [DIAGNÓSTICO] VALORES del primer registro completo:')
        for k, v in datos[0].items():
            print(f'      {k!r}: {v!r}')

        # CONFIRMADO con una auditoría real de los datos (el usuario notó
        # que salían registros "sospechosos", sin municipio/tipo/nada):
        # el OpenRTA de Andalucía NO es solo alojamientos -- también
        # incluye SERVICIOS turísticos (guías, restaurantes, oficinas de
        # turismo, empresas de eventos, actividades de buceo/charter...).
        # Se distinguen por el prefijo del código de registro. Verificado
        # con ejemplos reales de nombre para cada prefijo antes de
        # excluir nada -- los que SÍ son alojamiento real (VTAR, VUT, CR)
        # se quedan aunque también les falte alguna columna.
        PREFIJOS_NO_ALOJAMIENTO = {
            'GT',    # Guías turísticos (personas, no alojamiento)
            'REST',  # Restaurantes (hasta McDonald's aparecía aquí)
            'OT',    # Oficinas de Turismo
            'OCC',   # Empresas de organización de congresos/eventos
            'PIT',   # Puntos de Información Turística
            'AT',    # Actividades turísticas (buceo, charters de barco...)
            'AIAT',  # Agencias/guías de turismo local
            # OJO -- 'H' NO se excluye: aunque vimos un registro basura
            # con ese prefijo (nombre literal "xxx"), 'H/...' es TAMBIÉN
            # el prefijo de verdad de los HOTELES reales de Andalucía
            # (ej. 'H/AL/00598' = Hotel Moon). Probado con datos reales:
            # excluir 'H' se cargaba TODOS los hoteles de la comunidad,
            # no solo ese único registro basura -- mucho peor que dejar
            # pasar 1 fila rara de 372.000.
        }

        registros = []
        excluidos_no_alojamiento = 0
        for item in datos:
            # Nombres de campo CONFIRMADOS con datos reales (no es una
            # suposición esta vez): 'provinces', 'municipalities', 'group',
            # 'categories', 'registration_code', 'name',
            # 'establishment_address', 'postal_code', 'tot_gen_ua' (=hab),
            # 'tot_gen_places' (=plazas). Están en inglés, sin acentos en
            # las claves, porque es una API de datos "crudos" con IDs de
            # referencia (province_id, municipality_id) además del nombre
            # ya resuelto en 'provinces'/'municipalities'.
            def val(campo):
                v = item.get(campo)
                return clean(v) if v is not None else ''

            codigo_registro = val('registration_code')
            prefijo = codigo_registro.split('/')[0] if '/' in codigo_registro else ''
            if prefijo in PREFIJOS_NO_ALOJAMIENTO:
                excluidos_no_alojamiento += 1
                continue

            municipio = val('municipalities').upper()

            registros.append({
                'destino': calcular_destino(municipio),
                'provincia': val('provinces').upper(),
                'municipio': municipio,
                'tipo': val('group'),
                'categoria': val('categories'),
                'registro': codigo_registro,
                'nombre': val('name'),
                'direccion': val('establishment_address'),
                'cp': val('postal_code'),
                'hab': item.get('tot_gen_ua') or '',
                'plazas': item.get('tot_gen_places') or '',
            })

        if excluidos_no_alojamiento:
            print(f'  ({excluidos_no_alojamiento} registros excluidos por ser '
                  f'servicios turísticos, no alojamiento: guías, restaurantes, '
                  f'oficinas de turismo, actividades...)')

        print(f'  Andalucía: {len(registros)} registros procesados')
        if registros:
            print(f'  Ejemplo primera fila: {registros[0]}')
        return registros

    except json.JSONDecodeError as e:
        print(f'  Error: la respuesta no es JSON válido ({e}). '
              f'Primeros 300 caracteres: {texto[:300]}')
        return []
    except Exception as e:
        print(f'  Error procesando datos de Andalucía: {e}')
        return []


def _descargar_andalucia_csv_zip(url_csv_zip):
    """Plan B para Andalucía: el mismo dataset publicado como CSV dentro
    de un ZIP (confirmado en datos.gob.es). Como NO tenemos una muestra
    real de las columnas de este CSV (nunca ha hecho falta usarlo hasta
    ahora), esto va con diagnóstico y búsqueda de columna flexible —
    si los nombres reales no coinciden con lo que probamos aquí, el
    print de [DIAGNÓSTICO] dirá exactamente qué columnas hay de verdad
    para poder ajustarlo, igual que hemos hecho con todo lo demás."""
    import io
    import zipfile
    import csv as csv_module

    headers = {'User-Agent': HEADERS.get('User-Agent', '')}
    try:
        r = requests.get(url_csv_zip, headers=headers, timeout=120)
        r.raise_for_status()
    except Exception as e:
        print(f'  [Plan B CSV/ZIP] fallo de descarga: {e}')
        return []

    try:
        zip_en_memoria = zipfile.ZipFile(io.BytesIO(r.content))
        nombres_csv = [n for n in zip_en_memoria.namelist() if n.lower().endswith('.csv')]
        if not nombres_csv:
            print(f'  [Plan B CSV/ZIP] el ZIP no contiene ningún .csv '
                  f'(contiene: {zip_en_memoria.namelist()})')
            return []
        contenido_csv = zip_en_memoria.read(nombres_csv[0])
    except Exception as e:
        print(f'  [Plan B CSV/ZIP] no se pudo abrir el ZIP: {e}')
        return []

    try:
        texto_csv = contenido_csv.decode('utf-8-sig')
    except UnicodeDecodeError:
        texto_csv = contenido_csv.decode('windows-1252', errors='replace')

    # Detección de separador, igual que en el resto de fuentes CSV de este
    # proyecto (Madrid, Castilla y León, Extremadura...): casi todos los
    # CSV de administraciones españolas usan ';' en vez de ',' porque
    # muchos números decimales llevan coma.
    primera_linea = texto_csv.split('\n', 1)[0]
    separador = ';' if primera_linea.count(';') > primera_linea.count(',') else ','
    print(f'  [DIAGNÓSTICO Plan B] Separador detectado: {separador!r}')

    lector = csv_module.DictReader(io.StringIO(texto_csv), delimiter=separador)
    columnas = lector.fieldnames or []
    print(f'  [DIAGNÓSTICO Plan B] Columnas reales del CSV: {columnas}')

    def buscar_columna(*candidatas):
        """Busca la primera columna real que coincida (sin distinguir
        mayúsculas/minúsculas) con alguna de las candidatas."""
        columnas_lower = {c.lower(): c for c in columnas}
        for candidata in candidatas:
            if candidata.lower() in columnas_lower:
                return columnas_lower[candidata.lower()]
        return None

    col_municipio = buscar_columna('municipalities', 'municipio', 'MUNICIPIO')
    col_provincia = buscar_columna('provinces', 'provincia', 'PROVINCIA')
    col_tipo = buscar_columna('group', 'grupo', 'tipo', 'GRUPO')
    col_categoria = buscar_columna('categories', 'categoria', 'categoría', 'CATEGORIA')
    col_registro = buscar_columna('registration_code', 'signatura', 'registro', 'codigo')
    col_nombre = buscar_columna('name', 'nombre', 'denominacion', 'denominación')
    col_direccion = buscar_columna('establishment_address', 'direccion', 'dirección')
    col_cp = buscar_columna('postal_code', 'cp', 'codigo_postal', 'código postal')
    col_hab = buscar_columna('tot_gen_ua', 'habitaciones', 'nº hab', 'num_habitaciones')
    col_plazas = buscar_columna('tot_gen_places', 'plazas')

    if not col_municipio or not col_nombre:
        print('  [Plan B CSV/ZIP] No reconozco las columnas clave '
              '(municipio/nombre) en este CSV -- hace falta revisar '
              'los nombres reales de arriba y ajustar el código.')
        return []

    registros = []
    for fila in lector:
        municipio = clean(fila.get(col_municipio, '')).upper()
        registros.append({
            'destino': calcular_destino(municipio),
            'provincia': clean(fila.get(col_provincia, '')).upper() if col_provincia else '',
            'municipio': municipio,
            'tipo': clean(fila.get(col_tipo, '')) if col_tipo else '',
            'categoria': clean(fila.get(col_categoria, '')) if col_categoria else '',
            'registro': clean(fila.get(col_registro, '')) if col_registro else '',
            'nombre': clean(fila.get(col_nombre, '')),
            'direccion': clean(fila.get(col_direccion, '')) if col_direccion else '',
            'cp': clean(fila.get(col_cp, '')) if col_cp else '',
            'hab': fila.get(col_hab, '') if col_hab else '',
            'plazas': fila.get(col_plazas, '') if col_plazas else '',
        })

    print(f'  [Plan B CSV/ZIP] Andalucía: {len(registros)} registros procesados')
    if registros:
        print(f'  [Plan B CSV/ZIP] Ejemplo primera fila: {registros[0]}')
    return registros


# ══════════════════════════════════════════════════════
# CANARIAS — Registro General Turístico de Canarias
# Fuente: datos.canarias.es — API JSON oficial, CONFIRMADA con datos
# reales y con diccionario de datos oficial (no es una suposición).
# Cubre 4 de tus 15 destinos de un tirón: Fuerteventura, Gran Canaria,
# Lanzarote y Tenerife.
# ══════════════════════════════════════════════════════
def descargar_canarias():
    print('\n→ Canarias (Registro General Turístico)...')
    url = ('https://datos.canarias.es/catalogos/general/dataset/'
           '429db33d-cbce-4920-b1b6-b4dde9e5f90f/resource/'
           'd98f6ce7-e045-4d1b-9c8c-0b4233b4889a/download/'
           'establecimientos-hoteleros-inscritos-en-el-registro-general-turistico-de-canarias.json')

    texto = descargar_texto(url, timeout=60)
    if not texto:
        print('  Canarias: 0 registros (fallo de descarga)')
        return []

    def limpio(v):
        """En este registro, '_U' significa 'desconocido/no consta' —
        lo tratamos como vacío, igual que un campo realmente vacío."""
        v = clean(v)
        return '' if v == '_U' else v

    try:
        datos = json.loads(texto)
        establecimientos = datos.get('result', datos) if isinstance(datos, dict) else datos

        if not isinstance(establecimientos, list):
            print(f'  [DIAGNÓSTICO] Estructura inesperada: {type(establecimientos)}')
            return []

        registros = []
        for e in establecimientos:
            municipio = limpio(e.get('direccion_municipio_nombre')).upper()
            isla = limpio(e.get('direccion_isla_nombre'))

            # OJO: en tu lista de destinos, Canarias está por ISLA
            # (Fuerteventura, Gran Canaria, Lanzarote, Tenerife), no por
            # municipio — un hotel en "Puerto De La Cruz" nunca va a
            # coincidir con "Tenerife" si comparamos por municipio. Primero
            # probamos por isla (el caso real de Canarias); si no encuentra
            # nada, probamos por municipio (por si algún día metes un
            # destino más concreto, tipo "Playa del Inglés").
            destino = calcular_destino(isla) or calcular_destino(municipio)

            registros.append({
                'destino': destino,
                'provincia': limpio(e.get('direccion_provincia_nombre')).upper(),
                'municipio': municipio,
                'tipo': limpio(e.get('establecimiento_tipologia')) or limpio(e.get('establecimiento_modalidad')),
                'categoria': limpio(e.get('establecimiento_clasificacion')),
                'registro': limpio(e.get('establecimiento_id')),
                'nombre': limpio(e.get('establecimiento_nombre_comercial')),
                'direccion': limpio(e.get('direccion')),
                'cp': limpio(e.get('direccion_codigo_postal')),
                'hab': e.get('unidades_explotacion') or '',
                'plazas': e.get('plazas') or '',
            })

        print(f'  Canarias: {len(registros)} registros procesados')
        if registros:
            print(f'  Ejemplo primera fila: {registros[0]}')
        return registros

    except json.JSONDecodeError as e:
        print(f'  Error: la respuesta no es JSON válido ({e})')
        return []
    except Exception as e:
        print(f'  Error procesando datos de Canarias: {e}')
        return []


# ══════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════
def guardar_json(datos, ruta, formato_compacto=False):
    """
    Guarda 'datos' como JSON en 'ruta', SIEMPRE con el mismo nombre (se
    sobreescribe cada vez que corres el script — eso es lo correcto).

    Antes de escribir, intenta activamente "desbloquear" el archivo si ya
    existe de una vez anterior: le quita el atributo de solo-lectura
    (típico en Windows cuando un archivo se descargó del navegador) y lo
    borra primero. Esto ataca la causa real en vez de rodearla con nombres
    alternativos. Si con todo y eso sigue bloqueado (algo lo tiene abierto
    AHORA MISMO), como último recurso guarda con otro nombre para no
    perder los datos ya descargados.

    formato_compacto=True guarda como {"columnas": [...], "filas": [[...]]}
    en vez de una lista de objetos — evita repetir el nombre de cada
    columna en CADA registro (con 372.676 registros y 11 columnas, eso
    son ~30 MB solo en nombres de columna repetidos). CONFIRMADO con los
    datos reales: baja el archivo de 91,5 MB a 54,2 MB — necesario para
    quedar con margen cómodo bajo el límite de 100 MB de GitHub. El
    JavaScript que lo lee tiene que reconstruir las filas usando
    'columnas' como cabecera (documentado también en index_template.html).
    """
    import os
    import stat

    def _escribir(f):
        if formato_compacto and datos:
            columnas = list(datos[0].keys())
            filas = [[registro.get(c, '') for c in columnas] for registro in datos]
            json.dump({'columnas': columnas, 'filas': filas}, f,
                      ensure_ascii=False, separators=(',', ':'))
        else:
            json.dump(datos, f, ensure_ascii=False, separators=(',', ':'))

    if os.path.exists(ruta):
        try:
            os.chmod(ruta, stat.S_IWRITE)
            os.remove(ruta)
            print(f'  (Se ha borrado el "{ruta}" anterior para reemplazarlo)')
        except Exception as e:
            print(f'  Aviso: no se pudo preparar "{ruta}" para sobreescribir: {e}')

    try:
        with open(ruta, 'w', encoding='utf-8') as f:
            _escribir(f)
        print(f'✅ Guardado correctamente en: {os.path.abspath(ruta)}')
        return True
    except PermissionError as e:
        print(f'   No se pudo guardar como "{ruta}": {e}')

    nombre_alternativo = ruta.replace('.json', f'_{int(time.time())}.json')
    try:
        with open(nombre_alternativo, 'w', encoding='utf-8') as f:
            _escribir(f)
        print(f'✅ Guardado como: {os.path.abspath(nombre_alternativo)}')
        print(f'   ⚠️  "{ruta}" seguía bloqueado — probablemente lo tienes')
        print('   abierto AHORA MISMO en otro programa (Excel, Bloc de notas...).')
        print(f'   Ciérralo y renombra "{nombre_alternativo}" a "{ruta}".')
        return True
    except PermissionError:
        print()
        print(f'❌ No se pudo guardar "{ruta}" con ningún nombre. Esto casi')
        print('   siempre significa que la carpeta actual tiene restricciones')
        print('   de escritura (permisos de Windows, antivirus, o la carpeta')
        print('   está sincronizada con OneDrive y bloqueada temporalmente).')
        print()
        print('   SOLUCIÓN: copia este script a una carpeta nueva y simple,')
        print('   por ejemplo C:\\licencias\\ (créala si no existe), y ejecútalo')
        print('   desde ahí.')
        return False


# ══════════════════════════════════════════════════════
# CATALUÑA — Registre de Turisme de Catalunya
# Fuente: analisi.transparenciacatalunya.cat — plataforma Socrata (API
# muy estandarizada, la usan cientos de portales de datos abiertos del
# mundo). El PATRÓN de la URL sí está confirmado (es el estándar de
# Socrata: /resource/{id}.json), pero NO pude comprobar yo mismo los
# nombres reales de los campos — mapeo a ciegas con nombres razonables
# en catalán/castellano + diagnóstico, igual que hicimos al principio
# con Madrid y Andalucía. Probablemente haga falta un ajuste tras la
# primera prueba.
# ══════════════════════════════════════════════════════
def descargar_cataluna():
    print('\n→ Cataluña (Registre de Turisme)...')
    BASE = 'https://analisi.transparenciacatalunya.cat/resource/t2h3-cgys.json'
    PAGINA = 50000  # tamaño de cada página

    todos_raw = []
    offset = 0
    while True:
        url = f'{BASE}?$limit={PAGINA}&$offset={offset}'
        texto = descargar_texto(url, timeout=60)
        if not texto:
            print(f'  [Cataluña] fallo descargando offset={offset}, seguimos con lo que ya tenemos')
            break
        try:
            pagina_datos = json.loads(texto)
        except json.JSONDecodeError as e:
            print(f'  [Cataluña] respuesta no es JSON válido en offset={offset}: {e}')
            break

        if not isinstance(pagina_datos, list) or not pagina_datos:
            break  # ya no hay más páginas

        todos_raw.extend(pagina_datos)
        print(f'  [Cataluña] offset={offset}: +{len(pagina_datos)} (acumulado: {len(todos_raw)})')

        if len(pagina_datos) < PAGINA:
            break  # última página (llegó incompleta = no hay más)
        offset += PAGINA
        time.sleep(1)  # pequeña pausa entre páginas, cortesía con el servidor

    if not todos_raw:
        print('  Cataluña: 0 registros')
        return []

    print(f'  [DIAGNÓSTICO] Campos reales del primer registro: {list(todos_raw[0].keys())}')

    try:
        registros = []
        for item in todos_raw:
            # Nombres de campo CONFIRMADOS con datos reales. Ojo: Socrata
            # generó estos nombres recortando tildes/ñ de forma un poco
            # rara ('r_tol' = "rètol" = nombre comercial en catalán,
            # 'n_mero_inscripci' = "número d'inscripció", 'prov_ncia' =
            # "província").
            def val(campo):
                v = item.get(campo)
                return clean(v) if v is not None else ''

            municipio = val('municipi').upper()

            # La dirección viene troceada — la unimos
            direccion = ' '.join(p for p in [val('tipus_de_via'), val('nom_de_la_via'), val('numero')] if p)

            registros.append({
                'destino': calcular_destino(municipio),
                'provincia': val('prov_ncia').upper(),
                'municipio': municipio,
                'tipo': val('tipus_establiment'),
                'categoria': val('categoria'),
                'registro': val('n_mero_inscripci'),
                'nombre': val('r_tol'),
                'direccion': direccion,
                'cp': val('codi_postal'),
                'hab': item.get('total_estances') or '',
                'plazas': item.get('total_places') or '',
            })

        print(f'  Cataluña: {len(registros)} registros procesados')
        if registros:
            print(f'  Ejemplo primera fila: {registros[0]}')
        return registros

    except Exception as e:
        print(f'  Error procesando datos de Cataluña: {e}')
        return []


# ══════════════════════════════════════════════════════
# COMUNIDAD VALENCIANA — Registre de Turisme (hoteles)
# Fuente: dadesobertes.gva.es — CKAN oficial. El nombre del archivo CSV
# lleva la fecha de la última actualización pegada (ej. "listarthoteles_
# 20250126.csv"), así que en vez de fijar una fecha que se quedaría vieja,
# usamos la API package_show para que el script encuentre SOLO el enlace
# de descarga actual, sea cual sea la fecha en ese momento.
# No pude comprobar yo mismo el CSV real (igual que Cataluña la primera
# vez) — mapeo razonado + diagnóstico.
# ══════════════════════════════════════════════════════
def descargar_valencia():
    print('\n→ Comunidad Valenciana (hoteles)...')
    url_api = 'https://dadesobertes.gva.es/api/3/action/package_show?id=dades-turisme-hotels-comunitat-valenciana'

    texto_api = descargar_texto(url_api, timeout=30)
    if not texto_api:
        print('  C. Valenciana: 0 registros (fallo al consultar el catálogo)')
        return []

    try:
        info = json.loads(texto_api)
        recursos = info.get('result', {}).get('resources', [])
        url_csv = None
        for r in recursos:
            formato = (r.get('format') or '').upper()
            nombre = (r.get('name') or '').lower()
            if formato == 'CSV' and ('hotel' in nombre or 'últim' in nombre or 'ultimo' in nombre or not url_csv):
                url_csv = r.get('url')
                if 'hotel' in nombre:
                    break  # el más específico, nos quedamos con este

        if not url_csv:
            print(f'  [DIAGNÓSTICO] No se encontró recurso CSV. Recursos disponibles: '
                  f'{[(r.get("name"), r.get("format")) for r in recursos]}')
            return []

        print(f'  [C. Valenciana] URL de descarga encontrada dinámicamente: {url_csv}')

    except Exception as e:
        print(f'  Error consultando el catálogo de C. Valenciana: {e}')
        return []

    texto = descargar_texto(url_csv, timeout=60)
    if not texto:
        print('  C. Valenciana: 0 registros (fallo de descarga del CSV)')
        return []

    try:
        muestra = texto[:2000]
        separador = ';' if muestra.count(';') > muestra.count(',') else ','
        lector = csv.DictReader(io.StringIO(texto), delimiter=separador)

        print(f'  [DIAGNÓSTICO] Separador: {separador!r}')
        print(f'  [DIAGNÓSTICO] Columnas reales del CSV: {lector.fieldnames}')

        registros = []
        for fila in lector:
            # Normalizamos SIN tildes (normalizar() ya lo hace) para no
            # depender de si la fuente escribe "categoría" o "categoria" —
            # así encajan las claves pase lo que pase con los acentos.
            fila_norm = {normalizar(k).lstrip('\ufeff'): v for k, v in fila.items()}

            def val(*campos):
                for c in campos:
                    v = fila_norm.get(c)
                    if v:
                        return clean(v)
                return ''

            municipio = val('municipio', 'municipi', 'localidad').upper()

            # La dirección puede venir en un solo campo, o troceada en
            # tipo de vía + vía + número — probamos el campo completo
            # primero, y si viene vacío, la componemos.
            direccion = val('direccion', 'domicilio')
            if not direccion:
                partes = [val('tipo via'), val('via'), val('numero')]
                direccion = ' '.join(p for p in partes if p)

            registros.append({
                'destino': calcular_destino(municipio),
                'provincia': val('provincia', 'provincia_nombre').upper(),
                'municipio': municipio,
                'tipo': val('grupo', 'tipo', 'modalidad'),
                'categoria': val('categoria', 'categoria_nombre'),
                'registro': val('signatura', 'numero_registro', 'codigo', 'nrt', 'expediente'),
                'nombre': val('nombre', 'denominacion', 'razon_comercial'),
                'direccion': direccion,
                'cp': val('cp', 'codigo_postal'),
                'hab': fila_norm.get('habitaciones') or fila_norm.get('unidades') or '',
                'plazas': fila_norm.get('plazas') or fila_norm.get('capacidad') or '',
            })

        print(f'  C. Valenciana: {len(registros)} registros procesados')
        if registros:
            print(f'  Ejemplo primera fila: {registros[0]}')
        return registros

    except Exception as e:
        print(f'  Error procesando CSV de C. Valenciana: {e}')
        return []


# ══════════════════════════════════════════════════════
# PAÍS VASCO — Hoteles de Euskadi (REATE)
# Fuente: opendata.euskadi.eus — JSON directo, URL fija (sin fecha, se
# actualiza sola cada día). Confirmado con datos reales.
# Cubre Bilbao y San Sebastián — los 2 últimos destinos que faltaban.
#
# OJO con esta fuente en concreto: el JSON tiene claves DUPLICADAS
# ('address' y 'phone' aparecen dos veces por registro — la primera con
# el dato real, la segunda vacía). Si lo parseamos con json.loads normal,
# Python se queda con la ÚLTIMA aparición (la vacía) y perdemos el dato
# real. Por eso usamos un object_pairs_hook que se queda con el primer
# valor no vacío que encuentre para cada clave.
# ══════════════════════════════════════════════════════
def _hook_primer_valor_no_vacio(pares):
    d = {}
    for k, v in pares:
        if k not in d or not d[k]:
            d[k] = v
    return d


def descargar_euskadi():
    print('\n→ País Vasco (Hoteles de Euskadi)...')
    url = 'https://opendata.euskadi.eus/contenidos/ds_recursos_turisticos/hoteles_de_euskadi/opendata/alojamientos.json'

    texto = descargar_texto(url, timeout=60)
    if not texto:
        print('  País Vasco: 0 registros (fallo de descarga)')
        return []

    try:
        datos = json.loads(texto, object_pairs_hook=_hook_primer_valor_no_vacio)

        if not isinstance(datos, list) or not datos:
            print(f'  [DIAGNÓSTICO] Estructura inesperada: {type(datos)}')
            return []

        print(f'  [DIAGNÓSTICO] Campos reales del primer registro: {list(datos[0].keys())}')

        registros = []
        for item in datos:
            def val(campo):
                v = item.get(campo)
                return clean(v) if v is not None else ''

            municipio_completo = val('municipality')

            # San Sebastián viene como "Donostia / San Sebastián" (nombre
            # bilingüe) — probamos el nombre completo primero, y si no
            # encaja, cada mitad por separado.
            destino = calcular_destino(municipio_completo)
            if not destino and '/' in municipio_completo:
                for parte in municipio_completo.split('/'):
                    destino = calcular_destino(parte.strip())
                    if destino:
                        break

            registros.append({
                'destino': destino,
                'provincia': val('territory').upper(),  # Bizkaia/Gipuzkoa/Araba
                'municipio': municipio_completo.upper(),
                'tipo': val('lodgingType'),
                'categoria': val('category'),
                'registro': val('signatura'),
                'nombre': val('documentName'),
                'direccion': val('address'),
                'cp': val('postalCode'),
                'hab': '',  # esta fuente no publica nº de habitaciones, solo plazas
                'plazas': val('capacity'),
            })

        print(f'  País Vasco: {len(registros)} registros procesados')
        if registros:
            print(f'  Ejemplo primera fila: {registros[0]}')
        return registros

    except json.JSONDecodeError as e:
        print(f'  Error: la respuesta no es JSON válido ({e})')
        return []
    except Exception as e:
        print(f'  Error procesando datos de País Vasco: {e}')
        return []


# ══════════════════════════════════════════════════════
# GALICIA — Directorio de alojamientos del REAT
# Fuente: descargascdn.xunta.gal — CSV directo, confirmado con datos
# reales. Cubre TODOS los tipos en un único archivo (albergues, hoteles,
# apartamentos, pensiones, casas rurales...) — como Cataluña.
#
# Ninguna de tus 15 ciudades objetivo está en Galicia, así que este
# aporta 0 al 'licencias.json' filtrado — pero sí suma al
# 'licencias_completo.json' nacional, que es lo que buscabas.
#
# OJO con esta fuente: el CSV tiene varias líneas de cabecera decorativa
# ANTES de la fila real de columnas (título, fecha de referencia...).
# Hay que saltarlas hasta encontrar la línea que empieza por "signatura".
# ══════════════════════════════════════════════════════
def descargar_galicia():
    print('\n→ Galicia (REAT)...')
    url = 'https://descargascdn.xunta.gal/interno/smarxa/reat_directorio-alojamientos_esp.csv'

    texto = descargar_texto(url, timeout=90)  # archivo grande, más margen
    if not texto:
        print('  Galicia: 0 registros (fallo de descarga)')
        return []

    try:
        lineas = texto.splitlines()
        inicio = None
        for i, linea in enumerate(lineas):
            if linea.strip().lower().startswith('"signatura"'):
                inicio = i
                break

        if inicio is None:
            print(f'  [DIAGNÓSTICO] No se encontró la fila de cabecera real. '
                  f'Primeras 5 líneas: {lineas[:5]}')
            return []

        texto_limpio = '\n'.join(lineas[inicio:])
        lector = csv.DictReader(io.StringIO(texto_limpio), delimiter=';')

        print(f'  [DIAGNÓSTICO] Columnas reales del CSV: {lector.fieldnames}')

        registros = []
        for fila in lector:
            fila_norm = {clean(k).lower().lstrip('\ufeff'): v for k, v in fila.items()}

            def val(campo):
                v = fila_norm.get(campo)
                # Reparamos mojibake AQUÍ: es un fallo del propio CSV de
                # origen (algunas celdas, sobre todo 'tipo', vienen con el
                # texto codificado en UTF-8 dos veces — p.ej. 'TURÍSTICOS'
                # llega como 'TURÃ\x8dSTICOS'), no de cómo decodificamos
                # el fichero completo (por eso 'A CORUÑA' sale bien en la
                # misma fila). Ver reparar_mojibake() para el detalle.
                return reparar_mojibake(clean(v)) if v else ''

            municipio = val('municipio').upper()

            registros.append({
                'destino': calcular_destino(municipio),  # casi siempre vacío: Galicia no está en tu targeting
                'provincia': val('provincia').upper(),
                'municipio': municipio,
                'tipo': val('tipo'),
                'categoria': val('categoria') or val('modalidad'),
                'registro': val('signatura'),
                'nombre': val('denominacion'),
                'direccion': val('direccion'),
                'cp': val('codigo_postal'),
                'hab': val('habitaciones'),
                'plazas': val('plazas'),
            })

        print(f'  Galicia: {len(registros)} registros procesados')
        if registros:
            print(f'  Ejemplo primera fila: {registros[0]}')
        return registros

    except Exception as e:
        print(f'  Error procesando CSV de Galicia: {e}')
        return []


# ══════════════════════════════════════════════════════
# CASTILLA Y LEÓN — Registro de alojamientos hoteleros
# Fuente: opendata.jcyl.es — CSV directo. Confirmé la URL real (redirige
# desde el portal de datos abiertos), pero NO pude ver el contenido en
# texto (llegó en binario, probablemente por su codificación) — mapeo
# razonado + diagnóstico, igual que hicimos con Cataluña la primera vez.
# ══════════════════════════════════════════════════════
def descargar_castillayleon():
    print('\n→ Castilla y León (alojamientos hoteleros)...')
    url = 'https://opendata.jcyl.es/ficheros/cct/retu/alojamientoshoteleros.csv'

    texto = descargar_texto(url, timeout=60)
    if not texto:
        print('  Castilla y León: 0 registros (fallo de descarga)')
        return []

    try:
        muestra = texto[:2000]
        separador = ';' if muestra.count(';') > muestra.count(',') else ','
        lector = csv.DictReader(io.StringIO(texto), delimiter=separador)

        print(f'  [DIAGNÓSTICO] Separador: {separador!r}')
        print(f'  [DIAGNÓSTICO] Columnas reales del CSV: {lector.fieldnames}')

        registros = []
        for fila in lector:
            fila_norm = {normalizar(k).lstrip('\ufeff'): v for k, v in fila.items()}

            def val(*campos):
                for c in campos:
                    v = fila_norm.get(c)
                    if v:
                        return clean(v)
                return ''

            municipio = val('municipio', 'localidad').upper()

            registros.append({
                'destino': calcular_destino(municipio),
                'provincia': val('provincia').upper(),
                'municipio': municipio,
                'tipo': val('tipo', 'grupo', 'modalidad'),
                'categoria': val('categoria'),
                'registro': val('n.registro', 'numero registro', 'codigo', 'nrt', 'inscripcion'),
                'nombre': val('nombre', 'denominacion'),
                'direccion': val('direccion', 'domicilio'),
                'cp': val('c.postal', 'cp', 'codigo postal'),
                'hab': fila_norm.get('habitaciones') or fila_norm.get('num habitaciones') or '',
                'plazas': fila_norm.get('plazas') or fila_norm.get('num plazas') or '',
            })

        print(f'  Castilla y León: {len(registros)} registros procesados')
        if registros:
            print(f'  Ejemplo primera fila: {registros[0]}')
        return registros

    except Exception as e:
        print(f'  Error procesando CSV de Castilla y León: {e}')
        return []


# ══════════════════════════════════════════════════════
# ARAGÓN — Alojamientos hoteleros en la Comunidad Autónoma de Aragón
# Fuente: opendata.aragon.es — JSON directo. Confirmé la URL real (via
# datos.gob.es), pero NO pude ver el contenido (robots.txt me bloqueó el
# acceso) — mapeo razonado + diagnóstico, como con Cataluña la 1ª vez.
# ══════════════════════════════════════════════════════
# Aragón solo tiene 3 provincias — código INE fijo, no cambia nunca.
_PROVINCIAS_ARAGON_POR_CODIGO_INE = {
    '22': 'HUESCA',
    '44': 'TERUEL',
    '50': 'ZARAGOZA',
}


def descargar_aragon():
    print('\n→ Aragón (alojamientos hoteleros)...')
    url = ('https://opendata.aragon.es/GA_OD_Core/download?resource_id=65'
           '&formato=json&name=Alojamientos+hoteleros+en+la+Comunidad+Aut%C3%B3noma+de+Arag%C3%B3n')

    texto = descargar_texto(url, timeout=60)
    if not texto:
        print('  Aragón: 0 registros (fallo de descarga)')
        return []

    try:
        datos = json.loads(texto)

        # La API puede devolver la lista directamente, o envuelta en una
        # clave tipo 'result'/'data'/'items'/'records' — probamos varias.
        if isinstance(datos, dict):
            for clave in ('result', 'data', 'items', 'records', 'features'):
                if clave in datos and isinstance(datos[clave], list):
                    datos = datos[clave]
                    break

        if not isinstance(datos, list) or not datos:
            print(f'  [DIAGNÓSTICO] Estructura inesperada. Tipo: {type(datos)}. '
                  f'Primeros 500 caracteres: {texto[:500]}')
            return []

        print(f'  [DIAGNÓSTICO] Campos reales del primer registro: {list(datos[0].keys())}')

        registros = []
        for item in datos:
            item_norm = {clave_normalizada(k): v for k, v in item.items()}

            def val(*campos):
                for c in campos:
                    v = item_norm.get(c)
                    if v not in (None, ''):
                        return clean(v)
                return ''

            # Nombres de campo CONFIRMADOS con datos reales (run del
            # 2026-09-02): el registro trae 'nombre_alojamiento',
            # 'signatura' (nº registro), 'tot_hab' (habitaciones),
            # 'numero_plazas'. OJO: el campo llamado literalmente
            # 'categoria' contiene el TIPO de alojamiento (p.ej.
            # 'Hostal'), no la categoría por estrellas — la categoría
            # real de estrellas está en 'categoria_alojamiento'.
            #
            # OJO 2 — confirmado con la 2ª prueba real: 'municipio_esta-
            # blecimiento' y 'provincia_establecimiento' NO son nombres,
            # son CÓDIGOS numéricos (p.ej. provincia='50', municipio=
            # '251' — códigos INE). El nombre de la localidad en texto
            # viene en 'localidad_establecimiento'. Para la provincia no
            # hay ningún campo de texto en todo el dataset — pero Aragón
            # solo tiene 3 provincias con código INE fijo y conocido, así
            # que lo resolvemos con una tabla fija en vez de adivinar.
            municipio = val('localidad_establecimiento', 'municipio_establecimiento').upper()
            cod_provincia = val('provincia_establecimiento')

            registros.append({
                'destino': calcular_destino(municipio),
                'provincia': _PROVINCIAS_ARAGON_POR_CODIGO_INE.get(cod_provincia, cod_provincia).upper(),
                'municipio': municipio,
                'tipo': val('categoria', 'grupo'),
                'categoria': val('categoria_alojamiento', 'subgrupo'),
                'registro': val('signatura'),
                'nombre': val('nombre_alojamiento'),
                'direccion': val('direccion_establecimiento'),
                'cp': val('codigo_postal_establecimiento'),
                'hab': item_norm.get('tot_hab') or '',
                'plazas': item_norm.get('numero_plazas') or '',
            })

        print(f'  Aragón: {len(registros)} registros procesados')
        if registros:
            print(f'  Ejemplo primera fila: {registros[0]}')
        return registros

    except json.JSONDecodeError as e:
        print(f'  Error: la respuesta no es JSON válido ({e}). '
              f'Primeros 300 caracteres: {texto[:300]}')
        return []
    except Exception as e:
        print(f'  Error procesando datos de Aragón: {e}')
        return []


# ══════════════════════════════════════════════════════
# EXTREMADURA — Alojamientos hoteleros de la Junta de Extremadura
# Fuente: www.juntaex.es — CSV directo, URL confirmada via datos.gob.es
# (la propia página del portal nacional lista el enlace real, aunque no
# he podido ver el contenido del CSV en sí — mapeo razonado + diagnóstico).
# Ninguna de tus 15 ciudades objetivo está en Extremadura, así que esto
# no aporta nada a licencias.json (el filtrado), pero sí suma al
# licencias_completo.json nacional.
# ══════════════════════════════════════════════════════
def descargar_extremadura():
    print('\n→ Extremadura (alojamientos hoteleros)...')
    url = 'https://www.juntaex.es/documents/77055/5801338/AlojamientosHoteleros.csv'

    texto = descargar_texto(url, timeout=60)
    if not texto:
        print('  Extremadura: 0 registros (fallo de descarga)')
        return []

    try:
        muestra = texto[:2000]
        separador = ';' if muestra.count(';') > muestra.count(',') else ','
        lector = csv.DictReader(io.StringIO(texto), delimiter=separador)

        print(f'  [DIAGNÓSTICO] Separador: {separador!r}')
        print(f'  [DIAGNÓSTICO] Columnas reales del CSV: {lector.fieldnames}')

        registros = []
        for fila in lector:
            fila_norm = {clave_normalizada(k): v for k, v in fila.items()}

            def val(*campos):
                for c in campos:
                    v = fila_norm.get(c)
                    if v:
                        return clean(v)
                return ''

            # Columnas REALES confirmadas (run 2026-09-02): no hay campo
            # de nº de registro/signatura en este CSV — se queda vacío
            # siempre, no es un fallo nuestro, la fuente no lo publica.
            municipio = val('municipio').upper()

            registros.append({
                'destino': calcular_destino(municipio),
                'provincia': val('provincia').upper() or 'EXTREMADURA',
                'municipio': municipio,
                'tipo': val('tipo recurso'),
                'categoria': val('categoria'),
                'registro': '',  # esta fuente no publica nº de registro
                'nombre': val('nombre establecimiento'),
                'direccion': val('direccion'),
                'cp': val('c. postal'),
                'hab': fila_norm.get('total nº habitaciones') or '',
                'plazas': fila_norm.get('total nº plazas') or '',
            })

        print(f'  Extremadura: {len(registros)} registros procesados')
        if registros:
            print(f'  Ejemplo primera fila: {registros[0]}')
        return registros

    except Exception as e:
        print(f'  Error procesando CSV de Extremadura: {e}')
        return []


# ══════════════════════════════════════════════════════
# CASTILLA-LA MANCHA — Establecimientos hoteleros
# Fuente: datosabiertos.castillalamancha.es — CSV directo, URL confirmada
# via datos.gob.es. Igual que Extremadura, ninguna de tus 15 ciudades
# está aquí, así que solo suma al archivo nacional.
# ══════════════════════════════════════════════════════
def descargar_castillalamancha():
    print('\n→ Castilla-La Mancha (establecimientos hoteleros)...')
    url = 'https://datosabiertos.castillalamancha.es/sites/datosabiertos.castillalamancha.es/files/Hoteles.csv'

    texto = descargar_texto(url, timeout=60)
    if not texto:
        print('  Castilla-La Mancha: 0 registros (fallo de descarga)')
        return []

    try:
        muestra = texto[:2000]
        separador = ';' if muestra.count(';') > muestra.count(',') else ','
        lector = csv.DictReader(io.StringIO(texto), delimiter=separador)

        print(f'  [DIAGNÓSTICO] Separador: {separador!r}')
        print(f'  [DIAGNÓSTICO] Columnas reales del CSV: {lector.fieldnames}')

        registros = []
        for fila in lector:
            # OJO con esta fuente: la cabecera 'Tipo Establecimiento' viene
            # con un SALTO DE LÍNEA literal dentro ('Tipo\nEstablecimiento')
            # — clave_normalizada() lo colapsa a un espacio normal antes de
            # normalizar, si no, nunca encontraríamos esta columna.
            fila_norm = {clave_normalizada(k): v for k, v in fila.items()}

            def val(*campos):
                for c in campos:
                    v = fila_norm.get(c)
                    if v:
                        return clean(v)
                return ''

            municipio = val('municipio').upper()

            registros.append({
                'destino': calcular_destino(municipio),
                'provincia': val('provincia').upper(),
                'municipio': municipio,
                'tipo': val('tipo establecimiento'),
                'categoria': val('categoria'),
                'registro': '',  # esta fuente no publica nº de registro
                'nombre': val('nombre establecimiento'),
                'direccion': val('direccion establecimiento'),
                'cp': val('codigo postal establecimiento'),
                'hab': '',  # esta fuente solo da el total de plazas, no habitaciones
                'plazas': fila_norm.get('total plazas') or '',
            })

        print(f'  Castilla-La Mancha: {len(registros)} registros procesados')
        if registros:
            print(f'  Ejemplo primera fila: {registros[0]}')
        return registros

    except Exception as e:
        print(f'  Error procesando CSV de Castilla-La Mancha: {e}')
        return []


# ══════════════════════════════════════════════════════
# NAVARRA — Registro de Turismo de Navarra (alojamientos)
# Fuente: datosabiertos.navarra.es — API CKAN estándar (datastore/dump),
# JSON limpio, se actualiza A DIARIO. La mejor fuente de las nuevas: URL
# confirmada, formato CKAN muy predecible (clave 'records' con lista de
# dicts, 'fields' con los nombres reales de columna).
# ══════════════════════════════════════════════════════
def descargar_navarra():
    print('\n→ Navarra (Registro de Turismo)...')
    url = ('https://datosabiertos.navarra.es/datastore/dump/'
           '5527debf-7e72-4f9e-8e12-b562f3027fc2?format=json&bom=True')

    texto = descargar_texto(url, timeout=60)
    if not texto:
        print('  Navarra: 0 registros (fallo de descarga)')
        return []

    try:
        # El parámetro '&bom=True' de la URL (lo copiamos tal cual del
        # enlace de datos.gob.es) le pide al servidor que incluya la
        # marca BOM (\ufeff) al principio del JSON — Python no la digiere
        # con json.loads tal cual, hay que quitarla primero.
        datos_raw = json.loads(texto.lstrip('\ufeff'))

        # CONFIRMADO con el run real: el JSON viene como un diccionario
        # con DOS claves separadas — 'fields' (los nombres de columna,
        # cada uno como {"id": "nombre_campo", "type": "..."}) y
        # 'records' (los datos, como lista de LISTAS posicionales, SIN
        # nombres). Mi primer intento solo cogía 'records' y tiraba
        # 'fields' a la basura — por eso perdíamos los nombres de columna
        # y acabábamos usando la primera fila de datos como si fueran
        # cabeceras (de ahí el desastre de la vez anterior).
        campos_meta = None
        if isinstance(datos_raw, dict):
            campos_meta = datos_raw.get('fields')
            for clave in ('records', 'result', 'data'):
                if clave in datos_raw and isinstance(datos_raw[clave], list):
                    datos = datos_raw[clave]
                    break
            else:
                datos = datos_raw
        else:
            datos = datos_raw

        if not isinstance(datos, list) or not datos:
            print(f'  [DIAGNÓSTICO] Estructura inesperada: {type(datos)}. '
                  f'Primeros 500 caracteres: {texto[:500]}')
            return []

        if isinstance(datos[0], list):
            if campos_meta:
                # Caso normal de CKAN: nombres de columna en 'fields'.
                cabeceras = [c.get('id') if isinstance(c, dict) else str(c)
                             for c in campos_meta]
            elif isinstance(datos[0][0], list):
                cabeceras = datos[0]
                datos = datos[1:]
            else:
                print('  [DIAGNÓSTICO] Los datos vienen como listas de '
                      'valores pero no hay ninguna metadata de nombres de '
                      'columna en la respuesta — no se puede mapear con '
                      'certeza. Primeros 500 caracteres: ' + texto[:500])
                return []
            datos = [dict(zip(cabeceras, fila)) for fila in datos]

        if not datos:
            print('  [DIAGNÓSTICO] 0 filas de datos tras el parseo.')
            return []

        print(f'  [DIAGNÓSTICO] Campos reales del primer registro: {list(datos[0].keys())}')

        registros = []
        for item in datos:
            item_norm = {clave_normalizada(k): v for k, v in item.items()}

            def val(*campos):
                for c in campos:
                    v = item_norm.get(c)
                    if v not in (None, ''):
                        return clean(v)
                return ''

            municipio = val('municipio', 'localidad', 'poblacion')

            registros.append({
                'destino': calcular_destino(municipio.upper()),
                'provincia': 'NAVARRA',
                'municipio': municipio.upper(),
                'tipo': val('modalidad', 'tipo', 'clase'),
                'categoria': val('categoria'),
                'registro': val('cod_inscripcion', 'numregistro', 'n.registro', 'codigo', 'signatura', 'id'),
                'nombre': val('nombre', 'denominacion', 'nombrecomercial'),
                'direccion': val('direccion', 'domicilio'),
                'cp': val('codigo_postal', 'cp', 'codigopostal'),
                'hab': item_norm.get('habitaciones') or '',
                'plazas': item_norm.get('plazas') or item_norm.get('capacidad') or '',
            })

        print(f'  Navarra: {len(registros)} registros procesados')
        if registros:
            print(f'  Ejemplo primera fila: {registros[0]}')
        return registros

    except json.JSONDecodeError as e:
        print(f'  Error: la respuesta no es JSON válido ({e})')
        return []
    except Exception as e:
        print(f'  Error procesando datos de Navarra: {e}')
        return []


# ══════════════════════════════════════════════════════
# BALEARES — Mallorca (Registro Insular de Empresas, Actividades y
# Establecimientos Turísticos)
# Fuente: intranet.caib.es/opendatacataleg — CSV directo, actualización
# DIARIA. OJO: Baleares NO tiene un registro único autonómico — cada
# isla lleva el suyo por separado (Consell Insular). Esto es SOLO
# Mallorca; Menorca tiene su propio dataset (pendiente), y no encontré
# datos abiertos equivalentes para Eivissa/Formentera todavía.
# ══════════════════════════════════════════════════════
def descargar_baleares_mallorca():
    print('\n→ Baleares — Mallorca (alojamientos turísticos)...')
    url = ('https://intranet.caib.es/opendatacataleg/files/dataset/'
           'allotjaments_turistics_mallorca/allotjaments_turistics_mallorca.csv')

    texto = descargar_texto(url, timeout=60)
    if not texto:
        print('  Mallorca: 0 registros (fallo de descarga)')
        return []

    try:
        muestra = texto[:2000]
        separador = ';' if muestra.count(';') > muestra.count(',') else ','
        lector = csv.DictReader(io.StringIO(texto), delimiter=separador)

        print(f'  [DIAGNÓSTICO] Separador: {separador!r}')
        print(f'  [DIAGNÓSTICO] Columnas reales del CSV: {lector.fieldnames}')

        registros = []
        for fila in lector:
            fila_norm = {clave_normalizada(k): v for k, v in fila.items()}

            def val(*campos):
                for c in campos:
                    v = fila_norm.get(c)
                    if v:
                        return clean(v)
                return ''

            # Columnas REALES confirmadas (run 2026-09-02, en catalán):
            # 'Grup'/'Subgrup' (tipo), 'Denominació comercial' (nombre),
            # 'Direcció' (dirección), 'Categoria' (categoría — puede
            # venir vacía en tipos de alojamiento sin clasificación por
            # estrellas, no es un fallo). No hay columna de código postal
            # en esta fuente, se queda vacío siempre. 'Unitats' es lo más
            # parecido a habitaciones que publican (nº de unidades de
            # alojamiento, no necesariamente habitaciones individuales).
            municipio = val('municipi').upper()

            registros.append({
                'destino': calcular_destino(municipio),
                'provincia': 'ILLES BALEARS',
                'municipio': municipio,
                'tipo': val('grup', 'subgrup'),
                'categoria': val('categoria'),
                'registro': val('signatura'),
                'nombre': val('denominacio comercial'),
                'direccion': val('direccio'),
                'cp': '',  # esta fuente no publica código postal
                'hab': fila_norm.get('unitats') or '',
                'plazas': fila_norm.get('places') or '',
            })

        print(f'  Mallorca: {len(registros)} registros procesados')
        if registros:
            print(f'  Ejemplo primera fila: {registros[0]}')
        return registros

    except Exception as e:
        print(f'  Error procesando CSV de Mallorca: {e}')
        return []


# ══════════════════════════════════════════════════════
# MURCIA — turismoregiondemurcia.es
# Fuente CONFIRMADA con diagnóstico real del formulario (no adivinada):
# POST a /es/etudoc.parser/ con 3 campos:
#   vtip      = código del tipo de establecimiento (ver _MURCIA_TIPOS)
#   vmuni     = código de municipio, o '' para "Todas" (confirmado en <select>)
#   documento = 'xls' | 'doc' | 'html'  → pedimos 'xls'
# El formulario no tiene botón "submit" nativo (el "Buscar" es
# type='button', se envía por JS) — replicamos la misma petición POST
# directamente con requests, sin necesidad de navegador.
#
# OJO: no sabemos con certeza si 'documento=xls' nos devuelve un .xlsx
# moderno o un .xls antiguo (formato binario BIFF) — _parsear_excel_murcia()
# prueba primero como .xlsx y si falla cae a .xls, así que no hace falta
# adivinarlo a mano.
#
# Solo pedimos los tipos que son alojamiento turístico de verdad (excluimos
# agencias de viajes, oficinas de turismo, guías, organizadores de
# congresos... — igual que el resto de CCAA, esto es sobre PLAZAS/CAMAS,
# no sobre negocios turísticos en general).
# ══════════════════════════════════════════════════════
_MURCIA_TIPOS = {
    '1': 'ESTABLECIMIENTOS HOTELEROS',
    '2': 'APARTAMENTOS TURÍSTICOS',
    '6': 'VIVIENDAS DE USO TURÍSTICO',
    '7': 'CAMPINGS',
    '3': 'CASAS RURALES DE ALQUILER',
    '4': 'CASAS RURALES EN REGIMEN COMPARTIDO',
    '5': 'HOSPEDERÍAS RURALES',
    '14': 'ALBERGUES / HOSTELS',
}


def _parsear_tabla_html_murcia(contenido_bytes):
    """El servidor de Murcia devuelve el 'Excel' como una tabla HTML con
    content-type mentiroso (dice application/vnd.ms-excel pero el
    contenido empieza por '<!DOCTYPE') — es un truco típico de portales
    antiguos: Excel abre tablas HTML si les pones extensión .xls.

    OJO (confirmado con el run real: todo salía "0 filas"): páginas HTML
    de este estilo casi siempre tienen VARIAS <table> anidadas — una para
    maquetación (menús, cabeceras...) y, dentro o al lado, la tabla de
    datos de verdad. Coger la PRIMERA <table> a ciegas (como hacía antes)
    era el problema. Ahora puntuamos todas las tablas por cuántas filas
    "con pinta de datos" tienen (≥3 celdas) y nos quedamos con la mejor,
    imprimiendo el diagnóstico para poder ajustar si hiciera falta."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        print('  ⚠️  Falta instalar beautifulsoup4: pip install beautifulsoup4')
        return None

    try:
        texto = contenido_bytes.decode('utf-8')
    except UnicodeDecodeError:
        texto = contenido_bytes.decode('windows-1252', errors='replace')

    # 'lxml' (motor en C) es mucho más rápido que el 'html.parser' por
    # defecto de Python cuando la tabla tiene miles de filas (Viviendas
    # de Uso Turístico llega a 12.000+) — probablemente el cuello de
    # botella real no era la descarga, sino este parseo. Si no está
    # instalado, caemos de vuelta al de siempre, más lento pero sin fallar.
    try:
        soup = BeautifulSoup(texto, 'lxml')
    except Exception:
        soup = BeautifulSoup(texto, 'html.parser')
    tablas = soup.find_all('table')
    if not tablas:
        print('  ⚠️  El HTML devuelto no contiene ninguna <table>. '
              f'Primeros 300 caracteres: {texto[:300]!r}')
        return []

    candidatas = []
    for tabla in tablas:
        filas_html = tabla.find_all('tr')
        filas_con_datos = sum(
            1 for f in filas_html if len(f.find_all(['td', 'th'])) >= 3
        )
        candidatas.append((filas_con_datos, len(filas_html), tabla))

    candidatas.sort(key=lambda t: t[0], reverse=True)
    print(f'  [DIAGNÓSTICO Murcia] {len(tablas)} <table> encontradas, '
          f'filas-con-datos por tabla: {[c[0] for c in candidatas[:5]]}')

    mejor_filas_con_datos, _, mejor_tabla = candidatas[0]
    if mejor_filas_con_datos == 0:
        print('  ⚠️  Ninguna tabla parece tener filas de datos reales '
              '(todas con <3 celdas por fila).')
        return []

    filas_html = mejor_tabla.find_all('tr')
    # La cabecera puede no ser la primera <tr> si hay filas de título/
    # subtítulo por encima — cogemos la primera fila que tenga ≥3 celdas.
    idx_cabecera = next(
        (i for i, f in enumerate(filas_html) if len(f.find_all(['td', 'th'])) >= 3),
        0,
    )
    cabeceras = [clean(c.get_text()) for c in filas_html[idx_cabecera].find_all(['th', 'td'])]

    registros = []
    for fila in filas_html[idx_cabecera + 1:]:
        celdas = [clean(c.get_text()) for c in fila.find_all(['td', 'th'])]
        if not celdas or not any(celdas):
            continue
        registros.append(dict(zip(cabeceras, celdas)))
    return registros


def _parsear_excel_murcia(contenido_bytes):
    """El campo 'documento=xls' del formulario no garantiza el formato
    real del archivo devuelto. CONFIRMADO con datos reales: el servidor
    manda una tabla HTML con content-type mentiroso (dice
    'application/vnd.ms-excel' pero el contenido empieza literalmente por
    '<!DOCTYPE'). En vez de adivinar a ciegas, miramos los primeros bytes
    para saber con certeza qué formato es antes de intentar abrirlo:
      - Empieza por 'PK'          → .xlsx moderno (es un ZIP) → openpyxl
      - Empieza por el magic OLE2 → .xls antiguo (BIFF)        → xlrd
      - Empieza por '<'/'\\ufeff<' → tabla HTML disfrazada       → bs4
    Devuelve una lista de diccionarios (cabecera real → valor), o None si
    no se pudo interpretar de ninguna forma."""
    cabecera_bytes = contenido_bytes[:16].lstrip(b'\xef\xbb\xbf')  # por si viene con BOM

    if cabecera_bytes.startswith(b'PK'):
        try:
            import openpyxl
            libro = openpyxl.load_workbook(io.BytesIO(contenido_bytes),
                                            read_only=True, data_only=True)
            hoja = libro.active
            filas = list(hoja.iter_rows(values_only=True))
            if not filas:
                return []
            cabeceras = [str(c) if c is not None else '' for c in filas[0]]
            return [dict(zip(cabeceras, fila)) for fila in filas[1:]]
        except ImportError:
            print('  ⚠️  Falta instalar openpyxl: pip install openpyxl')
            return None
        except Exception as e:
            print(f'  ⚠️  Parecía .xlsx pero no se pudo abrir: {e}')
            return None

    if cabecera_bytes.startswith(b'\xd0\xcf\x11\xe0'):
        try:
            import xlrd
            libro = xlrd.open_workbook(file_contents=contenido_bytes)
            hoja = libro.sheet_by_index(0)
            cabeceras = [str(hoja.cell_value(0, c)) for c in range(hoja.ncols)]
            filas = []
            for fila_idx in range(1, hoja.nrows):
                valores = [hoja.cell_value(fila_idx, c) for c in range(hoja.ncols)]
                filas.append(dict(zip(cabeceras, valores)))
            return filas
        except ImportError:
            print('  ⚠️  Falta instalar xlrd: pip install xlrd')
            return None
        except Exception as e:
            print(f'  ⚠️  Parecía .xls antiguo pero no se pudo abrir: {e}')
            return None

    if cabecera_bytes.lstrip().startswith(b'<'):
        return _parsear_tabla_html_murcia(contenido_bytes)

    print(f'  ⚠️  Formato desconocido, primeros bytes: {cabecera_bytes!r}')
    return None


def descargar_murcia():
    print('\n→ Murcia (turismoregiondemurcia.es)...')
    url = 'https://www.turismoregiondemurcia.es/es/etudoc.parser/'
    headers = {
        'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                        'AppleWebKit/537.36 (KHTML, like Gecko) '
                        'Chrome/120.0.0.0 Safari/537.36'),
    }

    from concurrent.futures import ThreadPoolExecutor, as_completed
    from requests.adapters import HTTPAdapter

    # Solo son 8 categorías — pedirlas todas a la vez en vez de una detrás
    # de otra es totalmente razonable (nada que ver con machacar 550
    # páginas de golpe). Sesión compartida para reutilizar la conexión.
    sesion = requests.Session()
    adaptador = HTTPAdapter(pool_connections=8, pool_maxsize=8)
    sesion.mount('https://', adaptador)

    def descargar_tipo(codigo_tipo, nombre_tipo, intentos=3):
        payload = {
            'vtip': codigo_tipo,
            'vmuni': '',  # confirmado: '' = "Todas" en el <select> real
            'documento': 'xls',
        }
        for intento in range(1, intentos + 1):
            try:
                r = sesion.post(url, data=payload, headers=headers, timeout=180)
                r.raise_for_status()
                break
            except Exception as e:
                if intento < intentos:
                    espera = 5 * intento
                    print(f'  {nombre_tipo}: fallo de descarga ({e}) — '
                          f'reintento {intento}/{intentos - 1} en {espera}s')
                    time.sleep(espera)
                else:
                    print(f'  {nombre_tipo}: fallo de descarga tras '
                          f'{intentos} intentos ({e})')
                    return nombre_tipo, None

        filas = _parsear_excel_murcia(r.content)
        if filas is None:
            print(f'  {nombre_tipo}: no se pudo interpretar el archivo '
                  f'devuelto ({len(r.content)} bytes, '
                  f'content-type={r.headers.get("content-type")})')
        return nombre_tipo, filas

    resultados_por_tipo = {}
    with ThreadPoolExecutor(max_workers=8) as executor:
        futuros = {
            executor.submit(descargar_tipo, codigo, nombre): nombre
            for codigo, nombre in _MURCIA_TIPOS.items()
        }
        for futuro in as_completed(futuros):
            nombre_tipo, filas = futuro.result()
            resultados_por_tipo[nombre_tipo] = filas

    registros = []
    diagnostico_mostrado = False

    # Recorremos en el orden original de _MURCIA_TIPOS (no en el orden
    # en que terminaron, que es aleatorio) para que la salida sea
    # predecible de una ejecución a otra.
    for codigo_tipo, nombre_tipo in _MURCIA_TIPOS.items():
        filas = resultados_por_tipo.get(nombre_tipo)
        if not filas:
            if filas == []:
                print(f'  {nombre_tipo}: 0 filas')
            continue

        if not diagnostico_mostrado:
            print(f'  [DIAGNÓSTICO] Columnas reales (tipo={nombre_tipo}): '
                  f'{list(filas[0].keys())}')
            diagnostico_mostrado = True

        for fila in filas:
            fila_norm = {clave_normalizada(k): v for k, v in fila.items()}

            def val(*campos):
                for c in campos:
                    v = fila_norm.get(c)
                    if v not in (None, ''):
                        return clean(v)
                return ''

            municipio = val('municipio', 'localidad').upper()

            # Columnas REALES confirmadas contra el archivo de verdad que
            # nos subiste (2026-09-03): 'N. COMERCIAL' (nombre),
            # 'C.POSTAL' (con punto pegado, sin espacio), 'Nº HAB' (con
            # el símbolo º literal), 'GRUPO' (subtipo real: Hotel/
            # Pension/Hostal...) y 'CATEGORIA' (categoría por estrellas,
            # p.ej. '1 *'). Usamos GRUPO para 'tipo' en vez de la
            # categoría genérica del formulario (nombre_tipo) porque es
            # más específico — igual que hacemos en el resto de fuentes.
            registros.append({
                'destino': calcular_destino(municipio),
                'provincia': 'MURCIA',
                'municipio': municipio,
                'tipo': val('grupo') or nombre_tipo,
                'categoria': val('categoria'),
                'registro': val('signatura', 'numregistro', 'n.registro', 'codigo'),
                'nombre': val('n. comercial', 'nombre', 'denominacion', 'establecimiento'),
                'direccion': val('direccion', 'domicilio'),
                'cp': val('c.postal', 'cp', 'codigopostal', 'codigo postal'),
                'hab': fila_norm.get('nº hab') or fila_norm.get('habitaciones') or '',
                'plazas': fila_norm.get('plazas') or fila_norm.get('numplazas') or '',
            })

        print(f'  {nombre_tipo}: {len(filas)} registros procesados')

    print(f'  Murcia (total todos los tipos): {len(registros)} registros')
    if registros:
        print(f'  Ejemplo primera fila: {registros[0]}')
    return registros


# ══════════════════════════════════════════════════════
# CANTABRIA — turismodecantabria.com (buscador oficial "Dónde alojarse")
# Fuente CONFIRMADA con diagnóstico real (no adivinada): es el buscador
# propio del portal oficial de turismo (framework Avada/Fusion Builder de
# WordPress), NO un agregador comercial. ~9.500 alojamientos, paginado
# via ?sf_paged=N — el propio HTML trae el total real de páginas en el
# atributo data-pages del contenedor <ul class="fusion-grid-posts-cards">.
#
# Cada alojamiento es un <li class="post-card"> con esta estructura de
# texto (confirmada con 2 tarjetas reales):
#   1. Nombre (dentro de <h3><a href="...">)
#   2. Dirección  (div.fusion-text-2 > p)
#   3. Municipio  (div.fusion-text-3 > p)
#   4. Tipo       (div.fusion-text-4 > p)
#   5-7. Subtipo(s), si aplica (div.fusion-text-5/6/7 > p) — vacíos si no
#
# OJO — limitación real, no un bug: esta vista de LISTADO no trae
# categoría por estrellas, código postal ni plazas/habitaciones — esos
# datos solo estarían en la ficha individual de cada alojamiento
# (visitarlas todas multiplicaría por ~17 el número de peticiones, de
# 550 páginas a más de 10.000 — lo dejamos fuera por ahora).
# ══════════════════════════════════════════════════════
def descargar_cantabria():
    print('\n→ Cantabria (turismodecantabria.com)...')
    url_base = 'https://turismodecantabria.com/descubrela/donde-alojarse-ampliada/'
    headers = {
        'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                        'AppleWebKit/537.36 (KHTML, like Gecko) '
                        'Chrome/120.0.0.0 Safari/537.36'),
    }

    try:
        from bs4 import BeautifulSoup
    except ImportError:
        print('  ⚠️  Falta instalar beautifulsoup4: pip install beautifulsoup4')
        return []

    from concurrent.futures import ThreadPoolExecutor, as_completed
    from requests.adapters import HTTPAdapter

    # Bajamos la concurrencia (25 → 8): en el run real, a partir de la
    # página ~120 el servidor empezó a cortar conexiones activamente
    # (ConnectionResetError) y acabó bloqueando hasta la resolución DNS
    # del dominio — es justo el riesgo que quería evitar. Con menos
    # hilos a la vez debería costarle más detectarnos como "ataque".
    MAX_HILOS = 8
    sesion = requests.Session()
    adaptador = HTTPAdapter(pool_connections=MAX_HILOS, pool_maxsize=MAX_HILOS)
    sesion.mount('https://', adaptador)
    sesion.mount('http://', adaptador)

    def parsear_pagina(pagina):
        """Descarga y parsea UNA página, devuelve (pagina, lista_registros,
        total_paginas_detectado_o_None, exito). 'exito=False' significa
        que la petición falló de verdad (para poder reintentarla después
        — antes no distinguíamos esto de una página legítimamente vacía)."""
        params = {} if pagina == 1 else {'sf_paged': pagina}
        try:
            r = sesion.get(url_base, params=params, headers=headers, timeout=25)
            r.raise_for_status()
        except Exception as e:
            print(f'  Página {pagina}: fallo de descarga ({e})')
            return pagina, [], None, False

        soup = BeautifulSoup(r.text, 'html.parser')

        total_detectado = None
        contenedor = soup.find('ul', class_='fusion-grid-posts-cards')
        if contenedor and contenedor.get('data-pages'):
            total_detectado = int(contenedor.get('data-pages'))

        tarjetas = soup.find_all('li', class_='post-card')
        registros_pagina = []
        for tarjeta in tarjetas:
            enlace = tarjeta.select_one('h3.fusion-title-heading a')
            nombre = clean(enlace.get_text()) if enlace else ''

            # Los textos van en orden fijo dentro de divs fusion-text-N:
            # 2=dirección, 3=municipio, 4=tipo, 5/6/7=subtipo(s) opcional
            textos_p = [clean(p.get_text()) for p in tarjeta.select('div.fusion-text p')]
            textos_p = [t for t in textos_p if t]

            direccion = textos_p[0] if len(textos_p) > 0 else ''
            municipio = textos_p[1] if len(textos_p) > 1 else ''
            tipo = textos_p[2] if len(textos_p) > 2 else ''
            subtipo = textos_p[3] if len(textos_p) > 3 else ''

            registros_pagina.append({
                'destino': calcular_destino(municipio.upper()),
                'provincia': 'CANTABRIA',
                'municipio': municipio.upper(),
                'tipo': subtipo or tipo,
                'categoria': '',
                'registro': '',
                'nombre': nombre,
                'direccion': direccion,
                'cp': '',
                'hab': '',
                'plazas': '',
            })

        return pagina, registros_pagina, total_detectado, True

    # Primero pedimos SOLO la página 1, en serie, para saber cuántas
    # páginas hay en total (data-pages) antes de lanzar el resto en
    # paralelo — así no adivinamos un rango de más o de menos.
    _, registros_pagina1, total_paginas, exito1 = parsear_pagina(1)
    if total_paginas is None:
        print('  ⚠️  No pude detectar el total de páginas — algo cambió '
              'en la web, paro aquí con solo la página 1.')
        return registros_pagina1

    print(f'  [DIAGNÓSTICO] Total de páginas detectadas: {total_paginas}')

    resultados = {1: registros_pagina1}
    pendientes = list(range(2, total_paginas + 1))

    # Hasta 4 rondas: si una página falla, la reintentamos en la
    # siguiente ronda con MENOS hilos y una pausa antes de empezar, dando
    # tiempo a que el servidor "se olvide" de nosotros si nos frenó por
    # exceso de peticiones. Cada ronda es más suave que la anterior.
    hilos_por_ronda = [MAX_HILOS, 4, 2, 1]
    espera_antes_de_ronda = [0, 8, 20, 40]

    for num_ronda, (hilos_ronda, espera) in enumerate(zip(hilos_por_ronda, espera_antes_de_ronda)):
        if not pendientes:
            break
        if espera:
            print(f'  Esperando {espera}s antes de reintentar '
                  f'{len(pendientes)} páginas fallidas (ronda {num_ronda + 1})...')
            time.sleep(espera)

        fallidas_esta_ronda = []
        with ThreadPoolExecutor(max_workers=hilos_ronda) as executor:
            futuros = {executor.submit(parsear_pagina, p): p for p in pendientes}
            completadas = 0
            for futuro in as_completed(futuros):
                pagina, registros_pagina, _, exito = futuro.result()
                if exito:
                    resultados[pagina] = registros_pagina
                else:
                    fallidas_esta_ronda.append(pagina)
                completadas += 1
                if completadas % 50 == 0 or completadas == len(pendientes):
                    acumulado = sum(len(v) for v in resultados.values())
                    print(f'  Ronda {num_ronda + 1}: {completadas}/{len(pendientes)} '
                          f'(acumulado total: {acumulado})')

        pendientes = fallidas_esta_ronda

    if pendientes:
        print(f'  ⚠️  {len(pendientes)} páginas no se pudieron descargar '
              f'tras varios intentos, se quedan fuera: {pendientes[:20]}'
              f'{"..." if len(pendientes) > 20 else ""}')

    registros = []
    for pagina in sorted(resultados.keys()):
        registros.extend(resultados[pagina])

    print(f'  Cantabria: {len(registros)} registros procesados')
    if registros:
        print(f'  Ejemplo primera fila: {registros[0]}')
    return registros


# ══════════════════════════════════════════════════════
# LA RIOJA — lariojaturismo.com/dormir (buscador oficial, plataforma GNOSS)
# Fuente CONFIRMADA con diagnóstico real: NO es solo un folleto en PDF
# (como pensábamos en la investigación inicial) — tiene un buscador
# público de verdad, con 458 alojamientos en 39 páginas.
#
# Cada alojamiento es un <div class="resource">, con el nombre en
# <h2><a>...</a></h2> y el municipio en <p class="harmoniseCity"><a>.
# OJO: el HTML repite cada ficha DOS VECES (una dentro de
# div.listado y otra idéntica dentro de div.mosaico — dos vistas del
# mismo dato) — si no filtramos por div.listado, salen todos los
# registros duplicados.
#
# Igual que en Cantabria: esta vista de listado NO trae categoría,
# código postal, ni plazas/habitaciones — solo nombre y municipio.
# ══════════════════════════════════════════════════════
def descargar_larioja():
    """
    CONFIRMADO con captura real de Network (HAR manual, paso a paso): la
    paginacion NO es un simple GET con '?pagina=N'. Es una peticion POST
    a un backend de API DISTINTO (servicios.lariojaturismo.com),
    con un monton de parametros de formulario. Dos de ellos
    (PestanyaActualID y proyectoVirtualID) los confirmamos como FIJOS
    -- estan escritos literalmente en el HTML de la pagina inicial
    (variable JS 'parametros_adiccionales'), no cambian por sesion.

    El unico parametro que NO aparecia en el HTML de ninguna forma es
    'tokenAfinidad' -- por el nombre (afinidad = sticky session de
    balanceo de carga), es probablemente solo para enrutar al mismo
    servidor interno, no un token de seguridad de verdad. Lo generamos
    nosotros mismos como un GUID aleatorio -- si el servidor lo acepta
    igual (cosa habitual para tokens de afinidad, no de autenticacion),
    esto deberia funcionar sin necesitar sacarlo de ningun sitio.

    OJO: esto es la mejor reconstruccion posible con los datos que
    tenemos, pero NO se ha podido probar en vivo contra el servidor real
    desde aqui (sandbox sin acceso a esa red) -- hay que confirmarlo con
    un run real.
    """
    import uuid

    print('\n-> La Rioja (lariojaturismo.com, API AJAX real)...')
    url_pagina_inicial = 'https://lariojaturismo.com/dormir'
    url_api = ('https://servicios.lariojaturismo.com/resultados/'
               'CargadorResultados/CargarResultados')

    headers_pagina = {
        'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                        'AppleWebKit/537.36 (KHTML, like Gecko) '
                        'Chrome/120.0.0.0 Safari/537.36'),
    }
    headers_api = dict(headers_pagina)
    headers_api['Referer'] = url_pagina_inicial
    headers_api['X-Requested-With'] = 'XMLHttpRequest'

    try:
        from bs4 import BeautifulSoup
    except ImportError:
        print('  [WARN] Falta instalar beautifulsoup4: pip install beautifulsoup4')
        return []

    # Estos dos SI son fijos, confirmados en el HTML de la pagina (variable
    # JS 'parametros_adiccionales') -- no son un secreto de sesion.
    PESTANYA_ACTUAL_ID = '29e5a6ea-48fa-4c44-8281-67427b964ee4'
    PROYECTO_VIRTUAL_ID = '76b7a706-3906-4522-a8c5-ab1aefe01563'

    def extraer_de_html(html):
        soup = BeautifulSoup(html, 'html.parser')
        registros_pagina = []
        for tarjeta in soup.select('div.resource'):
            h2_enlace = tarjeta.select_one('h2 a')
            nombre = clean(h2_enlace.get_text()) if h2_enlace else ''

            municipio_tag = (tarjeta.select_one('div.listado p.harmoniseCity a')
                              or tarjeta.select_one('p.harmoniseCity a'))
            municipio = clean(municipio_tag.get_text()) if municipio_tag else ''

            if not nombre:
                continue

            registros_pagina.append({
                'destino': calcular_destino(municipio.upper()),
                'provincia': 'LA RIOJA',
                'municipio': municipio.upper(),
                'tipo': '',
                'categoria': '',
                'registro': '',
                'nombre': nombre,
                'direccion': '',
                'cp': '',
                'hab': '',
                'plazas': '',
            })
        return registros_pagina

    sesion = requests.Session()

    # Página 1: la pedimos con el GET normal de siempre (esta SÍ funciona
    # tal cual, confirmado en varios runs reales).
    try:
        r1 = sesion.get(url_pagina_inicial, headers=headers_pagina, timeout=25)
        r1.raise_for_status()
    except Exception as e:
        print(f'  [WARN] No se pudo cargar la pagina inicial ({e}).')
        return []

    registros = extraer_de_html(r1.text)
    print(f'  Pagina 1: acumulado {len(registros)}')

    # Detectamos el total de páginas del mismo modo que antes.
    total_paginas = None
    numeros_pagina = re.findall(r'pagina=(\d+)', r1.text)
    if numeros_pagina:
        total_paginas = max(int(n) for n in numeros_pagina)

    if not total_paginas or total_paginas <= 1:
        print('  [WARN] No pude detectar mas de 1 pagina -- me quedo solo con la 1.')
        return registros

    print(f'  [DIAGNOSTICO] Total de paginas detectadas: {total_paginas}')

    diagnostico_mostrado = False

    for numero_pagina in range(2, total_paginas + 1):
        parametros_adicionales = (
            f'PestanyaActualID={PESTANYA_ACTUAL_ID}|'
            f'proyectoVirtualID={PROYECTO_VIRTUAL_ID}|'
            f'rdf:type=accommodation|orden=asc|'
            f'ordenarPor=harmonise:city@@@harmonise:name,harmonise:name'
        )
        payload = {
            'pUsarMasterParaLectura': 'false',
            'pProyectoID': PROYECTO_VIRTUAL_ID,
            'pEsUsuarioInvitado': 'true',
            'pIdentidadID': 'FFFFFFFF-FFFF-FFFF-FFFF-FFFFFFFFFFFF',
            'pParametros': f'pagina={numero_pagina}',
            'pLanguageCode': 'es',
            'pPrimeraCarga': 'false',
            'pAdministradorVeTodasPersonas': 'false',
            'pTipoBusqueda': '0',
            'pNumeroParteResultados': '1',
            'pGrafo': PROYECTO_VIRTUAL_ID,
            'pFiltroContexto': '',
            'pParametros_adiccionales': parametros_adicionales,
            'cont': '1',
            'tokenAfinidad': str(uuid.uuid4()),
        }

        try:
            r = sesion.post(url_api, data=payload, headers=headers_api, timeout=25)
            r.raise_for_status()
        except Exception as e:
            print(f'  Pagina {numero_pagina}: fallo de descarga ({e})')
            continue

        if not diagnostico_mostrado:
            print(f'  [DIAGNOSTICO] Status: {r.status_code}, '
                  f'tamano respuesta: {len(r.text)} caracteres')
            print(f'  [DIAGNOSTICO] Primeros 300 caracteres de la respuesta: '
                  f'{r.text[:300]!r}')
            diagnostico_mostrado = True

        # CONFIRMADO con el run real: la respuesta NO es HTML suelto, es
        # un JSON tipo {"Key": 458, "Value": "<div>...(HTML escapado)...".
        # "Key" es el total de resultados (útil para verificar), "Value"
        # es el HTML real con las tarjetas -- json.loads() ya se encarga
        # de des-escapar los \u003c etc. a los caracteres normales.
        try:
            datos_json = json.loads(r.text)
            html_resultados = datos_json.get('Value', '')
        except (ValueError, KeyError, AttributeError):
            html_resultados = r.text  # por si alguna vez no viene envuelto en JSON

        nuevos = extraer_de_html(html_resultados)
        registros.extend(nuevos)

        if numero_pagina % 5 == 0 or not nuevos:
            print(f'  Pagina {numero_pagina}: +{len(nuevos)} '
                  f'(acumulado {len(registros)})')

    print(f'  La Rioja: {len(registros)} registros procesados')
    if registros:
        print(f'  Ejemplo primera fila: {registros[0]}')
    return registros


_ASTURIAS_CATEGORIAS = {
    'albergues.pdf/fa28aa32-0a97-14d4-f5af-8338ad28d14b': 'ALBERGUE',
    'apartamento-rural.pdf/0c127ad3-fb4d-2554-e3e3-b626aab58def': 'APARTAMENTO RURAL',
    'apartamento-turistico.pdf/f18934b9-f295-4077-db07-4646f2a52de2': 'APARTAMENTO TURÍSTICO',
    'camping.pdf/f09c4a9f-315f-015a-3f5d-87d717fbe96e': 'CAMPING',
    'casa-de-aldea.pdf/9714b92c-710a-1607-55ef-b29f0435311e': 'CASA DE ALDEA',
    'hotel-y-hotel-apartamento.pdf/df18daad-d966-bf5d-8a64-2d681143d186': None,  # se resuelve por fila (HOTEL/HOTEL-APARTAMENTO)
    'hotel-rural.pdf/abdf84da-6c32-a302-9b6e-cb4172469681': 'HOTEL RURAL',
    'pension.pdf/a2275a81-41a8-9e97-b0dc-b82c1c485491': 'PENSIÓN/HOSTAL',
    'refugio-de-montana.pdf/f9a2d1a4-6c9f-4a28-7b2e-f31106d1ed19': 'REFUGIO DE MONTAÑA',
    'vivienda-de-uso-turistico.pdf/5d9f274e-a029-e0b5-a253-732af8f98ce5': 'VIVIENDA DE USO TURÍSTICO',
    'vivienda-vacacional.pdf/8decb6af-2865-64dd-e67a-77379424401d': 'VIVIENDA VACACIONAL',
}
_ASTURIAS_URL_BASE = 'https://www.turismoasturias.es/documents/39908/17324856/'

# CONFIRMADO con los PDF reales (hoteles, campings, albergues...): hay
# CUATRO formatos distintos para la linea de "rating" de cada entrada:
#   1. 'N ESTRELLAS/LLAVES/TIENDAS · M PLAZAS'  (hoteles, hoteles-apto...)
#   2. 'CATEGORÍA N · M PLAZAS'                  (campings, orden invertido)
#   3. 'SUPERIOR · M PLAZAS' / 'PRIMERA · M PLAZAS' (albergues turisticos,
#      una palabra de categoria SIN numero)
#   4. 'M PLAZAS' a secas, sin categoria de ningun tipo (albergues de
#      peregrinos y albergues juveniles no tienen categoria)
# En vez de seguir anadiendo un patron nuevo cada vez que aparece un
# formato distinto, usamos UN SOLO patron generico: "cualquier cosa
# (opcional) + PLAZAS al final", y tratamos lo que venga antes de
# 'PLAZAS' como texto libre de categoria (puede estar vacio).
_RE_RATING_AST = re.compile(
    r'^(?:(.+?)\s*·\s*)?(\d+)\s*PLAZAS?$', re.IGNORECASE
)


def _es_linea_rating_ast(texto):
    return bool(_RE_RATING_AST.match(texto))


def _extraer_categoria_y_plazas_ast(texto):
    """Devuelve (texto_categoria, plazas). 'texto_categoria' puede salir
    vacio si la fuente no publica categoria para ese tipo de alojamiento
    (p.ej. albergues de peregrinos) -- eso es correcto, no un fallo."""
    m = _RE_RATING_AST.match(texto)
    if not m:
        return '', ''
    categoria = m.group(1).strip().upper() if m.group(1) else ''
    plazas = m.group(2)
    return categoria, plazas


_RE_MUNICIPIO_AST = re.compile(r"^([A-ZÀ-Ý][A-Za-zÀ-ÿ'’\- ]*?)\s+(\d{1,3})$")
_RE_RUIDO_AST = re.compile(
    r'^(HOTELES|PENSIONES|HOSTALES|ALOJAMIENTOS|H\s*O\s*T\s*E\s*L\s*E\s*S|'
    r'P\s*E\s*N\s*S\s*I\s*O\s*N\s*E\s*S|Centro de Asturias|'
    r'Occidente de Asturias|Oriente de Asturias|Pág\.|^\d+$)',
    re.IGNORECASE,
)
# OJO — bug real encontrado: si esto incluyera 'CASAS?'/'VIVIENDAS?' como
# prefijo (para filtrar la cabecera de categoría "Casas de aldea", etc.),
# también descartaría por error hoteles de verdad cuyo NOMBRE empieza por
# esas palabras (p.ej. 'Casa El Rápido' — nos hizo perder 29 registros
# reales la primera vez). Por eso estos van en un patrón APARTE que exige
# coincidir con la LÍNEA COMPLETA, nunca solo el principio.
_RE_RUIDO_CATEGORIA_EXACTA_AST = re.compile(
    r'^(ALBERGUES|APARTAMENTOS RURALES|APARTAMENTOS TUR[IÍ]STICOS|'
    r'CAMPINGS?|CASAS DE ALDEA|VIVIENDAS DE USO TUR[IÍ]STICO|'
    r'VIVIENDAS VACACIONALES|REFUGIOS DE MONTA[ÑN]A|'
    r'HOTELES-APARTAMENTO)$',
    re.IGNORECASE,
)
_RE_TELEFONO_AST = re.compile(r'^[\d\s/]+$')
_RE_WEB_AST = re.compile(r'^https?://|^www\.', re.IGNORECASE)


def _extraer_lineas_columna_ast(palabras, x_min, x_max, tolerancia=3):
    filtradas = sorted(
        [w for w in palabras if x_min <= w['x0'] < x_max],
        key=lambda w: (w['top'], w['x0'])
    )
    lineas = []
    grupo_actual = []
    top_actual = None
    for w in filtradas:
        if top_actual is None or abs(w['top'] - top_actual) <= tolerancia:
            grupo_actual.append(w)
            top_actual = w['top'] if top_actual is None else top_actual
        else:
            grupo_actual.sort(key=lambda w: w['x0'])
            lineas.append((top_actual, ' '.join(x['text'] for x in grupo_actual)))
            grupo_actual = [w]
            top_actual = w['top']
    if grupo_actual:
        grupo_actual.sort(key=lambda w: w['x0'])
        lineas.append((top_actual, ' '.join(x['text'] for x in grupo_actual)))
    return lineas


def _es_candidato_municipio_ast(texto):
    if any(c in texto for c in '.,/'):
        return False
    return bool(_RE_MUNICIPIO_AST.match(texto))


def _extraer_eventos_municipio_ast(izq, der):
    eventos = []
    for lineas in (izq, der):
        for idx, (top, texto) in enumerate(lineas):
            if _RE_RUIDO_AST.match(texto) or _RE_RUIDO_CATEGORIA_EXACTA_AST.fullmatch(texto.strip()):
                continue
            if not _es_candidato_municipio_ast(texto):
                continue
            siguiente_es_rating = (
                idx + 1 < len(lineas) and _es_linea_rating_ast(lineas[idx + 1][1])
            )
            if siguiente_es_rating:
                continue
            m = _RE_MUNICIPIO_AST.match(texto)
            eventos.append((top, m.group(1).strip().upper()))
    eventos.sort(key=lambda e: e[0])
    return eventos


def _municipio_en_ast(eventos, top, ultimo_conocido):
    resultado = ultimo_conocido
    for evento_top, nombre in eventos:
        if evento_top <= top + 1:
            resultado = nombre
        else:
            break
    return resultado


def _parsear_columna_ast(lineas, eventos_municipio, categoria_fija, municipio_inicial=''):
    registros = []
    municipio_actual = municipio_inicial
    i = 0
    while i < len(lineas):
        top, texto = lineas[i]

        if _RE_RUIDO_AST.match(texto) or _RE_RUIDO_CATEGORIA_EXACTA_AST.fullmatch(texto.strip()):
            i += 1
            continue

        if _es_candidato_municipio_ast(texto) and not (
            i + 1 < len(lineas) and _es_linea_rating_ast(lineas[i + 1][1])
        ):
            i += 1
            continue

        if i + 1 < len(lineas) and _es_linea_rating_ast(lineas[i + 1][1]):
            nombre = texto.strip()
            categoria, plazas = _extraer_categoria_y_plazas_ast(lineas[i + 1][1])
            if categoria_fija:
                tipo = categoria_fija
            else:
                tipo = 'HOTEL' if 'ESTRELLA' in categoria.upper() else 'HOTEL-APARTAMENTO'

            municipio_actual = _municipio_en_ast(eventos_municipio, top, municipio_actual)

            cursor = i + 2
            direccion = lineas[cursor][1].strip() if cursor < len(lineas) else ''
            cursor += 1

            if cursor < len(lineas) and _RE_TELEFONO_AST.match(lineas[cursor][1].replace('/', '').strip()):
                cursor += 1
            if cursor < len(lineas) and '@' in lineas[cursor][1]:
                cursor += 1
            if cursor < len(lineas) and _RE_WEB_AST.match(lineas[cursor][1].strip()):
                cursor += 1

            registros.append({
                'destino': calcular_destino(municipio_actual),
                'provincia': 'ASTURIAS',
                'municipio': municipio_actual,
                'tipo': tipo,
                'categoria': categoria,
                'registro': '',   # no disponible en estos PDF
                'nombre': nombre,
                'direccion': direccion,
                'cp': '',         # no disponible en estos PDF
                'hab': '',        # no disponible en estos PDF
                'plazas': plazas,
            })
            i = cursor
        else:
            i += 1

    return registros, municipio_actual


def _parsear_pdf_asturias(contenido_bytes, categoria_fija):
    try:
        import pdfplumber
    except ImportError:
        print('  ⚠️  Falta instalar pdfplumber: pip install pdfplumber')
        return []

    registros = []
    municipio_previo = ''
    with pdfplumber.open(io.BytesIO(contenido_bytes)) as pdf:
        for pagina in pdf.pages:
            palabras = pagina.extract_words()
            if not palabras:
                continue
            umbral = pagina.width / 2
            izq = _extraer_lineas_columna_ast(palabras, 0, umbral)
            der = _extraer_lineas_columna_ast(palabras, umbral, 10000)

            eventos = _extraer_eventos_municipio_ast(izq, der)

            regs_izq, municipio_previo = _parsear_columna_ast(
                izq, eventos, categoria_fija, municipio_previo)
            regs_der, _ = _parsear_columna_ast(
                der, eventos, categoria_fija, municipio_previo)
            registros.extend(regs_izq)
            registros.extend(regs_der)
    return registros


def descargar_asturias():
    print('\n→ Asturias (turismoasturias.es — 11 PDF por categoría)...')
    headers = {
        'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                        'AppleWebKit/537.36 (KHTML, like Gecko) '
                        'Chrome/120.0.0.0 Safari/537.36'),
    }
    sesion = requests.Session()

    registros = []
    for ruta_relativa, categoria_fija in _ASTURIAS_CATEGORIAS.items():
        url = _ASTURIAS_URL_BASE + ruta_relativa
        nombre_categoria = categoria_fija or 'HOTEL/HOTEL-APARTAMENTO'
        try:
            r = sesion.get(url, headers=headers, timeout=60)
            r.raise_for_status()
        except Exception as e:
            print(f'  {nombre_categoria}: fallo de descarga ({e})')
            continue

        regs = _parsear_pdf_asturias(r.content, categoria_fija)
        print(f'  {nombre_categoria}: {len(regs)} registros procesados')
        registros.extend(regs)

    print(f'  Asturias: {len(registros)} registros')
    if registros:
        print(f'  Ejemplo primera fila: {registros[0]}')
    return registros


def main():
    print('=== Descarga de licencias turísticas oficiales ===\n')

    todos = []
    todos.extend(descargar_madrid())
    todos.extend(descargar_andalucia())
    todos.extend(descargar_canarias())
    todos.extend(descargar_cataluna())
    todos.extend(descargar_valencia())
    todos.extend(descargar_euskadi())
    todos.extend(descargar_galicia())
    todos.extend(descargar_castillayleon())
    todos.extend(descargar_aragon())
    todos.extend(descargar_extremadura())
    todos.extend(descargar_castillalamancha())
    todos.extend(descargar_navarra())
    todos.extend(descargar_baleares_mallorca())
    todos.extend(descargar_murcia())
    todos.extend(descargar_cantabria())
    todos.extend(descargar_larioja())
    todos.extend(descargar_asturias())

    # TODO: pendientes de fuente automatizable real:
    #   - Baleares: falta Menorca (dataset propio, pendiente de probar),
    #     y no localicé datos abiertos de Eivissa/Formentera.

    # Normalizamos 'hab' y 'plazas' a un tipo ÚNICO y consistente en TODO
    # el dataset. Con 17 fuentes distintas, cada una entrega estos campos
    # de forma distinta (unas como número real porque su API ya lo manda
    # así, otras como texto porque vienen de un CSV) — confirmado con una
    # auditoría real del JSON: ~45% como int, ~55% como str, mezclados en
    # la misma columna. Eso se ve mal en Excel (números mal alineados, no
    # se puede sumar/ordenar toda la columna junta). Lo arreglamos UNA
    # sola vez aquí, en vez de tocar los 20+ sitios donde se rellenan
    # estos campos — más seguro que sea fácil que se me olvide alguno.
    def normalizar_numero(valor):
        """Convierte a int de verdad si es un número válido (venga como
        int, float, o texto tipo '16' o ' 16 '); si no hay nada
        aprovechable, devuelve '' de forma consistente (nunca None, nunca
        0 -- 0 sería un dato real y aquí no lo tenemos)."""
        if valor is None:
            return ''
        if isinstance(valor, int):
            return valor
        if isinstance(valor, float):
            return int(valor) if valor.is_integer() else valor
        texto = str(valor).strip()
        if not texto:
            return ''
        try:
            return int(texto)
        except ValueError:
            try:
                numero = float(texto.replace(',', '.'))
                return int(numero) if numero.is_integer() else numero
            except ValueError:
                return ''  # basura de verdad (no debería pasar, ya lo comprobamos)

    for registro in todos:
        registro['hab'] = normalizar_numero(registro.get('hab'))
        registro['plazas'] = normalizar_numero(registro.get('plazas'))

    # Ordenamos por provincia/municipio para que el archivo completo ya
    # salga legible sin que haga falta procesarlo más.
    todos.sort(key=lambda r: (r.get('provincia', ''), r.get('municipio', '')))

    # Tu base de datos nacional completa (las 17 CCAA). En formato
    # compacto (cabecera + filas) cabe con margen bajo el límite de
    # 100 MB de GitHub (~54 MB con ~372.000 registros) — SÍ se sube.
    print(f'\n{"="*50}')
    print(f'TOTAL LICENCIAS (España completa, sin filtrar): {len(todos)}')
    print('='*50)

    # ÚNICO archivo que se genera ahora: TODAS las licencias, sin filtrar,
    # en formato compacto (cabecera + filas, ~54 MB en vez de 91,5 MB).
    # SÍ se sube a GitHub — alimenta la 3ª hoja "TODAS LAS LICENCIAS" del
    # Excel descargable de la web (se pidió expresamente no dejar ninguna
    # fuera, así que ya no generamos la versión filtrada a 15 ciudades).
    guardar_json(todos, 'licencias_completo.json', formato_compacto=True)


if __name__ == '__main__':
    main()
