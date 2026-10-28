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
header{border-bottom:1px solid var(--linea);padding-bottom:16px}
.marca{display:flex;align-items:center;gap:8px;margin-bottom:14px;font-weight:650;font-size:1.05rem;letter-spacing:-.01em}.antetitulo{color:var(--acento);font-weight:600;
font-size:.8rem;letter-spacing:.06em;text-transform:uppercase;margin:0 0 6px}
.estado{display:flex;gap:12px;align-items:center;margin-top:14px;padding:12px 16px;border-radius:10px;
background:var(--papel);border:1px solid var(--linea);border-left:5px solid currentColor}
.estado b{font-size:1rem}.estado span{color:var(--suave);font-size:.88rem}
.etapas{display:grid;gap:10px;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));align-items:start}
.etapa{background:var(--papel);border:1px solid var(--linea);border-radius:10px;padding:12px 14px}
.etapa summary{cursor:pointer;list-style:none}.etapa summary::-webkit-details-marker{display:none}
.etapa .cab{display:flex;justify-content:space-between;gap:8px;align-items:baseline}
.etapa .nombre{font-weight:600}.etapa .que{color:var(--suave);font-size:.82rem;margin:2px 0 8px}
.etapa .cuenta{font-variant-numeric:tabular-nums;font-size:.85rem;white-space:nowrap}
.barra{display:flex;height:8px;border-radius:99px;overflow:hidden;background:var(--linea)}
.barra i{display:block}.barra .b-ok{background:var(--ok)}.barra .b-adv{background:var(--adv)}.barra .b-falla{background:var(--falla)}
.etapa ul{list-style:none;margin:10px 0 0;padding:0;font-size:.84rem}
.etapa li{display:grid;grid-template-columns:18px minmax(0,1fr);gap:6px;padding:4px 0;border-top:1px solid var(--linea)}
.etapa li{min-width:0}.etapa li>span{min-width:0}
.etapa li .d{grid-column:2;color:var(--suave);font-size:.8rem;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;cursor:help}
.etapa li .d.largo{white-space:normal;overflow-wrap:anywhere}td.t{overflow-wrap:anywhere}.ver{color:var(--acento);font-size:.8rem}
details[open] .ver{display:none}
.explica{grid-column:2;background:var(--tabla);border-radius:6px;padding:6px 8px;font-size:.8rem;margin-top:4px}
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


ETAPAS = {
    "0_insumos": ("Insumos", "Que existan, con su huella sha256 y sus metadatos"),
    "1_radios": ("Radios", "Unión de la tabla censal con la cartografía y asignación de región"),
    "2_grilla": ("Grilla y cobertura", "Cobertura en la grilla de trabajo, en urbano / no urbano / no habitable"),
    "3_dasimetria": ("Mapeo dasimétrico", "Población de cada radio repartida en sus píxeles, sin perder personas"),
    "4_cruce": ("Cruce con degradación", "Población por región, ámbito y categoría de degradación"),
    "5_publicacion": ("Publicación", "Capas en la grilla de entrega, conservando el total de personas"),
    "6_tablas": ("Tablas", "Indicadores del país y de las tierras degradadas, con cierres por sexo y ámbito"),
}


def _explicacion_conservacion(c: Path, no: pd.DataFrame) -> str:
    """Explica las advertencias de conservación de variables de la etapa 3.

    Las cifras salen de la ejecución: radios y personas de ``3_dasimetria/contingencias.csv``
    (contingencia de nivel 3) y diferencias de los controles (``valor`` − ``esperado``).
    """
    sel = no[(no["etapa"] == "3_dasimetria") & no["nombre"].str.startswith("conservación de ")
             & ~no["nombre"].str.contains("población")]
    if sel.empty:
        return ""
    cont = _leer(c / "3_dasimetria" / "contingencias.csv")
    if cont is None or "tipo_asignacion" not in cont.columns:
        return ""
    n3 = cont[cont["tipo_asignacion"] == "contingencia_extrema"]
    if n3.empty:
        return ""
    dif = (pd.to_numeric(sel["valor"], errors="coerce") - pd.to_numeric(sel["esperado"], errors="coerce")).abs()
    pct = 100 * dif / pd.to_numeric(sel["esperado"], errors="coerce")
    rango = (f" En esta ejecución la mayor diferencia es de {_num(dif.max(), 0)} personas "
             f"({_num(pct.max(), 4)} %).") if dif.notna().any() else ""
    return ("Esperable: " f"{len(n3)} radios ({_num(n3['pobla_total'].sum(), 0)} personas) no tienen píxeles propios "
            "(contingencia de nivel 3). Su población se reparte en píxeles de radios vecinos y toma las tasas "
            "de esos radios: la población total se conserva, pero las variables pueden diferir algo del censo."
            f"{rango} Detalle en <code>3_dasimetria/contingencias.csv</code>.")


def _detalle(texto: str) -> str:
    """Detalle de un control. Las rutas se cortan a una línea; el texto completo aparece al pasar el mouse."""
    t = _numeros_es(texto)
    es_ruta = "/" in t and " " not in t.strip()
    clase = "d" if es_ruta else "d largo"
    mostrar = t.rstrip("/").split("/")[-1] if es_ruta else t
    return f'<span class="{clase}" title="{html.escape(t, quote=True)}">{html.escape(mostrar)}</span>'


def _numeros_es(texto: str) -> str:
    """Pasa los números con formato inglés de un texto (4,297,055.6) al formato local (4.297.055,6)."""
    import re

    return re.sub(r"[+-]?\d{1,3}(?:,\d{3})+(?:\.\d+)?|[+-]?\d+\.\d+",
                  lambda m: m.group(0).replace(",", "_").replace(".", ",").replace("_", "."), texto)


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


def _estado(ctrl: pd.DataFrame | None) -> tuple[str, str, str]:
    """(clase, título, detalle) del estado general de la ejecución."""
    if ctrl is None or ctrl.empty:
        return "adv", "Sin controles", "La ejecución no registró controles."
    ok = ctrl["ok"].astype(str).str.lower() == "true"
    bloq = ctrl["bloqueante"].astype(str).str.lower() == "true"
    n_adv, n_falla = int((~ok & ~bloq).sum()), int((~ok & bloq).sum())
    if n_falla:
        return "falla", "Ejecución detenida", f"{n_falla} control(es) bloqueante(s) sin cumplir. Ver Controles."
    if n_adv:
        return "adv", "Completa, con advertencias", f"{n_adv} advertencia(s) para revisar. Ver Controles."
    return "ok", "Completa: todos los controles cumplidos", f"{len(ctrl)} controles en {ctrl['etapa'].nunique()} etapas."


def _seccion_controles(c: Path) -> str:
    ctrl = _leer(c / "controles.csv")
    if ctrl is None:
        return "<p class='nota'>Sin controles registrados.</p>"
    ctrl = ctrl.assign(ok=ctrl["ok"].astype(str).str.lower() == "true",
                       bloqueante=ctrl["bloqueante"].astype(str).str.lower() == "true")
    ctrl["clase"] = ["ok" if o else ("falla" if b else "adv") for o, b in zip(ctrl["ok"], ctrl["bloqueante"])]
    n = ctrl["clase"].value_counts()
    tarjetas = (f'<div class="grilla"><div class="tarjeta"><div class="n ok">{n.get("ok", 0)}</div><div class="l">controles cumplidos</div></div>'
                f'<div class="tarjeta"><div class="n adv">{n.get("adv", 0)}</div><div class="l">advertencias</div></div>'
                f'<div class="tarjeta"><div class="n falla">{n.get("falla", 0)}</div><div class="l">fallas bloqueantes</div></div></div>')
    no = ctrl[~ctrl["ok"]]
    explica = _explicacion_conservacion(c, no) if len(no) else ""
    iconos = {"ok": "✓", "adv": "!", "falla": "✕"}
    tarjetas_etapa = []
    for etapa, g in ctrl.groupby("etapa", sort=True):
        nombre, que = ETAPAS.get(etapa, (etapa, ""))
        k = g["clase"].value_counts()
        tot = len(g)
        barra = "".join(f'<i class="b-{cl}" style="width:{100 * k.get(cl, 0) / tot:.2f}%"></i>'
                        for cl in ("ok", "adv", "falla"))
        cl_etapa = "falla" if k.get("falla") else ("adv" if k.get("adv") else "ok")
        items = []
        for _, f in g.sort_values("clase", key=lambda s: s.map({"falla": 0, "adv": 1, "ok": 2})).iterrows():
            items.append(f'<li><span class="{f["clase"]}">{iconos[f["clase"]]}</span><span>{html.escape(str(f["nombre"]))}</span>'
                         f'{_detalle(str(f["detalle"]))}</li>')
        if etapa == "3_dasimetria" and explica and not g["detalle"].astype(str).str.contains("Esperable").any():
            items.insert(int((g["clase"] != "ok").sum()), f'<li><span></span><div class="explica">{explica}</div></li>')
        abierta = " open" if cl_etapa != "ok" else ""
        tarjetas_etapa.append(
            f'<details class="etapa"{abierta}><summary><div class="cab"><span class="nombre">'
            f'<span class="{cl_etapa}">{iconos[cl_etapa]}</span> {etapa[0]} · {html.escape(nombre)}</span>'
            f'<span class="cuenta">{k.get("ok", 0)}/{tot}</span></div><div class="que">{html.escape(que)}</div>'
            f'<div class="barra">{barra}</div><span class="ver">Ver controles</span></summary>'
            f'<ul>{"".join(items)}</ul></details>')
    return (tarjetas + "<h3>Por etapa</h3><p class='nota'>Cada etapa con sus controles: ✓ cumplido, ! advertencia, "
            "✕ falla. Las etapas con algo para revisar aparecen abiertas.</p>"
            f'<div class="etapas">{"".join(tarjetas_etapa)}</div>')


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
    escala = None
    for prod, pie in (("poblacion", "Población (personas por km², escala logarítmica)"),
                      ("degradacion", "Tierras degradadas"),
                      ("expuesta", "Población en tierras degradadas (personas por km²)")):
        if prod in disponibles:
            try:
                fig = vista.mapa(c, prod)
                if prod == "expuesta":
                    escala = vista.escala_de(fig)
                figs.append(_figura(_png(fig), pie))
            except Exception as e:  # noqa: BLE001 — una vista que falla no impide el informe
                log.warning("Vista '%s' no generada: %s", prod, e)
    regiones = []
    if "expuesta" in disponibles:
        campo = cfg["region"]["campo"]
        nombres = pd.read_parquet(c / "1_radios" / "radios.parquet", columns=[campo])[campo].unique()
        for reg in sorted(n for n in nombres if n != cfg["region"].get("etiqueta_fuera")):
            try:
                fig, ax = plt.subplots(figsize=(5, 5))
                vista.mapa(c, "expuesta", region=reg, ax=ax, ancho_px=600, titulo="", escala=escala,
                           barra=escala is None)
                regiones.append(_figura(_png(fig), reg))
            except Exception as e:  # noqa: BLE001
                log.warning("Vista de la región '%s' no generada: %s", reg, e)
    html_ = f'<div class="mapas">{"".join(figs)}</div>' if figs else "<p class='nota'>Sin rasters para mostrar.</p>"
    if regiones:
        html_ += ("<h3>Población en tierras degradadas, por región</h3>"
                  + ("<p class='nota'>Misma escala de colores que el mapa nacional.</p>" if escala else "")
                  + f'<div class="mapas chicos">{"".join(regiones)}</div>')
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
    reut = ""
    if (c / "reutilizado.json").exists():
        import json

        r = json.loads((c / "reutilizado.json").read_text(encoding="utf-8"))
        reut = (f"<p class='nota'>Etapas reutilizadas de otra ejecución (mismos criterios e insumos): "
                f"{html.escape(', '.join(r.get('etapas', [])))}, de <code>{html.escape(Path(r.get('base', '')).name)}</code>.</p>")
    return (f'<div class="envoltura"><table><tbody>{tabla}</tbody></table></div>{reut}<h3>Insumos</h3>{filas}'
            "<p class='nota'>Configuración completa en <code>config.yaml</code>; huellas de todos los productos en "
            "<code>manifiesto.csv</code>.</p>")


TITULO_POR_DEFECTO = "Población expuesta a la degradación de tierras"
# Isotipo de poblar (docs/img/isotipo.svg)
ISOTIPO = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 60 60" width="34" height="34" role="img" aria-label="poblar">  <rect x="3.96" y="3.96" width="7.08" height="7.08" rx="1.27" fill="#c49a5a"/>  <rect x="17.76" y="2.76" width="9.48" height="9.48" rx="1.71" fill="#8a5cd6"/>  <rect x="31.32" y="1.32" width="12.36" height="12.36" rx="2.22" fill="#4a2f7a"/>  <rect x="45.60" y="0.60" width="13.80" height="13.80" rx="2.48" fill="#4a2f7a"/>  <rect x="4.44" y="19.44" width="6.12" height="6.12" rx="1.10" fill="#c49a5a"/>  <rect x="18.48" y="18.48" width="8.04" height="8.04" rx="1.45" fill="#8a5cd6"/>  <rect x="31.80" y="16.80" width="11.40" height="11.40" rx="2.05" fill="#4a2f7a"/>  <rect x="46.08" y="16.08" width="12.84" height="12.84" rx="2.31" fill="#4a2f7a"/>  <rect x="4.82" y="34.82" width="5.35" height="5.35" rx="0.96" fill="#c49a5a"/>  <rect x="19.20" y="34.20" width="6.60" height="6.60" rx="1.19" fill="#c49a5a"/>  <rect x="33.24" y="33.24" width="8.52" height="8.52" rx="1.53" fill="#8a5cd6"/>  <rect x="47.52" y="32.52" width="9.96" height="9.96" rx="1.79" fill="#8a5cd6"/>  <rect x="5.85" y="50.85" width="3.30" height="3.30" rx="0.59" fill="#ddd3c0"/>  <rect x="19.82" y="49.82" width="5.35" height="5.35" rx="0.96" fill="#c49a5a"/>  <rect x="34.44" y="49.44" width="6.12" height="6.12" rx="1.10" fill="#c49a5a"/>  <rect x="48.86" y="48.86" width="7.27" height="7.27" rx="1.31" fill="#c49a5a"/></svg>')


def ruta(carpeta: str | Path) -> Path:
    """Ruta del informe de una ejecución: ``informe_<nombre>.html`` (o ``informe.html``, de versiones anteriores)."""
    c = Path(carpeta)
    nuevo = c / f"informe_{c.name}.html"
    viejo = c / "informe.html"
    return viejo if viejo.exists() and not nuevo.exists() else nuevo


def generar(carpeta: str | Path, mapas: bool = True) -> Path:
    """Escribe ``informe_<nombre>.html`` en la carpeta de la ejecución y devuelve su ruta.

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
    titulo = str(obtener_titulo(cfg))
    anio = cfg.get("anio_censo", "")
    nombre = str(cfg.get("nombre", c.name))
    clase, estado, det = _estado(_leer(c / "controles.csv"))
    variante = ""
    if (c / "metodo.yaml").exists():
        lineas = (c / "metodo.yaml").read_text(encoding="utf-8").splitlines()
        if lineas and lineas[0].startswith("# Variante de"):
            cambios = [x[4:].strip() for x in lineas[1:] if x.startswith("#   ")]
            variante = (f'<div class="estado"><b>{html.escape(lineas[0][2:])}</b><span>'
                        + html.escape("; ".join(cambios)) + "</span></div>")
    fecha = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M")
    e = html.escape
    doc = (f'<!doctype html><html lang="es"><head><meta charset="utf-8">'
           f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>{e(titulo)} · {anio}</title>'
           f"<style>{CSS}</style></head><body><main><header>"
           f'<div class="marca">{ISOTIPO}<span>poblar</span></div>'
           f'<p class="antetitulo">Informe de ejecución · período {anio}</p><h1>{e(titulo)}</h1>'
           f'<p class="sub">Ejecución <code>{e(nombre)}</code> · generado el {fecha} UTC por poblar</p>'
           f'<div class="estado {clase}"><b>{e(estado)}</b><span>{e(det)}</span></div>{variante}</header>'
           f"{cuerpo}</main></body></html>")
    destino = c / f"informe_{c.name}.html"
    destino.write_text(doc, encoding="utf-8")
    viejo = c / "informe.html"
    if viejo.exists():
        viejo.unlink()
    log.info("Informe: %s", destino)
    return destino


def obtener_titulo(cfg: dict[str, Any]) -> str:
    """Título del informe: ``informe.titulo`` del método o el título por defecto."""
    return (cfg.get("informe") or {}).get("titulo") or TITULO_POR_DEFECTO
