"""Orquestador: lee la configuración, crea la carpeta de la ejecución y ejecuta las etapas."""

from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path

from poblar import config as cfgmod
from poblar.trazabilidad import ControlFallido, Ejecucion, log, sincronizar

ETAPAS_DISPONIBLES = ["insumos", "radios", "grilla", "dasimetria", "cruce", "publicacion", "tablas"]


DIRECTORIOS = {"radios": "1_radios", "grilla": "2_grilla", "dasimetria": "3_dasimetria",
               "cruce": "4_cruce", "publicacion": "5_publicacion", "tablas": "6_tablas"}
PREVIA = {"grilla": "radios", "dasimetria": "grilla", "cruce": "dasimetria",
          "publicacion": "dasimetria", "tablas": "cruce"}


# Para reutilizar una etapa de otra ejecución: secciones del método de las que depende y etapas previas
SECCIONES = {"radios": ["radios", "region"], "grilla": ["grilla_trabajo", "cobertura"],
             "dasimetria": ["dasimetria"], "cruce": ["cruce"], "publicacion": ["publicacion"], "tablas": ["tablas"]}
DEPENDE_DE = {"radios": [], "grilla": ["radios"], "dasimetria": ["radios", "grilla"], "cruce": ["dasimetria"],
              "publicacion": ["dasimetria"], "tablas": ["radios", "cruce"]}


def etapas_afectadas(claves: list[str] | set[str]) -> list[str]:
    """Etapas que hay que recalcular si cambian estas claves del método (y las que dependen de ellas)."""
    secciones = {c.split(".")[0] for c in claves}
    afectadas: list[str] = []
    for etapa in ETAPAS_DISPONIBLES[1:]:
        if secciones & set(SECCIONES[etapa]) or any(d in afectadas for d in DEPENDE_DE[etapa]):
            afectadas.append(etapa)
    return afectadas


# Nombres de rol de versiones anteriores
ROLES_ANTERIORES = {"mapbiomas": "cobertura"}
# Claves que nombran archivos o tienen un valor por defecto: no cambian resultados
_NEUTRAS = {"insumo", "grilla_referencia"}


def _huellas(carpeta: Path) -> dict[str, str]:
    ruta = carpeta / "0_insumos" / "insumos.json"
    if not ruta.exists():
        return {}
    return {ROLES_ANTERIORES.get(i["insumo"], i["insumo"]): i.get("sha256")
            for i in json.loads(ruta.read_text(encoding="utf-8"))}


def _seccion(cfg: dict, sec: str) -> object:
    """Sección del método sin las claves que no cambian resultados (para comparar)."""
    v = cfg.get(sec)
    if not isinstance(v, dict):
        return v
    v = {k: x for k, x in v.items() if k not in _NEUTRAS}
    if sec == "cruce" and v.get("banda", 1) == 1:
        v.pop("banda", None)
    return v


def etapas_reutilizables(cfg: dict, huellas: dict[str, str], base: Path) -> list[str]:
    """Etapas de ``base`` que darían lo mismo con esta configuración: mismos criterios, mismos
    insumos (sha256) y mismas etapas de las que dependen."""
    cfg_base = cfgmod._leer_yaml(base / "config.yaml")
    huellas_base = _huellas(base)
    if cfg_base.get("anio_censo") != cfg.get("anio_censo"):
        return []
    ok: list[str] = []
    for etapa in ETAPAS_DISPONIBLES[1:]:
        if not (base / DIRECTORIOS[etapa]).exists():
            continue
        iguales = all(_seccion(cfg, sec) == _seccion(cfg_base, sec) for sec in SECCIONES[etapa])
        roles = cfgmod.roles_necesarios(cfg, etapa)
        mismos_insumos = all(huellas.get(r) and huellas.get(r) == huellas_base.get(r) for r in roles)
        if iguales and mismos_insumos and all(d in ok for d in DEPENDE_DE[etapa]):
            ok.append(etapa)
    return ok


def _reutilizar(ejecucion: Ejecucion, base: Path, lista: list[str]) -> list[str]:
    """Copia de ``base`` las etapas reutilizables y las quita de la lista. Devuelve la lista nueva."""
    candidatas = [e for e in etapas_reutilizables(ejecucion.cfg, _huellas(ejecucion.carpeta), base)
                  if e in lista and not (ejecucion.carpeta / DIRECTORIOS[e]).exists()]
    if not candidatas:
        log.info("No hay etapas para reutilizar de %s (cambian los criterios o los insumos)", base)
        return lista
    dirs = {DIRECTORIOS[e] for e in candidatas}
    for e in candidatas:
        log.info("Reutilizando la etapa '%s' de %s", e, base)
        shutil.copytree(base / DIRECTORIOS[e], ejecucion.carpeta / DIRECTORIOS[e], dirs_exist_ok=True)
    cj = base / "controles.json"
    if cj.exists():
        ejecucion.previos_controles += [f for f in json.loads(cj.read_text(encoding="utf-8"))
                                        if f.get("etapa") in dirs]
    bc = base / "balance.csv"
    if bc.exists():
        with bc.open(encoding="utf-8") as f:
            ejecucion.previos_balance += [r for r in list(csv.reader(f))[1:] if r and r[0] in dirs]
    (ejecucion.carpeta / "reutilizado.json").write_text(
        json.dumps({"base": str(base), "etapas": candidatas}, ensure_ascii=False, indent=2), encoding="utf-8")
    return [e for e in lista if e not in candidatas]


def _es_config_completa(ruta: Path) -> bool:
    """Una configuración en un solo archivo (método + año + insumos con rutas)."""
    cfg = cfgmod._leer_yaml(ruta)
    return "anio_censo" in cfg


def _elegir_etapas(cfg: dict, pedidas: list[str] | str, previa: Path) -> list[str]:
    """Etapas a correr. Con "todas", las que tienen sus insumos y lo que necesitan de la etapa anterior."""
    dados = set(cfg.get("insumos") or {})
    if pedidas != "todas":
        lista = list(pedidas)
        faltan = {e: [r for r in cfgmod.roles_necesarios(cfg, e) if r not in dados] for e in lista}
        faltan = {e: f for e, f in faltan.items() if f}
        if faltan:
            detalle = "; ".join(f"'{e}' necesita {f}" for e, f in faltan.items())
            raise cfgmod.ErrorConfig(f"Faltan insumos: {detalle}. Indicarlos en insumos=.")
        return lista
    lista = ["insumos"]
    for etapa in ETAPAS_DISPONIBLES[1:]:
        sin_definir = [c for c in cfgmod.OBLIGATORIAS.get(etapa, []) if cfgmod.obtener(cfg, c, None) is None]
        if sin_definir:
            log.info("Se omite la etapa '%s': el método no la define (falta %s)", etapa, sin_definir[0])
            continue
        tiene_insumos = all(r in dados for r in cfgmod.roles_necesarios(cfg, etapa))
        antes = PREVIA.get(etapa)
        tiene_previa = antes is None or antes in lista or (previa / DIRECTORIOS[antes]).exists()
        if tiene_insumos and tiene_previa:
            lista.append(etapa)
        else:
            motivo = ("faltan insumos " + str([r for r in cfgmod.roles_necesarios(cfg, etapa) if r not in dados])
                      if not tiene_insumos else f"falta la etapa '{antes}'")
            log.info("Se omite la etapa '%s': %s", etapa, motivo)
    return lista


def ejecutar(
    metodo: str | Path,
    anio: int | None = None,
    insumos: dict | str | Path | None = None,
    salida: str | Path = "ejecuciones",
    etapas: list[str] | str = "todas",
    trabajo: str | Path | None = None,
    registro: str | Path | None = None,
    nombre: str | None = None,
    base: str | Path | None = None,
) -> Ejecucion:
    """Ejecuta las etapas y deja todo en ``<salida>/<nombre>/``.

    Args:
        metodo: YAML con los criterios del método. (También acepta una configuración completa en un
            solo archivo, con ``anio_censo`` e ``insumos``; entonces ``insumos`` es su carpeta base).
        anio: Año o período de la ejecución.
        insumos: ``{rol: ruta}`` con los archivos de esta ejecución, con cualquier nombre y en
            cualquier carpeta. Roles: ``tabla_censo``, ``radios``, ``regiones``, ``cobertura``,
            ``degradacion``; se pasan solo los que necesitan las etapas a correr. Junto a la ruta se
            pueden dar datos del archivo: ``{"ruta": ..., "campo_codigo": ...}`` (radios),
            ``{"ruta": ..., "banda": ...}`` (degradación), ``capa``, ``hoja``, ``sha256``.
        salida: Carpeta donde se crean las ejecuciones.
        etapas: ``"todas"`` (las que tienen sus insumos) o lista con nombres de :data:`ETAPAS_DISPONIBLES`.
        trabajo: Carpeta local donde se procesa (opcional); lo terminado se copia a ``salida``. En
            Colab conviene ``/content/trabajo``: escribir rasters grandes directamente en Drive es lento.
        registro: YAML opcional con los datos fijos de un período (sha256 de los insumos, cifras
            esperadas). Ver ``aplicaciones/prais2026/periodos/``.
        nombre: Nombre de la ejecución (por defecto ``<aplicacion>_<anio>``).
        base: Carpeta de otra ejecución (por ejemplo, la estándar del mismo año) de la que se copian
            las etapas que darían lo mismo: mismos criterios, mismos insumos (sha256) y mismas etapas
            previas. Sirve para probar un criterio sin repetir lo que no cambia. Queda registrado en
            ``reutilizado.json``.

    Returns:
        La ejecución, con sus controles y su balance.
    """
    if etapas != "todas":
        desconocidas = sorted(set(etapas) - set(ETAPAS_DISPONIBLES))
        if desconocidas:
            raise ValueError(f"Etapas desconocidas: {desconocidas}. Disponibles: {ETAPAS_DISPONIBLES}")

    if _es_config_completa(Path(metodo)):
        cfg = cfgmod.cargar(metodo, insumos if isinstance(insumos, (str, Path)) else None)
    else:
        cfg = cfgmod.armar(metodo, anio, insumos, registro, nombre)
    lista = _elegir_etapas(cfg, etapas, Path(salida) / str(cfg["nombre"]))
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
        if base is not None and Path(base).resolve() != Path(salida, ejecucion.carpeta.name).resolve():
            lista = _reutilizar(ejecucion, Path(base), lista)
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
            ejecucion.guardar_avance()
        if "tablas" in lista:
            from poblar import tablas as etapa6

            etapa6.construir(ejecucion)
    except ControlFallido as e:
        if trabajo is not None:
            raise ControlFallido(str(e), carpeta=Path(salida) / ejecucion.carpeta.name) from e
        raise
    finally:
        ejecucion.guardar_registros()
        if cfgmod.obtener(cfg, "informe.generar", True):
            try:
                from poblar import informe

                informe.generar(ejecucion.carpeta, mapas=bool(cfgmod.obtener(cfg, "informe.mapas", True)))
            except Exception as e:  # noqa: BLE001 — el informe nunca detiene una ejecución
                log.warning("No se pudo generar el informe: %s", e)
        ejecucion.manifiesto()
        if trabajo is not None:
            destino = Path(salida) / ejecucion.carpeta.name
            log.info("Copiando la ejecución a %s", destino)
            sincronizar(ejecucion.carpeta, destino, verificar=True)
            ejecucion.carpeta = destino
    fallas = [v for v in ejecucion.controles if not v.ok]
    log.info("Ejecución terminada: %d controles, %d con advertencia o falla", len(ejecucion.controles), len(fallas))
    return ejecucion

