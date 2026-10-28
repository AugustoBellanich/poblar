"""Lectura y verificación del archivo de configuración de una ejecución.

Todo lo que cambia un resultado tiene que estar en la configuración. Si falta
un criterio obligatorio, la ejecución no comienza: no hay valores implícitos en
el código.
"""

from __future__ import annotations

import copy
import logging
from pathlib import Path
from typing import Any

import yaml

log = logging.getLogger(__name__)

# Claves obligatorias por etapa. Se verifican antes de ejecutar.
OBLIGATORIAS: dict[str, list[str]] = {
    "general": ["nombre", "anio_censo"],
    "insumos": ["insumos.tabla_censo.ruta", "insumos.radios.ruta", "insumos.regiones.ruta"],
    "radios": [
        "radios.campo_codigo_mapa",
        "radios.union",
        "radios.id_desde",
        "region.campo",
        "region.umbral_vecino_km",
        "region.etiqueta_fuera",
        "region.excluir_fuera",
        "grilla_trabajo.crs",
    ],
    "grilla": [
        "grilla_trabajo.modo",
        "grilla_trabajo.extension",
        "grilla_trabajo.remuestreo_cobertura",
        "cobertura.insumo",
        "cobertura.clases",
        "cobertura.codigo_nodata",
    ],
    "dasimetria": [
        "dasimetria.campo_ambito",
        "dasimetria.ambitos",
        "dasimetria.ponderadores.normalizar_por",
        "dasimetria.ponderadores.peso_urbano",
        "dasimetria.variables",
    ],
    "cruce": [
        "cruce.insumo",
        "cruce.clases",
    ],
    "publicacion": [
        "publicacion.grilla_referencia",
        "publicacion.remuestreo",
        "publicacion.productos",
    ],
    "tablas": [
        "tablas.urbano_rural",
        "tablas.variables",
        "tablas.salidas",
        "cruce.grupo_expuesto",
    ],
}

VALORES_PERMITIDOS: dict[str, set[Any]] = {
    "radios.union": {"inner", "left"},
    "radios.id_desde": {"tabla", "mapa"},
    "radios.orden": {"area_desc", "area_desc_estable"},
    "controles.modo": {"detener", "advertir"},
    "grilla_trabajo.modo": {"gdal_auto", "fija"},
    "grilla_trabajo.extension": {"radios", "regiones"},
    "grilla_trabajo.remuestreo_cobertura": {"near", "mode"},
    "dasimetria.ponderadores.peso_urbano": {"complemento", "uno"},
}


class ErrorConfig(ValueError):
    """A la configuración le falta un criterio obligatorio o tiene un valor inválido."""


def obtener(cfg: dict[str, Any], clave: str, defecto: Any = ...) -> Any:
    """Devuelve ``cfg["a"]["b"]`` a partir de ``"a.b"``.

    Args:
        cfg: Config ya leído.
        clave: Ruta separada por puntos.
        defecto: Valor si la clave no existe. Si se omite, falta = error.

    Raises:
        ErrorConfig: Si la clave no existe y no se dio un valor por defecto.
    """
    nodo: Any = cfg
    for parte in clave.split("."):
        if not isinstance(nodo, dict) or parte not in nodo:
            if defecto is ...:
                raise ErrorConfig(f"Falta '{clave}' en la configuración.")
            return defecto
        nodo = nodo[parte]
    return nodo


def cargar(ruta: str | Path, insumos: str | Path | None = None) -> dict[str, Any]:
    """Lee el YAML, resuelve rutas de insumos y verifica claves obligatorias.

    Args:
        ruta: Archivo de configuración.
        insumos: Carpeta base de los insumos. Las rutas relativas de la configuración se
            resuelven contra ella (si no se indica, contra la carpeta del archivo de configuración).

    Returns:
        Diccionario de configuración con ``_meta`` (ruta del archivo y carpeta base).
    """
    ruta = Path(ruta)
    with ruta.open(encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    base = Path(insumos) if insumos else ruta.parent
    cfg = copy.deepcopy(cfg)
    for ins in (cfg.get("insumos") or {}).values():
        if isinstance(ins, dict) and ins.get("ruta"):
            p = Path(ins["ruta"])
            ins["ruta"] = str(p if p.is_absolute() else (base / p))
    cfg["_meta"] = {"config": str(ruta.resolve()), "base_insumos": str(base)}

    verificar(cfg)
    return cfg


def verificar(cfg: dict[str, Any], etapas: list[str] | None = None) -> None:
    """Verifica que estén todas las claves obligatorias y con valores válidos.

    Raises:
        ErrorConfig: Con la lista completa de lo que falta, no solo lo primero.
    """
    grupos = ["general", "insumos"] + (etapas or ["radios"])
    faltan = [c for g in grupos for c in OBLIGATORIAS.get(g, []) if obtener(cfg, c, None) is None]
    invalidos = []
    for clave, permitidos in VALORES_PERMITIDOS.items():
        valor = obtener(cfg, clave, None)
        if valor is not None and valor not in permitidos:
            invalidos.append(f"{clave}={valor!r} (permitidos: {sorted(permitidos)})")
    if faltan or invalidos:
        partes = []
        if faltan:
            partes.append("faltan: " + ", ".join(faltan))
        if invalidos:
            partes.append("valores inválidos: " + ", ".join(invalidos))
        raise ErrorConfig("La configuración no está completa — " + "; ".join(partes))
