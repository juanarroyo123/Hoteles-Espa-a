#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
agregar_manual.py -- Anade a mano un anuncio que te llega DIRECTAMENTE (por
WhatsApp, email, un contacto...) y que no esta publicado en ningun portal,
para que aparezca en la web exactamente igual que cualquier otro anuncio
(en "Hoteles en venta", con sus filtros, favoritos, seguimiento, analisis
financiero, mapa, etc.).

Te va preguntando los datos uno a uno y, al final, te pide la carpeta de tu
ordenador donde hayas guardado las fotos y los videos de ese anuncio (los
mismos que te hayan pasado) -- los copia dentro del proyecto y los deja
enlazados al anuncio.

Uso (desde C:\\HotelMonitor):
    python agregar_manual.py

Despues de correrlo:
    python regenerar_web.py      <- para que se vea en la web y se suba
"""
import json
import os
import re
import shutil
import subprocess
import unicodedata
from datetime import date

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE = os.path.join(BASE_DIR, 'hoteles_cache.json')
MEDIA_DIR = os.path.join(BASE_DIR, 'fotos_manuales')

EXT_IMAGENES = {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp', '.heic', '.heif'}
EXT_HEIC = {'.heic', '.heif'}
EXT_VIDEOS = {'.mp4', '.mov', '.avi', '.mkv', '.3gp', '.webm', '.m4v'}

TIPOS_SUGERIDOS = [
    'Hotel', 'Hotel boutique', 'Hostal', 'Pensión', 'Casa de huéspedes',
    'Apartahotel', 'Resort', 'Casa Rural', 'Albergue/Hostel',
]
OPERACIONES = [('venta', 'Venta'), ('traspaso', 'Traspaso'), ('gestion', 'Contrato de gestión')]


def slug(texto):
    texto = unicodedata.normalize('NFKD', texto or '').encode('ascii', 'ignore').decode('ascii')
    texto = re.sub(r'[^a-zA-Z0-9]+', '_', texto).strip('_').lower()
    return texto or 'anuncio'


def preguntar(etiqueta, obligatorio=False, default=None):
    while True:
        sufijo = f' [{default}]' if default else ''
        valor = input(f'{etiqueta}{sufijo}: ').strip()
        if not valor and default is not None:
            return default
        if not valor and obligatorio:
            print('  (este dato hace falta, escribe algo)')
            continue
        return valor


def preguntar_entero(etiqueta, obligatorio=False):
    while True:
        valor = input(f'{etiqueta}: ').strip().replace('.', '').replace(',', '')
        if not valor:
            if obligatorio:
                print('  (este dato hace falta, escribe un numero)')
                continue
            return None
        try:
            return int(valor)
        except ValueError:
            print('  (eso no es un numero, prueba otra vez)')


def preguntar_descripcion():
    print('Descripción del anuncio (puedes escribir varias líneas).')
    print('Cuando termines, escribe FIN en una línea sola y pulsa Enter:')
    lineas = []
    while True:
        linea = input()
        if linea.strip().upper() == 'FIN':
            break
        lineas.append(linea)
    return '\n'.join(lineas).strip()


def preguntar_operacion():
    print('¿Qué tipo de operación es?')
    for i, (_, etiqueta) in enumerate(OPERACIONES, 1):
        print(f'  {i}. {etiqueta}')
    while True:
        valor = input('Elige 1-3 [1]: ').strip() or '1'
        if valor in ('1', '2', '3'):
            return OPERACIONES[int(valor) - 1][0]
        print('  (elige 1, 2 o 3)')


def preguntar_tipo():
    print('¿Qué tipo de alojamiento es? (elige un número o escribe uno tuyo)')
    for i, t in enumerate(TIPOS_SUGERIDOS, 1):
        print(f'  {i}. {t}')
    valor = input('Elige un número, o escribe el tipo directamente: ').strip()
    if valor.isdigit() and 1 <= int(valor) <= len(TIPOS_SUGERIDOS):
        return TIPOS_SUGERIDOS[int(valor) - 1]
    return valor or 'Alojamiento (n.d.)'


def hay_ffmpeg():
    return shutil.which('ffmpeg') is not None


def convertir_heic_a_jpg(origen, destino):
    try:
        subprocess.run(['ffmpeg', '-y', '-i', origen, destino], check=True,
                        capture_output=True, timeout=60)
        return True
    except Exception:
        return False


def convertir_video_a_mp4(origen, destino):
    try:
        subprocess.run(
            ['ffmpeg', '-y', '-i', origen, '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
             '-c:a', 'aac', '-movflags', '+faststart', destino],
            check=True, capture_output=True, timeout=300)
        return True
    except Exception:
        return False


def recopilar_media(carpeta, id_anuncio):
    """Busca fotos y videos dentro de la carpeta (y subcarpetas) que haya
    indicado el usuario, los copia (convirtiendo si hace falta) a
    fotos_manuales/<id_anuncio>/ y devuelve (lista_fotos_rel, lista_videos_rel, avisos)."""
    ficheros = []
    for raiz, _dirs, nombres in os.walk(carpeta):
        for nombre in sorted(nombres):
            ficheros.append(os.path.join(raiz, nombre))

    destino_dir = os.path.join(MEDIA_DIR, id_anuncio)
    contador = 1
    while os.path.isdir(destino_dir):
        contador += 1
        destino_dir = os.path.join(MEDIA_DIR, f'{id_anuncio}_{contador}')
    id_carpeta = os.path.basename(destino_dir)

    fotos_rel = []
    videos_rel = []
    avisos = []
    con_ffmpeg = hay_ffmpeg()
    idx_foto = 0
    idx_video = 0

    for ruta in ficheros:
        ext = os.path.splitext(ruta)[1].lower()
        nombre_orig = os.path.basename(ruta)

        if ext in EXT_IMAGENES:
            idx_foto += 1
            if ext in EXT_HEIC:
                if not con_ffmpeg:
                    avisos.append(
                        f'"{nombre_orig}" es formato HEIC (fotos de iPhone) y no se ve en '
                        f'los navegadores -- no se ha podido convertir automaticamente. '
                        f'Abrela en la app Fotos de Windows y "Guardar copia como" JPG, y '
                        f'vuelve a correr este script.')
                    continue
                os.makedirs(destino_dir, exist_ok=True)
                destino = os.path.join(destino_dir, f'{idx_foto:02d}_{slug(nombre_orig)}.jpg')
                if not convertir_heic_a_jpg(ruta, destino):
                    avisos.append(f'No se pudo convertir "{nombre_orig}" (HEIC) a JPG, se ha omitido.')
                    idx_foto -= 1
                    continue
            else:
                os.makedirs(destino_dir, exist_ok=True)
                destino_nombre = f'{idx_foto:02d}_{slug(os.path.splitext(nombre_orig)[0])}{ext}'
                destino = os.path.join(destino_dir, destino_nombre)
                shutil.copyfile(ruta, destino)
            rel = os.path.relpath(destino, BASE_DIR).replace(os.sep, '/')
            fotos_rel.append(rel)

        elif ext in EXT_VIDEOS:
            idx_video += 1
            os.makedirs(destino_dir, exist_ok=True)
            if ext == '.mp4':
                destino_nombre = f'{idx_video:02d}_{slug(os.path.splitext(nombre_orig)[0])}.mp4'
                destino = os.path.join(destino_dir, destino_nombre)
                shutil.copyfile(ruta, destino)
            else:
                destino_nombre = f'{idx_video:02d}_{slug(os.path.splitext(nombre_orig)[0])}.mp4'
                destino = os.path.join(destino_dir, destino_nombre)
                if con_ffmpeg:
                    if not convertir_video_a_mp4(ruta, destino):
                        avisos.append(f'No se pudo convertir el video "{nombre_orig}", se copia tal cual '
                                       f'(puede que no se reproduzca en todos los navegadores).')
                        destino = os.path.join(destino_dir, f'{idx_video:02d}_{slug(os.path.splitext(nombre_orig)[0])}{ext}')
                        shutil.copyfile(ruta, destino)
                else:
                    avisos.append(f'"{nombre_orig}" no es .mp4 y no se ha podido convertir (falta ffmpeg) -- '
                                   f'puede que no se reproduzca bien en algunos navegadores.')
                    destino = os.path.join(destino_dir, f'{idx_video:02d}_{slug(os.path.splitext(nombre_orig)[0])}{ext}')
                    shutil.copyfile(ruta, destino)
            rel = os.path.relpath(destino, BASE_DIR).replace(os.sep, '/')
            videos_rel.append(rel)

    return fotos_rel, videos_rel, avisos


def main():
    print('=' * 70)
    print('AÑADIR UN ANUNCIO A MANO (recibido directamente, sin portal)')
    print('=' * 70)
    print('Ve contestando y al final se añade a la web como cualquier otro anuncio.\n')

    titulo = preguntar('Nombre del anuncio (ej. "Pensión 11 habitaciones, C/ Eusebio Sempere, Alicante")', obligatorio=True)
    tipo = preguntar_tipo()
    operacion = preguntar_operacion()
    rooms = preguntar_entero('Número de habitaciones')
    m2 = preguntar_entero('Superficie en m² (déjalo en blanco si no lo sabes)')
    precio = preguntar('Precio (ej. "950.000 €"; déjalo en blanco para "A consultar")')
    comunidad = preguntar('Comunidad Autónoma (ej. "Comunidad Valenciana")', obligatorio=True)
    municipio = preguntar('Municipio / ciudad (ej. "Alicante")', obligatorio=True)
    print()
    descripcion = preguntar_descripcion()

    print()
    print('Por último, la carpeta con las fotos y vídeos de este anuncio')
    print('(los que te hayan pasado por WhatsApp u otro medio).')
    print('Truco: puedes arrastrar la carpeta desde el Explorador de Windows')
    print('y soltarla aquí -- se rellena la ruta sola.')
    while True:
        carpeta = input('Carpeta con fotos/vídeos: ').strip().strip('"')
        if not carpeta:
            if input('¿Seguro que no quieres añadir fotos/vídeos ahora? (s/n): ').strip().lower() == 's':
                carpeta = None
                break
            continue
        if os.path.isdir(carpeta):
            break
        print('  No encuentro esa carpeta, prueba otra vez.')

    id_anuncio = slug(titulo)[:50] or 'anuncio_manual'
    fotos_rel, videos_rel, avisos = ([], [], [])
    if carpeta:
        print('\nCopiando fotos y vídeos...')
        fotos_rel, videos_rel, avisos = recopilar_media(carpeta, id_anuncio)
        print(f'  {len(fotos_rel)} foto(s) y {len(videos_rel)} vídeo(s) copiados.')
        for a in avisos:
            print(f'  ⚠ {a}')

    with open(CACHE_FILE, 'r', encoding='utf-8') as f:
        cache_data = json.load(f)
    cache = {item['url']: item for item in cache_data}

    url_manual = f'#manual-{id_anuncio}'
    contador = 1
    while url_manual in cache:
        contador += 1
        url_manual = f'#manual-{id_anuncio}-{contador}'

    entrada = {
        'title': titulo,
        'price': precio or '',
        'location': municipio,
        'location_region': comunidad,
        'description': descripcion,
        'url': url_manual,
        'source': 'Manual',
        'ausencias': 0,
        'tipo': tipo,
        'estado': 'Activo',
        'date': date.today().strftime('%d/%m/%Y'),
        'licencia_texto': '',
        'licencia_motivo': '',
        'operacion_detectada': operacion,
    }
    if rooms:
        entrada['rooms'] = rooms
    if m2:
        entrada['m2'] = m2
    if fotos_rel:
        entrada['fotos_url'] = fotos_rel
    if videos_rel:
        entrada['videos'] = videos_rel

    cache[url_manual] = entrada
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(list(cache.values()), f, ensure_ascii=False, indent=1)

    print()
    print('=' * 70)
    print(f'Anuncio añadido: {titulo}')
    print(f'  {len(fotos_rel)} foto(s), {len(videos_rel)} vídeo(s).')
    print('hoteles_cache.json guardado.')
    print('\nAhora corre:  python regenerar_web.py')
    print('=' * 70)
    input('\nPresiona Enter para cerrar...')


if __name__ == '__main__':
    main()
