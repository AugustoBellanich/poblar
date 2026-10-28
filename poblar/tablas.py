"""Etapa 6: tablas de indicadores (país y tierras degradadas).

Reúne, para un año, las cantidades de cada variable (población, NBI, agua de
red) por grupo (total, mujeres, varones, urbano, rural) y región, en el país y
en el grupo expuesto del cruce (por ejemplo, tierras degradadas), y calcula
los tres porcentajes posibles, con nombre propio para no mezclarlos:

* ``incidencia``: variable del grupo ÷ población del mismo grupo, en el mismo
  ámbito (país o TD). Ej.: personas con NBI en TD ÷ personas en TD.
  Es la definición de los indicadores SO2-1 y SO2-2 de la CNULD.
* ``exposicion``: cantidad en TD ÷ cantidad en el país, para la misma variable
  y grupo. Ej.: mujeres en TD ÷ mujeres del país. Es la definición del SO2-3.
* ``composicion``: cantidad del grupo ÷ total de la variable en el mismo
  ámbito. Ej.: mujeres en TD ÷ población en TD.

Las tablas de salida usan el porcentaje que la configuración indica para cada
una. Así, la fórmula queda escrita y es la misma en todas las filas.

Fuentes de las cantidades:

* País: suma de los campos de la tabla censal sobre los radios integrados
  (``1_radios/radios.parquet``).
* TD: ``4_cruce/cruce_largo.csv`` (filas del grupo expuesto).

Urbano y rural pueden definirse de dos maneras (``tablas.urbano_rural``), por
separado para el país y para TD:

* ``persona``: población urbana o rural según el censo (campos ``*_urbana`` y
  ``*_rural``; en TD, los productos dasimétricos de esas variables);
* ``radio``: ámbito del radio (con la agrupación de ``cruce.ambito_reporte``),
  aplicado a la variable total.

Productos en ``6_tablas/``: ``indicadores.csv`` (formato largo, con los tres
porcentajes) y una tabla por cada entrada de ``tablas.salidas``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from poblar.config import obtener
from poblar.trazabilidad import Control, Ejecucion, log

ETAPA = "6_tablas"
GRUPOS = ["total", "mujer", "varon", "urbano", "rural"]
NACIONAL = "NACIONAL"


def _pais(cfg: dict[str, Any], radios: pd.DataFrame, modo_ur: str) -> pd.DataFrame:
    campo_reg = obtener(cfg, "region.campo")
    campo_amb = obtener(cfg, "dasimetria.campo_ambito")
    amb_rep = obtener(cfg, "cruce.ambito_reporte", None) or {}
    filas = []
    for var, campos in obtener(cfg, "tablas.variables").items():
        r = radios.copy()
        for grupo in GRUPOS:
            if grupo in ("urbano", "rural") and modo_ur == "radio":
                etiqueta = "Urbano" if grupo == "urbano" else "Rural"
                sel = r[campo_amb].map(amb_rep).fillna(r[campo_amb]) == etiqueta
                serie = r.loc[sel, campos["censo"]["total"]]
                regiones = r.loc[sel, campo_reg]
            else:
                serie = r[campos["censo"][grupo]]
                regiones = r[campo_reg]
            por_region = serie.groupby(regiones).sum()
            for reg, n in por_region.items():
                filas.append({"ambito": "pais", "region": reg, "variable": var, "grupo": grupo, "n": float(n)})
            filas.append({"ambito": "pais", "region": NACIONAL, "variable": var, "grupo": grupo,
                          "n": float(serie.sum())})
    return pd.DataFrame(filas)


def _td(cfg: dict[str, Any], largo: pd.DataFrame, modo_ur: str) -> pd.DataFrame:
    grupo_exp = obtener(cfg, "cruce.grupo_expuesto")
    exp = largo[largo["binario"] == grupo_exp]
    filas = []
    for var, campos in obtener(cfg, "tablas.variables").items():
        for grupo in GRUPOS:
            if grupo in ("urbano", "rural") and modo_ur == "radio":
                etiqueta = "Urbano" if grupo == "urbano" else "Rural"
                sel = exp[(exp["variable"] == campos["td"]["total"]) & (exp["ambito_reporte"] == etiqueta)]
            else:
                producto = campos["td"][grupo]
                if producto not in set(largo["variable"]):
                    raise ValueError(f"tablas.variables.{var}.td.{grupo}='{producto}' no está en el cruce; "
                                     f"agregarlo a cruce.variables.")
                sel = exp[exp["variable"] == producto]
            por_region = sel.groupby("region")["valor"].sum()
            for reg, n in por_region.items():
                filas.append({"ambito": "td", "region": reg, "variable": var, "grupo": grupo, "n": float(n)})
            filas.append({"ambito": "td", "region": NACIONAL, "variable": var, "grupo": grupo,
                          "n": float(sel["valor"].sum())})
    return pd.DataFrame(filas)


def indicadores(cfg: dict[str, Any], radios: pd.DataFrame, largo: pd.DataFrame) -> pd.DataFrame:
    """Tabla larga: ámbito × región × variable × grupo, con n y los tres porcentajes."""
    ur = obtener(cfg, "tablas.urbano_rural")
    t = pd.concat([_pais(cfg, radios, ur["pais"]), _td(cfg, largo, ur["td"])], ignore_index=True)
    pob = obtener(cfg, "tablas.variable_poblacion", "poblacion")
    claves = ["ambito", "region", "grupo"]
    base = t[t["variable"] == pob].set_index(claves)["n"]
    t["incidencia"] = 100 * t["n"] / t.set_index(claves).index.map(base).to_numpy()
    tot = t[t["grupo"] == "total"].set_index(["ambito", "region", "variable"])["n"]
    t["composicion"] = 100 * t["n"] / t.set_index(["ambito", "region", "variable"]).index.map(tot).to_numpy()
    pais = t[t["ambito"] == "pais"].set_index(["region", "variable", "grupo"])["n"]
    t["exposicion"] = 100 * t["n"] / t.set_index(["region", "variable", "grupo"]).index.map(pais).to_numpy()
    t.loc[t["ambito"] == "pais", "exposicion"] = float("nan")
    return t


def _tabla(ind: pd.DataFrame, spec: dict[str, Any]) -> pd.DataFrame:
    var, formula = spec["variable"], spec["formula"]
    grupos = spec.get("grupos", GRUPOS)
    sel = ind[(ind["variable"] == var) & (ind["grupo"].isin(grupos))]
    if spec.get("por", "grupos") == "regiones":
        sel = sel[sel["region"] != NACIONAL]
    else:
        sel = sel[sel["region"] == NACIONAL]
    sel = sel.assign(pct=sel[formula])
    out = sel.pivot_table(index=["region", "grupo"], columns="ambito", values=["n", "pct"], aggfunc="first")
    out.columns = [f"{a}_{b}" for a, b in out.columns]
    orden = {g: i for i, g in enumerate(grupos)}
    out = out.reset_index()
    out["_o"] = out["grupo"].map(orden)
    cols = [c for c in ["region", "grupo", "n_pais", "pct_pais", "n_td", "pct_td"] if c in out.columns]
    return out.sort_values(["region", "_o"])[cols].assign(formula=formula)


def construir(ejecucion: Ejecucion) -> pd.DataFrame:
    """Corre la etapa 6. Devuelve la tabla larga de indicadores."""
    cfg = ejecucion.cfg
    d = ejecucion.dir_etapa(ETAPA)
    radios = pd.read_parquet(ejecucion.carpeta / "1_radios" / "radios.parquet")
    radios = radios.drop(columns="geometry", errors="ignore")
    largo = pd.read_csv(ejecucion.carpeta / "4_cruce" / "cruce_largo.csv")
    ind = indicadores(cfg, radios, largo)
    ind.to_csv(d / "indicadores.csv", index=False, encoding="utf-8")
    for spec in obtener(cfg, "tablas.salidas"):
        if spec["formula"] not in ("incidencia", "exposicion", "composicion"):
            raise ValueError(f"tablas.salidas: fórmula '{spec['formula']}' no válida "
                             f"(incidencia | exposicion | composicion)")
        _tabla(ind, spec).to_csv(d / f"{spec['nombre']}.csv", index=False, encoding="utf-8")

    # Controles de consistencia
    nac = ind[ind["region"] == NACIONAL].set_index(["ambito", "variable", "grupo"])["n"]
    for amb in ("pais", "td"):
        for var in obtener(cfg, "tablas.variables"):
            tot = nac[(amb, var, "total")]
            for a, b in (("mujer", "varon"), ("urbano", "rural")):
                dif = nac[(amb, var, a)] + nac[(amb, var, b)] - tot
                ejecucion.controlar(Control(ETAPA, f"{amb} {var}: {a} + {b} = total", abs(dif) <= 1.0,
                                            f"diferencia {dif:+,.1f} personas", dif, 0, bloqueante=False))
    reg = ind[ind["region"] != NACIONAL].groupby(["ambito", "variable", "grupo"])["n"].sum()
    for (amb, var, grupo), n in reg.items():
        dif = n - nac[(amb, var, grupo)]
        if abs(dif) > 1.0:
            ejecucion.controlar(Control(ETAPA, f"{amb} {var} {grupo}: suma de regiones = nacional", False,
                                        f"diferencia {dif:+,.1f}", dif, 0, bloqueante=False))
    log.info("[%s] listo: %d filas de indicadores", ETAPA, len(ind))
    return ind


# ----------------------------------------------------------------- dos períodos
def unir_periodos(carpetas: dict[int, str | Path], salida: str | Path) -> dict[str, pd.DataFrame]:
    """Une las tablas de dos o más ejecuciones (una por año) en tablas con columnas por período.

    Args:
        carpetas: ``{año: carpeta de la ejecución}``.
        salida: Carpeta donde se escriben las tablas unidas.

    Returns:
        ``{nombre de tabla: DataFrame}``.
    """
    faltan = [f"{anio} ({c})" for anio, c in carpetas.items() if not (Path(c) / ETAPA / "indicadores.csv").exists()]
    if faltan:
        raise FileNotFoundError("Falta correr la etapa 'tablas' en: " + "; ".join(faltan))
    salida = Path(salida)
    salida.mkdir(parents=True, exist_ok=True)
    nombres = sorted({p.stem for c in carpetas.values() for p in (Path(c) / ETAPA).glob("*.csv")} - {"indicadores"})
    out = {}
    for nombre in nombres:
        partes = []
        for anio, c in sorted(carpetas.items()):
            t = pd.read_csv(Path(c) / ETAPA / f"{nombre}.csv")
            t = t.set_index(["region", "grupo"]).drop(columns="formula", errors="ignore")
            t.columns = [f"{col}_{anio}" for col in t.columns]
            partes.append(t)
        u = pd.concat(partes, axis=1).reset_index()
        u.to_csv(salida / f"{nombre}.csv", index=False, encoding="utf-8")
        out[nombre] = u
    return out
