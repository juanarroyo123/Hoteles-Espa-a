# 🏨 Hotel España — Radar de Hoteles en Venta

Agregador automático y gratuito de hoteles en venta en España. Se actualiza cada día a las 8:00h automáticamente.

## 🚀 Configuración paso a paso

### 1. Crear cuenta en GitHub
1. Ve a [github.com](https://github.com) y haz clic en **Sign up**
2. Elige un nombre de usuario (p.ej. `tuusuario`)
3. Verifica tu email

### 2. Crear el repositorio
1. Haz clic en el **+** arriba a la derecha → **New repository**
2. Nombre del repositorio: `hoteles-espana`
3. Márcalo como **Public**
4. Haz clic en **Create repository**

### 3. Subir los archivos
Sube estos 3 archivos al repositorio:
- `scraper.py` → el script de scraping
- `.github/workflows/scrape.yml` → la automatización diaria
- `index.html` → la web (se regenera sola, pero súbela la primera vez)

Para subir archivos: en tu repositorio haz clic en **Add file → Upload files**

### 4. Activar GitHub Pages
1. En tu repositorio ve a **Settings → Pages**
2. En **Source** selecciona **Deploy from a branch**
3. Rama: **main**, carpeta: **/ (root)**
4. Haz clic en **Save**

### 5. ¡Listo!
Tu web estará disponible en:
```
https://tuusuario.github.io/hoteles-espana
```

Sustitiye `tuusuario` por tu nombre de usuario de GitHub.

---

## ⚙️ Cómo funciona

| Componente | Función |
|---|---|
| `scraper.py` | Hace scraping de Idealista, Fotocasa, Kyero, ThinkSpain y Habitaclia |
| `scrape.yml` | GitHub Actions ejecuta el scraper cada día a las 8:00h |
| `index.html` | Web con diseño elegante que muestra todos los anuncios |

## 🔄 Ejecutar manualmente
En GitHub, ve a **Actions → Actualizar Hoteles en Venta → Run workflow**

## 📋 Portales rastreados
- [Idealista](https://www.idealista.com)
- [Fotocasa](https://www.fotocasa.es)
- [Habitaclia](https://www.habitaclia.com)
- [Kyero](https://www.kyero.com)
- [ThinkSpain](https://www.thinkspain.com)

## 💰 Coste total
**0 €** — GitHub Actions gratuito (2.000 minutos/mes), GitHub Pages gratuito.
