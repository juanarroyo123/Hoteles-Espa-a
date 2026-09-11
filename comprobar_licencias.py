# -*- coding: utf-8 -*-
"""
Comprueba, AHORA MISMO y sin tocar nada, cuántos anuncios activos cruzan
con licencias turísticas oficiales -- usando exactamente la misma lógica
que ya corre sola dentro de scraper.py (cruzar_licencias.js), pero sin
tener que esperar al próximo scrapeo ni modificar hoteles_cache.json.

Cómo usarlo:
  1. Doble clic en comprobar_licencias.bat (o, en una consola, dentro de la
     carpeta del proyecto: "python comprobar_licencias.py").
  2. Al terminar, se abre/genera "comprobacion_licencias.csv" en la misma
     carpeta -- ábrelo con Excel para ver, anuncio por anuncio, con qué
     licencia ha cruzado cada uno y por qué motivo.

Requisitos: los mismos que ya necesita el cruce automático -- Node.js
instalado, y que existan hoteles_cache.json, licencias_completo.json e
index_template.html en esta misma carpeta (los tres ya están si has
scrapeado alguna vez).

No hace ninguna llamada a internet ni modifica ningún archivo del
proyecto: solo lee, calcula y escribe el informe.
"""
import json, os, subprocess, sys, shutil, csv

CARPETA = os.path.dirname(os.path.abspath(__file__))


def ruta(nombre):
    return os.path.join(CARPETA, nombre)


def main():
    print("Comprobando cruce de licencias con los datos actuales...\n")

    faltan = [f for f in ("hoteles_cache.json", "licencias_completo.json",
                           "index_template.html", "cruzar_licencias.js")
              if not os.path.exists(ruta(f))]
    if faltan:
        print("Faltan estos archivos en la carpeta del proyecto:", faltan)
        print("Comprueba que ejecutas esto dentro de la carpeta de HotelMonitor.")
        sys.exit(1)

    if shutil.which("node") is None:
        print("No encuentro Node.js instalado (o no está en el PATH).")
        print("Instálalo desde https://nodejs.org (versión LTS) y vuelve a intentarlo.")
        print("Esto es lo mismo que necesita el cruce automático dentro de scraper.py --")
        print("si no está instalado, ese cruce tampoco se está ejecutando cuando scrapeas.")
        sys.exit(1)

    with open(ruta("hoteles_cache.json"), "r", encoding="utf-8") as f:
        cache = json.load(f)
    activos = [h for h in cache if h.get("estado") != "Retirado"]
    print(f"Anuncios activos en la caché: {len(activos)}")

    tmp_in = ruta("_tmp_comprobar_activos.json")
    tmp_out = ruta("_tmp_comprobar_resultado.json")
    try:
        with open(tmp_in, "w", encoding="utf-8") as f:
            json.dump(activos, f, ensure_ascii=False)

        resultado = subprocess.run(
            ["node", ruta("cruzar_licencias.js"), ruta("index_template.html"),
             ruta("licencias_completo.json"), tmp_in, tmp_out],
            cwd=CARPETA, capture_output=True, text=True, timeout=900,
        )
        if resultado.stdout:
            print(resultado.stdout.strip())
        if resultado.returncode != 0:
            print("\ncruzar_licencias.js ha fallado -- nada que revisar, revisa el error de arriba:")
            print(resultado.stderr.strip())
            sys.exit(1)

        with open(tmp_out, "r", encoding="utf-8") as f:
            por_url = json.load(f)
    finally:
        for p in (tmp_in, tmp_out):
            if os.path.exists(p):
                os.remove(p)

    # Informe legible: una fila por anuncio activo, ordenado para que los
    # que SÍ tienen licencia salgan primero.
    filas = []
    for h in activos:
        info = por_url.get(h.get("url"), {})
        texto = info.get("licencia_texto", "") or ""
        motivo = info.get("licencia_motivo", "") or ""
        filas.append({
            "Municipio/Zona": h.get("location", ""),
            "Habitaciones": h.get("rooms", ""),
            "Portal": h.get("source", ""),
            "Título": h.get("title", ""),
            "Licencia cruzada": texto,
            "Motivo": motivo,
            "URL": h.get("url", ""),
        })
    filas.sort(key=lambda r: (0 if r["Licencia cruzada"] else 1, r["Municipio/Zona"]))

    salida_csv = ruta("comprobacion_licencias.csv")
    with open(salida_csv, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0].keys()) if filas else [])
        w.writeheader()
        w.writerows(filas)

    con_licencia = sum(1 for r in filas if r["Licencia cruzada"])
    print(f"\nCon licencia identificada: {con_licencia} / {len(activos)} "
          f"({100*con_licencia/max(len(activos),1):.1f}%)")
    print(f"Informe detallado guardado en: {salida_csv}")


if __name__ == "__main__":
    main()
