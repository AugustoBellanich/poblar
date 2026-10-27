"""Etapas 2 y 3 con un caso sintético.

La cobertura sintética está en EPSG:4326 (como MapBiomas) sobre las mismas dos
regiones de la prueba de las etapas 0 y 1. Se verifica la conservación, las
contingencias y que el atajo de pesos por búsqueda equivale a rasterizar los
pesos con ``gdal_rasterize`` (el método del C2).

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

    e = ejecutar(_con_cruce(tmp_path, insumos), insumos=insumos, salida=tmp_path / "ejecuciones")
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
