"""Orquestador: lee la configuración, crea la carpeta de la ejecución y ejecuta las etapas."""

from __future__ import annotations

import shutil
from pathlib import Path

from poblar import config as cfgmod
from poblar.trazabilidad import ControlFallido, Ejecucion, log

ETAPAS_DISPONIBLES = ["insumos", "radios", "grilla", "dasimetria"]  # pendientes: cruce_td, publicacion


def ejecutar(
    ruta_config: str | Path,
    insumos: str | Path | None = None,
    salida: str | Path = "ejecuciones",
    etapas: list[str] | str = "todas",
    trabajo: str | Path | None = None,
) -> Ejecucion:
    """Ejecuta las etapas pedidas y deja todo en ``<salida>/<nombre>/``.

    Args:
        ruta_config: Archivo YAML de configuración.
        insumos: Carpeta base de los insumos (las rutas de la configuración son relativas a ella).
        salida: Carpeta donde se crean las ejecuciones.
        etapas: ``"todas"`` o lista con nombres de :data:`ETAPAS_DISPONIBLES`.
        trabajo: Carpeta local donde se procesa (opcional). Al terminar, con o sin error, la
            ejecución completa se copia a ``salida``. En Colab conviene un disco local
            (``/content/trabajo``): escribir rasters grandes por bloques directamente en Drive es lento.

    Returns:
        La ejecución, con sus controles y su balance.
    """
    lista = ETAPAS_DISPONIBLES if etapas == "todas" else list(etapas)
    desconocidas = sorted(set(lista) - set(ETAPAS_DISPONIBLES))
    if desconocidas:
        raise ValueError(f"Etapas desconocidas: {desconocidas}. Disponibles: {ETAPAS_DISPONIBLES}")

    cfg = cfgmod.cargar(ruta_config, insumos)
    cfgmod.verificar(cfg, [e for e in lista if e in cfgmod.OBLIGATORIAS])
    ejecucion = Ejecucion.crear(cfg, trabajo or salida)
    try:
        if "insumos" in lista:
            from poblar import insumos as etapa0

            etapa0.registrar(ejecucion)
        radios = None
        if "radios" in lista:
            from poblar import radios as etapa1

            radios = etapa1.construir(ejecucion)
        if "grilla" in lista:
            from poblar import grilla as etapa2

            etapa2.construir(ejecucion, radios)
        if "dasimetria" in lista:
            from poblar import dasimetria as etapa3

            etapa3.construir(ejecucion, radios)
    except ControlFallido as e:
        if trabajo is not None:
            raise ControlFallido(str(e), carpeta=Path(salida) / ejecucion.carpeta.name) from e
        raise
    finally:
        ejecucion.guardar_registros()
        ejecucion.manifiesto()
        if trabajo is not None:
            destino = Path(salida) / ejecucion.carpeta.name
            log.info("Copiando la ejecución a %s", destino)
            shutil.copytree(ejecucion.carpeta, destino, dirs_exist_ok=True)
            ejecucion.carpeta = destino
    fallas = [v for v in ejecucion.controles if not v.ok]
    log.info("Ejecución terminada: %d controles, %d con advertencia o falla", len(ejecucion.controles), len(fallas))
    return ejecucion
