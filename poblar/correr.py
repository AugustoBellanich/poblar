"""Orquestador: lee el config, crea la carpeta de corrida y ejecuta las etapas."""

from __future__ import annotations

from pathlib import Path

from poblar import config as cfgmod
from poblar.trazabilidad import Corrida, log

ETAPAS_DISPONIBLES = ["insumos", "radios"]  # se suman grilla, dasimetria, cruce_td, publicacion


def correr(
    ruta_config: str | Path,
    insumos: str | Path | None = None,
    salida: str | Path = "corridas",
    etapas: list[str] | str = "todas",
) -> Corrida:
    """Corre las etapas pedidas y deja todo en ``<salida>/<corrida>/``.

    Args:
        ruta_config: Archivo YAML de la corrida.
        insumos: Carpeta base de los insumos (las rutas del config son relativas a ella).
        salida: Carpeta donde se crean las corridas.
        etapas: ``"todas"`` o lista con nombres de :data:`ETAPAS_DISPONIBLES`.

    Returns:
        La corrida, con sus validaciones y cuentas.
    """
    lista = ETAPAS_DISPONIBLES if etapas == "todas" else list(etapas)
    desconocidas = sorted(set(lista) - set(ETAPAS_DISPONIBLES))
    if desconocidas:
        raise ValueError(f"Etapas desconocidas: {desconocidas}. Disponibles: {ETAPAS_DISPONIBLES}")

    cfg = cfgmod.cargar(ruta_config, insumos)
    cfgmod.verificar(cfg, [e for e in lista if e in cfgmod.OBLIGATORIAS])
    corrida = Corrida.crear(cfg, salida)
    try:
        if "insumos" in lista:
            from poblar import insumos as etapa0

            etapa0.registrar(corrida)
        if "radios" in lista:
            from poblar import radios as etapa1

            etapa1.construir(corrida)
    finally:
        corrida.guardar_registros()
        corrida.manifiesto()
    fallas = [v for v in corrida.validaciones if not v.ok]
    log.info("Corrida terminada: %d validaciones, %d con aviso o falla", len(corrida.validaciones), len(fallas))
    return corrida
