"""Orquestador: lee la configuración, crea la carpeta de la ejecución y ejecuta las etapas."""

from __future__ import annotations

from pathlib import Path

from poblar import config as cfgmod
from poblar.trazabilidad import Ejecucion, log

ETAPAS_DISPONIBLES = ["insumos", "radios"]  # se suman grilla, dasimetria, cruce_td, publicacion


def ejecutar(
    ruta_config: str | Path,
    insumos: str | Path | None = None,
    salida: str | Path = "ejecuciones",
    etapas: list[str] | str = "todas",
) -> Ejecucion:
    """Ejecuta las etapas pedidas y deja todo en ``<salida>/<nombre>/``.

    Args:
        ruta_config: Archivo YAML de configuración.
        insumos: Carpeta base de los insumos (las rutas de la configuración son relativas a ella).
        salida: Carpeta donde se crean las ejecuciones.
        etapas: ``"todas"`` o lista con nombres de :data:`ETAPAS_DISPONIBLES`.

    Returns:
        La ejecución, con sus controles y su balance.
    """
    lista = ETAPAS_DISPONIBLES if etapas == "todas" else list(etapas)
    desconocidas = sorted(set(lista) - set(ETAPAS_DISPONIBLES))
    if desconocidas:
        raise ValueError(f"Etapas desconocidas: {desconocidas}. Disponibles: {ETAPAS_DISPONIBLES}")

    cfg = cfgmod.cargar(ruta_config, insumos)
    cfgmod.verificar(cfg, [e for e in lista if e in cfgmod.OBLIGATORIAS])
    ejecucion = Ejecucion.crear(cfg, salida)
    try:
        if "insumos" in lista:
            from poblar import insumos as etapa0

            etapa0.registrar(ejecucion)
        if "radios" in lista:
            from poblar import radios as etapa1

            etapa1.construir(ejecucion)
    finally:
        ejecucion.guardar_registros()
        ejecucion.manifiesto()
    fallas = [v for v in ejecucion.controles if not v.ok]
    log.info("Ejecución terminada: %d controles, %d con advertencia o falla", len(ejecucion.controles), len(fallas))
    return ejecucion
