"""Etapa 5: publicación de los rasters en la grilla de entrega.

Método (equivalente al cuaderno C5 del PRAIS 2026): cada raster de cantidad de
la etapa 3 se reproyecta a la grilla de un insumo de referencia (en el PRAIS
2026, la del MapBiomas en EPSG:4326) con remuestreo por suma, que conserva el
total de personas salvo en los bordes de la grilla de referencia. Se recorre la
grilla de destino por bloques para no cargar el raster entero en memoria.

Productos en ``5_publicacion/``: un raster por producto con el nombre de
entrega que fija la configuración, y ``publicacion.csv`` con la suma de origen,
la suma publicada y la diferencia de cada uno.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.warp import reproject
from rasterio.windows import Window

from poblar.config import obtener
from poblar.cruce import rutas_productos
from poblar.grilla import ventanas_por_filas
from poblar.trazabilidad import Control, Ejecucion, log

ETAPA = "5_publicacion"
NODATA = -9999.0
REMUESTREOS = {"sum": Resampling.sum, "average": Resampling.average, "near": Resampling.nearest}


def _suma(ruta: Path, filas: int = 1024) -> float:
    total = 0.0
    with rasterio.open(ruta) as s:
        for w in ventanas_por_filas(s.height, s.width, filas):
            a = s.read(1, window=w).astype(np.float64)
            total += float(a[(a != s.nodata) & np.isfinite(a)].sum())
    return total


def reproyectar(origen: Path, referencia: Path, salida: Path, remuestreo: str, bloque: int,
                compresion: str) -> None:
    """Reproyecta ``origen`` a la grilla de ``referencia`` recorriendo el destino por bloques (C5, celda 32)."""
    with rasterio.open(origen) as src, rasterio.open(referencia) as ref:
        perfil = ref.profile.copy()
        perfil.update(driver="GTiff", dtype="float32", count=1, nodata=NODATA, compress=compresion,
                      tiled=True, blockxsize=bloque, blockysize=bloque, BIGTIFF="IF_SAFER")
        with rasterio.open(salida, "w", **perfil) as dst:
            for fila in range(0, ref.height, bloque):
                for col in range(0, ref.width, bloque):
                    v = Window(col, fila, min(bloque, ref.width - col), min(bloque, ref.height - fila))
                    datos = np.full((int(v.height), int(v.width)), NODATA, dtype=np.float32)
                    reproject(source=rasterio.band(src, 1), destination=datos,
                              src_transform=src.transform, src_crs=src.crs, src_nodata=NODATA,
                              dst_transform=rasterio.windows.transform(v, ref.transform), dst_crs=ref.crs,
                              dst_nodata=NODATA, resampling=REMUESTREOS[remuestreo], num_threads=1)
                    dst.write(datos, 1, window=v)


def construir(ejecucion: Ejecucion) -> list[dict[str, Any]]:
    """Corre la etapa 5. Devuelve una fila por raster publicado."""
    cfg = ejecucion.cfg
    d = ejecucion.dir_etapa(ETAPA)
    anio = cfg["anio_censo"]
    referencia = Path(cfg["insumos"][obtener(cfg, "publicacion.grilla_referencia")]["ruta"])
    remuestreo = obtener(cfg, "publicacion.remuestreo")
    if remuestreo not in REMUESTREOS:
        raise ValueError(f"publicacion.remuestreo='{remuestreo}' no válido ({sorted(REMUESTREOS)})")
    bloque = int(obtener(cfg, "publicacion.bloque", 1024))
    compresion = obtener(cfg, "publicacion.compresion", "deflate")
    plantilla = obtener(cfg, "publicacion.plantilla_nombre", "{nombre}_{anio}.tif")
    tol_pct = float(obtener(cfg, "publicacion.tolerancia_masa_pct", 0.001))
    todas = rutas_productos(cfg, ejecucion.carpeta)
    nombres: dict[str, str] = dict(obtener(cfg, "publicacion.productos"))
    faltan = [p for p in nombres if p not in todas]
    if faltan:
        raise ValueError(f"publicacion.productos: productos que la etapa 3 no genera: {faltan}")

    with rasterio.open(referencia) as ref:
        grilla_ref = (ref.width, ref.height, ref.crs, ref.transform)
    filas = []
    for prod, nombre in nombres.items():
        salida = d / plantilla.format(nombre=nombre, anio=anio, producto=prod)
        log.info("[%s] %s → %s", ETAPA, prod, salida.name)
        reproyectar(todas[prod], referencia, salida, remuestreo, bloque, compresion)
        s_in, s_out = _suma(todas[prod]), _suma(salida)
        dif = s_out - s_in
        pct = 100 * dif / s_in if s_in else 0.0
        with rasterio.open(salida) as s:
            misma = (s.width, s.height, s.crs, s.transform) == grilla_ref
        filas.append({"producto": prod, "archivo": salida.name, "suma_origen": round(s_in, 3),
                      "suma_publicada": round(s_out, 3), "diferencia": round(dif, 3),
                      "diferencia_pct": round(pct, 6), "misma_grilla": misma})
        ejecucion.controlar(Control(ETAPA, f"grilla de referencia: {salida.name}", misma,
                                    "coincide" if misma else "no coincide"))
        ejecucion.controlar(Control(ETAPA, f"conservación de la masa: {prod}", abs(pct) <= tol_pct,
                                    f"{s_in:,.3f} → {s_out:,.3f} ({dif:+,.3f}; {pct:+.5f} %)", s_out, s_in,
                                    bloqueante=False))

    with (d / "publicacion.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0]))
        w.writeheader()
        w.writerows(filas)

    esperado = obtener(cfg, "resultados_esperados.publicacion", None) or {}
    por_prod = {f["producto"]: f["suma_publicada"] for f in filas}
    for prod, valor in esperado.items():
        if prod in por_prod:
            ok = abs(por_prod[prod] - float(valor)) <= 0.01
            ejecucion.controlar(Control(ETAPA, f"resultado esperado: suma publicada de {prod}", ok,
                                        f"{por_prod[prod]:,.3f} vs {float(valor):,.3f}", por_prod[prod], valor,
                                        bloqueante=False))
    log.info("[%s] listo: %d rasters publicados", ETAPA, len(filas))
    return filas
