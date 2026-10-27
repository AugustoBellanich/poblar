"""Carpeta de corrida, log, cuentas por etapa, validaciones y manifiesto."""

from __future__ import annotations

import csv
import hashlib
import json
import logging
import platform
import shutil
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


class ValidacionFallida(RuntimeError):
    """Una validación en modo 'cortar' no se cumplió."""


def sha256(ruta: str | Path) -> str:
    """sha256 de un archivo, leído por bloques (sirve para rasters grandes)."""
    h = hashlib.sha256()
    with Path(ruta).open("rb") as f:
        while bloque := f.read(BLOQUE_HASH):
            h.update(bloque)
    return h.hexdigest()


@dataclass
class Validacion:
    """Resultado de un chequeo. ``ok`` False en modo 'cortar' frena la corrida."""

    etapa: str
    nombre: str
    ok: bool
    detalle: str
    valor: float | int | str | None = None
    esperado: float | int | str | None = None
    bloqueante: bool = True


@dataclass
class Corrida:
    """Estado de una corrida: carpeta, config, validaciones y cuentas."""

    carpeta: Path
    cfg: dict[str, Any]
    validaciones: list[Validacion] = field(default_factory=list)
    cuentas: list[dict[str, Any]] = field(default_factory=list)

    # ------------------------------------------------------------ creación
    @classmethod
    def crear(cls, cfg: dict[str, Any], salida: str | Path) -> Corrida:
        """Crea ``<salida>/<corrida>/``, copia el config y configura el log."""
        carpeta = Path(salida) / str(cfg["corrida"])
        carpeta.mkdir(parents=True, exist_ok=True)
        corrida = cls(carpeta=carpeta, cfg=cfg)
        corrida._configurar_log()
        cfg_sin_meta = {k: v for k, v in cfg.items() if k != "_meta"}
        (carpeta / "config.yaml").write_text(
            yaml.safe_dump(cfg_sin_meta, allow_unicode=True, sort_keys=False), encoding="utf-8"
        )
        shutil.copy2(cfg["_meta"]["config"], carpeta / "config_original.yaml")
        corrida._escribir_entorno()
        log.info("Corrida '%s' en %s", cfg["corrida"], carpeta)
        return corrida

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
        (self.carpeta / "entorno.txt").write_text("\n".join(lineas) + "\n", encoding="utf-8")

    # ------------------------------------------------------------ rutas
    def dir_etapa(self, nombre: str) -> Path:
        d = self.carpeta / nombre
        d.mkdir(parents=True, exist_ok=True)
        return d

    # ------------------------------------------------------------ registro
    def cuenta(self, etapa: str, paso: str, **valores: Any) -> None:
        """Una línea de cuentas: qué entra y qué sale de cada paso."""
        fila = {"etapa": etapa, "paso": paso, **valores}
        self.cuentas.append(fila)
        log.info("[%s] %s: %s", etapa, paso, ", ".join(f"{k}={v}" for k, v in valores.items()))

    def validar(self, v: Validacion) -> Validacion:
        """Registra una validación; en modo 'cortar' frena si es bloqueante y falla."""
        self.validaciones.append(v)
        estado = "OK" if v.ok else ("FALLA" if v.bloqueante else "AVISO")
        log.info("[%s] %s %s — %s", v.etapa, estado, v.nombre, v.detalle)
        modo = (self.cfg.get("validaciones") or {}).get("modo", "cortar")
        if not v.ok and v.bloqueante and modo == "cortar":
            self.guardar_registros()
            raise ValidacionFallida(f"[{v.etapa}] {v.nombre}: {v.detalle}")
        return v

    def guardar_registros(self) -> None:
        """Escribe cuentas.csv y validaciones.csv/json (se llama al terminar o al cortar)."""
        if self.cuentas:
            claves: list[str] = []
            for fila in self.cuentas:
                claves += [k for k in fila if k not in claves]
            with (self.carpeta / "cuentas.csv").open("w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=claves)
                w.writeheader()
                w.writerows(self.cuentas)
        filas = [asdict(v) for v in self.validaciones]
        with (self.carpeta / "validaciones.json").open("w", encoding="utf-8") as f:
            json.dump(filas, f, ensure_ascii=False, indent=2, default=str)
        if filas:
            with (self.carpeta / "validaciones.csv").open("w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=list(filas[0]))
                w.writeheader()
                w.writerows(filas)

    def manifiesto(self) -> Path:
        """sha256 y tamaño de todo lo que produjo la corrida."""
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
