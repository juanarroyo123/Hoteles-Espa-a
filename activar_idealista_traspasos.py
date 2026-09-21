"""
Igual que la parte 2 de activar_novedades.py, pero solo para Idealista
Traspasos -- pensado para REINTENTAR cuando te bloquee la IP, sin tener
que repetir tambien el backfill de NegociosEnVenta (que ya esta hecho y
no hace falta volver a correr cada vez).

Uso:  python activar_idealista_traspasos.py
Luego: python regenerar_web.py   (solo hace falta si trae anuncios nuevos)
"""
import scraper

cache = scraper.load_cache()

scraper.found_listings.clear()
scraper.seen_urls.clear()

driver = scraper.init_driver_stealth()
try:
    scraper.scrape_idealista_traspasos(driver)
finally:
    try:
        driver.quit()
    except Exception:
        pass

nuevos = 0
actualizados = 0
for item in scraper.found_listings:
    url_key = item['url']
    if url_key not in cache:
        cache[url_key] = item
        nuevos += 1
    else:
        cache[url_key]['price'] = item.get('price', cache[url_key].get('price', ''))
        _desc_nueva = item.get('description') or ''
        _desc_vieja = cache[url_key].get('description') or ''
        cache[url_key]['description'] = _desc_nueva if len(_desc_nueva) >= len(_desc_vieja) else _desc_vieja
        cache[url_key]['tipo'] = item.get('tipo', cache[url_key].get('tipo', ''))
        cache[url_key]['ausencias'] = 0
        for _k in ('rooms', 'm2', 'beds', 'bathrooms', 'fotos_url', 'operacion_detectada'):
            if item.get(_k):
                cache[url_key][_k] = item[_k]
        actualizados += 1

scraper.save_cache(cache)
print(f"\nIdealista Traspasos -- encontrados: {len(scraper.found_listings)} | nuevos: {nuevos} | ya existian: {actualizados}")
print(f"hoteles_cache.json guardado: {len(cache)} anuncios totales.")
if nuevos or actualizados:
    print("\nAhora corre:  python regenerar_web.py   para subir esto a la web.")
else:
    print("\nSin cambios que subir esta vez (probablemente bloqueado de nuevo -- reintenta mas tarde).")
