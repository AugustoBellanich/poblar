"""Comparación de una salida de poblar contra una ejecución de referencia.

Sirve para verificar la reproducción de resultados publicados: por ejemplo, comparar ``1_radios/radios.parquet``
con la caché ``02_radios_curados_<año>.parquet`` del C2 original.
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pandas as pd


def comparar_radios(
    nuevo: str | Path,
    referencia: str | Path,
    campo_region: str = "Reg_PRAIS",
    tolerancia_area_m2: float = 1.0,
) -> pd.DataFrame:
    """Compara radio por radio: ids, población, región, área y orden.

    Args:
        nuevo: ``radios.parquet`` de poblar.
        referencia: GeoParquet del C2 original (``02_radios_curados_<año>.parquet``).
        campo_region: Columna de región en los dos archivos.
        tolerancia_area_m2: Diferencia de área admitida por radio.

    Returns:
        Tabla resumen con una fila por comparación.
    """
    a = gpd.read_parquet(nuevo)
    b = gpd.read_parquet(referencia)
    for g in (a, b):
        g["id_radio"] = g["id_radio"].astype(str)
    ids_a, ids_b = set(a["id_radio"]), set(b["id_radio"])
    m = a.merge(b, on="id_radio", suffixes=("_nuevo", "_ref"))
    if "area_m2_ref" not in m:
        m["area_m2_ref"] = gpd.GeoSeries(m["geometry_ref"], crs=b.crs).area
    if "area_m2_nuevo" not in m:
        m["area_m2_nuevo"] = gpd.GeoSeries(m["geometry_nuevo"], crs=a.crs).area

    comunes = ids_a & ids_b
    orden_a = [i for i in a["id_radio"] if i in comunes]
    orden_b = [i for i in b["id_radio"] if i in comunes]
    filas = [
        ("radios (nuevo / referencia)", f"{len(a)} / {len(b)}", len(a) == len(b)),
        ("ids solo en nuevo", len(ids_a - ids_b), not (ids_a - ids_b)),
        ("ids solo en referencia", len(ids_b - ids_a), not (ids_b - ids_a)),
        ("población total (nuevo / referencia)",
         f"{a['pobla_total'].sum():,.0f} / {b['pobla_total'].sum():,.0f}",
         abs(a["pobla_total"].sum() - b["pobla_total"].sum()) < 0.5),
        ("radios con población distinta",
         int(((m["pobla_total_nuevo"] - m["pobla_total_ref"]).abs() > 0.5).sum()), None),
        ("radios con región distinta",
         int((m[f"{campo_region}_nuevo"].astype(str) != m[f"{campo_region}_ref"].astype(str)).sum()), None),
        ("radios con área distinta (> tolerancia)",
         int(((m["area_m2_nuevo"] - m["area_m2_ref"]).abs() > tolerancia_area_m2).sum()), None),
        ("mismo orden de rasterización (radios en común)", orden_a == orden_b, orden_a == orden_b),
    ]
    df = pd.DataFrame(filas, columns=["comparación", "resultado", "ok"])
    df.loc[df["ok"].isna(), "ok"] = df.loc[df["ok"].isna(), "resultado"].eq(0)
    return df


def comparar_raster(
    nuevo: str | Path,
    referencia: str | Path,
    filas_por_bloque: int = 512,
    tolerancia: float = 1e-4,
) -> pd.DataFrame:
    """Compara dos rasters píxel por píxel, por bloques (sin cargarlos enteros en memoria).

    Verifica grilla (tamaño, transformación y CRS), máscara de nodata, sumas y diferencias.

    Args:
        nuevo: Raster de poblar (por ejemplo ``3_dasimetria/poblacion_dasimetrica_2010.tif``).
        referencia: Raster equivalente del método original.
        filas_por_bloque: Filas por bloque de lectura.
        tolerancia: Diferencia absoluta por píxel a partir de la cual se cuenta como distinto.

    Returns:
        Tabla resumen con una fila por comparación.
    """
    import numpy as np
    import rasterio
    from rasterio.windows import Window

    filas = []
    with rasterio.open(nuevo) as a, rasterio.open(referencia) as b:
        misma = (a.width, a.height) == (b.width, b.height)
        filas.append({"comparacion": "tamaño de la grilla", "nuevo": f"{a.width} x {a.height}",
                      "referencia": f"{b.width} x {b.height}", "igual": misma})
        filas.append({"comparacion": "transformación", "nuevo": str(tuple(a.transform)[:6]),
                      "referencia": str(tuple(b.transform)[:6]),
                      "igual": a.transform.almost_equals(b.transform, precision=1e-6)})
        filas.append({"comparacion": "CRS", "nuevo": str(a.crs), "referencia": str(b.crs),
                      "igual": a.crs == b.crs})
        if not misma:
            return pd.DataFrame(filas)
        suma_a = suma_b = 0.0
        dif_max = 0.0
        distintos = mascara_distinta = 0
        for f in range(0, a.height, filas_por_bloque):
            w = Window(0, f, a.width, min(filas_por_bloque, a.height - f))
            x = a.read(1, window=w).astype(np.float64)
            y = b.read(1, window=w).astype(np.float64)
            vx = x != a.nodata if a.nodata is not None else np.isfinite(x)
            vy = y != b.nodata if b.nodata is not None else np.isfinite(y)
            mascara_distinta += int((vx != vy).sum())
            x = np.where(vx, x, 0.0)
            y = np.where(vy, y, 0.0)
            suma_a += float(x.sum())
            suma_b += float(y.sum())
            d = np.abs(x - y)
            if d.size:
                dif_max = max(dif_max, float(d.max()))
            distintos += int((d > tolerancia).sum())
    filas += [
        {"comparacion": "píxeles con distinta máscara de nodata", "nuevo": mascara_distinta,
         "referencia": 0, "igual": mascara_distinta == 0},
        {"comparacion": "suma", "nuevo": round(suma_a, 3), "referencia": round(suma_b, 3),
         "igual": abs(suma_a - suma_b) <= max(1e-3, 1e-9 * abs(suma_b))},
        {"comparacion": f"píxeles con diferencia > {tolerancia}", "nuevo": distintos, "referencia": 0,
         "igual": distintos == 0},
        {"comparacion": "diferencia máxima por píxel", "nuevo": dif_max, "referencia": 0.0,
         "igual": dif_max <= tolerancia},
    ]
    return pd.DataFrame(filas)


# Nombres de variables del C3 original → productos de poblar (configuración PRAIS 2026)
NOMBRES_C3 = {
    "poblacion_total": "poblacion_dasimetrica", "nbi": "nbi", "agua_red": "agua_red",
    "varones": "pobla_varon", "mujeres": "pobla_mujer", "varones_nbi": "nbi_varon",
    "mujeres_nbi": "nbi_mujer", "varones_red": "agua_red_varon", "mujeres_red": "agua_red_mujer",
    "agua_sin_red": "agua_sin_red",
}


def comparar_cruce(nuevo: str | Path, referencia: str | Path, tolerancia: float = 0.5) -> pd.DataFrame:
    """Compara ``4_cruce/cruce_largo.csv`` con ``exposicion_degradacion_<año>_largo.csv`` del C3.

    Compara fila por fila (región × ámbito × clase × variable).

    Returns:
        Una fila por variable: suma nueva, suma de referencia, filas comparadas,
        filas que difieren más que ``tolerancia`` personas y diferencia máxima.
    """
    n = pd.read_csv(nuevo)
    r = pd.read_csv(referencia).rename(columns={"categoria": "clase", "poblacion": "valor"})
    r["variable"] = r["variable"].map(NOMBRES_C3).fillna(r["variable"])
    claves = ["region", "ambito", "clase", "variable"]
    m = n.groupby(claves)["valor"].sum().to_frame("nuevo").join(
        r.groupby(claves)["valor"].sum().to_frame("referencia"), how="outer").fillna(0.0)
    m["dif"] = m["nuevo"] - m["referencia"]
    t = m.reset_index().groupby("variable").agg(
        suma_nueva=("nuevo", "sum"), suma_referencia=("referencia", "sum"), filas=("dif", "size"),
        filas_distintas=("dif", lambda x: int((x.abs() > tolerancia).sum())),
        dif_max=("dif", lambda x: float(x.abs().max())))
    t["dif_suma"] = t["suma_nueva"] - t["suma_referencia"]
    return t.reset_index()
