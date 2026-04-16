"""
╔════════════════════════════════════════════════════════════════════════════════╗
║  VISUALIZADOR DE ELECCIONES GENERALES PERÚ 2026  v3.0                        ║
║  Autores: Manuel F. Ruiz Huidobro Vera & Ignacio Alvarez Calvo-Parra        ║
║  Datos: ONPE 2026                                                            ║
╚════════════════════════════════════════════════════════════════════════════════╝

Cambios v3.0:
  - Mapas: hover muestra nombre real de región/provincia (no código)
  - Doble barrera electoral: 5% + mínimo 3 senadores / 7 diputados (iterativo)
  - Scraper ONPE integrado: descarga automática al inicio si faltan datos
  - Preparado para hosting en Render (lee PORT del entorno)

Uso local:
    pip install -r requirements.txt
    python dashboard.py
    Abre: http://127.0.0.1:8050/
"""

# ─────────────────────────────────────────────
#  IMPORTACIONES
# ─────────────────────────────────────────────
import os, sys, warnings, json, unicodedata, time
import pandas as pd
import geopandas as gpd
import plotly.graph_objects as go
import plotly.io as pio
from dash import Dash, dcc, html, Input, Output, State
import numpy as np

warnings.filterwarnings("ignore")

# ─────────────────────────────────────────────
#  RUTAS
# ─────────────────────────────────────────────
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
EXCEL_PATH = os.path.join(BASE_DIR, "resultados_onpe_2026.xlsx")
SHP_DEPTO  = os.path.join(BASE_DIR, "DEPARTAMENTOS_inei_geogpsperu_suyopomalia.shp")
SHP_PROV   = os.path.join(BASE_DIR, "PROVINCIAS_inei_geogpsperu_suyopomalia.shp")

# Máximo antigüedad del Excel antes de re-descargar (horas)
MAX_ANTIGUEDAD_HORAS = 6

def validar_archivos():
    errores = []
    for ruta, nombre in [(EXCEL_PATH,"Excel"),(SHP_DEPTO,"SHP Departamentos"),(SHP_PROV,"SHP Provincias")]:
        if not os.path.exists(ruta):
            errores.append(f"  X No encontrado: {ruta}  [{nombre}]")
    if errores:
        print("\nARCHIVOS FALTANTES:\n" + "\n".join(errores))
        sys.exit(1)
    print("Archivos encontrados correctamente.")

def excel_necesita_actualizar():
    """True si el Excel no existe o es más antiguo que MAX_ANTIGUEDAD_HORAS."""
    if not os.path.exists(EXCEL_PATH):
        return True
    edad_seg = time.time() - os.path.getmtime(EXCEL_PATH)
    edad_hrs = edad_seg / 3600
    if edad_hrs > MAX_ANTIGUEDAD_HORAS:
        print(f"  Excel tiene {edad_hrs:.1f}h de antigüedad (máx {MAX_ANTIGUEDAD_HORAS}h)")
        return True
    return False

def intentar_scraping():
    """Intenta descargar datos de ONPE. Retorna True si tuvo éxito."""
    try:
        from scraper_onpe import run_scraper
        print("\n  Descargando datos de ONPE...")
        return run_scraper(EXCEL_PATH)
    except ImportError:
        print("  [WARN] scraper_onpe.py no encontrado. Usando Excel existente.")
        return False
    except Exception as e:
        print(f"  [ERROR] Scraping falló: {e}")
        return False

# ─────────────────────────────────────────────
#  PALETA — un partido = un color en TODO el dashboard
# ─────────────────────────────────────────────
COLORES_PARTIDO = {
    "RENOVACION POPULAR"                                           : "#003366",
    "FUERZA POPULAR"                                               : "#FF6600",
    "AHORA NACION - AN"                                            : "#808080",
    "PARTIDO DEL BUEN GOBIERNO"                                    : "#FFD700",
    "JUNTOS POR EL PERU"                                           : "#CC0000",
    "PARTIDO CIVICO OBRAS"                                         : "#008000",
    "PARTIDO PAIS PARA TODOS"                                      : "#9B59B6",
    "PRIMERO LA GENTE - COMUNIDAD, ECOLOGIA, LIBERTAD Y PROGRESO"  : "#1ABC9C",
    "PARTIDO SICREO"                                               : "#E74C3C",
    "ALIANZA PARA EL PROGRESO"                                     : "#F39C12",
    "PODEMOS PERU"                                                 : "#2ECC71",
    "PARTIDO APRISTA PERUANO"                                      : "#E67E22",
    "PARTIDO FRENTE DE LA ESPERANZA 2021"                          : "#D35400",
    "FRENTE POPULAR AGRICOLA FIA DEL PERU"                         : "#5D6D7E",
    "PARTIDO DEMOCRATICO SOMOS PERU"                               : "#A93226",
    "ALIANZA ELECTORAL VENCEREMOS"                                 : "#117A65",
    "OTROS"                                                        : "#BBBBBB",
    "VOTOS EN BLANCO"                                              : "#D5D8DC",
    "VOTOS NULOS"                                                  : "#F5CBA7",
}

COLOR_OTRO   = "#BBBBBB"
COLOR_FONDO  = "#F8F9FA"
COLOR_HEADER = "#1a1a2e"
COLOR_ACCENT = "#e94560"
COLOR_TEXT   = "#2c3e50"

def normalizar(texto):
    """Elimina tildes, mayúsculas, espacios extra."""
    if not isinstance(texto, str): return ""
    texto = texto.strip().upper()
    texto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in texto if not unicodedata.combining(c))

def color_partido(nombre):
    key = normalizar(nombre) if nombre else ""
    return COLORES_PARTIDO.get(key, COLOR_OTRO)

def colores_lista(nombres):
    return [color_partido(n) for n in nombres]

# ─────────────────────────────────────────────
#  NORMALIZACIÓN DE NOMBRES DE CANDIDATOS
# ─────────────────────────────────────────────
CANDIDATOS_NORM = {
    "KEIKO SOFIA FUJIMORI HIGUCHI"         : "Keiko Fujimori",
    "RAFAEL BERNARDO LOPEZ ALIAGA CAZORLA" : "Rafael Lopez Aliaga",
    "JORGE NIETO MONTESINOS"               : "Jorge Nieto",
    "ROBERTO HELBERT SANCHEZ PALOMINO"     : "Roberto Sanchez",
    "RICARDO PABLO BELMONT CASSINELLI"     : "Ricardo Belmont",
    "CARLOS GONSALO ALVAREZ LOAYZA"        : "Carlos Alvarez",
    "PABLO ALFONSO LOPEZ CHAU NAVA"        : "Alfonso Lopez Chau",
    "MARIA SOLEDAD PEREZ TELLO"            : "Maria Perez Tello",
    "LUIS FERNANDO OLIVERA VEGA"           : "Luis Olivera",
}

def norm_candidato(nombre):
    if pd.isna(nombre) or not nombre: return ""
    key = normalizar(str(nombre))
    return CANDIDATOS_NORM.get(key, str(nombre).title())

# ─────────────────────────────────────────────
#  CONSTANTES ELECTORALES
# ─────────────────────────────────────────────
CODIGOS_NO_PARTIDO = {80, 81}
ESCANOS_SEN_NAC    = 30

# Mínimo de escaños para pasar la segunda barrera
MIN_ESCANOS_SENADO    = 3
MIN_ESCANOS_DIPUTADOS = 7

ESCANOS_SEN_REG = {
    "LIMA METROPOLITANA"                  : 4,
    "PERUANOS RESIDENTES EN EL EXTRANJERO": 1,
    "AMAZONAS":1,"ANCASH":1,"APURIMAC":1,"AREQUIPA":1,"AYACUCHO":1,
    "CAJAMARCA":1,"CALLAO":1,"CUSCO":1,"HUANCAVELICA":1,"HUANUCO":1,
    "ICA":1,"JUNIN":1,"LA LIBERTAD":1,"LAMBAYEQUE":1,"LIMA PROVINCIAS":1,
    "LORETO":1,"MADRE DE DIOS":1,"MOQUEGUA":1,"PASCO":1,"PIURA":1,
    "PUNO":1,"SAN MARTIN":1,"TACNA":1,"TUMBES":1,"UCAYALI":1,
}

ESCANOS_DIP = {
    "LIMA":32,"LIMA METROPOLITANA":32,
    "LA LIBERTAD":7,"PIURA":7,
    "AREQUIPA":6,"CAJAMARCA":6,
    "ANCASH":5,"CUSCO":5,"JUNIN":5,"LAMBAYEQUE":5,"PUNO":5,
    "CALLAO":4,"ICA":4,"LIMA PROVINCIAS":4,"LORETO":4,"SAN MARTIN":4,
    "AYACUCHO":3,"HUANUCO":3,"UCAYALI":3,
    "AMAZONAS":2,"APURIMAC":2,"HUANCAVELICA":2,
    "MADRE DE DIOS":2,"MOQUEGUA":2,"PASCO":2,"TACNA":2,
    "TUMBES":2,"PERUANOS RESIDENTES EN EL EXTRANJERO":2,
}

# ─────────────────────────────────────────────
#  D'HONDT
# ─────────────────────────────────────────────
def dhondt_escanos(votos_dict, escanos):
    """D'Hondt: retorna {partido: n_escanos}."""
    if escanos <= 0 or not votos_dict: return {}
    filas = [
        {"partido": p, "cociente": v / d}
        for p, v in votos_dict.items()
        for d in range(1, escanos + 1)
    ]
    df = pd.DataFrame(filas).nlargest(escanos, "cociente")
    return df.groupby("partido").size().to_dict()

def dhondt_margen(votos_dict, escanos, n=3):
    """Tabla de últimos escaños dentro y primeros fuera."""
    if escanos <= 0 or not votos_dict: return pd.DataFrame()
    filas = [
        {"partido": p, "cociente": v / d, "divisor": d, "votos": v}
        for p, v in votos_dict.items()
        for d in range(1, escanos + 2)
    ]
    df = pd.DataFrame(filas).sort_values("cociente", ascending=False).reset_index(drop=True)
    df["posicion"] = df.index + 1
    df["estado"]   = df["posicion"].apply(lambda x: "Dentro" if x <= escanos else "Fuera")
    dentro = df[df["posicion"] <= escanos].tail(n)
    fuera  = df[df["posicion"] >  escanos].head(n)
    res    = pd.concat([dentro, fuera]).copy()
    res["votos_cociente"] = (res["cociente"] * res["divisor"]).astype(int)
    return res[["estado","posicion","partido","votos_cociente","divisor","cociente"]]

# ─────────────────────────────────────────────
#  BARRERAS ELECTORALES (primera: 5%)
# ─────────────────────────────────────────────
def barrera_senado_5pct(sen_nac_df, sen_reg_df, total_sn_valid, total_sr_valid):
    """Primera barrera: >= 5% combinado (SenNac + SenReg)/2."""
    excl = CODIGOS_NO_PARTIDO
    sn_v = sen_nac_df[~sen_nac_df["codigo_agrupacion"].isin(excl)].groupby("agrupacion_politica")["votos_validos"].sum()
    sr_v = sen_reg_df[~sen_reg_df["codigo_agrupacion"].isin(excl)].groupby("agrupacion_politica")["votos_validos"].sum()

    total_comb = (total_sn_valid + total_sr_valid) / 2
    comb = pd.DataFrame({"sn": sn_v, "sr": sr_v}).fillna(0)
    comb["pct"] = ((comb["sn"] + comb["sr"]) / 2) / total_comb * 100

    hab = set(comb[comb["pct"] >= 5.0].index)
    print(f"  [Barrera 1ª Senado >=5%] {len(hab)} partidos habilitados")
    return hab

def barrera_diputados_5pct(dip_df, total_dip_valid):
    """Primera barrera: >= 5% nacional Diputados."""
    excl  = CODIGOS_NO_PARTIDO
    df    = dip_df[~dip_df["codigo_agrupacion"].isin(excl)]
    votos = df.groupby("agrupacion_politica")["votos_validos"].sum()
    pct   = votos / total_dip_valid * 100
    hab   = set(pct[pct >= 5.0].index)
    print(f"  [Barrera 1ª Diputados >=5%] {len(hab)} partidos habilitados")
    return hab

# ─────────────────────────────────────────────
#  CARGA DE DATOS
# ─────────────────────────────────────────────
def cargar_datos():
    xl = pd.ExcelFile(EXCEL_PATH)
    return {
        "pres_nac"  : pd.read_excel(xl, "PRES_Nacional"),
        "pres_dep"  : pd.read_excel(xl, "PRES_Departamento"),
        "pres_prov" : pd.read_excel(xl, "PRES_Provincia"),
        "sen_nac"   : pd.read_excel(xl, "SEN_NAC_Nacional"),
        "sen_reg"   : pd.read_excel(xl, "SEN_REG_Region"),
        "dip_reg"   : pd.read_excel(xl, "DIPUTADOS_Region"),
        "meta_nac"  : pd.read_excel(xl, "METADATA_Nacional"),
    }

def cargar_shapefiles():
    gdf_dep  = gpd.read_file(SHP_DEPTO).to_crs(epsg=4326)
    gdf_prov = gpd.read_file(SHP_PROV).to_crs(epsg=4326)
    return gdf_dep, gdf_prov

def detectar_col(gdf, candidatos):
    cu = {c.upper(): c for c in gdf.columns}
    for c in candidatos:
        if c.upper() in cu: return cu[c.upper()]
    for c in gdf.columns:
        if any(k in c.upper() for k in ("NOMB","NAME","DEPART","PROVIN")):
            return c
    raise ValueError(f"Sin col nombre. Disponibles: {list(gdf.columns)}")

def detectar_col_dep_en_prov(gdf):
    candidatos = ["NOMBDEP","NOMB_DEP","DEPARTAMEN","DEPARTAMENTO","DEP","DPTO","DEPTO"]
    cu = {c.upper(): c for c in gdf.columns}
    for c in candidatos:
        if c in cu: return cu[c]
    for c in gdf.columns:
        if "DEP" in c.upper() or "DPTO" in c.upper(): return c
    return None

# ─────────────────────────────────────────────
#  SEPARAR LIMA METROPOLITANA / PROVINCIAS
# ─────────────────────────────────────────────
LIMA_METRO_PROV = {"LIMA"}

def crear_lima_dividida(gdf_prov):
    col_dep  = detectar_col_dep_en_prov(gdf_prov)
    col_prov = detectar_col(gdf_prov, ("NOMBPROV","NOMB_PROV","PROVINCIA","NOM_PROV","NOMBRE"))
    if col_dep is None:
        print("  [WARN] Sin col departamento en provincias.shp; Lima no se dividira.")
        return None
    mask_lima = gdf_prov[col_dep].apply(normalizar) == "LIMA"
    lima      = gdf_prov[mask_lima].copy()
    if lima.empty:
        print("  [WARN] No hay provincias Lima en shapefile.")
        return None
    mask_metro = lima[col_prov].apply(normalizar).isin(LIMA_METRO_PROV)
    geo_metro  = lima[mask_metro].geometry.unary_union
    geo_prov   = lima[~mask_metro].geometry.unary_union
    rows = []
    if geo_metro: rows.append({"nombre": "LIMA METROPOLITANA", "geometry": geo_metro})
    if geo_prov : rows.append({"nombre": "LIMA PROVINCIAS",    "geometry": geo_prov})
    if not rows: return None
    gdf_lima = gpd.GeoDataFrame(rows, crs=gdf_prov.crs)
    print(f"  Lima dividida: {[r['nombre'] for r in rows]}")
    return gdf_lima

def gdf_con_lima_dividida(gdf_dep, gdf_lima):
    if gdf_lima is None: return gdf_dep
    col = detectar_col(gdf_dep, ("NOMBDEP","NOMB_DEP","DEPARTAMENTO","NOMBRE","NOM_DEP"))
    sin_lima = gdf_dep[gdf_dep[col].apply(normalizar) != "LIMA"].copy()
    for _, row in gdf_lima.iterrows():
        nueva = {c: None for c in gdf_dep.columns}
        nueva[col] = row["nombre"]
        nueva["geometry"] = row["geometry"]
        sin_lima = pd.concat(
            [sin_lima, gpd.GeoDataFrame([nueva], crs=gdf_dep.crs)],
            ignore_index=True
        )
    return sin_lima.reset_index(drop=True)

# ─────────────────────────────────────────────
#  CÁLCULOS ELECTORALES
# ─────────────────────────────────────────────
def calcular_senado(sen_nac_df, sen_reg_df, habilitados):
    excl = CODIGOS_NO_PARTIDO
    sn = sen_nac_df[
        (~sen_nac_df["codigo_agrupacion"].isin(excl)) &
        (sen_nac_df["agrupacion_politica"].isin(habilitados))
    ]
    votos_sn    = sn.set_index("agrupacion_politica")["votos_validos"].to_dict()
    escanos_nac = dhondt_escanos(votos_sn, ESCANOS_SEN_NAC)

    sr = sen_reg_df[
        (~sen_reg_df["codigo_agrupacion"].isin(excl)) &
        (sen_reg_df["agrupacion_politica"].isin(habilitados))
    ]
    escanos_reg = {}
    for region, grp in sr.groupby("departamento"):
        n_key = normalizar(region)
        n = ESCANOS_SEN_REG.get(n_key, 1)
        votos = grp.set_index("agrupacion_politica")["votos_validos"].to_dict()
        escanos_reg[region] = dhondt_escanos(votos, n)

    return escanos_nac, escanos_reg, votos_sn

def calcular_diputados(dip_df, habilitados):
    excl = CODIGOS_NO_PARTIDO
    df   = dip_df[
        (~dip_df["codigo_agrupacion"].isin(excl)) &
        (dip_df["agrupacion_politica"].isin(habilitados))
    ]
    escanos = {}
    for region, grp in df.groupby("departamento"):
        n_key = normalizar(region)
        n = ESCANOS_DIP.get(n_key, 2)
        votos = grp.set_index("agrupacion_politica")["votos_validos"].to_dict()
        escanos[region] = dhondt_escanos(votos, n)
    return escanos

def sumar_escanos(*dicts):
    total = {}
    for d in dicts:
        for p, n in d.items():
            total[p] = total.get(p, 0) + n
    return total

def total_de_regiones(escanos_reg_dict):
    total = {}
    for rd in escanos_reg_dict.values():
        for p, n in rd.items():
            total[p] = total.get(p, 0) + n
    return total

def ganadores_por_grupo(df, cols):
    dv  = df[~df["codigo_agrupacion"].isin(CODIGOS_NO_PARTIDO)].copy()
    idx = dv.groupby(cols)["votos_validos"].idxmax()
    return dv.loc[idx].reset_index(drop=True)

# ─────────────────────────────────────────────
#  DOBLE BARRERA ELECTORAL (iterativa)
# ─────────────────────────────────────────────
def aplicar_doble_barrera_senado(sen_nac_df, sen_reg_df, total_sn_valid, total_sr_valid):
    """
    Barrera iterativa Senado:
      1) >= 5% del promedio combinado SenNac + SenReg
      2) >= 3 escaños totales (Nacional + Regional)
    Si al quitar partidos que no cumplen la 2ª barrera cambia el reparto,
    se repite hasta que todos los que quedan cumplen ambas.
    """
    hab = barrera_senado_5pct(sen_nac_df, sen_reg_df, total_sn_valid, total_sr_valid)

    iteracion = 0
    while True:
        iteracion += 1
        escanos_nac, escanos_reg, votos_sn = calcular_senado(sen_nac_df, sen_reg_df, hab)
        total_sen = sumar_escanos(escanos_nac, total_de_regiones(escanos_reg))

        eliminados = {p for p, n in total_sen.items() if n < MIN_ESCANOS_SENADO}

        if not eliminados:
            print(f"  [Doble barrera Senado] Convergió en {iteracion} iteración(es)")
            print(f"  [Doble barrera Senado] {len(hab)} partidos finales: "
                  f"{', '.join(sorted(p[:25] for p in hab))}")
            break

        print(f"  [Doble barrera Senado — iter {iteracion}] Eliminados (<{MIN_ESCANOS_SENADO} escaños): "
              f"{', '.join(sorted(p[:25] for p in eliminados))}")
        hab -= eliminados

    return hab, escanos_nac, escanos_reg, votos_sn


def aplicar_doble_barrera_diputados(dip_df, total_dip_valid):
    """
    Barrera iterativa Diputados:
      1) >= 5% votos válidos nacionales
      2) >= 7 escaños totales
    Mismo proceso iterativo que Senado.
    """
    hab = barrera_diputados_5pct(dip_df, total_dip_valid)

    iteracion = 0
    while True:
        iteracion += 1
        escanos_dip = calcular_diputados(dip_df, hab)
        total_dip = total_de_regiones(escanos_dip)

        eliminados = {p for p, n in total_dip.items() if n < MIN_ESCANOS_DIPUTADOS}

        if not eliminados:
            print(f"  [Doble barrera Diputados] Convergió en {iteracion} iteración(es)")
            print(f"  [Doble barrera Diputados] {len(hab)} partidos finales: "
                  f"{', '.join(sorted(p[:25] for p in hab))}")
            break

        print(f"  [Doble barrera Diputados — iter {iteracion}] Eliminados (<{MIN_ESCANOS_DIPUTADOS} escaños): "
              f"{', '.join(sorted(p[:25] for p in eliminados))}")
        hab -= eliminados

    return hab, escanos_dip

# ─────────────────────────────────────────────
#  LAYOUT BASE
# ─────────────────────────────────────────────
def LB():
    return dict(
        paper_bgcolor="white", plot_bgcolor="white",
        font=dict(family="Inter, Arial, sans-serif", color=COLOR_TEXT, size=11),
        title_font=dict(size=14, color=COLOR_HEADER),
        hoverlabel=dict(bgcolor="white", font_size=11),
    )

# ─────────────────────────────────────────────
#  FIGURA: BARRAS PRESIDENCIALES
# ─────────────────────────────────────────────
def fig_barras_pres(pres_nac):
    excl = CODIGOS_NO_PARTIDO
    dv   = pres_nac[~pres_nac["codigo_agrupacion"].isin(excl)].copy()
    total_validos = dv["votos_validos"].sum()
    dv["pct_real"] = dv["votos_validos"] / total_validos * 100

    principales = dv[dv["pct_real"] >= 5.0].sort_values("votos_validos", ascending=True)
    menores     = dv[dv["pct_real"] <  5.0]

    fila_otros = {
        "agrupacion_politica": "OTROS",
        "candidato"          : f"{len(menores)} partidos con <5%",
        "votos_validos"      : menores["votos_validos"].sum(),
        "pct_votos_validos"  : menores["pct_real"].sum(),
        "pct_votos_emitidos" : menores["pct_votos_emitidos"].sum() if "pct_votos_emitidos" in menores.columns else 0,
    }

    def row_especial(codigo, nombre):
        r = pres_nac[pres_nac["codigo_agrupacion"] == codigo]
        return {
            "agrupacion_politica": nombre,
            "candidato": "",
            "votos_validos"      : int(r["votos_validos"].sum()) if not r.empty else 0,
            "pct_votos_validos"  : float("nan"),
            "pct_votos_emitidos" : float(r["pct_votos_emitidos"].sum()) if not r.empty else 0,
        }

    rows = [row_especial(81,"VOTOS NULOS"), row_especial(80,"VOTOS EN BLANCO"),
            fila_otros] + principales.to_dict("records")
    df_plot = pd.DataFrame(rows)

    def label_y(row):
        p = row["agrupacion_politica"]
        if p in ("VOTOS EN BLANCO","VOTOS NULOS","OTROS"):
            return p.title()
        cand = norm_candidato(row.get("candidato",""))
        return cand if cand else p

    labels_y = [label_y(r) for r in rows]
    colores   = colores_lista(df_plot["agrupacion_politica"])
    pct_text  = df_plot["pct_votos_validos"].apply(
        lambda x: f"{x:.1f}%" if pd.notna(x) and x > 0 else "")

    fig = go.Figure(go.Bar(
        y=labels_y,
        x=df_plot["votos_validos"],
        orientation="h",
        marker=dict(color=colores, line=dict(color="white", width=0.8)),
        width=0.7,
        customdata=np.column_stack([
            df_plot["agrupacion_politica"].fillna(""),
            [norm_candidato(r.get("candidato","")) for r in rows],
            df_plot["votos_validos"].apply(lambda x: f"{int(x):,}"),
            df_plot["pct_votos_validos"].fillna(0).apply(lambda x: f"{x:.2f}%"),
            df_plot["pct_votos_emitidos"].fillna(0).apply(lambda x: f"{x:.2f}%"),
        ]),
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "Candidato: %{customdata[1]}<br>"
            "Votos: %{customdata[2]}<br>"
            "% validos: %{customdata[3]}<br>"
            "% emitidos: %{customdata[4]}<extra></extra>"
        ),
        text=pct_text,
        textposition="outside",
        textfont=dict(size=10),
    ))
    fig.update_layout(
        **LB(),
        title="Resultados Presidenciales — Votos Validos",
        xaxis=dict(tickformat=",", title="Votos"),
        yaxis=dict(tickfont=dict(size=10.5)),
        margin=dict(l=200, r=120, t=55, b=40),
        height=650,
    )
    return fig

# ─────────────────────────────────────────────
#  FIGURA: MAPA GENÉRICO DE GANADORES
#  FIX v3: hover muestra nombre real, no código
# ─────────────────────────────────────────────
def _mapa_ganadores(gdf, col_nombre, datos_df, key_col, partido_col, titulo="",
                    extra_hover=""):
    gdf   = gdf.copy()
    datos = datos_df.copy()
    gdf["_k"]   = gdf[col_nombre].apply(normalizar)
    datos["_k"] = datos[key_col].apply(normalizar)
    merged = gdf.merge(datos, on="_k", how="left")
    merged["idx"] = merged.index.astype(str)
    geojson = json.loads(merged.to_json())

    mapa_colores_norm = {normalizar(k): v for k, v in COLORES_PARTIDO.items()}
    partidos_ord = list(mapa_colores_norm.keys())

    n = len(partidos_ord)
    def pnum(p):
        key = normalizar(str(p))
        i = partidos_ord.index(key) if key in partidos_ord else partidos_ord.index("OTROS")
        return (i + 0.5) / n

    cscale = []
    for i, p in enumerate(partidos_ord):
        color = mapa_colores_norm[p]
        cscale.append([i / n,       color])
        cscale.append([(i + 1) / n, color])
    cscale[-1][0] = 1.0

    ganador_col = merged[partido_col].fillna("Sin datos")
    pct_col     = merged.get("pct_votos_validos", pd.Series([0.0]*len(merged))).fillna(0)
    # ── FIX: usar nombre real de la región/provincia ──
    nombre_col  = merged[col_nombre].fillna("Sin nombre")

    fig = go.Figure(go.Choropleth(
        geojson=geojson,
        locations=merged["idx"],
        z=[pnum(p) for p in merged[partido_col].fillna("OTRO")],
        zmin=0,
        zmax=1,
        colorscale=cscale,
        showscale=False,
        featureidkey="id",
        marker_line_color="white",
        marker_line_width=0.7,
        customdata=np.column_stack([
            ganador_col.values,
            pct_col.values,
            nombre_col.values,       # ← nombre real
        ]),
        hovertemplate=(
            "<b>%{customdata[2]}</b><br>"     # ← nombre real en vez de %{location}
            "Ganador: %{customdata[0]}<br>"
            "% validos: %{customdata[1]:.1f}%" +
            extra_hover + "<extra></extra>"
        ),
    ))
    fig.update_geos(fitbounds="locations", visible=False, projection_type="mercator")
    fig.update_layout(**LB(), title=titulo, height=520,
                      margin=dict(l=0, r=0, t=50, b=0))
    return fig

def fig_mapa_dep(pres_dep, gdf_dep):
    gan = ganadores_por_grupo(pres_dep, ["departamento"])
    col = detectar_col(gdf_dep, ("NOMBDEP","NOMB_DEP","DEPARTAMENTO","NOMBRE","NOM_DEP"))
    return _mapa_ganadores(gdf_dep, col, gan, "departamento", "agrupacion_politica",
                            titulo="Ganador Presidencial por Departamento")

def fig_mapa_prov(pres_prov, gdf_prov):
    gan = ganadores_por_grupo(pres_prov, ["departamento","provincia"])
    col = detectar_col(gdf_prov, ("NOMBPROV","NOMB_PROV","PROVINCIA","NOM_PROV","NOMBRE"))
    return _mapa_ganadores(gdf_prov, col, gan, "provincia", "agrupacion_politica",
                            titulo="Ganador Presidencial por Provincia")

# ─────────────────────────────────────────────
#  FIGURA: MAPA DE CALOR POR PARTIDO
#  FIX v3: hover muestra nombre real
# ─────────────────────────────────────────────
def fig_heat_partido(pres_dep, partido, gdf_dep):
    excl = CODIGOS_NO_PARTIDO
    df   = pres_dep[(~pres_dep["codigo_agrupacion"].isin(excl)) &
                    (pres_dep["agrupacion_politica"] == partido)].copy()
    col  = detectar_col(gdf_dep, ("NOMBDEP","NOMB_DEP","DEPARTAMENTO","NOMBRE","NOM_DEP"))
    gdf  = gdf_dep.copy()
    gdf["_k"] = gdf[col].apply(normalizar)
    df["_k"]  = df["departamento"].apply(normalizar)
    merged = gdf.merge(df[["_k","pct_votos_validos","candidato"]], on="_k", how="left")
    merged["idx"] = merged.index.astype(str)
    geojson = json.loads(merged.to_json())

    color_b = COLORES_PARTIDO.get(normalizar(partido), "#888")
    cand    = df["candidato"].dropna().iloc[0] if len(df) > 0 else ""
    titulo  = f"{partido[:22]} — {norm_candidato(cand)}"

    # ── FIX: nombre real en hover ──
    nombre_col = merged[col].fillna("Sin nombre")

    fig = go.Figure(go.Choropleth(
        geojson=geojson,
        locations=merged["idx"],
        z=merged["pct_votos_validos"].fillna(0),
        colorscale=[[0,"#EEEEEE"],[1,color_b]],
        featureidkey="id",
        marker_line_color="white", marker_line_width=0.4,
        colorbar=dict(title="%", thickness=8, len=0.45, tickfont=dict(size=8)),
        customdata=nombre_col.values.reshape(-1, 1),
        hovertemplate="<b>%{customdata[0]}</b><br>% validos: %{z:.1f}%<extra></extra>",
    ))
    fig.update_geos(fitbounds="locations", visible=False, projection_type="mercator")
    fig.update_layout(
        **LB(),
        title=dict(text=titulo, font=dict(size=10)),
        height=270,
        margin=dict(l=0, r=28, t=36, b=0),
    )
    return fig

def fig_mapa_senado_reg(sen_reg_df, gdf_ext):
    excl = CODIGOS_NO_PARTIDO
    df   = sen_reg_df[~sen_reg_df["codigo_agrupacion"].isin(excl)].copy()
    gan  = ganadores_por_grupo(df, ["departamento"])
    col  = detectar_col(gdf_ext, ("NOMBDEP","NOMB_DEP","DEPARTAMENTO","NOMBRE","NOM_DEP","nombre"))
    return _mapa_ganadores(gdf_ext, col, gan, "departamento", "agrupacion_politica",
                            titulo="Ganador Senado Regional por Circunscripcion")

def fig_mapa_dip_region(escanos_dip, gdf_ext):
    filas = []
    for region, esc in escanos_dip.items():
        if esc:
            gan = max(esc, key=esc.get)
            filas.append({
                "departamento": region, "agrupacion_politica": gan,
                "pct_votos_validos": esc[gan],
            })
    if not filas: return go.Figure()
    df  = pd.DataFrame(filas)
    col = detectar_col(gdf_ext, ("NOMBDEP","NOMB_DEP","DEPARTAMENTO","NOMBRE","NOM_DEP","nombre"))
    return _mapa_ganadores(gdf_ext, col, df, "departamento", "agrupacion_politica",
                            titulo="Partido con Mas Escanos por Circunscripcion (Diputados)")

# ─────────────────────────────────────────────
#  FIGURA: HEMICICLO
# ─────────────────────────────────────────────
def fig_hemiciclo(escanos_dict, titulo="Hemiciclo"):
    if not escanos_dict: return go.Figure()

    partidos = sorted(escanos_dict.items(), key=lambda x: -x[1])
    total    = sum(escanos_dict.values())

    RADIO_INI = 0.80
    RADIO_INC = 0.28
    N_FILAS   = 5
    ESPACIO   = 0.09

    asientos_fila = []
    restantes = total
    for f in range(N_FILAS):
        radio = RADIO_INI + f * RADIO_INC
        cap   = max(1, int(np.pi * radio / ESPACIO))
        n     = min(restantes, cap)
        asientos_fila.append((radio, n))
        restantes -= n
        if restantes <= 0: break

    asientos_p = []
    for nombre, n in partidos:
        asientos_p.extend([nombre] * n)

    px, py, pc, pp = [], [], [], []
    idx = 0
    for radio, n_asientos in asientos_fila:
        angulos = np.linspace(np.pi - 0.04, 0.04, n_asientos)
        for ang in angulos:
            if idx >= len(asientos_p): break
            p = asientos_p[idx]
            px.append(radio * np.cos(ang))
            py.append(radio * np.sin(ang))
            pc.append(color_partido(p))
            pp.append(p)
            idx += 1

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=px, y=py, mode="markers",
        marker=dict(color=pc, size=10, line=dict(color="white", width=0.7)),
        text=pp,
        hovertemplate="<b>%{text}</b><extra></extra>",
        showlegend=False,
    ))

    for nombre, n_esc in partidos[:12]:
        fig.add_trace(go.Scatter(
            x=[None], y=[None], mode="markers",
            marker=dict(color=color_partido(nombre), size=11),
            name=f"{nombre[:28]} ({n_esc})",
            showlegend=True,
        ))

    fig.add_annotation(
        x=0, y=0.12,
        text=f"<b>{total}</b><br><span style='font-size:10px'>escanos</span>",
        showarrow=False, font=dict(size=15, color=COLOR_HEADER),
        xref="x", yref="y",
    )
    fig.update_layout(
        **LB(), title=titulo,
        xaxis=dict(visible=False, range=[-2.0, 2.0]),
        yaxis=dict(visible=False, range=[-0.15, 2.0], scaleanchor="x", scaleratio=1),
        height=470,
        margin=dict(l=10, r=10, t=55, b=10),
        legend=dict(
            orientation="h", yanchor="top", y=-0.02,
            xanchor="center", x=0.5,
            font=dict(size=9), itemsizing="constant",
        ),
    )
    return fig

# ─────────────────────────────────────────────
#  FIGURA: TABLA MARGENES D'HONDT
# ─────────────────────────────────────────────
def fig_tabla_margen(votos_dict, escanos, titulo):
    tabla = dhondt_margen(votos_dict, escanos, n=3)
    if tabla.empty: return go.Figure()

    fills = [["#d4edda" if "Dentro" in v else "#f8d7da" for v in tabla["estado"]]]
    fig = go.Figure(go.Table(
        header=dict(
            values=["Estado","Pos.","Partido","Votos/Divisor","Divisor","Cociente"],
            fill_color=COLOR_HEADER,
            font=dict(color="white", size=11),
            align="left", height=30,
        ),
        cells=dict(
            values=[
                ["✅ " + v if "Dentro" in v else "❌ " + v for v in tabla["estado"]],
                tabla["posicion"],
                tabla["partido"].apply(lambda x: x[:36]+"..." if len(x)>36 else x),
                tabla["votos_cociente"].apply(lambda x: f"{x:,}"),
                tabla["divisor"],
                tabla["cociente"].apply(lambda x: f"{x:,.1f}"),
            ],
            fill_color=fills,
            align="left", font=dict(size=10), height=25,
        ),
    ))
    fig.update_layout(**LB(), title=titulo, height=275,
                      margin=dict(l=5, r=5, t=48, b=5))
    return fig

# ─────────────────────────────────────────────
#  TABLA HTML: ESCANOS POR CIRCUNSCRIPCION
# ─────────────────────────────────────────────
def _cel(p, n):
    bg = color_partido(p) + "33"
    return html.Td(
        str(n) if n else "—",
        style={"textAlign":"center","fontSize":"10px",
               "background": bg if n else "",
               "fontWeight":"700" if n else "400",
               "color": color_partido(p) if n else "#bbb"},
    )

def _enc(p):
    return html.Th(
        p[:18],
        style={"background":color_partido(p),"color":"white","padding":"5px 7px",
               "fontSize":"9px","textAlign":"center","wordWrap":"break-word"},
    )

def tabla_senado_circ(escanos_nac, escanos_reg):
    top_ps = sorted(
        sumar_escanos(escanos_nac, total_de_regiones(escanos_reg)).keys(),
        key=lambda p: -sumar_escanos(escanos_nac, total_de_regiones(escanos_reg)).get(p,0)
    )[:8]

    hdr = html.Tr([
        html.Th("Circunscripcion",  style={"background":COLOR_HEADER,"color":"white","padding":"6px 10px","fontSize":"10px"}),
        html.Th("Escanos",          style={"background":COLOR_HEADER,"color":"white","padding":"6px 10px","fontSize":"10px","textAlign":"center"}),
    ] + [_enc(p) for p in top_ps])

    total_nac = sum(escanos_nac.values())
    fila_nac  = html.Tr([
        html.Td(f"Senado Nacional (30 escanos)", style={"padding":"5px 10px","fontSize":"10px","fontWeight":"700","background":"#EEF2F7"}),
        html.Td(str(total_nac), style={"textAlign":"center","fontWeight":"800","fontSize":"11px","background":"#EEF2F7"}),
    ] + [_cel(p, escanos_nac.get(p,0)) for p in top_ps],
    style={"borderBottom":"2px solid #bbb"})

    filas_reg = [
        html.Tr([
            html.Td(r, style={"padding":"4px 10px","fontSize":"10px"}),
            html.Td(str(sum(escanos_reg[r].values())), style={"textAlign":"center","fontWeight":"700","fontSize":"10px"}),
        ] + [_cel(p, escanos_reg[r].get(p,0)) for p in top_ps],
        style={"borderBottom":"1px solid #eee"})
        for r in sorted(escanos_reg.keys())
    ]

    return html.Div([
        html.Table([html.Thead(hdr), html.Tbody([fila_nac]+filas_reg)],
            style={"width":"100%","borderCollapse":"collapse","background":"white",
                   "boxShadow":"0 1px 3px rgba(0,0,0,.1)","borderRadius":"6px","overflow":"hidden"})
    ], style={"overflowX":"auto"})

def tabla_dip_circ(escanos_dip):
    total_p = total_de_regiones(escanos_dip)
    top_ps  = sorted(total_p.keys(), key=lambda p: -total_p[p])[:8]

    hdr = html.Tr([
        html.Th("Circunscripcion", style={"background":COLOR_HEADER,"color":"white","padding":"6px 10px","fontSize":"10px"}),
        html.Th("Escanos",         style={"background":COLOR_HEADER,"color":"white","padding":"6px 10px","fontSize":"10px","textAlign":"center"}),
    ] + [_enc(p) for p in top_ps])

    filas = [
        html.Tr([
            html.Td(r, style={"padding":"4px 10px","fontSize":"10px"}),
            html.Td(str(sum(escanos_dip[r].values())), style={"textAlign":"center","fontWeight":"700","fontSize":"10px"}),
        ] + [_cel(p, escanos_dip[r].get(p,0)) for p in top_ps],
        style={"borderBottom":"1px solid #eee"})
        for r in sorted(escanos_dip.keys())
    ]

    return html.Div([
        html.Table([html.Thead(hdr), html.Tbody(filas)],
            style={"width":"100%","borderCollapse":"collapse","background":"white",
                   "boxShadow":"0 1px 3px rgba(0,0,0,.1)","borderRadius":"6px","overflow":"hidden"})
    ], style={"overflowX":"auto"})

# ─────────────────────────────────────────────
#  KPIs DINAMICOS
# ─────────────────────────────────────────────
def preparar_kpis(meta_nac):
    def m(eleccion):
        r = meta_nac[meta_nac["eleccion"] == eleccion]
        return r.iloc[0] if len(r) else None

    def kpi(eleccion):
        row = m(eleccion)
        if row is None: return {}
        return {
            "actas"        : f"{row['actas_contabilizadas_pct']:.1f}%",
            "emitidos"     : f"{int(row['votos_emitidos']):,}",
            "validos"      : f"{int(row['votos_validos']):,}",
            "participacion": f"{row['participacion_ciudadana_pct']:.1f}%",
        }

    return {
        "tab-pres": kpi("Presidencial"),
        "tab-sen" : kpi("Senado_Nacional"),
        "tab-dip" : kpi("Diputados"),
    }

def render_kpis(data):
    if not data: return html.Div()
    labels = [
        ("actas",         "Actas contabilizadas"),
        ("emitidos",      "Votos emitidos"),
        ("validos",       "Votos validos"),
        ("participacion", "Participacion"),
    ]
    return html.Div([
        html.Div([
            html.Div(label, style={"fontSize":"9px","color":"#aaa","textTransform":"uppercase","letterSpacing":"0.5px"}),
            html.Div(data.get(key,"—"), style={"fontSize":"14px","fontWeight":"800","color":"white"}),
        ], style={"textAlign":"center","padding":"6px 12px",
                  "background":"rgba(255,255,255,0.08)","borderRadius":"6px","minWidth":"110px"})
        for key, label in labels
    ], style={"display":"flex","gap":"6px","flexWrap":"wrap","alignItems":"center"})

# ─────────────────────────────────────────────
#  LEYENDA DE COLORES
# ─────────────────────────────────────────────
def leyenda_partidos():
    excluir_leyenda = {"OTROS","VOTOS EN BLANCO","VOTOS NULOS"}
    items = [
        html.Span([
            html.Span("●", style={"color":c,"fontSize":"16px","marginRight":"3px"}),
            html.Span(p[:30], style={"fontSize":"9.5px","color":COLOR_TEXT}),
        ], style={"marginRight":"10px","whiteSpace":"nowrap","display":"inline-flex","alignItems":"center"})
        for p, c in COLORES_PARTIDO.items() if p not in excluir_leyenda
    ]
    return html.Div(items,
        style={"display":"flex","flexWrap":"wrap","padding":"8px 12px",
               "background":"#f0f0f0","borderRadius":"6px","margin":"8px 0 12px"})

# ─────────────────────────────────────────────
#  GENERACION HTML STANDALONE
# ─────────────────────────────────────────────
def generar_html(figs_pres, figs_sen, figs_dip):
    def fig_script(fig, div_id):
        fig_json = pio.to_json(fig)
        return (
            f'<div id="{div_id}" style="width:100%;margin-bottom:16px;"></div>\n'
            f'<script>var d={fig_json};'
            f'Plotly.react("{div_id}",d.data,d.layout,{{responsive:true}});</script>\n'
        )

    p_html  = "".join(fig_script(f, f"p{i}") for i,f in enumerate(figs_pres))
    s_html  = "".join(fig_script(f, f"s{i}") for i,f in enumerate(figs_sen))
    d_html  = "".join(fig_script(f, f"d{i}") for i,f in enumerate(figs_dip))

    ley_html = "".join([
        f'<span style="margin-right:10px;white-space:nowrap;">'
        f'<span style="color:{c};font-size:16px;">&#9679;</span> '
        f'<span style="font-size:10px;">{p[:30]}</span></span>'
        for p, c in COLORES_PARTIDO.items()
        if p not in {"OTROS","VOTOS EN BLANCO","VOTOS NULOS"}
    ])

    ts  = pd.Timestamp.now().strftime("%d/%m/%Y %H:%M")
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>Elecciones Peru 2026</title>
<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:Inter,Arial,sans-serif;background:#F8F9FA;color:#2c3e50}}
.hdr{{background:linear-gradient(135deg,#1a1a2e,#16213e);padding:14px 20px;
      position:sticky;top:0;z-index:100;box-shadow:0 2px 10px rgba(0,0,0,.3)}}
.hdr h1{{color:white;font-size:18px;margin-bottom:4px}}
.hdr .sub{{color:#ddd;font-size:11px}}
.hdr a{{color:#7EB3F5;font-size:11px;margin-right:8px;text-decoration:none}}
.tabs{{display:flex;background:#f0f0f0;border-bottom:1px solid #ddd}}
.tb{{padding:11px 22px;cursor:pointer;font-weight:600;font-size:13px;
     border:none;background:#f0f0f0;color:#666;border-top:3px solid transparent}}
.tb.on{{background:white;color:#1a1a2e;border-top-color:#e94560}}
.tc{{display:none;padding:16px 20px}}
.tc.on{{display:block}}
.ley{{display:flex;flex-wrap:wrap;padding:8px 12px;background:#f0f0f0;
      border-radius:6px;margin:0 0 14px}}
.g2{{display:grid;grid-template-columns:1fr 1fr;gap:14px}}
.g3{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px}}
@media(max-width:700px){{.g2,.g3{{grid-template-columns:1fr}}}}
.ftr{{text-align:center;padding:12px;background:#1a1a2e;color:#aaa;font-size:11px;margin-top:20px}}
h3{{color:#1a1a2e;font-size:13px;margin:16px 0 8px;font-weight:700}}
</style>
</head>
<body>
<div class="hdr">
  <h1>&#127477;&#127466; Visualizador de Elecciones Generales Peru 2026</h1>
  <div class="sub">
  Manuel F. Ruiz Huidobro Vera &nbsp;|&nbsp;
  <a href="https://www.linkedin.com/in/manuel-f-ruiz-huidobro-vera-276394244/" target="_blank">LinkedIn</a>
  <a href="https://www.instagram.com/ruizhuidobro.manuel/" target="_blank">Instagram</a>
  <a href="https://www.tiktok.com/@ruizhuidobro.manuel" target="_blank">TikTok</a>
  <a href="mailto:mruiz@analistasperu.com">mruiz@analistasperu.com</a>
</div>

<div class="sub">
  Ignacio Álvarez Calvo-Parra &nbsp;|&nbsp;
  <a href="https://www.linkedin.com/in/ignacio-alvarez-calvo-parra/" target="_blank">LinkedIn</a>
  <a href="https://www.instagram.com/ignacioalvarez806/" target="_blank">Instagram</a>
</div>
</div>
<div class="tabs">
  <button class="tb on" onclick="show('presidenciales',this)">🗳️ Presidenciales</button>
  <button class="tb"    onclick="show('senado',this)">🏛️ Senado</button>
  <button class="tb"    onclick="show('diputados',this)">🧾 Diputados</button>
</div>
<div id="tab-presidenciales" class="tc on">
  <div class="ley">{ley_html}</div>
  {figs_pres[0] and fig_script(figs_pres[0],"pe0") if figs_pres else ""}
  <div class="g2">{fig_script(figs_pres[1],"pe1") if len(figs_pres)>1 else ""}{fig_script(figs_pres[2],"pe2") if len(figs_pres)>2 else ""}</div>
  <h3>Intensidad de Voto por Partido</h3>
  <div class="g3">{"".join(fig_script(figs_pres[i], f"ph{i}") for i in range(3, min(len(figs_pres),11)))}</div>
</div>
<div id="tab-senado" class="tc">
  <div class="ley">{ley_html}</div>
  <div class="g2">{"".join(fig_script(figs_sen[i], f"se{i}") for i in range(min(2,len(figs_sen))))}</div>
  <h3>Mapa Senado Regional</h3>
  {fig_script(figs_sen[2], "se2") if len(figs_sen)>2 else ""}
</div>
<div id="tab-diputados" class="tc">
  <div class="ley">{ley_html}</div>
  <div class="g2">{"".join(fig_script(figs_dip[i], f"de{i}") for i in range(min(2,len(figs_dip))))}</div>
  <h3>Mapa Diputados por Circunscripcion</h3>
  {fig_script(figs_dip[2], "de2") if len(figs_dip)>2 else ""}
</div>
<div class="ftr">Elaborado por Manuel F. Ruiz Huidobro Vera a partir de datos de la ONPE (2026) | Generado: {ts}</div>
<script>
function show(name,btn){{
  document.querySelectorAll('.tc').forEach(e=>e.classList.remove('on'));
  document.querySelectorAll('.tb').forEach(e=>e.classList.remove('on'));
  document.getElementById('tab-'+name).classList.add('on');
  btn.classList.add('on');
}}
</script>
</body></html>"""

# ─────────────────────────────────────────────
#  CREAR APP DASH
# ─────────────────────────────────────────────
def crear_app(datos, gdf_dep, gdf_prov, gdf_ext,
              escanos_sen_nac, escanos_sen_reg, escanos_dip,
              votos_sen_nac, meta_nac, hab_sen, hab_dip):

    pres_nac  = datos["pres_nac"]
    pres_dep  = datos["pres_dep"]
    pres_prov = datos["pres_prov"]
    sen_reg   = datos["sen_reg"]
    dip_reg   = datos["dip_reg"]

    # ── Figuras ──────────────────────────────
    print("  Barras presidenciales...")
    f_barras = fig_barras_pres(pres_nac)

    print("  Mapas presidenciales...")
    f_dep  = fig_mapa_dep(pres_dep, gdf_dep)
    f_prov = fig_mapa_prov(pres_prov, gdf_prov)

    excl = CODIGOS_NO_PARTIDO
    top8 = (pres_dep[~pres_dep["codigo_agrupacion"].isin(excl)]
            .groupby("agrupacion_politica")["votos_validos"].sum()
            .nlargest(8).index.tolist())
    print(f"  {len(top8)} mapas de intensidad...")
    figs_heat = [fig_heat_partido(pres_dep, p, gdf_dep) for p in top8]

    # Senado
    total_sen = sumar_escanos(escanos_sen_nac, total_de_regiones(escanos_sen_reg))
    print("  Hemiciclo Senado...")
    f_hemi_sen   = fig_hemiciclo(total_sen, f"Hemiciclo — Senado ({sum(total_sen.values())} escanos)")
    f_margen_sen = fig_tabla_margen(votos_sen_nac, ESCANOS_SEN_NAC,
                                     "Margen D'Hondt — Senado Nacional (30 escanos)")
    f_mapa_sen   = fig_mapa_senado_reg(sen_reg, gdf_ext)

    # Diputados
    total_dip = total_de_regiones(escanos_dip)
    print("  Hemiciclo Diputados...")
    f_hemi_dip = fig_hemiciclo(total_dip, f"Hemiciclo — Diputados ({sum(total_dip.values())} escanos)")
    f_mapa_dip = fig_mapa_dip_region(escanos_dip, gdf_ext)

    lima_key_list = [k for k in dip_reg["departamento"].unique()
                     if normalizar(k) in ("LIMA","LIMA METROPOLITANA")]
    dip_lima_v = (
        dip_reg[
            (~dip_reg["codigo_agrupacion"].isin(excl)) &
            (dip_reg["departamento"].isin(lima_key_list)) &
            (dip_reg["agrupacion_politica"].isin(hab_dip))
        ].set_index("agrupacion_politica")["votos_validos"].to_dict()
    )
    f_margen_dip = fig_tabla_margen(dip_lima_v, 32,
                                     "Margen D'Hondt — Diputados Lima (32 escanos)")

    # KPIs
    kpis = preparar_kpis(meta_nac)

    # ── Layout ────────────────────────────────
    app = Dash(__name__, suppress_callback_exceptions=True)
    app.title = "Elecciones Peru 2026"

    TS  = {"padding":"10px 20px","border":"none","background":"#f0f0f0","color":"#666","fontSize":"13px","fontWeight":"600"}
    TSA = {"padding":"10px 20px","borderTop":f"3px solid {COLOR_ACCENT}","background":"white","color":COLOR_HEADER,"fontWeight":"700","fontSize":"13px"}

    def banner_barrera(habilitados, descripcion):
        return html.Div([
            html.Span("⚖️ Barrera electoral: ", style={"fontWeight":"700"}),
            html.Span(descripcion, style={"marginRight":"8px"}),
            html.Span("Habilitados: ", style={"color":"#555"}),
            html.Span(", ".join(sorted(habilitados)[:7]) + ("..." if len(habilitados)>7 else ""),
                      style={"fontSize":"10px","color":COLOR_TEXT}),
        ], style={"background":"#EEF2F7","border":"1px solid #C5D8F5",
                  "borderRadius":"6px","padding":"10px 14px","fontSize":"11px","margin":"10px 0"})

    # TABS
    tab_pres = html.Div([
        leyenda_partidos(),
        dcc.Graph(figure=f_barras, config={"displayModeBar":False}),
        html.H3("Mapas de Ganadores", style={"color":COLOR_HEADER,"fontWeight":"700","margin":"16px 0 8px"}),
        html.Div([
            html.Div([dcc.Graph(figure=f_dep,  config={"displayModeBar":False})], style={"flex":"1","minWidth":"290px"}),
            html.Div([dcc.Graph(figure=f_prov, config={"displayModeBar":False})], style={"flex":"1","minWidth":"290px"}),
        ], style={"display":"flex","gap":"14px","flexWrap":"wrap"}),
        html.H3("Intensidad de Voto por Partido", style={"color":COLOR_HEADER,"fontWeight":"700","margin":"20px 0 8px"}),
        html.Div([
            html.Div([dcc.Graph(figure=figs_heat[i], config={"displayModeBar":False})],
                     style={"flex":"1","minWidth":"250px"})
            for i in range(len(figs_heat))
        ], style={"display":"flex","gap":"8px","flexWrap":"wrap"}),
    ], style={"padding":"0 20px"})

    tab_sen = html.Div([
        leyenda_partidos(),
        banner_barrera(hab_sen,
                       f"≥ 5% promedio SenNac+SenReg Y ≥ {MIN_ESCANOS_SENADO} escaños totales"),
        html.Div([
            html.Div([dcc.Graph(figure=f_hemi_sen,   config={"displayModeBar":False})], style={"flex":"1","minWidth":"300px"}),
            html.Div([dcc.Graph(figure=f_margen_sen, config={"displayModeBar":False})], style={"flex":"1","minWidth":"300px"}),
        ], style={"display":"flex","gap":"14px","flexWrap":"wrap","margin":"10px 0"}),
        html.H3("Mapa — Senado Regional", style={"color":COLOR_HEADER,"fontWeight":"700","margin":"14px 0 8px"}),
        dcc.Graph(figure=f_mapa_sen, config={"displayModeBar":False}),
        html.H3("Escanos por Circunscripcion — Senado", style={"color":COLOR_HEADER,"fontWeight":"700","margin":"18px 0 8px"}),
        tabla_senado_circ(escanos_sen_nac, escanos_sen_reg),
    ], style={"padding":"0 20px"})

    tab_dip = html.Div([
        leyenda_partidos(),
        banner_barrera(hab_dip,
                       f"≥ 5% votos validos nacionales Y ≥ {MIN_ESCANOS_DIPUTADOS} escaños totales"),
        html.Div([
            html.Div([dcc.Graph(figure=f_hemi_dip,   config={"displayModeBar":False})], style={"flex":"1","minWidth":"300px"}),
            html.Div([dcc.Graph(figure=f_margen_dip, config={"displayModeBar":False})], style={"flex":"1","minWidth":"300px"}),
        ], style={"display":"flex","gap":"14px","flexWrap":"wrap","margin":"10px 0"}),
        html.H3("Mapa — Escanos por Circunscripcion", style={"color":COLOR_HEADER,"fontWeight":"700","margin":"14px 0 8px"}),
        dcc.Graph(figure=f_mapa_dip, config={"displayModeBar":False}),
        html.H3("Escanos por Circunscripcion y Partido", style={"color":COLOR_HEADER,"fontWeight":"700","margin":"18px 0 8px"}),
        tabla_dip_circ(escanos_dip),
    ], style={"padding":"0 20px"})

    app.layout = html.Div([
        # HEADER
        html.Div([
            html.Div([
                html.H1("🇵🇪 Visualizador de Elecciones Generales Peru 2026",
                        style={"margin":"0","fontSize":"18px","fontWeight":"800","color":"white"}),
                html.Div([
                    html.Span("Manuel F. Ruiz Huidobro Vera",
                              style={"color":"#ddd","fontSize":"12px","fontWeight":"600","marginRight":"14px"}),
                    html.A("LinkedIn",  href="https://www.linkedin.com/in/manuel-f-ruiz-huidobro-vera-276394244/",
                           target="_blank", style={"color":"#7EB3F5","marginRight":"7px","fontSize":"11px"}),
                    html.A("Instagram", href="https://www.instagram.com/ruizhuidobro.manuel/",
                           target="_blank", style={"color":"#7EB3F5","marginRight":"7px","fontSize":"11px"}),
                    html.A("TikTok",    href="https://www.tiktok.com/@ruizhuidobro.manuel",
                           target="_blank", style={"color":"#7EB3F5","marginRight":"7px","fontSize":"11px"}),
                    html.A("mruiz@analistasperu.com", href="mailto:mruiz@analistasperu.com",
                           style={"color":"#7EB3F5","fontSize":"11px"}),
                ], style={"marginTop":"2px"}),
            ], style={"flex":"1"}),
            html.Div(id="header-kpis", children=render_kpis(kpis.get("tab-pres", {}))),
            html.Button("🔄 Actualizar ONPE", id="btn-refresh",
                style={"background":"#2ecc71","color":"white","border":"none",
                       "padding":"8px 14px","borderRadius":"6px","cursor":"pointer",
                       "fontSize":"11px","fontWeight":"700","whiteSpace":"nowrap",
                       "flexShrink":"0","marginRight":"6px"}),
            html.Button("📥 Exportar Dashboard", id="btn-export",
                style={"background":COLOR_ACCENT,"color":"white","border":"none",
                       "padding":"8px 14px","borderRadius":"6px","cursor":"pointer",
                       "fontSize":"11px","fontWeight":"700","whiteSpace":"nowrap",
                       "flexShrink":"0"}),
            dcc.Download(id="download-html"),
            # Div oculto para output del refresh
            html.Div(id="refresh-output", style={"display":"none"}),
        ], style={
            "background": f"linear-gradient(135deg,{COLOR_HEADER} 0%,#16213e 100%)",
            "padding": "12px 20px", "display": "flex",
            "alignItems": "center", "gap": "14px", "flexWrap": "wrap",
            "position": "sticky", "top": "0", "zIndex": "1000",
            "boxShadow": "0 2px 10px rgba(0,0,0,.3)",
        }),

        # TABS
        dcc.Tabs(id="tabs-main", value="tab-pres", children=[
            dcc.Tab(label="🗳️ Presidenciales", value="tab-pres",
                    children=[tab_pres], style=TS, selected_style=TSA),
            dcc.Tab(label="🏛️ Senado",         value="tab-sen",
                    children=[tab_sen],  style=TS, selected_style=TSA),
            dcc.Tab(label="🧾 Diputados",      value="tab-dip",
                    children=[tab_dip],  style=TS, selected_style=TSA),
        ], colors={"border":"#e0e0e0","primary":COLOR_ACCENT,"background":"#f0f0f0"}),

        # FOOTER
        html.Div("Elaborado por Manuel F. Ruiz Huidobro Vera a partir de datos de la ONPE (2026)",
                 style={"textAlign":"center","padding":"12px","background":COLOR_HEADER,
                        "color":"#aaa","fontSize":"11px","marginTop":"20px"}),
    ], style={"fontFamily":"Inter,Arial,sans-serif","background":COLOR_FONDO,"minHeight":"100vh"})

    # ── CALLBACKS ─────────────────────────────
    @app.callback(
        Output("header-kpis","children"),
        Input("tabs-main","value"),
    )
    def update_kpis(tab):
        return render_kpis(kpis.get(tab, kpis.get("tab-pres", {})))

    @app.callback(
        Output("download-html","data"),
        Input("btn-export","n_clicks"),
        prevent_initial_call=True,
    )
    def exportar(n_clicks):
        if not n_clicks: return None
        print("  Generando HTML standalone...")
        figs_pres = [f_barras, f_dep, f_prov] + figs_heat
        figs_sen  = [f_hemi_sen, f_margen_sen, f_mapa_sen]
        figs_dip  = [f_hemi_dip, f_margen_dip, f_mapa_dip]
        html_str  = generar_html(figs_pres, figs_sen, figs_dip)
        return dict(content=html_str, filename="elecciones_peru_2026.html", type="text/html")

    @app.callback(
        Output("refresh-output", "children"),
        Input("btn-refresh", "n_clicks"),
        prevent_initial_call=True,
    )
    def refresh_datos(n_clicks):
        """Descarga datos frescos de ONPE y recarga la página."""
        if not n_clicks: return ""
        print("\n  🔄 Actualizando datos desde ONPE...")
        ok = intentar_scraping()
        if ok:
            print("  ✓ Datos actualizados. Reinicia la app para ver cambios.")
            # En Render/producción, se podría usar os._exit(0) para forzar reinicio
            # Por ahora, notifica al usuario
            return "OK"
        return "ERROR"

    return app

# ─────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────
if __name__ == "__main__":
    print("\n" + "="*62)
    print("  VISUALIZADOR ELECTORAL PERU 2026  v3.0")
    print("  (con doble barrera + scraping integrado)")
    print("="*62)

    # ── Auto-scraping si falta el Excel o es antiguo ──
    if excel_necesita_actualizar():
        print("\n  Datos ausentes o antiguos. Intentando descargar de ONPE...")
        ok = intentar_scraping()
        if not ok and not os.path.exists(EXCEL_PATH):
            print("\n  ERROR: No se pudo descargar y no hay Excel previo.")
            print("  Coloca 'resultados_onpe_2026.xlsx' en la carpeta del proyecto")
            print("  o ejecuta: python scraper_onpe.py")
            sys.exit(1)
        elif not ok:
            print("  [WARN] Scraping falló pero existe Excel previo. Usando datos anteriores.")
    else:
        print(f"  Excel encontrado y reciente: {EXCEL_PATH}")

    validar_archivos()

    print("\n  Cargando datos del Excel...")
    datos    = cargar_datos()
    meta_nac = datos["meta_nac"]

    print("  Cargando shapefiles...")
    gdf_dep, gdf_prov = cargar_shapefiles()

    print("  Separando Lima Metropolitana / Lima Provincias...")
    gdf_lima = crear_lima_dividida(gdf_prov)
    gdf_ext  = gdf_con_lima_dividida(gdf_dep, gdf_lima)
    print(f"  GDF extendido: {len(gdf_ext)} unidades geograficas")

    # ── Doble barrera electoral ──
    print("\n  Calculando doble barrera electoral...")
    total_sn_v = int(meta_nac[meta_nac["eleccion"]=="Senado_Nacional"]["votos_validos"].values[0])
    total_sr_v = int(meta_nac[meta_nac["eleccion"]=="Senado_Regional"]["votos_validos"].values[0])
    total_dip_v= int(meta_nac[meta_nac["eleccion"]=="Diputados"]["votos_validos"].values[0])

    hab_sen, escanos_sen_nac, escanos_sen_reg, votos_sen_nac = \
        aplicar_doble_barrera_senado(datos["sen_nac"], datos["sen_reg"], total_sn_v, total_sr_v)

    hab_dip, escanos_dip = \
        aplicar_doble_barrera_diputados(datos["dip_reg"], total_dip_v)

    total_sen = sumar_escanos(escanos_sen_nac, total_de_regiones(escanos_sen_reg))
    total_dip = total_de_regiones(escanos_dip)
    print(f"\n  Senado total: {sum(total_sen.values())} escanos "
          f"| Diputados total: {sum(total_dip.values())} escanos")

    print("\n  Construyendo dashboard...")
    app = crear_app(
        datos, gdf_dep, gdf_prov, gdf_ext,
        escanos_sen_nac, escanos_sen_reg, escanos_dip,
        votos_sen_nac, meta_nac, hab_sen, hab_dip,
    )

    # ── Exponer server para gunicorn (Render) ──
    server = app.server

    # ── Puerto: usa variable de entorno PORT (Render) o 8050 (local) ──
    port = int(os.environ.get("PORT", 8050))

    print("\n" + "="*62)
    print("  Dashboard listo.")
    print(f"  Abre: http://127.0.0.1:{port}/")
    print("  Ctrl+C para detener")
    print("="*62 + "\n")

    app.run(host="0.0.0.0", port=port, debug=False)
