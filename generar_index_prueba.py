# -*- coding: utf-8 -*-
"""
Genera un index.html DE PRUEBA a partir de index_template.html, con un
par de anuncios de mentira (para que la hoja "OFERTAS TOTALES" no salga
vacía) — así puedes probar el botón "Descargar Excel" y ver las 3 hojas
sin tener que correr el scraper de hoteles completo (que tarda mucho y
abre varios navegadores Chrome).

Uso:
  python generar_index_prueba.py
"""
import json
import os

RUTA_TEMPLATE = 'index_template.html'
RUTA_SALIDA = 'index.html'

if not os.path.exists(RUTA_TEMPLATE):
    print(f'No encuentro "{RUTA_TEMPLATE}" en esta carpeta.')
    raise SystemExit(1)

anuncios_de_prueba = [
    {
        'url': 'https://ejemplo.com/hotel-1',
        'title': 'Hotel de Prueba en Madrid',
        'price': '1.200.000 €',
        'location': 'Madrid, España',
        'location_region': 'Comunidad de Madrid',
        'source': 'ThinkSpain',
        'tipo': 'Hotel',
        'rooms': 20,
        'beds': 40,
        'm2': 800,
        'description': 'Anuncio de prueba para verificar el Excel.',
        'date': '07/09/2026',
        'estado': 'Activo',
    },
    {
        'url': 'https://ejemplo.com/hotel-2',
        'title': 'Hostal de Prueba en Sevilla',
        'price': '450.000 €',
        'location': 'Sevilla, España',
        'location_region': 'Andalucía',
        'source': 'Idealista',
        'tipo': 'Hostal / Pensión',
        'rooms': 8,
        'beds': 16,
        'm2': 300,
        'description': 'Segundo anuncio de prueba.',
        'date': '07/09/2026',
        'estado': 'Activo',
    },
]

with open(RUTA_TEMPLATE, 'r', encoding='utf-8') as f:
    template = f.read()

html = template.replace('__LISTINGS_JSON__', json.dumps(anuncios_de_prueba, ensure_ascii=False))
html = html.replace('__ADR_BENCHMARK_JSON__', '{}')

with open(RUTA_SALIDA, 'w', encoding='utf-8') as f:
    f.write(html)

print(f'✅ "{RUTA_SALIDA}" generado con {len(anuncios_de_prueba)} anuncios de prueba.')
print()
print('Ahora corre esto para servirlo con un servidor local (necesario para')
print('que el navegador pueda cargar licencias_completo.json):')
print()
print('    python -m http.server 8000')
print()
print('Y abre en el navegador: http://localhost:8000/index.html')
