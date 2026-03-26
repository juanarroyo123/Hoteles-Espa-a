import json, re

with open('hoteles_cache.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

print(f'Anuncios antes: {len(data)}')

# Limpiar caracteres problemáticos de todos los campos de texto
def limpiar(s):
    if not s: return ''
    s = re.sub(r'<[^>]+>', ' ', str(s))  # quitar tags HTML
    s = re.sub(r'[<>]', '', s)            # quitar < > sueltos
    s = re.sub(r'\s+', ' ', s)
    return s.strip()

for item in data:
    item['title']       = limpiar(item.get('title',''))
    item['description'] = limpiar(item.get('description',''))
    item['location']    = limpiar(item.get('location',''))
    item['price']       = limpiar(item.get('price',''))

# Verificar que el JSON es válido
try:
    json.dumps(data, ensure_ascii=False)
    print('JSON válido ✅')
except Exception as e:
    print(f'Error JSON: {e}')

with open('hoteles_cache.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print(f'Anuncios después: {len(data)}')
print('Cache limpiado y guardado.')
