"""Etapa 3: mapeo dasimétrico.

Distribuye la población de cada radio entre sus píxeles habitables, ponderando
por la cobertura (urbano / no urbano) con ponderadores empíricos por región y
ámbito, y genera en una sola pasada los rasters de las variables derivadas
(sexo, ámbito, NBI, agua de red) como población del píxel × tasa del radio.

Método (equivalente a las secciones 4 a 7 del cuaderno C2 del PRAIS 2026):

1. Raster de identificadores de radio (``gdal_rasterize -at``; el último radio
   que toca un píxel se lo queda, por eso los radios chicos van al final).
2. Composición de cada radio: píxeles urbanos, no urbanos y totales.
3. Ponderadores: mediana de la densidad por píxel habitable en cada región ×
   ámbito; el peso del píxel no urbano es la razón respecto del ámbito urbano.
4. Factor dasimétrico = población / suma de pesos del radio. Contingencia de
   nivel 2 (radio sin píxeles habitables: reparto uniforme en sus píxeles) y de
   nivel 3 (radio sin píxeles propios: reparto uniforme sobre su polígono,
   sumado a lo que haya).
5. Población del píxel = factor × peso; variables = población × tasa del radio.
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import rasterio.features
from rasterio.windows import Window, from_bounds

from poblar.config import obtener
from poblar.gdal import ejecutar_gdal, opciones_creacion
from poblar.grilla import ventanas_por_filas
from poblar.trazabilidad import Control, Ejecucion, log

ETAPA = "3_dasimetria"
NODATA_POB = -9999.0


# ----------------------------------------------------------------- 3.1 ids
def rasterizar_ids(radios: gpd.GeoDataFrame, cobertura: Path, salida: Path, tmp: Path) -> None:
    """Raster UInt32 de ``raster_id`` sobre la grilla de la cobertura (todos los píxeles tocados)."""
    capa = radios[["raster_id", "geometry"]].sort_values("raster_id")
    capa.to_file(tmp, driver="GPKG")
    with rasterio.open(cobertura) as src:
        b, w, h, crs = src.bounds, src.width, src.height, src.crs.to_string()
    try:
        ejecutar_gdal(["gdal_rasterize", "-a", "raster_id", "-ot", "UInt32", "-a_nodata", "0",
                       "-te", str(b.left), str(b.bottom), str(b.right), str(b.top),
                       "-ts", str(w), str(h), "-a_srs", crs, "-at", *opciones_creacion(),
                       "--config", "GDAL_NUM_THREADS", "ALL_CPUS", str(tmp), str(salida)])
    finally:
        tmp.unlink(missing_ok=True)


# ----------------------------------------------------------------- 3.2 composición
def composicion(ids_tif: Path, cobertura: Path, n: int, filas: int) -> tuple[np.ndarray, ...]:
    """Píxeles totales, urbanos y no urbanos por ``raster_id`` (índice = raster_id)."""
    px_tot = np.zeros(n + 1, dtype=np.int64)
    px_u = np.zeros(n + 1, dtype=np.int64)
    px_nu = np.zeros(n + 1, dtype=np.int64)
    with rasterio.open(ids_tif) as si, rasterio.open(cobertura) as sc:
        for w in ventanas_por_filas(si.height, si.width, filas, avance="composición"):
            ids = si.read(1, window=w).ravel()
            cls = sc.read(1, window=w).ravel()
            m = ids > 0
            if not m.any():
                continue
            iv, cv = ids[m], cls[m]
            px_tot += np.bincount(iv, minlength=n + 1)
            px_u += np.bincount(iv[cv == 1], minlength=n + 1)
            px_nu += np.bincount(iv[cv == 2], minlength=n + 1)
    return px_tot, px_u, px_nu


# ----------------------------------------------------------------- 3.3 ponderadores
def calcular_ponderadores(df: pd.DataFrame, campo_region: str, campo_ambito: str,
                          ambitos: list[str], ref: str, peso_urbano: str) -> pd.DataFrame:
    """Matriz de ponderadores región × ámbito (columnas ``<ámbito>_pxUrbano`` / ``_pxNoUrbano``).

    ``peso_urbano``: ``complemento`` (1 − r, método PRAIS 2026) o ``uno`` (1).
    """
    validos = df[(df["pobla_total"] > 0) & (df["densidad_px"] > 0)]
    med = (validos.groupby([campo_region, campo_ambito])["densidad_px"].median()
           .unstack().fillna(0))
    med.columns = [str(c).capitalize() for c in med.columns]
    matriz = pd.DataFrame(index=med.index)
    base = med[ref].replace(0, 1) if ref in med.columns else 1
    for amb in ambitos:
        if amb not in med.columns:
            continue
        matriz[f"{amb}_pxNoUrbano"] = med[amb] / base
        if amb == ref or peso_urbano == "uno":
            matriz[f"{amb}_pxUrbano"] = 1
        else:
            matriz[f"{amb}_pxUrbano"] = 1 - matriz[f"{amb}_pxNoUrbano"]
    return matriz.fillna(0)


# ----------------------------------------------------------------- etapa
def construir(ejecucion: Ejecucion, radios: gpd.GeoDataFrame | None = None) -> gpd.GeoDataFrame:
    """Corre la etapa 3 y devuelve los radios con su factor dasimétrico."""
    cfg = ejecucion.cfg
    d = ejecucion.dir_etapa(ETAPA)
    anio = cfg["anio_censo"]
    filas = int(obtener(cfg, "rendimiento.filas_por_bloque", 512))
    campo_reg = obtener(cfg, "region.campo")
    campo_amb = obtener(cfg, "dasimetria.campo_ambito")
    ambitos = list(obtener(cfg, "dasimetria.ambitos"))
    cobertura = ejecucion.carpeta / "2_grilla" / "cobertura.tif"
    if radios is None:
        radios = gpd.read_parquet(ejecucion.carpeta / "1_radios" / "radios.parquet")
    radios = radios.sort_values("raster_id").reset_index(drop=True)
    n = int(radios["raster_id"].max())

    # 1. Raster de ids
    ids_tif = d / "raster_ids_radios.tif"
    rasterizar_ids(radios, cobertura, ids_tif, d / "_tmp_radios.gpkg")

    # 2. Composición
    px_tot, px_u, px_nu = composicion(ids_tif, cobertura, n, filas)
    rid = radios["raster_id"].to_numpy()
    radios["px_urbano"] = px_u[rid]
    radios["px_no_urbano"] = px_nu[rid]
    radios["px_total"] = px_tot[rid]
    radios["px_habitable"] = radios["px_urbano"] + radios["px_no_urbano"]
    sin_hab = radios["px_habitable"] == 0
    # Como el C2: para la densidad, un radio sin píxeles habitables cuenta como 1 píxel no urbano.
    radios.loc[sin_hab, ["px_no_urbano", "px_habitable"]] = 1
    radios["densidad_px"] = radios["pobla_total"] / radios["px_habitable"]
    ejecucion.balance(ETAPA, "composición", radios_sin_pixeles_habitables=int(sin_hab.sum()),
                      radios_sin_pixeles=int((radios["px_total"] == 0).sum()))

    # 3. Ponderadores
    matriz = calcular_ponderadores(radios, campo_reg, campo_amb, ambitos,
                                   obtener(cfg, "dasimetria.ponderadores.normalizar_por"),
                                   obtener(cfg, "dasimetria.ponderadores.peso_urbano"))
    matriz.to_csv(d / "ponderadores.csv", encoding="utf-8")
    radios["peso_u"] = 0.0
    radios["peso_nu"] = 0.0
    for region in matriz.index:
        for amb in ambitos:
            cu, cnu = f"{amb}_pxUrbano", f"{amb}_pxNoUrbano"
            if cu not in matriz.columns:
                continue
            m = (radios[campo_reg] == region) & (radios[campo_amb] == amb)
            radios.loc[m, "peso_u"] = matriz.loc[region, cu]
            radios.loc[m, "peso_nu"] = matriz.loc[region, cnu]

    # 4. Suma de pesos por radio. El peso de cada píxel es el del radio dueño del
    #    píxel según su clase; equivale a rasterizar peso_u y peso_nu con el mismo
    #    orden y ALL_TOUCHED (C2 4.4), sin rasterizar dos veces.
    lut_u = np.zeros(n + 1, dtype=np.float32)
    lut_nu = np.zeros(n + 1, dtype=np.float32)
    lut_u[rid] = radios["peso_u"].to_numpy(np.float32)
    lut_nu[rid] = radios["peso_nu"].to_numpy(np.float32)
    pesos_tif = d / "pesos_dasimetricos.tif"
    suma = np.zeros(n + 1, dtype=np.float64)
    conteo = np.zeros(n + 1, dtype=np.int64)
    with rasterio.open(ids_tif) as si, rasterio.open(cobertura) as sc:
        perfil = si.profile.copy()
        perfil.update(dtype="float32", nodata=0, compress="lzw", BIGTIFF="IF_SAFER")
        with rasterio.open(pesos_tif, "w", **perfil) as dst:
            for w in ventanas_por_filas(si.height, si.width, filas, avance="suma de pesos"):
                ids = si.read(1, window=w)
                cls = sc.read(1, window=w)
                p = np.zeros(ids.shape, dtype=np.float32)
                p[cls == 1] = lut_u[ids[cls == 1]]
                p[cls == 2] = lut_nu[ids[cls == 2]]
                p[ids == 0] = 0
                dst.write(p, 1, window=w)
                iv = ids.ravel()
                m = iv > 0
                conteo += np.bincount(iv[m], minlength=n + 1)
                pv = p.ravel()
                mp = m & (pv > 0)
                suma += np.bincount(iv[mp], weights=pv[mp].astype(np.float64), minlength=n + 1)
    radios["suma_pesos"] = suma[rid]
    radios["px_totales_reales"] = conteo[rid]

    # 5. Factor y contingencias
    radios["factor_dist"] = 0.0
    radios["contingencia"] = False
    radios["tipo_asignacion"] = "normal"
    m = radios["suma_pesos"] > 0
    radios.loc[m, "factor_dist"] = radios.loc[m, "pobla_total"] / radios.loc[m, "suma_pesos"]
    m2 = (radios["pobla_total"] > 0) & (radios["suma_pesos"] == 0) & (radios["px_totales_reales"] > 0)
    radios.loc[m2, ["contingencia", "tipo_asignacion"]] = [True, "contingencia"]
    radios.loc[m2, "factor_dist"] = radios.loc[m2, "pobla_total"] / radios.loc[m2, "px_totales_reales"]
    m3 = (radios["pobla_total"] > 0) & (radios["px_totales_reales"] == 0)
    radios.loc[m3, ["contingencia", "tipo_asignacion"]] = [True, "contingencia_extrema"]
    radios.loc[radios["tipo_asignacion"] != "normal",
               ["id_radio", campo_reg, "pobla_total", "tipo_asignacion"]].to_csv(
        d / "contingencias.csv", index=False, encoding="utf-8")
    ejecucion.balance(ETAPA, "contingencias", nivel_2=int(m2.sum()),
                      poblacion_nivel_2=float(radios.loc[m2, "pobla_total"].sum()),
                      nivel_3=int(m3.sum()), poblacion_nivel_3=float(radios.loc[m3, "pobla_total"].sum()))

    # 6. Población y variables derivadas, en una sola pasada
    variables = list(obtener(cfg, "dasimetria.variables"))
    denom = radios["pobla_total"].replace(0, np.nan)
    tasas = {}
    for v in variables:
        num = v["numerador"]
        if num not in radios.columns:
            raise ValueError(f"La variable '{num}' no está en la tabla censal.")
        t = (radios[num].fillna(0) / denom).fillna(0)
        lut = np.zeros(n + 1, dtype=np.float32)
        lut[rid] = t.to_numpy(np.float32)
        tasas[v["producto"]] = lut
        n_inc = int((t > 1.0001).sum())
        if n_inc:
            log.warning("[%s] %d radios con tasa > 1 en '%s'", ETAPA, n_inc, num)

    lut_f = np.zeros(n + 1, dtype=np.float32)
    lut_f[rid] = radios["factor_dist"].to_numpy(np.float32)
    lut_c = np.zeros(n + 1, dtype=bool)
    lut_c[rid] = radios["contingencia"].to_numpy(bool)
    nombre_pob = obtener(cfg, "dasimetria.producto_poblacion", "poblacion_dasimetrica")
    rutas = {"__pob__": d / f"{nombre_pob}_{anio}.tif"}
    rutas.update({p: d / f"{p}_dasimetrico_{anio}.tif" for p in tasas})
    suma_por_radio = np.zeros(n + 1, dtype=np.float64)
    totales = dict.fromkeys(rutas, 0.0)  # suma de cada raster, para los controles sin releerlos

    with rasterio.open(ids_tif) as si, rasterio.open(pesos_tif) as sp:
        perfil = sp.profile.copy()
        perfil.update(dtype="float32", nodata=NODATA_POB)
        salidas = {k: rasterio.open(r, "w", **perfil) for k, r in rutas.items()}
        try:
            for w in ventanas_por_filas(si.height, si.width, filas, avance="población y variables"):
                ids = si.read(1, window=w)
                pesos = sp.read(1, window=w)
                pesos_ef = np.where(lut_c[ids], np.float32(1.0), pesos).astype(np.float32)
                pob = (lut_f[ids] * pesos_ef).astype(np.float32)
                fuera = ids == 0
                m = ~fuera
                suma_por_radio += np.bincount(ids[m].ravel(), weights=pob[m].ravel().astype(np.float64),
                                              minlength=n + 1)
                totales["__pob__"] += float(pob[m].astype(np.float64).sum())
                pob[fuera] = NODATA_POB
                salidas["__pob__"].write(pob, 1, window=w)
                for prod, lut in tasas.items():
                    out = np.where(fuera, np.float32(NODATA_POB), pob * lut[ids]).astype(np.float32)
                    totales[prod] += float(out[m].astype(np.float64).sum())
                    salidas[prod].write(out, 1, window=w)
        finally:
            for s in salidas.values():
                s.close()

    # 7. Contingencia de nivel 3: reparto uniforme sobre el polígono, sumado a lo existente.
    #    Después se recalculan las variables en esas ventanas (población final × tasa del dueño
    #    del píxel), como en el C2, donde las variables se derivan del raster ya estampado.
    if m3.any():
        for k, delta in _estampar_nivel3(radios[m3], rutas, tasas, ids_tif).items():
            totales[k] += delta

    # 8. Controles
    _controlar(ejecucion, radios, totales, variables, suma_por_radio, rid, m3)

    # 9. Salidas tabulares
    cols = [c for c in radios.columns if c != "geometry"]
    radios[cols].to_parquet(d / "radios_factores.parquet", index=False)
    log.info("[%s] listo: %d rasters", ETAPA, len(rutas))
    return radios


def _sin_nodata(a: np.ndarray) -> np.ndarray:
    return np.where(a == NODATA_POB, 0.0, a.astype(np.float64))


def _estampar_nivel3(extremos: gpd.GeoDataFrame, rutas: dict[str, Path],
                     tasas: dict[str, np.ndarray], ids_tif: Path) -> dict[str, float]:
    """Suma pobla_total / n_píxeles en los píxeles que toca cada polígono (C2 5.3).

    Returns:
        Cambio en la suma de cada raster (para actualizar los totales sin releer).
    """
    deltas = dict.fromkeys(rutas, 0.0)
    ventanas: list[Window] = []
    with rasterio.open(rutas["__pob__"], "r+") as dst:
        transform, alto, ancho = dst.transform, dst.height, dst.width
        for _, fila in extremos.iterrows():
            geom = fila.geometry
            w = from_bounds(*geom.bounds, transform=transform)
            col0 = max(int(np.floor(w.col_off)) - 1, 0)
            row0 = max(int(np.floor(w.row_off)) - 1, 0)
            col1 = min(int(np.ceil(w.col_off + w.width)) + 1, ancho)
            row1 = min(int(np.ceil(w.row_off + w.height)) + 1, alto)
            if col1 <= col0 or row1 <= row0:
                continue
            ventana = Window(col0, row0, col1 - col0, row1 - row0)
            mascara = rasterio.features.rasterize(
                [(geom, 1)], out_shape=(row1 - row0, col1 - col0),
                transform=rasterio.windows.transform(ventana, transform),
                all_touched=True, fill=0, dtype=np.uint8) == 1
            npx = int(mascara.sum())
            if npx == 0:
                continue
            valor = float(fila["pobla_total"]) / npx
            bloque = dst.read(1, window=ventana)
            antes = float(_sin_nodata(bloque).sum())
            previo = np.where(bloque[mascara] == NODATA_POB, 0.0, bloque[mascara].astype(np.float64))
            bloque[mascara] = (previo + valor).astype(np.float32)
            deltas["__pob__"] += float(_sin_nodata(bloque).sum()) - antes
            dst.write(bloque, 1, window=ventana)
            ventanas.append(ventana)
    if not ventanas:
        return deltas
    with rasterio.open(rutas["__pob__"]) as sp, rasterio.open(ids_tif) as si:
        archivos = {k: rasterio.open(r, "r+") for k, r in rutas.items() if k != "__pob__"}
        try:
            for ventana in ventanas:
                pob = sp.read(1, window=ventana)
                ids = si.read(1, window=ventana)
                for k, f in archivos.items():
                    antes = float(_sin_nodata(f.read(1, window=ventana)).sum())
                    out = np.where(pob == NODATA_POB, np.float32(NODATA_POB),
                                   pob * tasas[k][ids]).astype(np.float32)
                    f.write(out, 1, window=ventana)
                    deltas[k] += float(_sin_nodata(out).sum()) - antes
        finally:
            for f in archivos.values():
                f.close()
    return deltas


def _controlar(ejecucion: Ejecucion, radios: gpd.GeoDataFrame, totales: dict[str, float],
               variables: list[dict], suma_por_radio: np.ndarray, rid: np.ndarray, m3: pd.Series) -> None:
    cfg = ejecucion.cfg
    tol_rel = float(obtener(cfg, "controles.tolerancia_conservacion_pct", 0.001)) / 100
    tol_radio = float(obtener(cfg, "controles.tolerancia_radio_personas", 0.5))

    pob_censo = float(radios["pobla_total"].sum())
    pob_raster = totales["__pob__"]
    dif = pob_raster - pob_censo
    ejecucion.controlar(Control(ETAPA, "conservación de la población (total)",
                                abs(dif) <= tol_rel * pob_censo,
                                f"raster {pob_raster:,.3f} vs censo {pob_censo:,.0f} (dif {dif:+,.3f})",
                                pob_raster, pob_censo))

    # Por radio (antes del nivel 3, que suma sobre píxeles de otros radios)
    no_ext = ~m3.to_numpy()
    dif_r = np.abs(suma_por_radio[rid][no_ext] - radios["pobla_total"].to_numpy()[no_ext])
    n_mal = int((dif_r > tol_radio).sum())
    ejecucion.controlar(Control(ETAPA, "conservación por radio", n_mal == 0,
                                f"{n_mal} radios difieren más de {tol_radio} personas "
                                f"(máx. {dif_r.max():.4f})", n_mal, 0))

    for v in variables:
        s_r = totales[v["producto"]]
        s_c = float(radios.loc[radios["pobla_total"] > 0, v["numerador"]].fillna(0).sum())
        ok = abs(s_r - s_c) <= max(tol_rel * s_c, 1.0)
        ejecucion.controlar(Control(ETAPA, f"conservación de {v['producto']}", ok,
                                    f"raster {s_r:,.1f} vs censo {s_c:,.0f}", s_r, s_c, bloqueante=False))
        ejecucion.balance(ETAPA, f"variable {v['producto']}", censo=s_c, raster=round(s_r, 3))

    esperado = obtener(cfg, "resultados_esperados.poblacion_raster", None)
    if esperado is not None:
        ejecucion.controlar(Control(ETAPA, "resultado esperado: población del raster",
                                    abs(pob_raster - esperado) <= 1.0, f"{pob_raster:,.3f} vs {esperado:,.3f}",
                                    pob_raster, esperado, bloqueante=False))
