"""Etapa 2: grilla de trabajo y cobertura del suelo.

Lleva el raster de cobertura (MapBiomas) a la grilla de trabajo con vecino más
cercano y lo reclasifica en tres metacategorías según la tabla de clases de la
configuración: 0 no habitable, 1 urbano, 2 no urbano.

Productos en ``2_grilla/``: ``cobertura_trabajo.tif`` (clases originales en la
grilla de trabajo), ``cobertura.tif`` (metacategorías), ``clases_aplicadas.csv``
y ``grilla.json``.
"""

from __future__ import annotations

import json
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.windows import Window

from poblar.config import obtener
from poblar.gdal import ejecutar_gdal, opciones_creacion, version_gdal_cli
from poblar.insumos import ruta_vector
from poblar.trazabilidad import Control, Ejecucion, log

ETAPA = "2_grilla"
METACATEGORIAS = {"no_habitable": 0, "urbano": 1, "no_urbano": 2}


def ventanas_por_filas(alto: int, ancho: int, filas: int, avance: str | None = None):
    """Ventanas de franjas horizontales completas (recorrido por bloques).

    Args:
        avance: Si se indica, se informa en el registro el porcentaje recorrido cada 10 %.
    """
    total = -(-alto // filas)
    paso = max(1, total // 10)
    for i, fila in enumerate(range(0, alto, filas)):
        if avance and i and i % paso == 0:
            log.info("  %s: %d %%", avance, round(100 * i / total))
        yield Window(0, fila, ancho, min(filas, alto - fila))


def tabla_clases(cfg: dict[str, Any]) -> pd.DataFrame:
    """Tabla de clases de la configuración como DataFrame (clase, descripción, meta)."""
    filas = []
    for item in obtener(cfg, "cobertura.clases"):
        meta = item["meta"]
        if meta not in METACATEGORIAS:
            raise ValueError(f"Metacategoría desconocida '{meta}' para la clase {item['clase']}. "
                             f"Usar: {sorted(METACATEGORIAS)}")
        filas.append({"clase_original": int(item["clase"]), "descripcion": item.get("descripcion", ""),
                      "meta_codigo": METACATEGORIAS[meta], "meta_categoria": meta})
    return pd.DataFrame(filas)


def _extension(cfg: dict[str, Any], radios: gpd.GeoDataFrame, crs: int) -> tuple[float, float, float, float]:
    ext = obtener(cfg, "grilla_trabajo.extension")
    if ext == "radios":
        return tuple(radios.total_bounds)  # type: ignore[return-value]
    if ext == "regiones":
        reg = gpd.read_file(ruta_vector(cfg["insumos"]["regiones"]),
                            layer=cfg["insumos"]["regiones"].get("capa")).to_crs(epsg=crs)
        return tuple(reg.total_bounds)  # type: ignore[return-value]
    raise ValueError(f"grilla_trabajo.extension='{ext}' no válido (radios | regiones)")


def construir(ejecucion: Ejecucion, radios: gpd.GeoDataFrame | None = None) -> dict[str, Any]:
    """Corre la etapa 2. Devuelve la descripción de la grilla."""
    cfg = ejecucion.cfg
    d = ejecucion.dir_etapa(ETAPA)
    crs = int(obtener(cfg, "grilla_trabajo.crs"))
    if radios is None:
        radios = gpd.read_parquet(ejecucion.carpeta / "1_radios" / "radios.parquet")

    # 1. Cobertura en la grilla de trabajo
    origen = cfg["insumos"][obtener(cfg, "cobertura.insumo")]["ruta"]
    xmin, ymin, xmax, ymax = _extension(cfg, radios, crs)
    trabajo = d / "cobertura_trabajo.tif"
    args = ["gdalwarp", "-overwrite", "-t_srs", f"EPSG:{crs}",
            "-te", str(xmin), str(ymin), str(xmax), str(ymax),
            "-r", obtener(cfg, "grilla_trabajo.remuestreo_cobertura")]
    modo = obtener(cfg, "grilla_trabajo.modo")
    if modo == "fija":
        res = float(obtener(cfg, "grilla_trabajo.resolucion_m"))
        args += ["-tr", str(res), str(res), "-tap"]
    elif modo != "gdal_auto":
        raise ValueError(f"grilla_trabajo.modo='{modo}' no válido (gdal_auto | fija)")
    args += ["-multi", "-wo", "NUM_THREADS=ALL_CPUS", *opciones_creacion(), str(origen), str(trabajo)]
    ejecutar_gdal(args)

    with rasterio.open(trabajo) as src:
        grilla = {"crs": f"EPSG:{crs}", "ancho": src.width, "alto": src.height,
                  "res_x": src.res[0], "res_y": src.res[1], "limites": list(src.bounds),
                  "transform": list(src.transform)[:6], "nodata_origen": src.nodata,
                  "dtype_origen": src.dtypes[0], "gdal_cli": version_gdal_cli()}
    (d / "grilla.json").write_text(json.dumps(grilla, indent=2), encoding="utf-8")
    ejecucion.balance(ETAPA, "grilla de trabajo", ancho=grilla["ancho"], alto=grilla["alto"],
                      res_x=round(grilla["res_x"], 6), res_y=round(grilla["res_y"], 6), modo=modo)

    # 2. Reclasificación a metacategorías
    clases = tabla_clases(cfg)
    clases.to_csv(d / "clases_aplicadas.csv", index=False, encoding="utf-8")
    lut = np.zeros(256, dtype=np.uint8)
    for _, f in clases.iterrows():
        lut[f["clase_original"]] = f["meta_codigo"]
    nodata_cob = int(obtener(cfg, "cobertura.codigo_nodata"))
    filas = int(obtener(cfg, "rendimiento.filas_por_bloque", 512))

    presentes: dict[int, int] = {}
    conteo_meta = np.zeros(256, dtype=np.int64)
    salida = d / "cobertura.tif"
    with rasterio.open(trabajo) as src:
        perfil = src.profile.copy()
        perfil.update(dtype="uint8", nodata=nodata_cob, compress="lzw", tiled=True,
                      blockxsize=256, blockysize=256, BIGTIFF="IF_SAFER")
        with rasterio.open(salida, "w", **perfil) as dst:
            for w in ventanas_por_filas(src.height, src.width, filas, avance="reclasificación"):
                orig = src.read(1, window=w)
                valido = orig != src.nodata if src.nodata is not None else np.ones(orig.shape, bool)
                v, n = np.unique(orig[valido], return_counts=True)
                for a, b in zip(v.tolist(), n.tolist()):
                    presentes[int(a)] = presentes.get(int(a), 0) + int(b)
                meta = np.zeros(orig.shape, dtype=np.uint8)
                meta[valido] = lut[orig[valido].astype(np.int64) & 0xFF]
                conteo_meta += np.bincount(meta.ravel(), minlength=256)
                dst.write(meta, 1, window=w)

    (d / "clases_presentes.json").write_text(json.dumps(presentes, indent=2), encoding="utf-8")
    sin_mapear = sorted(set(presentes) - set(clases["clase_original"]))
    ejecucion.controlar(Control(ETAPA, "todas las clases presentes están en la tabla", not sin_mapear,
                                f"clases sin mapear: {sin_mapear}" if sin_mapear else
                                f"{len(presentes)} clases presentes, todas mapeadas"))
    ejecucion.balance(ETAPA, "cobertura", no_habitable=int(conteo_meta[0]), urbano=int(conteo_meta[1]),
                      no_urbano=int(conteo_meta[2]), pixeles=int(conteo_meta.sum()))

    esperado = obtener(cfg, "resultados_esperados.grilla", None) or {}
    for clave in ("ancho", "alto"):
        if clave in esperado:
            ejecucion.controlar(Control(ETAPA, f"resultado esperado: {clave} de la grilla",
                                        grilla[clave] == esperado[clave],
                                        f"{grilla[clave]} vs {esperado[clave]}", grilla[clave],
                                        esperado[clave], bloqueante=False))
    log.info("[%s] listo: %d x %d píxeles", ETAPA, grilla["ancho"], grilla["alto"])
    return grilla
