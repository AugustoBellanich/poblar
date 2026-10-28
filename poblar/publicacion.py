"""Etapa 5: publicación de los rasters en la grilla de entrega.

Método: cada raster de cantidad de
la etapa 3 se reproyecta a la grilla de un insumo de referencia (por ejemplo, la de
la cobertura del suelo en EPSG:4326) con remuestreo por suma, que conserva el
total de personas salvo en los bordes de la grilla de referencia. Se recorre la
grilla de destino por bloques para no cargar el raster entero en memoria.

Productos en ``5_publicacion/``: un raster por producto con el nombre de
entrega que fija la configuración, y ``publicacion.csv`` con la suma de origen,
la suma publicada y la diferencia de cada uno.

Cada raster es independiente: se procesan en paralelo (``publicacion.procesos``;
no cambia los resultados) y cada uno se guarda apenas termina. Si la ejecución
se corta, al retomarla se saltean los rasters que ya figuran en
``publicacion.csv`` y cuyo archivo existe.
"""

from __future__ import annotations

import csv
import multiprocessing
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
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
from poblar.trazabilidad import SUFIJO_PARCIAL, Control, Ejecucion, log

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
    """Reproyecta ``origen`` a la grilla de ``referencia`` recorriendo el destino por bloques."""
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


def _publicar_uno(prod: str, origen: Path, referencia: Path, salida: Path, remuestreo: str, bloque: int,
                  compresion: str) -> dict[str, Any]:
    """Publica un raster y devuelve su fila de control (se ejecuta en un proceso aparte).

    Se escribe con el sufijo ``.parcial`` y se renombra recién cuando está completo y controlado:
    mientras tanto, el guardado de avance no lo copia.
    """
    tmp = salida.with_name(salida.name + SUFIJO_PARCIAL)
    reproyectar(origen, referencia, tmp, remuestreo, bloque, compresion)
    s_in, s_out = _suma(origen), _suma(tmp)
    with rasterio.open(tmp) as s, rasterio.open(referencia) as ref:
        misma = (s.width, s.height, s.crs, s.transform) == (ref.width, ref.height, ref.crs, ref.transform)
    os.replace(tmp, salida)
    dif = s_out - s_in
    return {"producto": prod, "archivo": salida.name, "suma_origen": round(s_in, 3),
            "suma_publicada": round(s_out, 3), "diferencia": round(dif, 3),
            "diferencia_pct": round(100 * dif / s_in if s_in else 0.0, 6), "misma_grilla": misma}


def _escribir_tabla(ruta: Path, filas: list[dict[str, Any]]) -> None:
    with ruta.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0]))
        w.writeheader()
        w.writerows(filas)


def _leer_tabla(ruta: Path, d: Path) -> dict[str, dict[str, Any]]:
    """Filas de una publicación anterior cuyo archivo existe (para retomar)."""
    if not ruta.exists():
        return {}
    previas = {}
    with ruta.open(encoding="utf-8") as f:
        for fila in csv.DictReader(f):
            if (d / fila["archivo"]).exists():
                fila["misma_grilla"] = fila["misma_grilla"] == "True"
                for k in ("suma_origen", "suma_publicada", "diferencia", "diferencia_pct"):
                    fila[k] = float(fila[k])
                previas[fila["producto"]] = fila
    return previas


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

    procesos = int(obtener(cfg, "publicacion.procesos", 0) or os.cpu_count() or 1)
    tabla = d / "publicacion.csv"
    hechas = _leer_tabla(tabla, d)
    filas: list[dict[str, Any]] = [hechas[p] for p in nombres if p in hechas]
    if filas:
        log.info("[%s] retomando: %d rasters ya publicados (%s)", ETAPA, len(filas),
                 ", ".join(f["producto"] for f in filas))
    pendientes = {p: n for p, n in nombres.items() if p not in hechas}

    def registrar(fila: dict[str, Any]) -> None:
        ejecucion.controlar(Control(ETAPA, f"grilla de referencia: {fila['archivo']}", fila["misma_grilla"],
                                    "coincide" if fila["misma_grilla"] else "no coincide"))
        ejecucion.controlar(Control(ETAPA, f"conservación de la masa: {fila['producto']}",
                                    abs(fila["diferencia_pct"]) <= tol_pct,
                                    f"{fila['suma_origen']:,.3f} → {fila['suma_publicada']:,.3f} "
                                    f"({fila['diferencia']:+,.3f}; {fila['diferencia_pct']:+.5f} %)",
                                    fila["suma_publicada"], fila["suma_origen"], bloqueante=False))

    for fila in filas:
        registrar(fila)
    log.info("[%s] %d rasters por publicar con %d procesos", ETAPA, len(pendientes), procesos)
    # 'spawn': procesos nuevos (no copias del proceso principal), seguro con GDAL y con hilos.
    with ProcessPoolExecutor(max_workers=procesos, mp_context=multiprocessing.get_context("spawn")) as pool:
        futuros = {pool.submit(_publicar_uno, prod, todas[prod], referencia,
                               d / plantilla.format(nombre=nombre, anio=anio, producto=prod),
                               remuestreo, bloque, compresion): prod
                   for prod, nombre in pendientes.items()}
        for fut in as_completed(futuros):
            fila = fut.result()
            log.info("[%s] publicado %d/%d: %s → %s", ETAPA, len(filas) + 1, len(nombres),
                     fila["producto"], fila["archivo"])
            filas.append(fila)
            registrar(fila)
            _escribir_tabla(tabla, filas)
            ejecucion.guardar_avance()   # cada raster queda guardado apenas termina

    orden = list(nombres)
    filas.sort(key=lambda f: orden.index(f["producto"]))
    _escribir_tabla(tabla, filas)

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
