"""Comparación de dos rasters píxel por píxel.

Sirve para comparar dos ejecuciones de poblar (por ejemplo, la misma aplicación
con dos configuraciones) o un producto contra otro raster de la misma grilla.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd


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
