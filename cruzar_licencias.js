#!/usr/bin/env node
'use strict';
const fs = require('fs');

const [,, templatePath, licenciasPath, activosPath, outPath] = process.argv;

if (!fs.existsSync(licenciasPath)) {
  console.log('cruzar_licencias.js: no hay licencias_completo.json todavia -- se omite el cruce.');
  fs.writeFileSync(outPath, '{}');
  process.exit(0);
}

const html = fs.readFileSync(templatePath, 'utf-8');

function extraer(desde, hasta) {
  const i0 = html.indexOf(desde);
  if (i0 === -1) return null;
  const i1 = html.indexOf(hasta, i0);
  if (i1 === -1) return null;
  return html.slice(i0, i1);
}

const bloquePrioridad = extraer('const PRIORIDAD_DEFECTO = [', '\nasync function descargarExcel()');
const bloquePrincipal = extraer('let columnasLicencias = [];', 'const CABECERA = [');

if (!bloquePrioridad || !bloquePrincipal) {
  console.error('cruzar_licencias.js: no se encontraron los marcadores esperados en ' + templatePath +
                 ' (¿cambió el template?) -- se omite el cruce para no arriesgar datos incorrectos.');
  fs.writeFileSync(outPath, '{}');
  process.exit(1);
}

const activos = JSON.parse(fs.readFileSync(activosPath, 'utf-8'));
// IMPORTANTE: este script es la fuente de verdad que recalcula el cruce
// cada vez que se scrapea -- si un anuncio ya trae licencia_texto/motivo de
// una ejecución anterior (persistido en hoteles_cache.json), cruzarLicencia()
// lo detectaría como "ya calculado" y lo devolvería sin más (ese atajo existe
// para que la web no repita el cálculo en el navegador). Aquí es al revés:
// SIEMPRE queremos recalcular con los datos de hoy (nuevas licencias,
// mejoras en la lógica, etc.), así que borramos cualquier valor previo
// antes de llamar a cruzarLicencia.
for (const h of activos) { delete h.licencia_texto; delete h.licencia_motivo; }

global.fetch = async (url) => {
  try {
    // En produccion, el navegador pide 'licencias_completo.json' (ruta
    // relativa, mismo directorio que index.html). Aqui la hacemos apuntar
    // al fichero real que nos pasaron por argumento.
    const ruta = url === 'licencias_completo.json' ? licenciasPath : url;
    const texto = fs.readFileSync(ruta, 'utf-8');
    return { ok: true, status: 200, json: async () => JSON.parse(texto) };
  } catch (e) {
    return { ok: false, status: 404 };
  }
};

const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
const cuerpo = [
  'let botonExcel; let textoOriginalBoton;',
  bloquePrioridad,
  bloquePrincipal,
  'return { cruzarLicencia };',
].join('\n');

(async () => {
  let cruzarLicencia;
  try {
    const fn = new AsyncFunction('HOTELES_RAW_PARA_EXCEL', cuerpo);
    ({ cruzarLicencia } = await fn(activos));
  } catch (e) {
    console.error('cruzar_licencias.js: error ejecutando la logica de cruce extraida del template:', e);
    fs.writeFileSync(outPath, '{}');
    process.exit(1);
    return;
  }

  const resultado = {};
  let conLicencia = 0;
  for (const h of activos) {
    const [texto, motivo] = cruzarLicencia(h);
    if (h.url) {
      resultado[h.url] = { licencia_texto: texto || '', licencia_motivo: motivo || '' };
      if (texto) conLicencia++;
    }
  }
  fs.writeFileSync(outPath, JSON.stringify(resultado));
  console.log(`cruzar_licencias.js: ${conLicencia} / ${activos.length} anuncios activos con licencia identificada (${(100*conLicencia/Math.max(activos.length,1)).toFixed(1)}%).`);
})();
