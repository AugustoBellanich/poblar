"""Etapa 4: cruce de la población con una capa temática categórica (por ejemplo, tierras degradadas).

Método (equivalente al cuaderno C3 del PRAIS 2026):

1. La capa temática se lleva a la grilla de trabajo con vecino más cercano
   (``gdalwarp -r near``, Byte, nodata 255).
2. Cada píxel recibe la zona (región × ámbito) del radio dueño del píxel, por
   búsqueda sobre el raster de identificadores de la etapa 3.
3. Por bloques, se suma cada variable por zona y categoría (``bincount``).
   Los píxeles sin radio (id 0) o sin dato en la capa temática no entran:
   su población se informa en el balance.
4. Tablas: formato largo (región, ámbito, categoría, variable), binario
   (categorías agrupadas según la tabla de clases, con el ámbito de reporte) y
   ancho. Las variables derivadas (por ejemplo, agua sin red = total − con red)
   se calculan en la tabla, porque la suma es lineal.

Productos en ``4_cruce/``: ``tematica_trabajo.tif``, ``cruce_largo.csv``,
``cruce_binario.csv``, ``cruce_ancho.csv``, ``resumen_expuesta.csv`` y,
si se pide, rasters de cada variable dentro de una categoría binaria.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import rasterio

from poblar.config import obtener
from poblar.gdal import ejecutar_gdal, opciones_creacion
from poblar.grilla import ventanas_por_filas
from poblar.trazabilidad import Control, Ejecucion, log

ETAPA = "4_cruce"
NODATA_CAT = 255
NODATA_POB = -9999.0


def rutas_productos(cfg: dict[str, Any], carpeta: Path) -> dict[str, Path]:
    """Ruta de cada raster de la etapa 3, por nombre de producto."""
    anio = cfg["anio_censo"]
    d = carpeta / "3_dasimetria"
    nombre_pob = obtener(cfg, "dasimetria.producto_poblacion", "poblacion_dasimetrica")
    rutas = {nombre_pob: d / f"{nombre_pob}_{anio}.tif"}
    for v in obtener(cfg, "dasimetria.variables"):
        rutas[v["producto"]] = d / f"{v['producto']}_dasimetrico_{anio}.tif"
    return rutas


def tabla_categorias(cfg: dict[str, Any]) -> pd.DataFrame:
    """Tabla de clases de la capa temática: clase, etiqueta y grupo binario (o vacío = se excluye)."""
    filas = []
    for item in obtener(cfg, "cruce.clases"):
        filas.append({"clase": int(item["clase"]), "etiqueta": str(item["etiqueta"]),
                      "binario": item.get("binario")})
    t = pd.DataFrame(filas)
    if t["clase"].duplicated().any():
        raise ValueError("cruce.clases tiene clases repetidas")
    return t


def alinear(origen: Path, referencia: Path, salida: Path) -> None:
    """Capa temática a la grilla de ``referencia`` (vecino más cercano, Byte, nodata 255)."""
    with rasterio.open(referencia) as r:
        b, w, h = r.bounds, r.width, r.height
        crs = r.crs.to_string()
        xres, yres = r.transform.a, -r.transform.e
    with rasterio.open(origen) as s:
        s_srs = f"EPSG:{s.crs.to_epsg()}" if s.crs.to_epsg() is not None else s.crs.to_wkt()
    # Mismos argumentos que el C3 (-te, -tr y -ts): la grilla queda idéntica a la de población.
    ejecutar_gdal(["gdalwarp", "-overwrite", "-s_srs", s_srs, "-t_srs", crs,
                   "-te", str(b.left), str(b.bottom), str(b.right), str(b.top),
                   "-tr", str(xres), str(yres), "-ts", str(w), str(h),
                   "-r", "near", "-ot", "Byte", "-dstnodata", str(NODATA_CAT), *opciones_creacion(),
                   "--config", "GDAL_NUM_THREADS", "ALL_CPUS", "-multi", str(origen), str(salida)])


def construir(ejecucion: Ejecucion, radios: pd.DataFrame | None = None) -> pd.DataFrame:
    """Corre la etapa 4. Devuelve la tabla larga del cruce."""
    cfg = ejecucion.cfg
    d = ejecucion.dir_etapa(ETAPA)
    anio = cfg["anio_censo"]
    filas_bloque = int(obtener(cfg, "rendimiento.filas_por_bloque", 512))
    banda = int(obtener(cfg, "cruce.banda", 1))
    campo_reg = obtener(cfg, "region.campo")
    campo_amb = obtener(cfg, "dasimetria.campo_ambito")
    d3 = ejecucion.carpeta / "3_dasimetria"
    ids_tif = d3 / "raster_ids_radios.tif"
    if radios is None:
        radios = pd.read_parquet(d3 / "radios_factores.parquet")
    radios = pd.DataFrame(radios).drop(columns="geometry", errors="ignore")

    # 1. Capa temática en la grilla de trabajo
    origen = Path(cfg["insumos"][obtener(cfg, "cruce.insumo")]["ruta"])
    tematica = d / "tematica_trabajo.tif"
    alinear(origen, ids_tif, tematica)
    with rasterio.open(tematica) as a, rasterio.open(ids_tif) as b:
        igual = (a.width, a.height) == (b.width, b.height) and a.transform.almost_equals(b.transform, 1e-6)
    ejecucion.controlar(Control(ETAPA, "capa temática alineada a la grilla de trabajo", igual,
                                "misma grilla" if igual else "la grilla no coincide"))

    # 2. Zonas región × ámbito por radio
    zonas = (radios[[campo_reg, campo_amb]].drop_duplicates()
             .sort_values([campo_reg, campo_amb]).reset_index(drop=True))
    zonas["zona"] = np.arange(1, len(zonas) + 1)
    rz = radios.merge(zonas, on=[campo_reg, campo_amb], how="left")
    n = int(radios["raster_id"].max())
    lut_zona = np.zeros(n + 1, dtype=np.int64)
    lut_zona[rz["raster_id"].to_numpy()] = rz["zona"].to_numpy()
    nz = len(zonas) + 1

    # 3. Cruce por bloques
    cats = tabla_categorias(cfg)
    lut_cat = np.full(256, -1, dtype=np.int64)
    lut_cat[cats["clase"].to_numpy()] = np.arange(len(cats))
    nc = len(cats)
    todas = rutas_productos(cfg, ejecucion.carpeta)
    pedidas = obtener(cfg, "cruce.variables", None) or list(todas)
    faltan = [v for v in pedidas if v not in todas]
    if faltan:
        raise ValueError(f"cruce.variables: productos que la etapa 3 no genera: {faltan}")
    nombre_pob = next(iter(todas))
    if nombre_pob not in pedidas:
        pedidas = [nombre_pob, *pedidas]
    acum = {v: np.zeros(nz * nc, dtype=np.float64) for v in pedidas}
    fuera = dict.fromkeys(pedidas, 0.0)           # población no cruzada (sin radio o sin dato temático)
    clases_sin_tabla: dict[int, int] = {}

    srcs = {v: rasterio.open(todas[v]) for v in pedidas}
    try:
        with rasterio.open(ids_tif) as si, rasterio.open(tematica) as st:
            for w in ventanas_por_filas(si.height, si.width, filas_bloque, avance="cruce"):
                ids = si.read(1, window=w)
                cat = st.read(banda, window=w)
                zona = lut_zona[ids]
                icat = lut_cat[cat]
                sin_tabla = (cat != NODATA_CAT) & (icat < 0)
                if sin_tabla.any():
                    u, c = np.unique(cat[sin_tabla], return_counts=True)
                    for a, b in zip(u.tolist(), c.tolist()):
                        clases_sin_tabla[a] = clases_sin_tabla.get(a, 0) + b
                valido = (zona > 0) & (icat >= 0)
                idx = zona[valido] * nc + icat[valido]
                for v, s in srcs.items():
                    x = s.read(1, window=w).astype(np.float64)
                    x = np.where(np.isfinite(x) & (x != NODATA_POB) & (x >= 0), x, 0.0)
                    acum[v] += np.bincount(idx, weights=x[valido], minlength=nz * nc)
                    fuera[v] += float(x[~valido].sum())
    finally:
        for s in srcs.values():
            s.close()

    ejecucion.controlar(Control(ETAPA, "todas las clases de la capa temática están en la tabla",
                                not clases_sin_tabla,
                                f"clases sin tabla (píxeles): {clases_sin_tabla}" if clases_sin_tabla
                                else f"{nc} clases declaradas"))

    # 4. Tablas
    zl = zonas.set_index("zona")
    filas = []
    for v, m in acum.items():
        m = m.reshape(nz, nc)
        for z in range(1, nz):
            for j in range(nc):
                if m[z, j] == 0:
                    continue
                filas.append({"region": zl.at[z, campo_reg], "ambito": zl.at[z, campo_amb],
                              "clase": int(cats.at[j, "clase"]), "etiqueta": cats.at[j, "etiqueta"],
                              "binario": cats.at[j, "binario"], "variable": v, "valor": float(m[z, j])})
    largo = pd.DataFrame(filas)
    claves = ["region", "ambito", "clase", "etiqueta", "binario"]
    for der in obtener(cfg, "cruce.derivadas", None) or []:
        base = largo.assign(binario=largo["binario"].fillna("__sin_grupo__"))
        tot = base[base["variable"] == der["total"]].set_index(claves)["valor"]
        res = base[base["variable"] == der["resta"]].set_index(claves)["valor"]
        nueva = tot.sub(res, fill_value=0).clip(lower=0).rename("valor").reset_index()
        nueva["binario"] = nueva["binario"].replace("__sin_grupo__", None)
        nueva["variable"] = der["nombre"]
        largo = pd.concat([largo, nueva[[*claves, "variable", "valor"]]], ignore_index=True)
    ambito_rep = obtener(cfg, "cruce.ambito_reporte", None) or {}
    largo["ambito_reporte"] = largo["ambito"].map(ambito_rep).fillna(largo["ambito"])
    largo.to_csv(d / "cruce_largo.csv", index=False, encoding="utf-8")

    binario = (largo[largo["binario"].notna()]
               .groupby(["region", "ambito_reporte", "binario", "variable"])["valor"].sum().reset_index())
    binario.to_csv(d / "cruce_binario.csv", index=False, encoding="utf-8")
    largo.pivot_table(index=["region", "ambito_reporte"], columns=["variable", "etiqueta"],
                      values="valor", aggfunc="sum", fill_value=0).to_csv(d / "cruce_ancho.csv", encoding="utf-8")

    grupo = obtener(cfg, "cruce.grupo_expuesto", None)
    if grupo:
        exp = binario[binario["binario"] == grupo]
        resumen = pd.concat([
            exp.groupby(["region", "variable"])["valor"].sum().reset_index(),
            exp.groupby("variable")["valor"].sum().reset_index().assign(region="NACIONAL"),
        ], ignore_index=True)[["region", "variable", "valor"]]
        resumen.to_csv(d / "resumen_expuesta.csv", index=False, encoding="utf-8")

    # 5. Balance y controles
    total_pob = float(acum[nombre_pob].sum()) + fuera[nombre_pob]
    ejecucion.balance(ETAPA, "cruce", poblacion_cruzada=round(float(acum[nombre_pob].sum()), 3),
                      poblacion_no_cruzada=round(fuera[nombre_pob], 3), poblacion_raster=round(total_pob, 3))
    tol = float(obtener(cfg, "controles.tolerancia_personas_cruce", 1.0))
    ejecucion.controlar(Control(ETAPA, "población no cruzada (sin radio o sin dato temático)",
                                fuera[nombre_pob] <= tol, f"{fuera[nombre_pob]:,.3f} personas",
                                fuera[nombre_pob], tol, bloqueante=False))
    if not largo.empty and (largo["valor"] < 0).any():
        ejecucion.controlar(Control(ETAPA, "sin valores negativos", False, "hay valores negativos"))
    _controles_esperados(ejecucion, binario, grupo, nombre_pob)

    if obtener(cfg, "cruce.rasters_por_grupo", None):
        _rasters_grupo(ejecucion, d, tematica, cats, srcs_rutas={v: todas[v] for v in pedidas},
                       grupos=list(obtener(cfg, "cruce.rasters_por_grupo")), anio=anio, filas=filas_bloque,
                       banda=banda)
    log.info("[%s] listo: %d filas en la tabla larga", ETAPA, len(largo))
    return largo


def _controles_esperados(ejecucion: Ejecucion, binario: pd.DataFrame, grupo: str | None, nombre_pob: str) -> None:
    esperado = obtener(ejecucion.cfg, "resultados_esperados.cruce", None) or {}
    if not grupo:
        return
    for variable, valor in esperado.items():
        obtenido = float(binario[(binario["binario"] == grupo) & (binario["variable"] == variable)]["valor"].sum())
        ok = abs(obtenido - float(valor)) <= 1.0
        ejecucion.controlar(Control(ETAPA, f"resultado esperado: {variable} en '{grupo}'", ok,
                                    f"{obtenido:,.1f} vs {float(valor):,.1f}", obtenido, valor, bloqueante=False))


def _rasters_grupo(ejecucion: Ejecucion, d: Path, tematica: Path, cats: pd.DataFrame,
                   srcs_rutas: dict[str, Path], grupos: list[str], anio: int, filas: int,
                   banda: int = 1) -> None:
    """Rasters de cada variable con valor solo donde la categoría pertenece al grupo binario (0 fuera)."""
    for grupo in grupos:
        clases = cats.loc[cats["binario"] == grupo, "clase"].to_numpy()
        if len(clases) == 0:
            raise ValueError(f"cruce.rasters_por_grupo: '{grupo}' no es un grupo de cruce.clases")
        en_grupo = np.zeros(256, dtype=bool)
        en_grupo[clases] = True
        for v, ruta in srcs_rutas.items():
            salida = d / f"{v}_{grupo}_{anio}.tif"
            total = 0.0
            with rasterio.open(ruta) as s, rasterio.open(tematica) as st:
                perfil = s.profile.copy()
                with rasterio.open(salida, "w", **perfil) as dst:
                    for w in ventanas_por_filas(s.height, s.width, filas):
                        x = s.read(1, window=w)
                        g = en_grupo[st.read(banda, window=w)]
                        out = np.where(x == NODATA_POB, x, np.where(g, x, 0)).astype(np.float32)
                        total += float(np.where(out == NODATA_POB, 0, out).astype(np.float64).sum())
                        dst.write(out, 1, window=w)
            ejecucion.balance(ETAPA, f"raster {v} en {grupo}", suma=round(total, 3))
