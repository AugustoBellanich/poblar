"""Informe de una ejecución en HTML: controles, cifras principales, mapas de vista rápida y tablas.

Se genera al terminar cada ejecución (``<carpeta>/informe.html``) y también se puede
generar a mano con :func:`generar`. Es un solo archivo, con las imágenes incluidas,
que se abre en cualquier navegador y se puede compartir.
"""

from __future__ import annotations

import base64
import html
import io
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from poblar.trazabilidad import log

ETIQUETAS_VARIABLES = {
    "poblacion_dasimetrica": "Población", "poblacion": "Población", "nbi": "Con NBI",
    "agua_red": "Con agua de red", "agua_sin_red": "Sin agua de red", "pobla_mujer": "Mujeres",
    "pobla_varon": "Varones", "nbi_mujer": "Mujeres con NBI", "nbi_varon": "Varones con NBI",
    "agua_red_mujer": "Mujeres con agua de red", "agua_red_varon": "Varones con agua de red",
}
GRUPOS = {"total": "Total", "mujer": "Mujeres", "varon": "Varones", "urbano": "Urbano", "rural": "Rural"}
FORMULAS = {
    "incidencia": "incidencia: cantidad del grupo ÷ población del mismo grupo, en el mismo ámbito",
    "exposicion": "exposición: cantidad en tierras degradadas ÷ cantidad en el país, mismo grupo",
    "composicion": "composición: grupo ÷ total, en el mismo ámbito",
}

CSS = """
:root{--fondo:#fbfaf7;--papel:#fff;--texto:#1f1d1a;--suave:#6b665e;--linea:#e6e1d8;--ok:#2e7d4f;
--adv:#b7791f;--falla:#c0392b;--acento:#6a4c93;--tabla:#f4f1ea}
@media (prefers-color-scheme:dark){:root{--fondo:#16151a;--papel:#1e1d23;--texto:#ecebe7;--suave:#a9a5a0;
--linea:#33313a;--tabla:#25242b;--acento:#b9a3e3}}
*{box-sizing:border-box}body{margin:0;background:var(--fondo);color:var(--texto);
font:15px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
main{max-width:1100px;margin:0 auto;padding:28px 16px 60px}
h1{font-size:1.6rem;margin:0 0 4px}h2{font-size:1.15rem;margin:36px 0 10px;padding-bottom:6px;
border-bottom:1px solid var(--linea)}h3{font-size:1rem;margin:18px 0 8px}
.sub{color:var(--suave);margin:0}.grilla{display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(180px,1fr))}
.tarjeta{background:var(--papel);border:1px solid var(--linea);border-radius:10px;padding:14px 16px}
.tarjeta .n{font-size:1.55rem;font-weight:650;font-variant-numeric:tabular-nums}
.tarjeta .l{color:var(--suave);font-size:.85rem}.ok{color:var(--ok)}.adv{color:var(--adv)}.falla{color:var(--falla)}
table{border-collapse:collapse;width:100%;font-size:.85rem;font-variant-numeric:tabular-nums;background:var(--papel)}
th,td{padding:5px 8px;border-bottom:1px solid var(--linea);text-align:right;vertical-align:top}
th:first-child,td:first-child,td.t,th.t{text-align:left}th{background:var(--tabla);font-weight:600}
.envoltura{overflow-x:auto;border:1px solid var(--linea);border-radius:8px}
.mapas{display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));align-items:start}
.mapas.chicos{grid-template-columns:repeat(auto-fit,minmax(220px,1fr))}
figure{margin:0;background:#fff;border:1px solid var(--linea);border-radius:10px;padding:8px}
figure img{width:100%;height:auto;max-height:520px;object-fit:contain;display:block}
.mapas.chicos figure img{max-height:300px}figcaption{color:#555;font-size:.8rem;padding:4px 4px 0}
.nota{color:var(--suave);font-size:.85rem}.etiqueta{display:inline-block;padding:1px 8px;border-radius:99px;
font-size:.75rem;font-weight:600;border:1px solid currentColor}code{font-size:.85em}
"""


def _num(x: Any, dec: int = 0) -> str:
    """Número con formato argentino (miles con punto, decimales con coma)."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return html.escape(str(x))
    if pd.isna(v):
        return "—"
    s = f"{v:,.{dec}f}"
    return s.replace(",", "§").replace(".", ",").replace("§", ".")


def _png(fig) -> str:
    import matplotlib.pyplot as plt

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _figura(src: str, pie: str) -> str:
    return f'<figure><img src="{src}" alt="{html.escape(pie)}"><figcaption>{html.escape(pie)}</figcaption></figure>'


def _tabla_html(df: pd.DataFrame, formatos: dict[str, int] | None = None, texto: tuple[str, ...] = ()) -> str:
    formatos = formatos or {}
    cab = "".join(f'<th class="t">{html.escape(str(c))}</th>' if c in texto else f"<th>{html.escape(str(c))}</th>"
                  for c in df.columns)
    filas = []
    for _, f in df.iterrows():
        celdas = []
        for c in df.columns:
            v = f[c]
            if c in texto or not isinstance(v, (int, float)) or isinstance(v, bool):
                celdas.append(f'<td class="t">{html.escape(str(v))}</td>')
            else:
                celdas.append(f"<td>{_num(v, formatos.get(c, 0))}</td>")
        filas.append("<tr>" + "".join(celdas) + "</tr>")
    return f'<div class="envoltura"><table><thead><tr>{cab}</tr></thead><tbody>{"".join(filas)}</tbody></table></div>'


def _leer(ruta: Path) -> pd.DataFrame | None:
    return pd.read_csv(ruta) if ruta.exists() else None


def _seccion_controles(c: Path) -> str:
    ctrl = _leer(c / "controles.csv")
    if ctrl is None:
        return "<p class='nota'>Sin controles registrados.</p>"
    ok = ctrl["ok"].astype(str).str.lower() == "true"
    bloq = ctrl["bloqueante"].astype(str).str.lower() == "true"
    n_ok, n_adv, n_falla = int(ok.sum()), int((~ok & ~bloq).sum()), int((~ok & bloq).sum())
    tarjetas = (f'<div class="grilla"><div class="tarjeta"><div class="n ok">{n_ok}</div><div class="l">controles cumplidos</div></div>'
                f'<div class="tarjeta"><div class="n adv">{n_adv}</div><div class="l">advertencias</div></div>'
                f'<div class="tarjeta"><div class="n falla">{n_falla}</div><div class="l">fallas bloqueantes</div></div></div>')
    por_etapa = (ctrl.assign(ok=ok).groupby("etapa")["ok"].agg(cumplidos="sum", total="size").reset_index())
    detalle = ""
    if (~ok).any():
        no = ctrl[~ok].assign(tipo=["falla" if b else "advertencia" for b in bloq[~ok]])
        detalle = "<h3>Controles no cumplidos</h3>" + _tabla_html(
            no[["etapa", "nombre", "detalle", "tipo"]].rename(columns=str.capitalize), texto=("Detalle",))
    return tarjetas + "<h3>Por etapa</h3>" + _tabla_html(por_etapa.rename(columns=str.capitalize)) + detalle


def _seccion_cifras(c: Path, cfg: dict[str, Any]) -> str:
    out = []
    ind = _leer(c / "6_tablas" / "indicadores.csv")
    res = _leer(c / "4_cruce" / "resumen_expuesta.csv")
    if res is not None:
        nac = res[res["region"] == "NACIONAL"].set_index("variable")["valor"]
        pob_pais = None
        if ind is not None:
            sel = ind[(ind.ambito == "pais") & (ind.region == "NACIONAL") & (ind.variable == "poblacion")
                      & (ind.grupo == "total")]
            pob_pais = float(sel["n"].iloc[0]) if len(sel) else None
        tarjetas = []
        for var in ("poblacion_dasimetrica", "nbi", "agua_red", "agua_sin_red"):
            if var in nac:
                extra = ""
                if var == "poblacion_dasimetrica" and pob_pais:
                    extra = f" · {_num(100 * nac[var] / pob_pais, 2)} % del país"
                tarjetas.append(f'<div class="tarjeta"><div class="n">{_num(nac[var])}</div>'
                                f'<div class="l">{ETIQUETAS_VARIABLES.get(var, var)} en tierras degradadas{extra}</div></div>')
        out.append(f'<div class="grilla">{"".join(tarjetas)}</div>')
        ancho = res.pivot_table(index="region", columns="variable", values="valor", aggfunc="sum")
        orden = [v for v in ("poblacion_dasimetrica", "pobla_mujer", "pobla_varon", "nbi", "agua_red", "agua_sin_red")
                 if v in ancho.columns]
        ancho = ancho[orden].rename(columns=ETIQUETAS_VARIABLES)
        ancho = pd.concat([ancho.drop(index="NACIONAL", errors="ignore"), ancho.loc[["NACIONAL"]]
                           if "NACIONAL" in ancho.index else None])
        ancho.index = [("Nacional" if i == "NACIONAL" else i) for i in ancho.index]
        out.append("<h3>Por región (personas en tierras degradadas)</h3>"
                   + _tabla_html(ancho.reset_index().rename(columns={"index": "Región"}), texto=("Región",)))
    if not out:
        out.append("<p class='nota'>La ejecución no incluye el cruce con tierras degradadas.</p>")
    pub = _leer(c / "5_publicacion" / "publicacion.csv")
    if pub is not None:
        out.append("<h3>Capas publicadas</h3>" + _tabla_html(
            pub[["archivo", "suma_origen", "suma_publicada", "diferencia", "diferencia_pct"]].rename(columns={
                "archivo": "Archivo", "suma_origen": "Suma de origen", "suma_publicada": "Suma publicada",
                "diferencia": "Diferencia", "diferencia_pct": "Diferencia (%)"}),
            formatos={"Diferencia": 1, "Diferencia (%)": 5}, texto=("Archivo",)))
    return "".join(out)


def _seccion_mapas(c: Path, cfg: dict[str, Any]) -> str:
    import matplotlib
    import matplotlib.pyplot as plt

    from poblar import vista

    matplotlib.use("Agg")
    disponibles = vista.productos(c)
    figs = []
    for prod, pie in (("poblacion", "Población (personas por km², escala logarítmica)"),
                      ("degradacion", "Tierras degradadas"),
                      ("expuesta", "Población en tierras degradadas (personas por km²)")):
        if prod in disponibles:
            try:
                figs.append(_figura(_png(vista.mapa(c, prod)), pie))
            except Exception as e:  # noqa: BLE001 — una vista que falla no impide el informe
                log.warning("Vista '%s' no generada: %s", prod, e)
    regiones = []
    if "expuesta" in disponibles:
        campo = cfg["region"]["campo"]
        nombres = pd.read_parquet(c / "1_radios" / "radios.parquet", columns=[campo])[campo].unique()
        for reg in sorted(n for n in nombres if n != cfg["region"].get("etiqueta_fuera")):
            try:
                fig, ax = plt.subplots(figsize=(5, 5))
                vista.mapa(c, "expuesta", region=reg, ax=ax, ancho_px=600, titulo="")
                regiones.append(_figura(_png(fig), reg))
            except Exception as e:  # noqa: BLE001
                log.warning("Vista de la región '%s' no generada: %s", reg, e)
    html_ = f'<div class="mapas">{"".join(figs)}</div>' if figs else "<p class='nota'>Sin rasters para mostrar.</p>"
    if regiones:
        html_ += "<h3>Población en tierras degradadas, por región</h3>" + f'<div class="mapas chicos">{"".join(regiones)}</div>'
    return html_ + ("<p class='nota'>Vistas rápidas a resolución reducida, para revisar. El dato completo está en "
                    "los rasters de la ejecución.</p>")


def _seccion_tablas(c: Path) -> str:
    d = c / "6_tablas"
    if not d.exists():
        return "<p class='nota'>La ejecución no incluye la etapa de tablas.</p>"
    out = []
    for ruta in sorted(d.glob("*.csv")):
        if ruta.stem == "indicadores":
            continue
        t = pd.read_csv(ruta)
        formula = t["formula"].iloc[0] if "formula" in t.columns and len(t) else ""
        t = t.drop(columns="formula", errors="ignore")
        t["grupo"] = t["grupo"].map(GRUPOS).fillna(t["grupo"])
        t = t.rename(columns={"region": "Región", "grupo": "Grupo", "n_pais": "País (n)", "pct_pais": "País (%)",
                              "n_td": "TD (n)", "pct_td": "TD (%)"})
        if (t["Región"] == "NACIONAL").all():
            t = t.drop(columns="Región")
        else:
            t["Región"] = t["Región"].replace("NACIONAL", "Nacional")
        out.append(f"<h3>{html.escape(ruta.stem)}</h3><p class='nota'>Porcentaje: {html.escape(FORMULAS.get(formula, formula))}.</p>"
                   + _tabla_html(t, formatos={"País (%)": 2, "TD (%)": 2}, texto=("Región", "Grupo")))
    return "".join(out)


def _seccion_ejecucion(c: Path, cfg: dict[str, Any]) -> str:
    entorno = {}
    if (c / "entorno.txt").exists():
        for linea in (c / "entorno.txt").read_text(encoding="utf-8").splitlines():
            if ": " in linea:
                k, v = linea.split(": ", 1)
                entorno[k] = v
    ins = _leer(c / "0_insumos" / "insumos.csv")
    filas = ""
    if ins is not None:
        ins = ins.assign(archivo=ins["ruta"].map(lambda r: Path(str(r)).name),
                         sha256=ins["sha256"].astype(str).str[:12] + "…")
        filas = _tabla_html(ins[["insumo", "archivo", "sha256"]].rename(columns=str.capitalize),
                            texto=("Insumo", "Archivo", "Sha256"))
    datos = [("poblar", entorno.get("poblar_commit", "—")), ("Python", entorno.get("python", "—")),
             ("GDAL", entorno.get("gdal", "—")), ("Fecha (UTC)", entorno.get("fecha_utc", "—"))]
    tabla = "".join(f"<tr><td class='t'>{k}</td><td class='t'>{html.escape(v)}</td></tr>" for k, v in datos)
    return (f'<div class="envoltura"><table><tbody>{tabla}</tbody></table></div><h3>Insumos</h3>{filas}'
            "<p class='nota'>Configuración completa en <code>config.yaml</code>; huellas de todos los productos en "
            "<code>manifiesto.csv</code>.</p>")


def generar(carpeta: str | Path, mapas: bool = True) -> Path:
    """Escribe ``informe.html`` en la carpeta de la ejecución y devuelve su ruta.

    Args:
        carpeta: Carpeta de la ejecución.
        mapas: Incluir los mapas de vista rápida (requieren leer los rasters; unos segundos a minutos).
    """
    import yaml

    c = Path(carpeta)
    cfg = yaml.safe_load((c / "config.yaml").read_text(encoding="utf-8"))
    secciones = [("Controles", _seccion_controles(c)), ("Resultados", _seccion_cifras(c, cfg))]
    if mapas:
        secciones.append(("Mapas", _seccion_mapas(c, cfg)))
    secciones += [("Tablas de indicadores", _seccion_tablas(c)), ("Ejecución", _seccion_ejecucion(c, cfg))]
    cuerpo = "".join(f"<h2>{t}</h2>{h}" for t, h in secciones)
    titulo = html.escape(str(cfg.get("nombre", c.name)))
    doc = (f'<!doctype html><html lang="es"><head><meta charset="utf-8">'
           f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>Informe {titulo}</title>'
           f"<style>{CSS}</style></head><body><main><h1>{titulo}</h1>"
           f'<p class="sub">Año {cfg.get("anio_censo", "")} · informe generado el '
           f'{datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M")} UTC por poblar</p>{cuerpo}</main></body></html>')
    ruta = c / "informe.html"
    ruta.write_text(doc, encoding="utf-8")
    log.info("Informe: %s", ruta)
    return ruta
