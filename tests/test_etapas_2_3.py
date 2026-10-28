"""Etapas 2 y 3 con un caso sintético.

La cobertura sintética está en EPSG:4326 (como MapBiomas) sobre las mismas dos
regiones de la prueba de las etapas 0 y 1. Se verifica la conservación, las
contingencias y que el atajo de pesos por búsqueda equivale a rasterizar los
pesos con ``gdal_rasterize``.

Correr: ``python -m pytest -q``
"""

from __future__ import annotations

import shutil
from pathlib import Path

import geopandas as gpd
import numpy as np
import pytest
import rasterio
import yaml
from rasterio.transform import from_origin

from poblar import ejecutar
from poblar.gdal import ejecutar_gdal
from tests.test_etapas_0_1 import _config, insumos  # noqa: F401  (fixture)

pytestmark = pytest.mark.skipif(shutil.which("gdalwarp") is None, reason="requiere GDAL CLI")

ETAPAS_03 = ["insumos", "radios", "grilla", "dasimetria"]

CLASES = [
    {"clase": 0, "meta": "no_habitable"},
    {"clase": 1, "meta": "no_urbano"},
    {"clase": 8, "meta": "urbano"},
    {"clase": 11, "meta": "no_habitable"},
]


def _cobertura(d: Path, radios_zip: Path) -> Path:
    """Raster 4326 con clases 1 (no urbano), 8 (urbano) y 11 (agua) sobre los radios."""
    r = gpd.read_file(f"/vsizip/{radios_zip}").to_crs(4326)
    xmin, ymin, xmax, ymax = r.total_bounds
    res = 0.0009
    ancho = int((xmax - xmin) / res) + 40
    alto = int((ymax - ymin) / res) + 40
    t = from_origin(xmin - 20 * res, ymax + 20 * res, res, res)
    a = np.ones((alto, ancho), dtype=np.int8)        # no urbano
    a[: alto // 3, : ancho // 2] = 8                  # urbano al noroeste
    a[alto // 2:, ancho // 2:] = 11                   # agua al sudeste
    ruta = d / "cobertura.tif"
    with rasterio.open(ruta, "w", driver="GTiff", width=ancho, height=alto, count=1, dtype="int8",
                       crs="EPSG:4326", transform=t, nodata=-1) as dst:
        dst.write(a, 1)
    return ruta


def _config_completa(tmp_path: Path, insumos: Path, **cambios) -> Path:  # noqa: F811
    ruta = _config(tmp_path, **cambios)
    cfg = yaml.safe_load(ruta.read_text(encoding="utf-8"))
    _cobertura(insumos, insumos / "radios_2010.zip")
    cfg["insumos"]["mapbiomas"] = {"ruta": "cobertura.tif"}
    cfg["grilla_trabajo"].update({"modo": "fija", "resolucion_m": 100, "extension": "radios",
                                  "remuestreo_cobertura": "near"})
    cfg["cobertura"] = {"insumo": "mapbiomas", "codigo_nodata": 0, "clases": CLASES}
    cfg["dasimetria"] = {
        "campo_ambito": "ambito", "ambitos": ["Urbano", "Mixto", "Rural"],
        "ponderadores": {"normalizar_por": "Urbano", "peso_urbano": "complemento"},
        "variables": [{"producto": "pobla_mujer", "numerador": "pobla_mujer"},
                      {"producto": "nbi", "numerador": "nbi_total"}],
    }
    cfg["rendimiento"] = {"filas_por_bloque": 37}  # bloques chicos e irregulares a propósito
    ruta.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
    return ruta


def _suma(ruta: Path) -> float:
    with rasterio.open(ruta) as s:
        a = s.read(1)
        return float(a[a != s.nodata].astype(np.float64).sum())


def test_dasimetria_conserva_y_deriva_variables(tmp_path: Path, insumos: Path) -> None:  # noqa: F811
    cfg = _config_completa(tmp_path, insumos)
    e = ejecutar(cfg, insumos=insumos, salida=tmp_path / "ejecuciones", etapas=ETAPAS_03)
    d = e.carpeta / "3_dasimetria"
    assert _suma(d / "poblacion_dasimetrica_2010.tif") == pytest.approx(165, abs=1e-3)
    assert _suma(d / "pobla_mujer_dasimetrico_2010.tif") == pytest.approx(60 + 25 + 5 + 2, abs=1e-3)
    assert _suma(d / "nbi_dasimetrico_2010.tif") == pytest.approx(10 + 5 + 3 + 1, abs=1e-3)
    assert all(c.ok for c in e.controles if c.bloqueante)


def test_pesos_por_busqueda_igual_a_gdal_rasterize(tmp_path: Path, insumos: Path) -> None:  # noqa: F811
    cfg = _config_completa(tmp_path, insumos)
    e = ejecutar(cfg, insumos=insumos, salida=tmp_path / "ejecuciones", etapas=ETAPAS_03)
    d = e.carpeta / "3_dasimetria"
    radios = gpd.read_parquet(e.carpeta / "1_radios" / "radios.parquet").sort_values("raster_id")
    import pandas as pd

    f = pd.read_parquet(d / "radios_factores.parquet").set_index("raster_id")
    radios["peso_u"] = f.loc[radios["raster_id"], "peso_u"].to_numpy()
    radios["peso_nu"] = f.loc[radios["raster_id"], "peso_nu"].to_numpy()
    gpkg = tmp_path / "pesos.gpkg"
    radios[["peso_u", "peso_nu", "geometry"]].to_file(gpkg, driver="GPKG")
    with rasterio.open(e.carpeta / "2_grilla" / "cobertura.tif") as c:
        b, w, h, cls = c.bounds, c.width, c.height, c.read(1)
    capas = {}
    for campo in ("peso_u", "peso_nu"):
        salida = tmp_path / f"{campo}.tif"
        ejecutar_gdal(["gdal_rasterize", "-l", "pesos", "-a", campo, "-ot", "Float32", "-a_nodata", "0",
                       "-te", str(b.left), str(b.bottom), str(b.right), str(b.top), "-ts", str(w), str(h),
                       "-at", str(gpkg), str(salida)])
        with rasterio.open(salida) as s:
            capas[campo] = s.read(1)
    esperado = np.zeros_like(capas["peso_u"])
    esperado[cls == 1] = capas["peso_u"][cls == 1]
    esperado[cls == 2] = capas["peso_nu"][cls == 2]
    with rasterio.open(d / "pesos_dasimetricos.tif") as s:
        obtenido = s.read(1)
    assert np.array_equal(obtenido, esperado)


def test_contingencia_nivel_2_radio_en_agua(tmp_path: Path, insumos: Path) -> None:  # noqa: F811
    """Un radio sin píxeles habitables reparte su población en sus píxeles (nivel 2)."""
    cfg_ruta = _config_completa(tmp_path, insumos)
    cob = insumos / "cobertura.tif"
    with rasterio.open(cob, "r+") as s:  # todo agua salvo una franja: fuerza nivel 2 en algún radio
        a = s.read(1)
        a[:, :] = 11
        a[:5, :5] = 8
        s.write(a, 1)
    e = ejecutar(cfg_ruta, insumos=insumos, salida=tmp_path / "ejecuciones", etapas=ETAPAS_03)
    d = e.carpeta / "3_dasimetria"
    assert _suma(d / "poblacion_dasimetrica_2010.tif") == pytest.approx(165, abs=1e-3)
    import pandas as pd

    cont = pd.read_csv(d / "contingencias.csv")
    assert (cont["tipo_asignacion"] == "contingencia").any()


def test_ejecutar_gdal_informa_error(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError):
        ejecutar_gdal(["gdalinfo", str(tmp_path / "no_existe.tif")])


def test_contingencia_nivel_3_radio_tapado(tmp_path: Path, insumos: Path) -> None:  # noqa: F811
    """Dos radios diminutos en el mismo píxel: el más chico se queda el píxel y el otro (sin píxeles
    propios) se reparte sobre su polígono (nivel 3). La población total se conserva."""
    import zipfile

    import pandas as pd
    from shapely.geometry import box

    from tests.test_etapas_0_1 import X0, Y0

    shp = insumos / "radios_2010"
    gdf = gpd.read_file(shp / "radios_2010.shp")
    extra = gpd.GeoDataFrame(
        {"COD_2010": ["020010106", "020010107"]},
        geometry=[box(X0 + 1_510, Y0 + 12_510, X0 + 1_540, Y0 + 12_540),   # 30 m
                  box(X0 + 1_515, Y0 + 12_515, X0 + 1_525, Y0 + 12_525)],  # 10 m, dentro del anterior
        crs=5347).to_crs(gdf.crs)
    gdf = pd.concat([gdf, extra], ignore_index=True)
    gdf.to_file(shp / "radios_2010.shp")
    with zipfile.ZipFile(insumos / "radios_2010.zip", "w") as z:
        for f in shp.iterdir():
            z.write(f, f.name)
    t = pd.read_excel(insumos / "tabla_censo2010.xlsx", dtype={"id_radio": str})
    nuevas = t.iloc[:2].copy()
    nuevas["id_radio"] = ["020010106", "020010107"]
    pd.concat([t, nuevas], ignore_index=True).to_excel(insumos / "tabla_censo2010.xlsx", index=False)

    cfg = _config_completa(tmp_path, insumos, **{"referencia.poblacion_integrada": 165 + 100 + 50})
    e = ejecutar(cfg, insumos=insumos, salida=tmp_path / "ejecuciones", etapas=ETAPAS_03)
    d = e.carpeta / "3_dasimetria"
    cont = pd.read_csv(d / "contingencias.csv", dtype={"id_radio": str})
    assert "contingencia_extrema" in set(cont["tipo_asignacion"])
    assert _suma(d / "poblacion_dasimetrica_2010.tif") == pytest.approx(315, abs=1e-3)
    assert _suma(d / "pobla_mujer_dasimetrico_2010.tif") <= 60 + 25 + 5 + 2 + 60 + 25 + 1e-3


def test_carpeta_de_trabajo_y_comparar_raster(tmp_path: Path, insumos: Path) -> None:  # noqa: F811
    """Con ``trabajo`` se procesa en local y se copia a ``salida``; el resultado es el mismo."""
    from poblar.verificar import comparar_raster

    cfg = _config_completa(tmp_path, insumos)
    directo = ejecutar(cfg, insumos=insumos, salida=tmp_path / "directo", etapas=ETAPAS_03)
    copiado = ejecutar(cfg, insumos=insumos, salida=tmp_path / "salida", trabajo=tmp_path / "local", etapas=ETAPAS_03)
    assert copiado.carpeta.parent == tmp_path / "salida"
    raster = Path("3_dasimetria") / "poblacion_dasimetrica_2010.tif"
    assert (copiado.carpeta / "manifiesto.csv").exists()
    tabla = comparar_raster(copiado.carpeta / raster, directo.carpeta / raster)
    assert tabla["igual"].all(), tabla


def _con_cruce(tmp_path: Path, insumos: Path) -> Path:  # noqa: F811
    """Configuración completa más una capa temática 4326: 1 (degradada) al oeste, 2 al este, 0 en una franja."""
    ruta = _config_completa(tmp_path, insumos)
    cfg = yaml.safe_load(ruta.read_text(encoding="utf-8"))
    with rasterio.open(insumos / "cobertura.tif") as c:
        perfil, alto, ancho = c.profile.copy(), c.height, c.width
    a = np.full((alto, ancho), 2, dtype=np.uint8)
    a[:, : ancho // 2] = 1
    a[: alto // 10, :] = 0
    perfil.update(dtype="uint8", nodata=None)
    with rasterio.open(insumos / "tematica.tif", "w", **perfil) as dst:
        dst.write(a, 1)
    cfg["insumos"]["degradacion"] = {"ruta": "tematica.tif"}
    cfg["dasimetria"]["variables"].append({"producto": "agua_red", "numerador": "agua_red_total"})
    cfg["cruce"] = {
        "insumo": "degradacion",
        "clases": [{"clase": 0, "etiqueta": "Sin datos", "binario": None},
                   {"clase": 1, "etiqueta": "Degradada", "binario": "degradada"},
                   {"clase": 2, "etiqueta": "No degradada", "binario": "no_degradada"}],
        "grupo_expuesto": "degradada",
        "ambito_reporte": {"Urbano": "Urbano", "Mixto": "Rural", "Rural": "Rural"},
        "derivadas": [{"nombre": "agua_sin_red", "total": "poblacion_dasimetrica", "resta": "agua_red"}],
        "rasters_por_grupo": ["degradada"],
    }
    ruta.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
    return ruta


def test_cruce_conserva_y_coincide_con_el_raster(tmp_path: Path, insumos: Path) -> None:  # noqa: F811
    import pandas as pd

    e = ejecutar(_con_cruce(tmp_path, insumos), insumos=insumos, salida=tmp_path / "ejecuciones",
                 etapas=[*ETAPAS_03, "cruce"])
    d = e.carpeta / "4_cruce"
    largo = pd.read_csv(d / "cruce_largo.csv")
    bal = pd.read_csv(e.carpeta / "balance.csv")
    def medida(m: str) -> float:
        return float(bal[(bal.etapa == "4_cruce") & (bal.medida == m)]["valor"].iloc[0])
    pob = largo[largo.variable == "poblacion_dasimetrica"]["valor"].sum()
    assert pob + medida("poblacion_no_cruzada") == pytest.approx(165, abs=1e-3)
    # la tabla y el raster "en degradada" dan lo mismo (salvo píxeles sin radio, que la tabla no cuenta)
    deg_tabla = largo[(largo.variable == "poblacion_dasimetrica") & (largo.binario == "degradada")]["valor"].sum()
    assert deg_tabla > 0
    assert _suma(d / "poblacion_dasimetrica_degradada_2010.tif") == pytest.approx(
        deg_tabla, abs=medida("poblacion_no_cruzada") + 1e-3)
    # derivada: agua sin red = total − con red, fila por fila
    piv = largo.pivot_table(index=["region", "ambito", "clase"], columns="variable", values="valor", fill_value=0)
    assert np.allclose(piv["agua_sin_red"], (piv["poblacion_dasimetrica"] - piv["agua_red"]).clip(lower=0))
    assert set(pd.read_csv(d / "cruce_binario.csv")["ambito_reporte"]) <= {"Urbano", "Rural"}
    assert all(c.ok for c in e.controles if c.bloqueante)


def test_retomar_solo_el_cruce(tmp_path: Path, insumos: Path) -> None:  # noqa: F811
    """Correr una etapa sobre una ejecución existente conserva los controles de las anteriores."""
    import pandas as pd

    cfg = _con_cruce(tmp_path, insumos)
    salida = tmp_path / "salida"
    ejecutar(cfg, insumos=insumos, salida=salida, etapas=ETAPAS_03, trabajo=tmp_path / "local")
    e = ejecutar(cfg, insumos=insumos, salida=salida, etapas=["cruce"], trabajo=tmp_path / "local2")
    ctrl = pd.read_csv(e.carpeta / "controles.csv")
    assert {"0_insumos", "1_radios", "2_grilla", "3_dasimetria", "4_cruce"} <= set(ctrl["etapa"])
    assert (e.carpeta / "4_cruce" / "cruce_largo.csv").exists()


def test_publicacion_conserva_y_usa_la_grilla_de_referencia(tmp_path: Path, insumos: Path) -> None:  # noqa: F811
    import pandas as pd

    ruta = _con_cruce(tmp_path, insumos)
    cfg = yaml.safe_load(ruta.read_text(encoding="utf-8"))
    cfg["publicacion"] = {"grilla_referencia": "mapbiomas", "remuestreo": "sum", "bloque": 16,
                          "plantilla_nombre": "{nombre}_{anio}.tif",
                          "productos": {"poblacion_dasimetrica": "POB", "nbi": "NBI"}}
    ruta.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
    e = ejecutar(ruta, insumos=insumos, salida=tmp_path / "ejecuciones",
                 etapas=[*ETAPAS_03, "cruce", "publicacion"])
    d = e.carpeta / "5_publicacion"
    t = pd.read_csv(d / "publicacion.csv")
    assert set(t["archivo"]) == {"POB_2010.tif", "NBI_2010.tif"}
    assert t["misma_grilla"].all()
    assert _suma(d / "POB_2010.tif") == pytest.approx(165, abs=0.05)
    with rasterio.open(d / "POB_2010.tif") as a, rasterio.open(insumos / "cobertura.tif") as b:
        assert (a.width, a.height, a.crs) == (b.width, b.height, b.crs)


def test_publicacion_retoma_lo_ya_publicado(tmp_path: Path, insumos: Path) -> None:  # noqa: F811
    """Si se corta, al retomar no repite los rasters ya publicados y completa los que faltan."""
    import pandas as pd

    ruta = _con_cruce(tmp_path, insumos)
    cfg = yaml.safe_load(ruta.read_text(encoding="utf-8"))
    cfg["publicacion"] = {"grilla_referencia": "mapbiomas", "remuestreo": "sum", "bloque": 16, "procesos": 2,
                          "plantilla_nombre": "{nombre}_{anio}.tif",
                          "productos": {"poblacion_dasimetrica": "POB", "nbi": "NBI"}}
    ruta.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
    salida, local = tmp_path / "salida", tmp_path / "local"
    e = ejecutar(ruta, insumos=insumos, salida=salida, trabajo=local,
                 etapas=[*ETAPAS_03, "cruce", "publicacion"])
    d = e.carpeta / "5_publicacion"
    t = pd.read_csv(d / "publicacion.csv")
    # simula un corte: se pierde NBI (archivo y fila) y la copia local
    (d / "NBI_2010.tif").unlink()
    t[t.producto != "nbi"].to_csv(d / "publicacion.csv", index=False)
    import shutil

    shutil.rmtree(local)
    mtime_pob = (d / "POB_2010.tif").stat().st_mtime
    e2 = ejecutar(ruta, insumos=insumos, salida=salida, etapas=["publicacion"], trabajo=tmp_path / "local2")
    d2 = e2.carpeta / "5_publicacion"
    assert (d2 / "NBI_2010.tif").exists()
    assert (d2 / "POB_2010.tif").stat().st_mtime == mtime_pob   # no se volvió a generar
    assert set(pd.read_csv(d2 / "publicacion.csv")["producto"]) == {"poblacion_dasimetrica", "nbi"}


def test_sincronizar_no_copia_parciales_y_verifica(tmp_path: Path) -> None:
    from poblar.trazabilidad import sincronizar

    a, b = tmp_path / "a", tmp_path / "b"
    (a / "x").mkdir(parents=True)
    (a / "x" / "listo.tif").write_bytes(b"1" * 1000)
    (a / "x" / "en_curso.tif.parcial").write_bytes(b"2" * 10)
    assert sincronizar(a, b, verificar=True) == 1
    assert (b / "x" / "listo.tif").read_bytes() == b"1" * 1000
    assert not (b / "x" / "en_curso.tif.parcial").exists()
    assert not list(b.rglob("*.parcial"))


def test_tablas_formulas_y_union_de_periodos(tmp_path: Path, insumos: Path) -> None:  # noqa: F811
    import pandas as pd

    from poblar.tablas import unir_periodos

    tabla = pd.read_excel(insumos / "tabla_censo2010.xlsx", dtype={"id_radio": str})
    tabla["nbi_mujer"] = [6, 3, 2, 0, 0]
    tabla["nbi_varon"] = tabla["nbi_total"] - tabla["nbi_mujer"]
    tabla["nbi_urbana"] = [10, 3, 0, 0, 0]
    tabla["nbi_rural"] = tabla["nbi_total"] - tabla["nbi_urbana"]
    tabla.to_excel(insumos / "tabla_censo2010.xlsx", index=False)
    ruta = _con_cruce(tmp_path, insumos)
    cfg = yaml.safe_load(ruta.read_text(encoding="utf-8"))
    cfg["dasimetria"]["variables"] += [{"producto": "pobla_varon", "numerador": "pobla_varon"},
                                       {"producto": "nbi_mujer", "numerador": "nbi_mujer"},
                                       {"producto": "nbi_varon", "numerador": "nbi_varon"}]
    cfg["cruce"]["variables"] = None
    def grupos(t, m, v, u, r):
        return {"total": t, "mujer": m, "varon": v, "urbano": u, "rural": r}
    cfg["tablas"] = {
        "urbano_rural": {"pais": "persona", "td": "radio"},
        "variables": {
            "poblacion": {"censo": grupos("pobla_total", "pobla_mujer", "pobla_varon", "pobla_total_urbana",
                                          "pobla_total_rural"),
                          "td": grupos("poblacion_dasimetrica", "pobla_mujer", "pobla_varon", "-", "-")},
            "nbi": {"censo": grupos("nbi_total", "nbi_mujer", "nbi_varon", "nbi_urbana", "nbi_rural"),
                    "td": grupos("nbi", "nbi_mujer", "nbi_varon", "-", "-")},
        },
        "salidas": [{"nombre": "nbi", "variable": "nbi", "por": "grupos", "formula": "incidencia"},
                    {"nombre": "pob", "variable": "poblacion", "por": "grupos", "formula": "exposicion"}],
    }
    ruta.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
    e = ejecutar(ruta, insumos=insumos, salida=tmp_path / "ejecuciones",
                 etapas=[*ETAPAS_03, "cruce", "tablas"])
    d = e.carpeta / "6_tablas"
    ind = pd.read_csv(d / "indicadores.csv").set_index(["ambito", "region", "variable", "grupo"])
    largo = pd.read_csv(e.carpeta / "4_cruce" / "cruce_largo.csv")
    td_pob = largo[(largo.binario == "degradada") & (largo.variable == "poblacion_dasimetrica")]["valor"].sum()
    td_nbi = largo[(largo.binario == "degradada") & (largo.variable == "nbi")]["valor"].sum()
    assert ind.loc[("pais", "NACIONAL", "poblacion", "total"), "n"] == pytest.approx(165)
    assert ind.loc[("td", "NACIONAL", "poblacion", "total"), "n"] == pytest.approx(td_pob)
    assert ind.loc[("td", "NACIONAL", "nbi", "total"), "incidencia"] == pytest.approx(100 * td_nbi / td_pob)
    assert ind.loc[("td", "NACIONAL", "poblacion", "total"), "exposicion"] == pytest.approx(100 * td_pob / 165)
    t = pd.read_csv(d / "pob.csv")
    assert set(t["formula"]) == {"exposicion"}
    u = unir_periodos({2010: e.carpeta, 2022: e.carpeta}, tmp_path / "unidas")
    assert {"n_td_2010", "pct_td_2022"} <= set(u["nbi"].columns)



def _metodo_y_archivos(tmp_path: Path, insumos: Path) -> tuple[Path, dict]:  # noqa: F811
    """Separa la configuración de prueba en método (YAML sin rutas ni año) e insumos con nombres libres."""
    import shutil as sh

    cfg = yaml.safe_load(_con_cruce(tmp_path, insumos).read_text(encoding="utf-8"))
    otra = tmp_path / "mis_datos"
    otra.mkdir()
    archivos = {"tabla_censo": "censo.xlsx", "radios": "radios_2010.zip", "regiones": "regiones.gpkg",
                "mapbiomas": "cobertura.tif", "degradacion": "tematica.tif"}
    rutas = {}
    for rol, original in archivos.items():
        nuevo = otra / f"cualquier_nombre_{rol}{Path(original).suffix}"
        sh.copy(insumos / original if (insumos / original).exists() else insumos / cfg["insumos"][rol]["ruta"],
                nuevo)
        rutas["cobertura" if rol == "mapbiomas" else rol] = str(nuevo)
    for clave in ("insumos", "anio_censo", "nombre"):
        cfg.pop(clave, None)
    cfg.pop("radios", None)
    cfg["radios"] = {"union": "inner", "id_desde": "tabla"}       # sin campo de código: se detecta
    cfg["aplicacion"] = "prueba"
    cfg["cobertura"].pop("insumo", None)
    cfg["cruce"].pop("insumo", None)
    metodo = tmp_path / "metodo.yaml"
    metodo.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
    return metodo, rutas


def test_insumos_por_rol_con_cualquier_nombre(tmp_path: Path, insumos: Path) -> None:  # noqa: F811
    metodo, rutas = _metodo_y_archivos(tmp_path, insumos)
    e = ejecutar(metodo, anio=2010, insumos=rutas, salida=tmp_path / "ejecuciones")
    assert e.carpeta.name == "prueba_2010"
    assert (e.carpeta / "4_cruce" / "cruce_largo.csv").exists()
    assert _suma(e.carpeta / "3_dasimetria" / "poblacion_dasimetrica_2010.tif") == pytest.approx(165, abs=1e-3)
    assert (e.carpeta / "metodo.yaml").exists()


def test_solo_los_insumos_necesarios(tmp_path: Path, insumos: Path) -> None:  # noqa: F811
    from poblar.config import ErrorConfig

    metodo, rutas = _metodo_y_archivos(tmp_path, insumos)
    sin_dt = {k: v for k, v in rutas.items() if k != "degradacion"}
    e = ejecutar(metodo, anio=2010, insumos=sin_dt, salida=tmp_path / "ejecuciones")
    assert (e.carpeta / "3_dasimetria").exists()
    assert not (e.carpeta / "4_cruce").exists()          # sin mapa de degradación no hay cruce
    with pytest.raises(ErrorConfig, match="degradacion"):
        ejecutar(metodo, anio=2010, insumos=sin_dt, salida=tmp_path / "ejecuciones", etapas=["cruce"])
    with pytest.raises(ErrorConfig, match="desconocidos"):
        ejecutar(metodo, anio=2010, insumos={**rutas, "censo": "x"}, salida=tmp_path / "otra")
    # retomar: solo el mapa de degradación y las etapas que faltan
    e2 = ejecutar(metodo, anio=2010, insumos={"degradacion": rutas["degradacion"]},
                  salida=tmp_path / "ejecuciones")
    assert (e2.carpeta / "4_cruce" / "cruce_largo.csv").exists()
    import pandas as pd

    registrados = set(pd.read_csv(e2.carpeta / "0_insumos" / "insumos.csv")["insumo"])
    assert {"tabla_censo", "radios", "regiones", "cobertura", "degradacion"} <= registrados


def test_informe_y_vistas(tmp_path: Path, insumos: Path) -> None:  # noqa: F811
    from poblar import vista

    metodo, rutas = _metodo_y_archivos(tmp_path, insumos)
    e = ejecutar(metodo, anio=2010, insumos=rutas, salida=tmp_path / "ejecuciones")
    informe = (e.carpeta / f"informe_{e.carpeta.name}.html").read_text(encoding="utf-8")
    for texto in ("Controles", "Resultados", "Mapas", "data:image/png;base64", "Tablas de indicadores"):
        assert texto in informe
    assert {"poblacion", "degradacion", "expuesta", "cobertura"} <= set(vista.productos(e.carpeta))
    fig = vista.mapa(e.carpeta, "nbi", ancho_px=50)
    assert fig is not None


def test_informe_explica_advertencias_de_conservacion(tmp_path: Path) -> None:
    import pandas as pd

    from poblar.informe import _explicacion_conservacion, _numeros_es

    assert _numeros_es("raster 4,297,055.6 vs censo 4,297,176 (dif -120.4)") == \
        "raster 4.297.055,6 vs censo 4.297.176 (dif -120,4)"
    (tmp_path / "3_dasimetria").mkdir()
    pd.DataFrame({"id_radio": ["1", "2"], "pobla_total": [30, 50],
                  "tipo_asignacion": ["contingencia", "contingencia_extrema"]}).to_csv(
        tmp_path / "3_dasimetria" / "contingencias.csv", index=False)
    no = pd.DataFrame({"etapa": ["3_dasimetria"], "nombre": ["conservación de nbi"],
                       "detalle": ["raster 880 vs censo 1000"], "valor": [880.0], "esperado": [1000.0]})
    texto = _explicacion_conservacion(tmp_path, no)
    assert "1 radios (50 personas)" in texto
    assert "120 personas (12,0000 %)" in texto


def test_reutilizar_etapas_de_otra_ejecucion(tmp_path: Path, insumos: Path) -> None:  # noqa: F811
    import json

    metodo, rutas = _metodo_y_archivos(tmp_path, insumos)
    base = ejecutar(metodo, anio=2010, insumos=rutas, salida=tmp_path / "ejecuciones")
    cfg = yaml.safe_load(metodo.read_text(encoding="utf-8"))
    cfg["cruce"]["clases"] = [dict(c, binario=None) if c.get("binario") not in (None, cfg["cruce"]["grupo_expuesto"])
                              else c for c in cfg["cruce"]["clases"]]   # cambia solo el cruce
    otro = tmp_path / "metodo_otro.yaml"
    otro.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
    e = ejecutar(otro, anio=2010, insumos=rutas, salida=tmp_path / "ejecuciones", nombre="variante",
                 base=base.carpeta)
    reut = json.loads((e.carpeta / "reutilizado.json").read_text(encoding="utf-8"))
    assert reut["etapas"] == ["radios", "grilla", "dasimetria"]
    assert (e.carpeta / "4_cruce" / "cruce_largo.csv").exists()
    import pandas as pd

    ctrl = pd.read_csv(e.carpeta / "controles.csv")
    assert {"1_radios", "3_dasimetria", "4_cruce"} <= set(ctrl["etapa"])   # se conservan los de la base
    # con los mismos criterios se reutiliza todo lo que existe
    e2 = ejecutar(metodo, anio=2010, insumos=rutas, salida=tmp_path / "ejecuciones", nombre="igual",
                  base=base.carpeta)
    assert "cruce" in json.loads((e2.carpeta / "reutilizado.json").read_text(encoding="utf-8"))["etapas"]
    from poblar.tablas import comparar

    if (base.carpeta / "6_tablas").exists():
        assert comparar(base.carpeta, base.carpeta).empty
        assert len(comparar(base.carpeta, base.carpeta, solo_distintos=False)) > 0


def test_variar_metodo_y_etapas_afectadas(tmp_path: Path) -> None:
    from poblar.config import _leer_yaml, variar
    from poblar.ejecutar import etapas_afectadas

    base = Path(__file__).parents[1] / "aplicaciones" / "prais2026" / "metodo.yaml"
    ruta = variar(base, {"cruce.ambito_reporte.Mixto": "Urbano"}, tmp_path / "v.yaml", quitar=["publicacion"])
    cfg = _leer_yaml(ruta)
    assert cfg["cruce"]["ambito_reporte"]["Mixto"] == "Urbano" and "publicacion" not in cfg
    assert ruta.read_text(encoding="utf-8").startswith("# Variante de metodo.yaml")
    assert etapas_afectadas(["cruce.ambito_reporte.Mixto"]) == ["cruce", "tablas"]
    assert etapas_afectadas(["tablas.urbano_rural.pais"]) == ["tablas"]
    assert etapas_afectadas(["grilla_trabajo.modo"]) == ["grilla", "dasimetria", "cruce", "publicacion", "tablas"]
    assert etapas_afectadas(["region.umbral_vecino_km"])[0] == "radios"
