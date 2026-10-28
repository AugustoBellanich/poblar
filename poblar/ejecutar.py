"""Orquestador: lee la configuración, crea la carpeta de la ejecución y ejecuta las etapas."""

from __future__ import annotations

from pathlib import Path

from poblar import config as cfgmod
from poblar.trazabilidad import ControlFallido, Ejecucion, log, sincronizar

ETAPAS_DISPONIBLES = ["insumos", "radios", "grilla", "dasimetria", "cruce", "publicacion"]


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
    if trabajo is not None:
        previa = Path(salida) / str(cfg["nombre"])
        if previa.exists():  # retomar: traer lo ya generado (solo lo que falta o cambió)
            log.info("Trayendo la ejecución previa de %s", previa)
            sincronizar(previa, Path(trabajo) / previa.name)
    ejecucion = Ejecucion.crear(cfg, trabajo or salida)
    if trabajo is not None:
        ejecucion.destino = Path(salida) / ejecucion.carpeta.name
    try:
        if "insumos" in lista:
            from poblar import insumos as etapa0

            etapa0.registrar(ejecucion)
            ejecucion.guardar_avance()
        radios = None
        if "radios" in lista:
            from poblar import radios as etapa1

            radios = etapa1.construir(ejecucion)
            ejecucion.guardar_avance()
        if "grilla" in lista:
            from poblar import grilla as etapa2

            etapa2.construir(ejecucion, radios)
            ejecucion.guardar_avance()
        if "dasimetria" in lista:
            from poblar import dasimetria as etapa3

            radios = etapa3.construir(ejecucion, radios)
            ejecucion.guardar_avance()
        if "cruce" in lista:
            from poblar import cruce as etapa4

            etapa4.construir(ejecucion, radios)
            ejecucion.guardar_avance()
        if "publicacion" in lista:
            from poblar import publicacion as etapa5

            etapa5.construir(ejecucion)
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
            sincronizar(ejecucion.carpeta, destino, verificar=True)
            ejecucion.carpeta = destino
    fallas = [v for v in ejecucion.controles if not v.ok]
    log.info("Ejecución terminada: %d controles, %d con advertencia o falla", len(ejecucion.controles), len(fallas))
    return ejecucion

