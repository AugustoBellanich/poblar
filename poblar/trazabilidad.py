"""Carpeta de ejecución, registro (log), balance por etapa, controles y manifiesto."""

from __future__ import annotations

import csv
import hashlib
import json
import logging
import platform
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import Any

import yaml

log = logging.getLogger("poblar")

PAQUETES_REGISTRADOS = [
    "poblar", "geopandas", "shapely", "pyproj", "pyogrio", "rasterio",
    "numpy", "pandas", "pyarrow", "openpyxl", "PyYAML",
]
BLOQUE_HASH = 1 << 24  # 16 MB


def version_codigo() -> str:
    """Commit de git del código de poblar en uso, o 'desconocido' si no es un clon."""
    raiz = Path(__file__).resolve().parent.parent
    try:
        r = subprocess.run(["git", "-C", str(raiz), "rev-parse", "HEAD"],
                           capture_output=True, text=True, timeout=10, check=True)
        sucio = subprocess.run(["git", "-C", str(raiz), "status", "--porcelain", "--", "poblar"],
                               capture_output=True, text=True, timeout=10, check=False).stdout.strip()
        return r.stdout.strip() + (" (con cambios locales)" if sucio else "")
    except (OSError, subprocess.SubprocessError):
        return "desconocido"


class ControlFallido(RuntimeError):
    """Un control bloqueante no se cumplió con el modo 'detener'.

    Attributes:
        carpeta: Carpeta de la ejecución detenida, con sus controles y balance.
    """

    def __init__(self, mensaje: str, carpeta: Path | None = None) -> None:
        super().__init__(mensaje)
        self.carpeta = carpeta


def sha256(ruta: str | Path) -> str:
    """sha256 de un archivo, leído por bloques (sirve para rasters grandes)."""
    h = hashlib.sha256()
    with Path(ruta).open("rb") as f:
        while bloque := f.read(BLOQUE_HASH):
            h.update(bloque)
    return h.hexdigest()


@dataclass
class Control:
    """Resultado de un control. Si es bloqueante y falla con el modo 'detener', la ejecución se detiene."""

    etapa: str
    nombre: str
    ok: bool
    detalle: str
    valor: float | int | str | None = None
    esperado: float | int | str | None = None
    bloqueante: bool = True


@dataclass
class Ejecucion:
    """Estado de una ejecución: carpeta, configuración, controles y balance."""

    carpeta: Path
    cfg: dict[str, Any]
    controles: list[Control] = field(default_factory=list)
    registros_balance: list[dict[str, Any]] = field(default_factory=list)

    # ------------------------------------------------------------ creación
    @classmethod
    def crear(cls, cfg: dict[str, Any], salida: str | Path) -> Ejecucion:
        """Crea ``<salida>/<nombre>/``, copia la configuración y prepara el registro."""
        carpeta = Path(salida) / str(cfg["nombre"])
        carpeta.mkdir(parents=True, exist_ok=True)
        ejecucion = cls(carpeta=carpeta, cfg=cfg)
        ejecucion._configurar_log()
        cfg_sin_meta = {k: v for k, v in cfg.items() if k != "_meta"}
        (carpeta / "config.yaml").write_text(
            yaml.safe_dump(cfg_sin_meta, allow_unicode=True, sort_keys=False), encoding="utf-8"
        )
        shutil.copy2(cfg["_meta"]["config"], carpeta / "config_original.yaml")
        ejecucion._escribir_entorno()
        log.info("Ejecución '%s' en %s", cfg["nombre"], carpeta)
        return ejecucion

    def _configurar_log(self) -> None:
        log.setLevel(logging.INFO)
        for h in list(log.handlers):
            log.removeHandler(h)
        fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S")
        fh = logging.FileHandler(self.carpeta / "pipeline.log", encoding="utf-8")
        fh.setFormatter(fmt)
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(fmt)
        log.addHandler(fh)
        log.addHandler(sh)
        log.propagate = False

    def _escribir_entorno(self) -> None:
        lineas = [
            f"fecha_utc: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
            f"python: {sys.version.split()[0]}",
            f"plataforma: {platform.platform()}",
        ]
        for p in PAQUETES_REGISTRADOS:
            try:
                lineas.append(f"{p}: {metadata.version(p)}")
            except metadata.PackageNotFoundError:
                lineas.append(f"{p}: no instalado")
        try:
            import rasterio

            lineas.append(f"gdal: {rasterio.__gdal_version__}")
        except ImportError:
            pass
        lineas.append(f"poblar_commit: {version_codigo()}")
        (self.carpeta / "entorno.txt").write_text("\n".join(lineas) + "\n", encoding="utf-8")

    # ------------------------------------------------------------ rutas
    def dir_etapa(self, nombre: str) -> Path:
        d = self.carpeta / nombre
        d.mkdir(parents=True, exist_ok=True)
        return d

    # ------------------------------------------------------------ registro
    def balance(self, etapa: str, paso: str, **valores: Any) -> None:
        """Una línea del balance: qué entra y qué sale de cada paso."""
        fila = {"etapa": etapa, "paso": paso, **valores}
        self.registros_balance.append(fila)
        log.info("[%s] %s: %s", etapa, paso, ", ".join(f"{k}={v}" for k, v in valores.items()))

    def controlar(self, v: Control) -> Control:
        """Registra un control; con el modo 'detener', detiene la ejecución si es bloqueante y falla."""
        self.controles.append(v)
        estado = "OK" if v.ok else ("FALLA" if v.bloqueante else "ADVERTENCIA")
        log.info("[%s] %s %s — %s", v.etapa, estado, v.nombre, v.detalle)
        modo = (self.cfg.get("controles") or {}).get("modo", "detener")
        if not v.ok and v.bloqueante and modo == "detener":
            self.guardar_registros()
            raise ControlFallido(f"[{v.etapa}] {v.nombre}: {v.detalle}", carpeta=self.carpeta)
        return v

    def guardar_registros(self) -> None:
        """Escribe balance.csv y controles.csv/json (al terminar o al detenerse)."""
        if self.registros_balance:
            claves: list[str] = []
            for fila in self.registros_balance:
                claves += [k for k in fila if k not in claves]
            with (self.carpeta / "balance.csv").open("w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=claves)
                w.writeheader()
                w.writerows(self.registros_balance)
        filas = [asdict(v) for v in self.controles]
        with (self.carpeta / "controles.json").open("w", encoding="utf-8") as f:
            json.dump(filas, f, ensure_ascii=False, indent=2, default=str)
        if filas:
            with (self.carpeta / "controles.csv").open("w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=list(filas[0]))
                w.writeheader()
                w.writerows(filas)

    def manifiesto(self) -> Path:
        """sha256 y tamaño de todo lo que produjo la ejecución."""
        ruta = self.carpeta / "manifiesto.csv"
        excluir = {"manifiesto.csv", "pipeline.log"}
        filas = []
        for p in sorted(self.carpeta.rglob("*")):
            if p.is_file() and p.name not in excluir:
                filas.append({
                    "archivo": p.relative_to(self.carpeta).as_posix(),
                    "bytes": p.stat().st_size,
                    "sha256": sha256(p),
                })
        with ruta.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["archivo", "bytes", "sha256"])
            w.writeheader()
            w.writerows(filas)
        return ruta
