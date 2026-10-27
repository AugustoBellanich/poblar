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

    orden_a = a["id_radio"].tolist()
    orden_b = b["id_radio"].tolist()
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
        ("mismo orden de rasterización", orden_a == orden_b, orden_a == orden_b),
    ]
    df = pd.DataFrame(filas, columns=["comparación", "resultado", "ok"])
    df.loc[df["ok"].isna(), "ok"] = df.loc[df["ok"].isna(), "resultado"].eq(0)
    return df
