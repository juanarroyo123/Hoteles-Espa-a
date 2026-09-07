# -*- coding: utf-8 -*-
"""
PRUEBA AISLADA — solo la función ejecutar_licencias_si_toca() de
scraper.py, sin arrancar Selenium ni tocar hoteles_cache.json.

Requisitos en la misma carpeta:
  - scraper.py (el nuevo, con la función)
  - scraper_licencias.py (el renombrado desde scraper_licencias40.py)

Uso:
  python test_licencias_semanal.py           -> simula "nunca se ha
                                                  ejecutado" y debería
                                                  disparar el scraper
                                                  completo de licencias
                                                  (tarda varios minutos)
  python test_licencias_semanal.py --forzar-reciente
                                              -> simula que ya corrió
                                                 HOY, no debería hacer
                                                 nada (prueba rápida,
                                                 sin esperar minutos)
"""
import sys
import os
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import scraper as scr  # noqa: E402

if '--forzar-reciente' in sys.argv:
    with open(scr.LICENCIAS_ESTADO_FILE, 'w', encoding='utf-8') as f:
        f.write(date.today().isoformat())
    print('(Forzado: archivo de estado puesto a HOY — no debería ejecutar nada)\n')
elif os.path.exists(scr.LICENCIAS_ESTADO_FILE):
    print(f'Archivo de estado existente: {scr.LICENCIAS_ESTADO_FILE}')
    with open(scr.LICENCIAS_ESTADO_FILE, encoding='utf-8') as f:
        print(f'  Contenido: {f.read().strip()}\n')
else:
    print('No hay archivo de estado todavía — se tratará como "nunca se ha ejecutado".\n')

scr.ejecutar_licencias_si_toca()

print('\n--- Prueba terminada ---')
if os.path.exists(scr.LICENCIAS_ESTADO_FILE):
    with open(scr.LICENCIAS_ESTADO_FILE, encoding='utf-8') as f:
        print(f'Archivo de estado ahora dice: {f.read().strip()}')
if os.path.exists('licencias_completo.json'):
    tam_mb = os.path.getsize('licencias_completo.json') / 1024 / 1024
    print(f'licencias_completo.json existe, {tam_mb:.1f} MB')
