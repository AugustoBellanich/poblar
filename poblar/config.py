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
    "insumos": [],
    "radios": [
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
        "cruce.clases",
    ],
    "publicacion": [
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


# Insumos por rol. Cada etapa necesita los suyos; los demás se pueden omitir.
ROLES = ["tabla_censo", "radios", "regiones", "cobertura", "degradacion"]
# Rol por defecto de los insumos que nombra el método (se pueden cambiar en el método).
ROL_POR_CLAVE = {"cobertura.insumo": "cobertura", "cruce.insumo": "degradacion",
                 "publicacion.grilla_referencia": "cobertura"}
# Datos que dependen del archivo y no del método: se dan junto al insumo y van a esta clave.
DATOS_DEL_ARCHIVO = {("radios", "campo_codigo"): "radios.campo_codigo_mapa",
                     ("degradacion", "banda"): "cruce.banda"}


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
    grupos = ["general", "insumos"] + (["radios"] if etapas is None else list(etapas))
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


def roles_necesarios(cfg: dict[str, Any], etapa: str) -> list[str]:
    """Insumos (roles) que necesita una etapa."""
    if etapa == "radios":
        return ["tabla_censo", "radios", "regiones"]
    if etapa == "grilla":
        return [obtener(cfg, "cobertura.insumo", ROL_POR_CLAVE["cobertura.insumo"])]
    if etapa == "cruce":
        return [obtener(cfg, "cruce.insumo", ROL_POR_CLAVE["cruce.insumo"])]
    if etapa == "publicacion":
        return [obtener(cfg, "publicacion.grilla_referencia", ROL_POR_CLAVE["publicacion.grilla_referencia"])]
    return []


def _leer_yaml(ruta: str | Path) -> dict[str, Any]:
    with Path(ruta).open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def armar(
    metodo: str | Path,
    anio: int | None = None,
    insumos: dict[str, Any] | str | Path | None = None,
    registro: str | Path | None = None,
    nombre: str | None = None,
) -> dict[str, Any]:
    """Arma la configuración de una ejecución a partir del método, el año y los insumos.

    Args:
        metodo: YAML con los criterios (sin rutas ni año).
        anio: Año o período de la ejecución. Si no se indica, se toma del registro.
        insumos: ``{rol: ruta}`` o ``{rol: {ruta, campo_codigo, banda, capa, hoja, sha256}}``,
            con los roles de :data:`ROLES`; se pasan solo los necesarios. También puede ser una
            carpeta: entonces las rutas salen del registro, relativas a esa carpeta.
        registro: YAML opcional con datos fijos de un período: ``anio``, ``nombre``, sha256 y datos
            de cada insumo, ``referencia`` y ``resultados_esperados``.
        nombre: Nombre de la ejecución (por defecto ``<aplicacion>_<anio>``).

    Returns:
        La configuración completa, con ``_meta``.
    """
    cfg = copy.deepcopy(_leer_yaml(metodo))
    reg = _leer_yaml(registro) if registro else {}
    anio = anio if anio is not None else reg.get("anio")
    if anio is None:
        raise ErrorConfig("Falta el año de la ejecución (anio= o 'anio' en el registro).")

    # Insumos: datos del registro + lo que se pasa al ejecutar (esto último manda)
    declarados: dict[str, dict[str, Any]] = {k: dict(v or {}) for k, v in (reg.get("insumos") or {}).items()}
    if isinstance(insumos, (str, Path)):
        base = Path(insumos)
        for v in declarados.values():
            if v.get("ruta") and not Path(v["ruta"]).is_absolute():
                v["ruta"] = str(base / v["ruta"])
    else:
        for v in declarados.values():  # sin carpeta, las rutas del registro son solo sugerencias
            v.pop("ruta", None)
        for rol, valor in (insumos or {}).items():
            datos = {"ruta": valor} if isinstance(valor, (str, Path)) else dict(valor)
            declarados.setdefault(rol, {}).update({k: (str(v) if k == "ruta" else v) for k, v in datos.items()})
    desconocidos = sorted(set(declarados) - set(ROLES))
    if desconocidos:
        raise ErrorConfig(f"Insumos desconocidos: {desconocidos}. Roles válidos: {ROLES}")
    cfg["insumos"] = {rol: v for rol, v in declarados.items() if v.get("ruta")}
    for (rol, dato), clave in DATOS_DEL_ARCHIVO.items():
        valor = declarados.get(rol, {}).get(dato)
        if valor is not None:
            seccion, sub = clave.split(".")
            cfg.setdefault(seccion, {})[sub] = valor

    for clave in ("referencia", "resultados_esperados"):
        if clave in reg:
            cfg[clave] = reg[clave]
    cfg["anio_censo"] = int(anio)
    cfg["nombre"] = nombre or reg.get("nombre") or f"{cfg.get('aplicacion', Path(metodo).stem)}_{anio}"
    cfg["_meta"] = {"metodo": str(Path(metodo).resolve()),
                    "registro": str(Path(registro).resolve()) if registro else None}
    verificar(cfg, [])
    return cfg


def variar(metodo: str | Path, cambios: dict[str, Any], destino: str | Path,
           quitar: list[str] | tuple[str, ...] = ()) -> Path:
    """Escribe una variante del método con algunos criterios cambiados.

    Args:
        metodo: YAML del método de partida.
        cambios: ``{"clave.con.puntos": valor}``; por ejemplo ``{"cruce.ambito_reporte.Mixto": "Urbano"}``.
        destino: YAML a escribir.
        quitar: Secciones a quitar (por ejemplo ``["publicacion"]``: la etapa se omite).

    Returns:
        La ruta del YAML escrito, que empieza con la lista de cambios respecto del método de partida.
    """
    cfg = copy.deepcopy(_leer_yaml(metodo))
    for clave, valor in cambios.items():
        nodo = cfg
        *camino, ultima = clave.split(".")
        for parte in camino:
            nodo = nodo.setdefault(parte, {})
        nodo[ultima] = valor
    for sec in quitar:
        cfg.pop(sec, None)
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    encabezado = [f"# Variante de {Path(metodo).name}" if cambios else f"# Copia de {Path(metodo).name}"]
    encabezado += [f"#   {k}: {v!r}" for k, v in cambios.items()]
    encabezado += [f"#   sin la sección '{sec}'" for sec in quitar]
    destino.write_text("\n".join(encabezado) + "\n\n" + yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False),
                       encoding="utf-8")
    return destino
