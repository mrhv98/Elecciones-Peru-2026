# 🇵🇪 Visualizador de Elecciones Generales Perú 2026 — v3.0

Dashboard interactivo de resultados electorales peruanos con datos de la ONPE.

## Novedades v3.0

- **Mapas corregidos**: el hover muestra el nombre real de la región/provincia (no el código interno)
- **Doble barrera electoral**: 5% de votos + mínimo de escaños (3 senadores / 7 diputados), aplicada de forma iterativa
- **Scraping integrado**: descarga automática de datos ONPE al iniciar si faltan o están desactualizados
- **Listo para hosting**: preparado para desplegar en Render (gratis)

---

## Uso local

```bash
# 1. Instalar dependencias
pip install -r requirements.txt

# 2. Colocar archivos necesarios en la carpeta:
#    - DEPARTAMENTOS_inei_geogpsperu_suyopomalia.shp (.dbf .shx .prj)
#    - PROVINCIAS_inei_geogpsperu_suyopomalia.shp (.dbf .shx .prj)
#    - resultados_onpe_2026.xlsx (se descarga automáticamente si no existe)

# 3. Ejecutar
python dashboard.py

# 4. Abrir en el navegador
#    http://127.0.0.1:8050/
```

---

## Despliegue en Render (hosting gratuito)

### Paso 1: Crear repositorio en GitHub

```bash
# En tu carpeta del proyecto (donde están dashboard.py, scraper_onpe.py, etc.)
git init
git add .
git commit -m "Dashboard electoral Peru 2026 v3.0"

# Crear repo en github.com → New Repository → "elecciones-peru-2026"
git remote add origin https://github.com/TU_USUARIO/elecciones-peru-2026.git
git branch -M main
git push -u origin main
```

**IMPORTANTE**: Asegúrate de que los shapefiles (.shp, .dbf, .shx, .prj) estén incluidos en el repositorio. Git los incluirá por defecto ya que no están en el .gitignore. El Excel (resultados_onpe_2026.xlsx) se puede incluir también como respaldo, o dejar que el scraper lo descargue automáticamente al arrancar.

### Paso 2: Crear cuenta en Render

1. Ve a [https://render.com](https://render.com)
2. Regístrate con tu cuenta de GitHub (más fácil para conectar repos)
3. Plan Free — no necesitas tarjeta de crédito

### Paso 3: Crear el servicio web

1. En el Dashboard de Render, click **"New +"** → **"Web Service"**
2. Conecta tu repositorio de GitHub `elecciones-peru-2026`
3. Configura:
   - **Name**: `elecciones-peru-2026` (o el que quieras)
   - **Region**: Oregon (US West) u Ohio (US East)
   - **Branch**: `main`
   - **Runtime**: `Python`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python dashboard.py`
   - **Instance Type**: **Free**
4. Click **"Create Web Service"**

### Paso 4: Esperar al despliegue

- Render instalará las dependencias y arrancará el dashboard
- El primer despliegue tarda 3-5 minutos
- Tu URL será algo como: `https://elecciones-peru-2026.onrender.com`

### Notas sobre el plan Free de Render

- La instancia se **duerme tras 15 minutos de inactividad**. La primera visita tras dormir tarda ~30 segundos en despertar.
- **750 horas/mes gratis** — más que suficiente para un proyecto personal.
- Si necesitas que no se duerma, puedes usar un servicio como [UptimeRobot](https://uptimerobot.com) para hacer ping cada 14 minutos (gratis también).
- La memoria es limitada (512 MB). Los shapefiles grandes pueden ser un problema. Si tienes errores de memoria, considera simplificar las geometrías de los shapefiles.

### Actualizar el dashboard

Cada vez que hagas `git push` a `main`, Render re-despliega automáticamente:

```bash
# Tras modificar algo
git add .
git commit -m "Actualización de datos"
git push
```

---

## Estructura del proyecto

```
elecciones-peru-2026/
├── dashboard.py                    # App principal (Dash)
├── scraper_onpe.py                 # Módulo de scraping ONPE
├── requirements.txt                # Dependencias Python
├── render.yaml                     # Config de Render
├── .gitignore
├── README.md
├── resultados_onpe_2026.xlsx       # Datos (auto-generado por scraper)
├── DEPARTAMENTOS_inei_*.shp/dbf/shx/prj   # Shapefiles departamentos
└── PROVINCIAS_inei_*.shp/dbf/shx/prj      # Shapefiles provincias
```

---

## Barreras electorales — cómo funcionan

### Senado
1. **Barrera 1 (5%)**: el partido debe obtener ≥ 5% del promedio de votos válidos de Senado Nacional + Senado Regional
2. **Barrera 2 (3 escaños)**: tras el reparto D'Hondt, el partido debe tener ≥ 3 senadores en total (Nacional + Regional)
3. Si un partido no cumple ambas, se elimina y se repite el reparto hasta que todos los que quedan cumplan

### Diputados
1. **Barrera 1 (5%)**: el partido debe obtener ≥ 5% de los votos válidos nacionales de Diputados
2. **Barrera 2 (7 escaños)**: tras el reparto D'Hondt, el partido debe tener ≥ 7 diputados en total
3. Mismo proceso iterativo que Senado

---

## Autoría

**Manuel F. Ruiz Huidobro Vera** — [LinkedIn](https://www.linkedin.com/in/manuel-f-ruiz-huidobro-vera-276394244/) · [mruiz@analistasperu.com](mailto:mruiz@analistasperu.com)

Datos: ONPE 2026
