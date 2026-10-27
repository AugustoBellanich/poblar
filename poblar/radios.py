"""Etapa 1: base de radios.

Une la tabla censal con la cartografía de radios, limpia geometrías, pasa al CRS
de trabajo, deduplica y asigna a cada radio una región por área mayoritaria.
Reemplaza al C1 (unión tabla↔mapa) y a las secciones 1.4 y 2.1–2.5 del C2.

Salida principal: ``1_radios/radios.parquet`` con una fila por radio, la
columna ``raster_id`` (orden de rasterización) y la región asignada.
"""

from __future__ import annotations

from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd

from poblar.config import obtener
from poblar.insumos import ruta_vector
from poblar.trazabilidad import Control, Ejecucion, log

ETAPA = "1_radios"
PREFIJOS_VARIABLES = ("pobla_", "agua_red_", "nbi_")


# ----------------------------------------------------------------- lectura
def leer_tabla(ins: dict[str, Any], campo_id: str = "id_radio") -> pd.DataFrame:
    """Lee la tabla censal con el código de radio como texto de 9 dígitos."""
    ruta = ins["ruta"]
    if str(ruta).lower().endswith(".csv"):
        df = pd.read_csv(ruta, dtype={campo_id: str}, encoding=ins.get("encoding", "utf-8"))
    else:
        df = pd.read_excel(ruta, dtype={campo_id: str}, sheet_name=ins.get("hoja", 0))
    df = df.loc[:, ~df.columns.astype(str).str.startswith("Unnamed")]
    df[campo_id] = df[campo_id].astype(str).str.strip().str.zfill(9)
    for c in df.columns:
        if str(c).startswith(PREFIJOS_VARIABLES):
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def leer_mapa(ins: dict[str, Any], campo_codigo: str) -> gpd.GeoDataFrame:
    """Lee la cartografía de radios (shapefile, zip, gpkg) y normaliza el código."""
    gdf = gpd.read_file(ruta_vector(ins), layer=ins.get("capa"))
    gdf[campo_codigo] = gdf[campo_codigo].astype(str).str.strip().str.zfill(9)
    return gdf


# ----------------------------------------------------------------- región
def asignar_region(
    radios: gpd.GeoDataFrame,
    regiones: gpd.GeoDataFrame,
    campo: str,
    umbral_m: float,
    etiqueta_fuera: str,
) -> tuple[gpd.GeoDataFrame, pd.DataFrame]:
    """Región por área mayoritaria; radios sin intersección: región más cercana si está a ≤ umbral.

    Es el método del C2 (celda 1.4): intersección con las regiones disueltas, se
    queda la de mayor área; los radios sin intersección van a la región más
    cercana si está a menos de ``umbral_m`` metros, y si no, a ``etiqueta_fuera``.

    Returns:
        Los radios con la columna ``campo`` y una tabla de radios sin intersección con su distancia.
    """
    geo_r = radios[["id_radio", "geometry"]].copy()
    geo_g = regiones[[campo, "geometry"]].copy()
    inter = gpd.overlay(geo_r, geo_g, how="intersection")
    inter["area_intersectada"] = inter.geometry.area
    inter["id_radio"] = inter["id_radio"].astype(str).str.strip()
    mayor = (
        inter.sort_values(["id_radio", "area_intersectada"], ascending=[True, False])
        .drop_duplicates(subset="id_radio", keep="first")
        .set_index("id_radio")[campo]
    )
    radios = radios.copy()
    radios[campo] = radios["id_radio"].map(mayor)

    sin_interseccion = radios[radios[campo].isna()].drop(columns=[campo])
    tabla_sin_interseccion = pd.DataFrame(columns=["id_radio", "dist_m", campo, "pobla_total"])
    if not sin_interseccion.empty:
        cerca = gpd.sjoin_nearest(sin_interseccion, geo_g, how="left", distance_col="dist_m")
        cerca = cerca[~cerca.index.duplicated(keep="first")]
        dentro = cerca["dist_m"] <= umbral_m
        radios.loc[cerca.index[dentro], campo] = cerca.loc[dentro, campo]
        radios.loc[cerca.index[~dentro], campo] = etiqueta_fuera
        tabla_sin_interseccion = pd.DataFrame({
            "id_radio": cerca["id_radio"],
            "dist_m": cerca["dist_m"].round(1),
            campo: radios.loc[cerca.index, campo],
            "pobla_total": cerca.get("pobla_total"),
        })
    return radios, tabla_sin_interseccion


# ----------------------------------------------------------------- etapa
def construir(ejecucion: Ejecucion) -> gpd.GeoDataFrame:
    """Corre la etapa 1 y devuelve los radios listos para la grilla."""
    cfg = ejecucion.cfg
    d = ejecucion.dir_etapa(ETAPA)
    campo_cod = obtener(cfg, "radios.campo_codigo_mapa")
    union = obtener(cfg, "radios.union")
    id_desde = obtener(cfg, "radios.id_desde")
    campo_reg = obtener(cfg, "region.campo")
    crs = int(obtener(cfg, "grilla_trabajo.crs"))

    # 1. Tabla censal
    tabla = leer_tabla(cfg["insumos"]["tabla_censo"])
    ejecucion.balance(ETAPA, "tabla censal", filas=len(tabla), ids_unicos=tabla["id_radio"].nunique(),
                   poblacion=int(tabla["pobla_total"].sum()))
    ejecucion.controlar(Control(ETAPA, "tabla sin ids repetidos", tabla["id_radio"].is_unique,
                               f"{len(tabla) - tabla['id_radio'].nunique()} repetidos"))

    # 2. Cartografía
    mapa = leer_mapa(cfg["insumos"]["radios"], campo_cod)
    ejecucion.balance(ETAPA, "cartografía", filas=len(mapa), crs=str(mapa.crs))

    ids_tabla, ids_mapa = set(tabla["id_radio"]), set(mapa[campo_cod])
    sin_carto = tabla[tabla["id_radio"].isin(ids_tabla - ids_mapa)]
    sin_carto[["id_radio", "pobla_total"]].to_csv(d / "radios_sin_cartografia.csv", index=False,
                                                  encoding="utf-8")
    ejecucion.balance(ETAPA, "cobertura tabla↔mapa", coinciden=len(ids_tabla & ids_mapa),
                   solo_tabla=len(ids_tabla - ids_mapa), solo_mapa=len(ids_mapa - ids_tabla),
                   poblacion_sin_cartografia=int(sin_carto["pobla_total"].sum()))

    # 3. Unión
    radios = mapa.merge(tabla, left_on=campo_cod, right_on="id_radio", how=union)
    if id_desde == "mapa":
        radios["id_radio"] = radios[campo_cod]
    radios = gpd.GeoDataFrame(radios, geometry="geometry", crs=mapa.crs)
    variables = [c for c in radios.columns if str(c).startswith(PREFIJOS_VARIABLES)]
    nulos = int(radios["pobla_total"].isna().sum())
    radios[variables] = radios[variables].fillna(0)
    ejecucion.balance(ETAPA, f"unión ({union}, id desde {id_desde})", filas=len(radios),
                   radios_sin_dato_censal=nulos)

    # 4. Deduplicación por id (como el C2: los ids nulos quedan como 'nan' y colapsan en uno)
    radios["id_radio"] = radios["id_radio"].astype(str).str.strip()
    rep = radios.duplicated(subset="id_radio", keep="first")
    radios[rep][["id_radio", "pobla_total"]].to_csv(d / "radios_descartados_duplicados.csv",
                                                    index=False, encoding="utf-8")
    pob_rep = float(radios.loc[rep, "pobla_total"].sum())
    radios = radios[~rep].reset_index(drop=True)
    ejecucion.balance(ETAPA, "deduplicación", quitados=int(rep.sum()), poblacion_quitada=pob_rep,
                   quedan=len(radios))

    # 5. Geometrías: quitar vacías, reproyectar y reparar (orden del C2 2.3)
    vacias = radios.geometry.is_empty | radios.geometry.isna()
    radios = radios[~vacias].to_crs(epsg=crs)
    radios["geometry"] = radios.geometry.make_valid()
    ejecucion.balance(ETAPA, "geometrías", vacias_quitadas=int(vacias.sum()), crs=f"EPSG:{crs}")

    # 6. Regiones (disueltas) y asignación
    regiones = gpd.read_file(ruta_vector(cfg["insumos"]["regiones"]),
                             layer=cfg["insumos"]["regiones"].get("capa"))
    regiones = regiones[~(regiones.geometry.is_empty | regiones.geometry.isna())].to_crs(epsg=crs)
    regiones["geometry"] = regiones.geometry.make_valid()
    regiones = regiones.dissolve(by=campo_reg).reset_index()
    radios, sin_interseccion = asignar_region(
        radios, regiones, campo_reg,
        umbral_m=float(obtener(cfg, "region.umbral_vecino_km")) * 1000,
        etiqueta_fuera=obtener(cfg, "region.etiqueta_fuera"),
    )
    sin_interseccion.to_csv(d / "radios_sin_interseccion.csv", index=False, encoding="utf-8")
    fuera = radios[campo_reg] == obtener(cfg, "region.etiqueta_fuera")
    radios[fuera][["id_radio", campo_reg, "pobla_total"]].to_csv(d / "radios_fuera_region.csv",
                                                                index=False, encoding="utf-8")
    ejecucion.balance(ETAPA, "región", sin_interseccion=len(sin_interseccion), fuera_de_region=int(fuera.sum()),
                   poblacion_fuera=float(radios.loc[fuera, "pobla_total"].sum()))
    if obtener(cfg, "region.excluir_fuera"):
        radios = radios[~fuera]
        ejecucion.balance(ETAPA, "exclusión fuera de región", quitados=int(fuera.sum()))

    # 7. Orden de rasterización: grandes primero, chicos al final (C2 2.5)
    radios["area_m2"] = radios.geometry.area
    if obtener(cfg, "radios.orden", "area_desc") == "area_desc_estable":
        radios = radios.sort_values(["area_m2", "id_radio"], ascending=[False, True], kind="mergesort")
    else:
        radios = radios.sort_values("area_m2", ascending=False)
    radios = radios.reset_index(drop=True)
    radios["raster_id"] = np.arange(1, len(radios) + 1, dtype=np.uint32)

    _validar(ejecucion, radios, campo_reg)

    # 8. Salidas
    radios.to_parquet(d / "radios.parquet", index=False)
    resumen = (radios.groupby(campo_reg, dropna=False)
               .agg(radios=("id_radio", "size"), pobla_total=("pobla_total", "sum"))
               .reset_index())
    resumen.to_csv(d / "resumen_regiones.csv", index=False, encoding="utf-8")
    if obtener(cfg, "radios.exportar_gpkg", False):
        radios.to_file(d / "radios.gpkg", driver="GPKG")
    ejecucion.balance(ETAPA, "salida", radios=len(radios), poblacion=float(radios["pobla_total"].sum()))
    log.info("[%s] listo: %d radios", ETAPA, len(radios))
    return radios


def _validar(ejecucion: Ejecucion, radios: gpd.GeoDataFrame, campo_reg: str) -> None:
    cfg = ejecucion.cfg
    tol = float(obtener(cfg, "controles.tolerancia_personas", 0.0))
    consist_bloq = bool(obtener(cfg, "controles.consistencia_bloqueante", True))
    pob = float(radios["pobla_total"].sum())

    ref = obtener(cfg, "referencia.poblacion_integrada", None)
    if ref is not None:
        ejecucion.controlar(Control(ETAPA, "población integrada = referencia", abs(pob - ref) <= tol,
                                   f"{pob:,.0f} vs {ref:,.0f}", pob, ref))
    ejecucion.controlar(Control(ETAPA, "sin ids repetidos", radios["id_radio"].is_unique,
                               f"{radios['id_radio'].duplicated().sum()} repetidos"))
    sin_reg = int(radios[campo_reg].isna().sum())
    ejecucion.controlar(Control(ETAPA, "todos los radios con región", sin_reg == 0, f"{sin_reg} sin región"))

    cierres = {
        "mujeres + varones = total": ("pobla_mujer", "pobla_varon", "pobla_total"),
        "urbana + rural = total": ("pobla_total_urbana", "pobla_total_rural", "pobla_total"),
    }
    for nombre, (a, b, t) in cierres.items():
        if {a, b, t} <= set(radios.columns):
            dif = (radios[a] + radios[b] - radios[t]).abs()
            n = int((dif > tol).sum())
            ejecucion.controlar(Control(ETAPA, nombre, n == 0,
                                       f"{n} radios no cierran (máx. {dif.max():.0f} personas)",
                                       n, 0, bloqueante=consist_bloq))
    for var in ("agua_red_total", "nbi_total"):
        if var in radios.columns:
            n = int((radios[var] > radios["pobla_total"] + tol).sum())
            ejecucion.controlar(Control(ETAPA, f"{var} ≤ pobla_total", n == 0, f"{n} radios lo superan",
                                       n, 0, bloqueante=consist_bloq))

    # Resultados esperados (no bloqueante): verifican la reproducción de una ejecución publicada.
    acept = obtener(cfg, "resultados_esperados.radios", None) or {}
    if "total" in acept:
        ejecucion.controlar(Control(ETAPA, "resultado esperado: cantidad de radios", len(radios) == acept["total"],
                                   f"{len(radios)} vs {acept['total']}", len(radios), acept["total"],
                                   bloqueante=False))
    for region, esperado in (acept.get("por_region") or {}).items():
        n = int((radios[campo_reg] == region).sum())
        ejecucion.controlar(Control(ETAPA, f"resultado esperado: radios en {region}", n == esperado,
                                   f"{n} vs {esperado}", n, esperado, bloqueante=False))
