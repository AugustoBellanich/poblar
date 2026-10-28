"""Ayudas para mostrar resultados en un cuaderno (Colab o Jupyter): avisos, tablas y revisión de insumos.

No hacen cálculos: presentan lo que producen las etapas.
"""

from __future__ import annotations

import html
from pathlib import Path

import pandas as pd

ROLES_DESCRIPCION = {
    "tabla_censo": "Tabla censal por radio",
    "radios": "Cartografía de radios",
    "regiones": "Regiones de reporte",
    "cobertura": "Cobertura del suelo",
    "degradacion": "Mapa de degradación",
}
ETAPAS_POR_ROL = {
    "tabla_censo": ["radios", "grilla", "dasimetria"],
    "radios": ["radios", "grilla", "dasimetria"],
    "regiones": ["radios", "grilla", "dasimetria"],
    "cobertura": ["grilla", "dasimetria", "publicacion"],
    "degradacion": ["cruce", "tablas"],
}
NOMBRES_ETAPAS = {"radios": "radios", "grilla": "grilla", "dasimetria": "población por píxel",
                  "cruce": "cruce con degradación", "publicacion": "capas publicadas", "tablas": "tablas"}

_CSS = """<style>
.pb{font:14px/1.45 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;color:inherit;max-width:900px}
.pb-caja{border-radius:8px;padding:10px 14px;margin:6px 0;border-left:4px solid;background:rgba(127,127,127,.08)}
.pb-caja b{display:block;margin-bottom:2px}.pb-info{border-color:#6a4c93}.pb-ok{border-color:#2e7d4f}
.pb-adv{border-color:#b7791f}.pb-falla{border-color:#c0392b}
.pb table{border-collapse:collapse;margin:6px 0;font-size:13px}
.pb th,.pb td{padding:4px 10px;border-bottom:1px solid rgba(127,127,127,.25);text-align:left;vertical-align:top}
.pb th{font-weight:600}.pb td.n{text-align:right;font-variant-numeric:tabular-nums}
.pb .suave{opacity:.7;font-size:12px}.pb code{font-size:12px}
</style>"""


class Html:
    """Fragmento HTML que un cuaderno muestra con ``display`` (sin depender de IPython)."""

    def __init__(self, data: str) -> None:
        self.data = data

    def _repr_html_(self) -> str:
        return self.data

    def __add__(self, otro: Html) -> Html:
        return Html(self.data + otro.data)


def _html(contenido: str) -> Html:
    return Html(_CSS + f'<div class="pb">{contenido}</div>')


def aviso(titulo: str, texto: str = "", tipo: str = "info"):
    """Recuadro con un título y un texto (``tipo``: info, ok, adv, falla). Devuelve un objeto para ``display``."""
    return _html(f'<div class="pb-caja pb-{tipo}"><b>{html.escape(titulo)}</b>{texto}</div>')


def tabla(df: pd.DataFrame, numeros: dict[str, int] | None = None, titulo: str = ""):
    """Tabla HTML con números en formato local (``numeros``: columna → decimales; por defecto, automático)."""
    from poblar.informe import _num

    if numeros is None:   # automático: enteros sin decimales, el resto con dos
        numeros = {c: (0 if pd.api.types.is_integer_dtype(df[c]) or (df[c].dropna() % 1 == 0).all() else 2)
                   for c in df.columns if pd.api.types.is_numeric_dtype(df[c]) and not pd.api.types.is_bool_dtype(df[c])}
    cab = "".join(f"<th>{html.escape(str(c))}</th>" for c in df.columns)
    filas = []
    for _, f in df.iterrows():
        celdas = []
        for c in df.columns:
            if c in numeros:
                celdas.append(f'<td class="n">{_num(f[c], numeros[c])}</td>')
            else:
                v = f[c]
                celdas.append(f"<td>{v if str(v).startswith('<') else html.escape(str(v))}</td>")
        filas.append("<tr>" + "".join(celdas) + "</tr>")
    t = f"<b>{html.escape(titulo)}</b>" if titulo else ""
    return _html(f"{t}<table><thead><tr>{cab}</tr></thead><tbody>{''.join(filas)}</tbody></table>")


def _tamano(ruta: Path) -> str:
    b = ruta.stat().st_size
    for unidad in ("B", "KB", "MB", "GB"):
        if b < 1024 or unidad == "GB":
            return f"{b:.0f} {unidad}" if unidad == "B" else f"{b:.1f} {unidad}".replace(".", ",")
        b /= 1024
    return ""


def revisar_insumos(insumos: dict[str, str], sin_usar: list[str] | tuple[str, ...] = ()) -> tuple[Html, bool]:
    """Tabla con cada insumo (encontrado, falta o no se usa) y qué se puede calcular con ellos.

    Returns:
        (objeto para ``display``, si están todos los indicados).
    """
    filas, ok = [], True
    for rol, desc in ROLES_DESCRIPCION.items():
        if rol in insumos:
            r = Path(insumos[rol])
            if r.exists():
                estado = f"✓ {_tamano(r)}"
            else:
                estado, ok = "✗ no encontrado", False
            filas.append({"Insumo": desc, "Archivo": f"<code>{html.escape(r.name)}</code>", "Estado": estado})
        else:
            filas.append({"Insumo": desc, "Archivo": "—", "Estado": "no se usa" if rol in sin_usar else "—"})
    posibles = []
    for etapa in ("radios", "grilla", "dasimetria", "cruce", "publicacion", "tablas"):
        roles = [r for r, es in ETAPAS_POR_ROL.items() if etapa in es]
        if all(r in insumos for r in roles):
            posibles.append(NOMBRES_ETAPAS[etapa])
    t = tabla(pd.DataFrame(filas))
    if not ok:
        pie = aviso("Faltan archivos", "Revisar las rutas marcadas con ✗.", "falla")
    elif posibles:
        pie = aviso("Insumos listos", "Con estos archivos se calcula: " + ", ".join(posibles) + ".", "ok")
    else:
        pie = aviso("Sin insumos suficientes", "No alcanza para ninguna etapa.", "adv")
    return t + pie, ok
