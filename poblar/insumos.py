"""Etapa 0: registro de insumos.

Para cada insumo del config calcula el sha256, lee sus metadatos (CRS, grilla,
columnas, cantidad de registros) y los compara con lo declarado. No transforma
nada: deja ``0_insumos/insumos.csv`` como huella de lo que entró.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import pandas as pd
import pyogrio

from poblar.trazabilidad import Corrida, Validacion, log, sha256

ETAPA = "0_insumos"
EXT_TABLA = {".xlsx", ".xls", ".csv"}
EXT_VECTOR = {".zip", ".shp", ".gpkg", ".parquet", ".geojson", ".fgb"}
EXT_RASTER = {".tif", ".tiff"}


def ruta_vector(ins: dict[str, Any]) -> str:
    """Ruta legible por GDAL; un .zip se lee directo con /vsizip/."""
    ruta = str(ins["ruta"])
    if ruta.lower().endswith(".zip"):
        interno = ins.get("archivo_interno")
        return f"/vsizip/{ruta}/{interno}" if interno else f"/vsizip/{ruta}"
    return ruta


def _meta_tabla(ins: dict[str, Any]) -> dict[str, Any]:
    ruta = Path(ins["ruta"])
    if ruta.suffix.lower() == ".csv":
        df = pd.read_csv(ruta, nrows=5, dtype=str, encoding=ins.get("encoding", "utf-8"))
        n = sum(1 for _ in ruta.open(encoding=ins.get("encoding", "utf-8"))) - 1
    else:
        df = pd.read_excel(ruta, dtype=str, sheet_name=ins.get("hoja", 0))
        n = len(df)
    return {"tipo": "tabla", "registros": n, "columnas": list(map(str, df.columns))}


def _meta_vector(ins: dict[str, Any]) -> dict[str, Any]:
    ruta = ruta_vector(ins)
    capa = ins.get("capa")
    info = pyogrio.read_info(ruta, layer=capa)
    # La cantidad declarada en los metadatos puede estar mal (caso
    # gpkg_ogr_contents = 0): se cuenta leyendo de verdad.
    n_real = len(pyogrio.read_dataframe(ruta, layer=capa, columns=[], read_geometry=False,
                                        fid_as_index=True))
    return {
        "tipo": "vector",
        "registros": n_real,
        "registros_metadatos": int(info.get("features", -1)),
        "crs": str(info.get("crs")),
        "geometria": str(info.get("geometry_type")),
        "columnas": list(map(str, info.get("fields", []))),
    }


def _meta_raster(ins: dict[str, Any]) -> dict[str, Any]:
    import rasterio

    with rasterio.open(ins["ruta"]) as r:
        return {
            "tipo": "raster",
            "crs": str(r.crs),
            "ancho": r.width,
            "alto": r.height,
            "res_x": r.res[0],
            "res_y": r.res[1],
            "limites": list(r.bounds),
            "nodata": r.nodata,
            "dtype": r.dtypes[0],
            "bandas": r.count,
        }


def registrar(corrida: Corrida) -> list[dict[str, Any]]:
    """Registra todos los insumos del config.

    Returns:
        Una fila por insumo con su hash y metadatos.
    """
    filas: list[dict[str, Any]] = []
    for nombre, ins in (corrida.cfg.get("insumos") or {}).items():
        ruta = Path(ins["ruta"])
        existe = ruta.exists()
        corrida.validar(Validacion(ETAPA, f"existe {nombre}", existe, str(ruta)))

        h = sha256(ruta)
        esperado = ins.get("sha256")
        if esperado:
            corrida.validar(Validacion(
                ETAPA, f"sha256 {nombre}", h == esperado,
                "coincide con el declarado" if h == esperado else f"es {h[:12]}…, se declaró {esperado[:12]}…",
                h, esperado,
            ))

        ext = ruta.suffix.lower()
        if ext in EXT_TABLA:
            meta = _meta_tabla(ins)
        elif ext in EXT_VECTOR:
            meta = _meta_vector(ins)
            corrida.validar(Validacion(
                ETAPA, f"{nombre} no vacío", meta["registros"] > 0,
                f"{meta['registros']} registros leídos (metadatos: {meta['registros_metadatos']})",
                meta["registros"],
            ))
        elif ext in EXT_RASTER:
            meta = _meta_raster(ins)
        else:
            meta = {"tipo": "otro"}

        fila = {"insumo": nombre, "ruta": str(ruta), "bytes": ruta.stat().st_size, "sha256": h, **meta}
        filas.append(fila)
        corrida.cuenta(ETAPA, nombre, tipo=meta["tipo"], registros=meta.get("registros", ""),
                       sha256=h[:12])

    d = corrida.dir_etapa(ETAPA)
    with (d / "insumos.json").open("w", encoding="utf-8") as f:
        json.dump(filas, f, ensure_ascii=False, indent=2, default=str)
    planas = [{k: (json.dumps(v, ensure_ascii=False) if isinstance(v, list) else v) for k, v in f.items()}
              for f in filas]
    claves: list[str] = []
    for f_ in planas:
        claves += [k for k in f_ if k not in claves]
    with (d / "insumos.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=claves)
        w.writeheader()
        w.writerows(planas)
    log.info("[%s] %d insumos registrados", ETAPA, len(filas))
    return filas
