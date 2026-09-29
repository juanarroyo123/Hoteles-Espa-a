# -*- coding: utf-8 -*-
"""
DIAGNÓSTICO — miramos en crudo unos cuantos registros "sospechosos"
(los que salían casi vacíos en el Excel) para entender de qué categoría
son de verdad, antes de decidir cómo filtrarlos.

Uso: python diagnostico_registros_vacios.py
(licencias_completo.json tiene que estar en la misma carpeta)
"""
import json

with open('licencias_completo.json', encoding='utf-8') as f:
    datos = json.load(f)

columnas = datos['columnas']
filas = datos['filas']
print('Columnas:', columnas)
print(f'Total filas: {len(filas)}')
print()

REGISTROS_A_BUSCAR = ['GT/05693', 'OCC/CA/00010', 'OCC/SE/00033']

for objetivo in REGISTROS_A_BUSCAR:
    idx_registro = columnas.index('registro')
    encontrado = None
    for fila in filas:
        if fila[idx_registro] == objetivo:
            encontrado = fila
            break
    print(f'--- Registro {objetivo} ---')
    if encontrado:
        for col, val in zip(columnas, encontrado):
            print(f'  {col}: {val!r}')
    else:
        print('  No encontrado')
    print()

# Además: contamos cuántas filas tienen 'tipo' vacío en TODO el archivo,
# y de esas, cuántas tienen un prefijo de registro tipo GT/ u OCC/
idx_tipo = columnas.index('tipo')
idx_registro = columnas.index('registro')
idx_provincia = columnas.index('provincia')

sin_tipo = [f for f in filas if not f[idx_tipo]]
print(f'Total filas con "tipo" VACÍO: {len(sin_tipo)} de {len(filas)} '
      f'({len(sin_tipo)/len(filas)*100:.1f}%)')

from collections import Counter
prefijos = Counter()
for f in sin_tipo:
    reg = f[idx_registro] or ''
    prefijo = reg.split('/')[0] if '/' in reg else (reg[:6] if reg else '(sin registro)')
    prefijos[prefijo] += 1

print('\nPrefijos de "registro" más comunes ENTRE LAS QUE TIENEN TIPO VACÍO:')
for prefijo, n in prefijos.most_common(15):
    print(f'  {prefijo}: {n}')

# ¿Cuántas de las que tienen tipo vacío también tienen provincia vacía?
sin_tipo_ni_provincia = [f for f in sin_tipo if not f[idx_provincia]]
print(f'\nDe esas, con "provincia" TAMBIÉN vacía: {len(sin_tipo_ni_provincia)}')
