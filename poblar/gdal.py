"""Llamadas a las herramientas de línea de comandos de GDAL.

Se usan ``gdalwarp`` y ``gdal_rasterize`` (las mismas que el método original)
para que la grilla y la rasterización sean idénticas a las del PRAIS 2026.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from poblar.trazabilidad import log


class ErrorGDAL(RuntimeError):
    """Una herramienta de GDAL terminó con error o no está instalada."""


def ejecutar_gdal(argumentos: list[str]) -> str:
    """Ejecuta una herramienta de GDAL y devuelve su salida estándar.

    Raises:
        ErrorGDAL: Si la herramienta no está instalada o devuelve un código de error.
    """
    herramienta = argumentos[0]
    if shutil.which(herramienta) is None:
        raise ErrorGDAL(
            f"No se encontró '{herramienta}'. Instalar GDAL (en Colab o Ubuntu: "
            f"'apt-get install -y gdal-bin')."
        )
    log.info("GDAL: %s", " ".join(argumentos))
    r = subprocess.run(argumentos, capture_output=True, text=True, check=False)
    if r.returncode != 0:
        raise ErrorGDAL(f"{herramienta} terminó con código {r.returncode}:\n{r.stderr.strip()}")
    return r.stdout


def version_gdal_cli() -> str:
    """Versión de las herramientas de línea de comandos de GDAL."""
    if shutil.which("gdalinfo") is None:
        return "no instalada"
    r = subprocess.run(["gdalinfo", "--version"], capture_output=True, text=True, check=False)
    return r.stdout.strip()


def opciones_creacion(compresion: str = "LZW") -> list[str]:
    return ["-co", f"COMPRESS={compresion}", "-co", "TILED=YES", "-co", "BIGTIFF=IF_SAFER"]


def existe_y_no_vacio(ruta: Path) -> bool:
    return ruta.exists() and ruta.stat().st_size > 0
