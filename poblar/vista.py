"""Vistas rápidas de los productos de una ejecución.

Los rasters se leen reducidos (por defecto, unos 900 píxeles de ancho) para que
la vista sea inmediata aun con grillas de miles de millones de píxeles. Son para
revisar, no para publicar: el dato completo está en los rasters de la ejecución.

Uso en un cuaderno::

    from poblar import vista
    vista.mapa("ejecuciones/prais2026_2022", "poblacion")
    vista.mapa("ejecuciones/prais2026_2022", "expuesta", region="Chaco")
    vista.productos("ejecuciones/prais2026_2022")     # qué se puede mostrar
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import rasterio
from rasterio.enums import Resampling
from rasterio.windows import from_bounds

COLOR_DEGRADADA = "#9b5de5"
COLOR_NO_DEGRADADA = "#f1efd9"
COLOR_SIN_DATO = "#c8c8c8"
TITULOS = {
    "poblacion": "Población",
    "expuesta": "Población en tierras degradadas",
    "degradacion": "Tierras degradadas",
    "cobertura": "Cobertura (metacategorías)",
}


def _cfg(carpeta: Path) -> dict[str, Any]:
    import yaml

    return yaml.safe_load((carpeta / "config.yaml").read_text(encoding="utf-8"))


def productos(carpeta: str | Path) -> list[str]:
    """Nombres que acepta :func:`mapa` para esta ejecución."""
    carpeta = Path(carpeta)
    out = []
    if (carpeta / "2_grilla" / "cobertura.tif").exists():
        out.append("cobertura")
    d3 = carpeta / "3_dasimetria"
    if d3.exists():
        out.append("poblacion")
        out += sorted(p.name.split("_dasimetrico_")[0] for p in d3.glob("*_dasimetrico_*.tif"))
    if (carpeta / "4_cruce" / "tematica_trabajo.tif").exists():
        out += ["degradacion", "expuesta"]
    return out


def _ruta(carpeta: Path, producto: str) -> Path:
    anio = _cfg(carpeta)["anio_censo"]
    d3 = carpeta / "3_dasimetria"
    if producto in ("poblacion", "expuesta"):
        cand = sorted(d3.glob(f"*_{anio}.tif"))
        pob = [p for p in cand if "_dasimetrico_" not in p.name]
        if not pob:
            raise FileNotFoundError(f"No hay raster de población en {d3}")
        return pob[0]
    if producto == "degradacion":
        return carpeta / "4_cruce" / "tematica_trabajo.tif"
    if producto == "cobertura":
        return carpeta / "2_grilla" / "cobertura.tif"
    ruta = d3 / f"{producto}_dasimetrico_{anio}.tif"
    if not ruta.exists():
        raise ValueError(f"Producto '{producto}' no encontrado. Disponibles: {productos(carpeta)}")
    return ruta


def extension(carpeta: str | Path, region: str | None = None) -> tuple[float, float, float, float]:
    """Límites de los radios de una región (o del país sin la región «fuera»), en el CRS de trabajo."""
    import geopandas as gpd

    carpeta = Path(carpeta)
    cfg = _cfg(carpeta)
    campo = cfg["region"]["campo"]
    radios = gpd.read_parquet(carpeta / "1_radios" / "radios.parquet", columns=[campo, "geometry"])
    if region is not None:
        sel = radios[radios[campo] == region]
        if sel.empty:
            raise ValueError(f"Región '{region}' no encontrada. Regiones: {sorted(radios[campo].unique())}")
    else:
        sel = radios[radios[campo] != cfg["region"].get("etiqueta_fuera")]
    return tuple(sel.total_bounds)  # type: ignore[return-value]


def leer(ruta: Path, limites: tuple[float, float, float, float], ancho_px: int,
         remuestreo: Resampling) -> tuple[np.ndarray, float, rasterio.Affine]:
    """Lee una ventana reducida. Devuelve la matriz (NaN = sin dato), el factor de reducción y la transformación."""
    with rasterio.open(ruta) as s:
        w = from_bounds(*limites, transform=s.transform).round_offsets().round_lengths()
        w = w.intersection(rasterio.windows.Window(0, 0, s.width, s.height))
        factor = max(1.0, w.width / ancho_px)
        forma = (max(1, int(w.height / factor)), max(1, int(w.width / factor)))
        a = s.read(1, window=w, out_shape=forma, resampling=remuestreo, masked=True)
        t = s.window_transform(w) @ rasterio.Affine.scale(w.width / forma[1], w.height / forma[0])
        return a.astype("float64").filled(np.nan), factor, t


def mapa(carpeta: str | Path, producto: str = "poblacion", region: str | None = None,
         ancho_px: int = 900, ax: Any = None, titulo: str | None = None):
    """Mapa de vista rápida de un producto.

    Args:
        carpeta: Carpeta de la ejecución.
        producto: ``poblacion``, ``expuesta`` (población en el grupo expuesto), ``degradacion``,
            ``cobertura`` o una variable de la etapa 3 (``nbi``, ``agua_red``, ...).
            Ver :func:`productos`.
        region: Acercamiento a una región (por defecto, el país sin la región «fuera»).
        ancho_px: Ancho de la lectura reducida.
        ax: Ejes de matplotlib donde dibujar (opcional).
        titulo: Título (por defecto, el del producto).

    Returns:
        La figura de matplotlib.
    """
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap, LogNorm
    from matplotlib.patches import Patch

    carpeta = Path(carpeta)
    limites = extension(carpeta, region)
    if ax is None:
        fig, ax = plt.subplots(figsize=(6, 8) if region is None else (7, 7))
    else:
        fig = ax.figure
    ax.set_axis_off()
    nombre = TITULOS.get(producto, producto) if titulo is None else titulo
    if nombre:
        ax.set_title(nombre + (f" — {region}" if region else ""), fontsize=11, loc="left")

    if producto in ("degradacion", "cobertura"):
        cat, _, _ = leer(_ruta(carpeta, producto), limites, ancho_px, Resampling.mode)
        if producto == "degradacion":
            cfg = _cfg(carpeta)
            grupo = cfg["cruce"].get("grupo_expuesto")
            clases = cfg["cruce"]["clases"]
            exp = [c["clase"] for c in clases if c.get("binario") == grupo]
            otros = [c["clase"] for c in clases if c.get("binario") not in (None, grupo)]
            img = np.full(cat.shape, np.nan)
            img[np.isin(cat, otros)] = 1
            img[np.isin(cat, exp)] = 2
            img[np.isin(cat, [c["clase"] for c in clases if c.get("binario") is None])] = 0
            cmap = ListedColormap([COLOR_SIN_DATO, COLOR_NO_DEGRADADA, COLOR_DEGRADADA])
            ax.imshow(img, cmap=cmap, vmin=0, vmax=2, interpolation="nearest")
            ax.legend(handles=[Patch(color=COLOR_DEGRADADA, label=str(grupo).replace("_", " ").capitalize()),
                               Patch(color=COLOR_NO_DEGRADADA, label="No degradada"),
                               Patch(color=COLOR_SIN_DATO, label="Sin datos")],
                      loc="lower right", fontsize=8, frameon=False)
        else:
            img = np.where(np.isnan(cat), np.nan, cat)
            cmap = ListedColormap(["#e9e4dc", "#d1495b", "#8ab17d"])
            ax.imshow(img, cmap=cmap, vmin=0, vmax=2, interpolation="nearest")
            ax.legend(handles=[Patch(color="#d1495b", label="Urbano"), Patch(color="#8ab17d", label="No urbano"),
                               Patch(color="#e9e4dc", label="No habitable")],
                      loc="lower right", fontsize=8, frameon=False)
        return fig

    # Cantidades: promedio por píxel de la grilla de trabajo → personas por km²
    ruta = _ruta(carpeta, producto)
    valores, _, _ = leer(ruta, limites, ancho_px, Resampling.average)
    with rasterio.open(ruta) as s:
        km2 = abs(s.transform.a * s.transform.e) / 1e6
    dens = valores / km2
    if producto == "expuesta":
        cat, _, _ = leer(_ruta(carpeta, "degradacion"), limites, ancho_px, Resampling.mode)
        cfg = _cfg(carpeta)
        grupo = cfg["cruce"].get("grupo_expuesto")
        exp = [c["clase"] for c in cfg["cruce"]["clases"] if c.get("binario") == grupo]
        fondo = np.where(np.isnan(cat), np.nan, 0.0)
        ax.imshow(fondo, cmap=ListedColormap(["#ecebe6"]), interpolation="nearest")
        dens = np.where(np.isin(cat, exp), dens, np.nan)
    else:
        fondo = np.where(np.isnan(valores), np.nan, 0.0)
        ax.imshow(fondo, cmap=ListedColormap(["#ecebe6"]), interpolation="nearest")
    dens = np.where(dens > 0, dens, np.nan)
    if np.isfinite(dens).any():
        vmin = max(np.nanpercentile(dens, 2), 1e-3)
        vmax = max(np.nanpercentile(dens, 99.8), vmin * 10)
        im = ax.imshow(dens, cmap="magma_r", norm=LogNorm(vmin=vmin, vmax=vmax), interpolation="nearest")
        cb = fig.colorbar(im, ax=ax, fraction=0.035, pad=0.02)
        cb.set_label("personas por km²", fontsize=8)
        cb.ax.tick_params(labelsize=7)
    return fig


def tabla_expuesta(carpeta: str | Path) -> pd.DataFrame:
    """Población expuesta por región y variable (de ``4_cruce/resumen_expuesta.csv``), en formato ancho."""
    r = pd.read_csv(Path(carpeta) / "4_cruce" / "resumen_expuesta.csv")
    return r.pivot_table(index="region", columns="variable", values="valor", aggfunc="sum")
