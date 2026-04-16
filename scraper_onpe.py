#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scraper_onpe.py  (v6 — módulo importable + standalone)
======================================================
Descarga resultados electorales de la ONPE 2026.
Puede usarse como módulo (desde el dashboard) o standalone.

Uso standalone:
    pip install requests pandas openpyxl
    python scraper_onpe.py

Uso como módulo:
    from scraper_onpe import run_scraper
    run_scraper("resultados_onpe_2026.xlsx")
"""

import requests
import pandas as pd
import time
import logging
import sys
from datetime import datetime, timezone, timedelta

# ============================================================================
# CONFIGURACIÓN
# ============================================================================

BASE = "https://resultadoelectoral.onpe.gob.pe/presentacion-backend"
SITE = "https://resultadoelectoral.onpe.gob.pe"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "es-PE,es;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Referer": "https://resultadoelectoral.onpe.gob.pe/main/presidenciales",
    "Origin": "https://resultadoelectoral.onpe.gob.pe",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Ch-Ua": '"Chromium";v="125", "Not.A/Brand";v="24"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
}

TZ_PERU = timezone(timedelta(hours=-5))
SLEEP = 0.8

# ============================================================================
# SESIÓN Y PETICIONES
# ============================================================================

def _crear_sesion():
    return requests.Session()


def inicializar_sesion(session):
    """Visita la página principal para obtener cookies de sesión."""
    logging.info("Inicializando sesión (obteniendo cookies)...")

    headers_html = {
        "User-Agent": HEADERS["User-Agent"],
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "es-PE,es;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
    }

    try:
        r = session.get(SITE, headers=headers_html, timeout=30)
        logging.info("  Página principal: HTTP %d, cookies: %s",
                     r.status_code, list(session.cookies.keys()) or "(ninguna)")
        r2 = session.get(f"{SITE}/main/presidenciales", headers=headers_html, timeout=30)
        logging.info("  Subpágina: HTTP %d", r2.status_code)
    except requests.RequestException as e:
        logging.warning("  Error al inicializar sesión: %s", e)

    session.headers.update(HEADERS)

    logging.info("  Probando conectividad con la API...")
    time.sleep(1)
    try:
        r3 = session.get(f"{BASE}/proceso/2/elecciones", timeout=30)
        logging.info("  Test API: HTTP %d, largo=%d", r3.status_code, len(r3.text))
        if r3.status_code == 200 and r3.text.strip():
            try:
                j = r3.json()
                if j.get("success"):
                    logging.info("  ✓ Conexión exitosa — %d elecciones", len(j.get("data", [])))
                    return True
            except ValueError:
                pass
        logging.warning("  Respuesta inesperada: %s", r3.text[:500])
    except requests.RequestException as e:
        logging.error("  Error de conexión: %s", e)

    return False


def fetch(session, url, params=None, retries=3, silent=False):
    """GET → data del JSON, o None."""
    for i in range(1, retries + 1):
        try:
            time.sleep(SLEEP)
            r = session.get(url, params=params, timeout=30)
            if r.status_code != 200:
                if not silent:
                    logging.warning("HTTP %d en %s — intento %d/%d", r.status_code, url, i, retries)
                if i < retries: time.sleep(2 ** i)
                continue
            if not r.text.strip():
                if not silent:
                    logging.warning("Respuesta vacía en %s — intento %d/%d", url, i, retries)
                if i < retries: time.sleep(2 ** i)
                continue
            try:
                j = r.json()
            except ValueError:
                if not silent:
                    logging.warning("No es JSON válido en %s", url)
                if i < retries: time.sleep(2 ** i)
                continue
            if not j.get("success"):
                if not silent: logging.warning("success=False en %s", url)
                return None
            return j.get("data")
        except requests.RequestException as e:
            if not silent:
                logging.warning("Error red %s: %s — intento %d/%d", url, e, i, retries)
            if i < retries: time.sleep(2 ** i)
    return None


def ts_fecha(ms):
    if not ms: return None
    try:
        return datetime.fromtimestamp(ms / 1000, tz=TZ_PERU).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(ms)


# ============================================================================
# CATÁLOGOS GEOGRÁFICOS
# ============================================================================

def cargar_departamentos(session):
    data = fetch(session, f"{BASE}/ubigeos/departamentos",
                 {"idEleccion": 10, "idAmbitoGeografico": 1})
    if not data:
        logging.error("No se pudieron cargar departamentos.")
        return None
    logging.info("Departamentos: %d", len(data))
    return data


def cargar_provincias(session, ubigeo_depto):
    return fetch(session, f"{BASE}/ubigeos/provincias",
                 {"idEleccion": 10, "idAmbitoGeografico": 1,
                  "idUbigeoDepartamento": ubigeo_depto}, silent=True) or []


def cargar_distritos_electorales(session):
    data = fetch(session, f"{BASE}/distrito-electoral/distritos")
    if not data:
        logging.error("No se pudieron cargar distritos electorales")
        return None
    logging.info("Distritos electorales: %d", len(data))
    return data


# ============================================================================
# ENDPOINTS DE RESULTADOS
# ============================================================================

PATHS = {
    "pres": "eleccion-presidencial/participantes-ubicacion-geografica-nombre",
    "sen_nac": "senadores-distrito-unico/participantes-ubicacion-geografica-nombre",
    "sen_reg": "senadores-distrital-multiple/participantes-ubicacion-geografica",
    "diputados": "eleccion-diputado/participantes-ubicacion-geografica-nombre",
}


def resultados(session, path_key, params, silent=False):
    return fetch(session, f"{BASE}/{PATHS[path_key]}", params, silent=silent) or []


def normalizar_fila(data, eleccion, **extra):
    """Normaliza datos de la API a filas planas."""
    filas = []
    for item in data:
        f = dict(extra)
        f["eleccion"] = eleccion
        f["agrupacion_politica"] = item.get("nombreAgrupacionPolitica", "")
        f["codigo_agrupacion"] = item.get("codigoAgrupacionPolitica", "")
        f["candidato"] = item.get("nombreCandidato", "")
        f["votos_validos"] = item.get("totalVotosValidos")
        f["pct_votos_validos"] = item.get("porcentajeVotosValidos")
        f["pct_votos_emitidos"] = item.get("porcentajeVotosEmitidos")
        filas.append(f)
    return filas


# ============================================================================
# DESCARGA POR ELECCIÓN
# ============================================================================

def dl_pres_nacional(session):
    logging.info("── PRES Nacional")
    data = resultados(session, "pres", {"idEleccion": 10, "tipoFiltro": "eleccion"})
    f = normalizar_fila(data, "Presidencial")
    logging.info("   %d registros", len(f))
    return f


def dl_pres_depto(session, deptos):
    logging.info("── PRES Departamento (%d deptos)", len(deptos))
    out = []
    for d in deptos:
        data = resultados(session, "pres", {
            "idEleccion": 10, "tipoFiltro": "ubigeo_nivel_01",
            "idAmbitoGeografico": 1, "ubigeoNivel1": d["ubigeo"],
        }, silent=True)
        out.extend(normalizar_fila(data, "Presidencial", departamento=d["nombre"]))
        logging.info("   %s → %d", d["nombre"], len(data))
    logging.info("   Total: %d", len(out))
    return out


def dl_pres_provincia(session, deptos):
    logging.info("── PRES Provincia")
    out = []
    for d in deptos:
        provs = cargar_provincias(session, d["ubigeo"])
        if not provs: continue
        logging.info("   %s → %d provincias", d["nombre"], len(provs))
        for p in provs:
            data = resultados(session, "pres", {
                "idEleccion": 10, "tipoFiltro": "ubigeo_nivel_02",
                "idAmbitoGeografico": 1,
                "ubigeoNivel1": d["ubigeo"], "ubigeoNivel2": p["ubigeo"],
            }, silent=True)
            out.extend(normalizar_fila(
                data, "Presidencial",
                departamento=d["nombre"], provincia=p["nombre"],
            ))
    logging.info("   Total: %d", len(out))
    return out


def dl_sen_nac(session):
    logging.info("── SEN_NAC Nacional")
    data = resultados(session, "sen_nac", {"idEleccion": 15, "tipoFiltro": "eleccion"})
    f = normalizar_fila(data, "Senado_Nacional")
    logging.info("   %d registros", len(f))
    return f


def dl_sen_reg(session, distritos):
    logging.info("── SEN_REG por distrito electoral (%d)", len(distritos))
    out = []
    for dist in distritos:
        data = resultados(session, "sen_reg", {
            "idEleccion": 14, "tipoFiltro": "distrito_electoral",
            "idDistritoElectoral": dist["codigo"],
        }, silent=True)
        out.extend(normalizar_fila(data, "Senado_Regional", departamento=dist["nombre"]))
        logging.info("   %s → %d", dist["nombre"], len(data))
    logging.info("   Total: %d", len(out))
    return out


def dl_diputados(session, distritos):
    logging.info("── DIPUTADOS por distrito electoral (%d)", len(distritos))
    out = []
    for dist in distritos:
        data = resultados(session, "diputados", {
            "idEleccion": 13, "tipoFiltro": "distrito_electoral",
            "idDistritoElectoral": dist["codigo"],
        }, silent=True)
        out.extend(normalizar_fila(data, "Diputados", departamento=dist["nombre"]))
        logging.info("   %s → %d", dist["nombre"], len(data))
    logging.info("   Total: %d", len(out))
    return out


def dl_meta_nacional(session):
    logging.info("── Metadata Nacional")
    filas = []
    for nombre, eid in [("Presidencial", 10), ("Senado_Nacional", 15),
                         ("Senado_Regional", 14), ("Diputados", 13)]:
        d = fetch(session, f"{BASE}/resumen-general/totales",
                  {"idEleccion": eid, "tipoFiltro": "eleccion"}, silent=True)
        if d and isinstance(d, dict):
            filas.append({
                "eleccion": nombre,
                "actas_contabilizadas_pct": d.get("actasContabilizadas"),
                "actas_contabilizadas": d.get("contabilizadas"),
                "total_actas": d.get("totalActas"),
                "participacion_ciudadana_pct": d.get("participacionCiudadana"),
                "votos_emitidos": d.get("totalVotosEmitidos"),
                "votos_validos": d.get("totalVotosValidos"),
                "fecha_actualizacion": ts_fecha(d.get("fechaActualizacion")),
            })
            logging.info("   %s OK", nombre)
    return filas


def dl_meta_regiones(session, deptos, distritos):
    logging.info("── Metadata Regiones")
    filas = []
    for dep in deptos:
        d = fetch(session, f"{BASE}/resumen-general/totales", {
            "idEleccion": 10, "tipoFiltro": "ubigeo_nivel_01",
            "idAmbitoGeografico": 1, "ubigeoNivel1": dep["ubigeo"],
        }, silent=True)
        if d and isinstance(d, dict):
            filas.append({
                "eleccion": "Presidencial", "departamento": dep["nombre"],
                "actas_contabilizadas_pct": d.get("actasContabilizadas"),
                "actas_contabilizadas": d.get("contabilizadas"),
                "total_actas": d.get("totalActas"),
                "participacion_ciudadana_pct": d.get("participacionCiudadana"),
                "votos_emitidos": d.get("totalVotosEmitidos"),
                "votos_validos": d.get("totalVotosValidos"),
                "fecha_actualizacion": ts_fecha(d.get("fechaActualizacion")),
            })
    for nombre_e, eid in [("Senado_Regional", 14), ("Diputados", 13)]:
        for dist in distritos:
            d = fetch(session, f"{BASE}/resumen-general/totales", {
                "idEleccion": eid, "tipoFiltro": "distrito_electoral",
                "idDistritoElectoral": dist["codigo"],
            }, silent=True)
            if d and isinstance(d, dict):
                filas.append({
                    "eleccion": nombre_e, "departamento": dist["nombre"],
                    "actas_contabilizadas_pct": d.get("actasContabilizadas"),
                    "actas_contabilizadas": d.get("contabilizadas"),
                    "total_actas": d.get("totalActas"),
                    "participacion_ciudadana_pct": d.get("participacionCiudadana"),
                    "votos_emitidos": d.get("totalVotosEmitidos"),
                    "votos_validos": d.get("totalVotosValidos"),
                    "fecha_actualizacion": ts_fecha(d.get("fechaActualizacion")),
                })
    logging.info("   %d registros", len(filas))
    return filas


# ============================================================================
# EXCEL
# ============================================================================

def make_df(filas, cols):
    if not filas:
        return pd.DataFrame(columns=cols)
    frame = pd.DataFrame(filas)
    for c in cols:
        if c not in frame.columns:
            frame[c] = None
    return frame[cols]


def guardar(hojas, output_path):
    logging.info("=" * 60)
    logging.info("EXPORTANDO → %s", output_path)
    logging.info("=" * 60)
    with pd.ExcelWriter(output_path, engine="openpyxl") as w:
        for nombre, frame in hojas.items():
            frame.to_excel(w, sheet_name=nombre[:31], index=False)
            logging.info("  %-25s %5d filas", nombre, len(frame))
    logging.info("Guardado: %s", output_path)


# ============================================================================
# FUNCIÓN PRINCIPAL (importable)
# ============================================================================

def run_scraper(output_path="resultados_onpe_2026.xlsx"):
    """
    Ejecuta el scraper completo y guarda en output_path.
    Retorna True si tuvo éxito, False en caso contrario.
    Puede llamarse desde el dashboard o como standalone.
    """
    logging.basicConfig(level=logging.INFO, format="%(asctime)s — %(message)s",
                        datefmt="%H:%M:%S")
    t0 = datetime.now(TZ_PERU)
    logging.info("Inicio scraper: %s", t0.strftime("%Y-%m-%d %H:%M:%S PET"))

    session = _crear_sesion()
    ok = inicializar_sesion(session)
    if not ok:
        logging.error("NO SE PUDO CONECTAR A LA API DE ONPE")
        logging.error("Posibles causas: API bloqueando, problemas de red, cookies.")
        return False

    # Catálogos
    deptos = cargar_departamentos(session)
    distritos = cargar_distritos_electorales(session)
    if not deptos or not distritos:
        logging.error("No se pudieron cargar catálogos geográficos.")
        return False

    # Columnas
    CN = ["eleccion", "agrupacion_politica", "codigo_agrupacion",
          "candidato", "votos_validos", "pct_votos_validos", "pct_votos_emitidos"]
    CD = ["departamento"] + CN
    CP = ["departamento", "provincia"] + CN
    CM = ["eleccion", "actas_contabilizadas_pct", "actas_contabilizadas",
          "total_actas", "participacion_ciudadana_pct",
          "votos_emitidos", "votos_validos", "fecha_actualizacion"]
    CR = ["eleccion", "departamento"] + CM[1:]

    # Descarga
    logging.info("=" * 60)
    logging.info("DESCARGANDO RESULTADOS")
    logging.info("=" * 60)

    h = {}
    h["PRES_Nacional"]     = make_df(dl_pres_nacional(session), CN)
    h["PRES_Departamento"] = make_df(dl_pres_depto(session, deptos), CD)
    h["PRES_Provincia"]    = make_df(dl_pres_provincia(session, deptos), CP)
    h["SEN_NAC_Nacional"]  = make_df(dl_sen_nac(session), CN)
    h["SEN_REG_Region"]    = make_df(dl_sen_reg(session, distritos), CD)
    h["DIPUTADOS_Region"]  = make_df(dl_diputados(session, distritos), CD)
    h["METADATA_Nacional"] = make_df(dl_meta_nacional(session), CM)
    h["METADATA_Regiones"] = make_df(dl_meta_regiones(session, deptos, distritos), CR)

    guardar(h, output_path)

    t1 = datetime.now(TZ_PERU)
    seg = (t1 - t0).total_seconds()
    logging.info("Scraper completado en %.0f seg (%.1f min)", seg, seg / 60)
    return True


# ============================================================================
# STANDALONE
# ============================================================================

if __name__ == "__main__":
    success = run_scraper()
    if not success:
        sys.exit(1)
