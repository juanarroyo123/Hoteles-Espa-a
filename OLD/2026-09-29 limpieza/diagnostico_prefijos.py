# -*- coding: utf-8 -*-
"""
DIAGNÓSTICO — ejemplos de "nombre" para cada prefijo de registro con
"tipo" vacío, para confirmar cuáles son alojamientos de verdad
(mal clasificados, hay que CONSERVARLOS) y cuáles son servicios
turísticos que no deberían estar (hay que QUITARLOS).

Uso: python diagnostico_prefijos.py
"""
import json
from collections import defaultdict

with open('licencias_completo.json', encoding='utf-8') as f:
    datos = json.load(f)

columnas = datos['columnas']
filas = datos['filas']
idx_tipo = columnas.index('tipo')
idx_registro = columnas.index('registro')
idx_nombre = columnas.index('nombre')
idx_hab = columnas.index('hab')
idx_plazas = columnas.index('plazas')

ejemplos_por_prefijo = defaultdict(list)
for f in filas:
    if f[idx_tipo]:
        continue
    reg = f[idx_registro] or ''
    prefijo = reg.split('/')[0] if '/' in reg else (reg[:6] if reg else '(sin registro)')
    if len(ejemplos_por_prefijo[prefijo]) < 5:
        ejemplos_por_prefijo[prefijo].append(
            (f[idx_nombre], f[idx_hab], f[idx_plazas])
        )

for prefijo in ['VTAR', 'GT', 'REST', 'OT', 'OCC', 'PIT', 'VUT', 'CR', 'AT',
                 'AIAT', 'H', 'EC', '(sin registro)']:
    if prefijo not in ejemplos_por_prefijo:
        continue
    print(f'=== {prefijo} ===')
    for nombre, hab, plazas in ejemplos_por_prefijo[prefijo]:
        print(f'  nombre={nombre!r}  hab={hab!r}  plazas={plazas!r}')
    print()
