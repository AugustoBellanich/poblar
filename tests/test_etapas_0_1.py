"""Prueba con un caso sintético chico donde la respuesta se conoce a mano.

Correr: ``python -m pytest -q``
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pytest
import yaml
from shapely.geometry import box

from poblar import ejecutar
from poblar.config import ErrorConfig
from poblar.trazabilidad import ControlFallido

X0, Y0 = 4_500_000, 6_000_000  # coordenadas plausibles en EPSG:5347
FUERA = "Fuera de Región (Antártida/Islas)"


def _caja(x: float, y: float, ancho: float, alto: float | None = None):
    return box(X0 + x, Y0 + y, X0 + x + ancho, Y0 + y + (alto or ancho))


@pytest.fixture()
def insumos(tmp_path: Path) -> Path:
    d = tmp_path / "insumos"
    d.mkdir()
    # Dos regiones contiguas de 10 km x 10 km
    gpd.GeoDataFrame(
        {"Reg_PRAIS": ["Norte", "Sur"]},
        geometry=[_caja(0, 10_000, 10_000), _caja(0, 0, 10_000)],
        crs=5347,
    ).to_file(d / "regiones.gpkg", driver="GPKG")

    radios = gpd.GeoDataFrame(
        {"COD_2010": ["020010101", "020010102", "020010103", "020010104", "020010105"]},
        geometry=[
            _caja(1_000, 12_000, 2_000),          # 101: dentro de Norte
            _caja(2_000, 8_000, 3_000, 4_000),    # 102: 2 km en Sur, 2 km en Norte → empate; ver abajo
            _caja(-5_000, 12_000, 1_000),         # 103: a 4 km de Norte → sin intersección, cercano
            _caja(-200_000, 0, 1_000),            # 104: a 190 km → fuera de región
            _caja(6_000, 2_000, 1_000),           # 105: solo en el mapa
        ],
        crs=5347,
    ).to_crs(3857)
    # 102 queda 3 km en Sur y 1 km en Norte para que no haya empate
    radios.loc[1, "geometry"] = gpd.GeoSeries([_caja(2_000, 7_000, 3_000, 4_000)], crs=5347).to_crs(3857).iloc[0]
    shp = d / "radios_2010"
    shp.mkdir()
    radios.to_file(shp / "radios_2010.shp")
    with zipfile.ZipFile(d / "radios_2010.zip", "w") as z:
        for f in shp.iterdir():
            z.write(f, f.name)

    pd.DataFrame({
        "id_radio": ["20010101", "020010102", "020010103", "020010104", "020010199"],  # el 1.º sin cero adelante
        "ambito": ["Urbano", "Mixto", "Rural", "Rural", "Urbano"],
        "pobla_total": [100, 50, 10, 5, 7],
        "pobla_mujer": [60, 25, 5, 2, 3],
        "pobla_varon": [40, 25, 5, 3, 4],
        "pobla_total_urbana": [100, 30, 0, 0, 7],
        "pobla_total_rural": [0, 20, 10, 5, 0],
        "agua_red_total": [90, 40, 2, 0, 7],
        "nbi_total": [10, 5, 3, 1, 0],
    }).to_excel(d / "tabla_censo2010.xlsx", index=False)
    return d


def _config(tmp_path: Path, **cambios) -> Path:
    cfg = {
        "nombre": "prueba",
        "anio_censo": 2010,
        "insumos": {
            "tabla_censo": {"ruta": "tabla_censo2010.xlsx"},
            "radios": {"ruta": "radios_2010.zip"},
            "regiones": {"ruta": "regiones.gpkg"},
        },
        "radios": {"campo_codigo_mapa": "COD_2010", "union": "inner", "id_desde": "tabla", "orden": "area_desc"},
        "region": {"campo": "Reg_PRAIS", "umbral_vecino_km": 50, "etiqueta_fuera": FUERA,
                   "excluir_fuera": False},
        "grilla_trabajo": {"crs": 5347},
        "referencia": {"poblacion_integrada": 165},
        "controles": {"modo": "detener", "tolerancia_personas": 0},
    }
    for clave, valor in cambios.items():
        nodo = cfg
        *ruta, ultima = clave.split(".")
        for p in ruta:
            nodo = nodo[p]
        if valor is None:
            nodo.pop(ultima, None)
        else:
            nodo[ultima] = valor
    ruta = tmp_path / "config.yaml"
    ruta.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
    return ruta


def test_union_inner_regiones_y_orden(tmp_path: Path, insumos: Path) -> None:
    c = ejecutar(_config(tmp_path), insumos=insumos, salida=tmp_path / "ejecuciones")
    r = gpd.read_parquet(c.carpeta / "1_radios" / "radios.parquet").set_index("id_radio")

    assert len(r) == 4                                  # 105 (solo mapa) y 199 (solo tabla) quedan afuera
    assert r["pobla_total"].sum() == 165
    assert r.loc["020010101", "Reg_PRAIS"] == "Norte"
    assert r.loc["020010102", "Reg_PRAIS"] == "Sur"     # mayor área en Sur
    assert r.loc["020010103", "Reg_PRAIS"] == "Norte"   # sin intersección, a 4 km
    assert r.loc["020010104", "Reg_PRAIS"] == FUERA     # sin intersección, a 190 km
    assert r.crs.to_epsg() == 5347
    # Orden: área descendente → 102 (12 km²) primero
    assert r.sort_values("raster_id").index[0] == "020010102"
    sin_carto = pd.read_csv(c.carpeta / "1_radios" / "radios_sin_cartografia.csv", dtype=str)
    assert sin_carto["id_radio"].tolist() == ["020010199"]
    assert (c.carpeta / "manifiesto.csv").exists()
    assert (c.carpeta / "0_insumos" / "insumos.csv").exists()
    assert all(v.ok for v in c.controles)


def test_union_left_desde_mapa_conserva_radios_sin_dato(tmp_path: Path, insumos: Path) -> None:
    cfg = _config(tmp_path, **{"radios.union": "left", "radios.id_desde": "mapa"})
    c = ejecutar(cfg, insumos=insumos, salida=tmp_path / "ejecuciones")
    r = gpd.read_parquet(c.carpeta / "1_radios" / "radios.parquet").set_index("id_radio")
    assert len(r) == 5
    assert r.loc["020010105", "pobla_total"] == 0


def test_excluir_fuera_de_region(tmp_path: Path, insumos: Path) -> None:
    cfg = _config(tmp_path, **{"region.excluir_fuera": True, "referencia.poblacion_integrada": 160})
    c = ejecutar(cfg, insumos=insumos, salida=tmp_path / "ejecuciones")
    r = gpd.read_parquet(c.carpeta / "1_radios" / "radios.parquet")
    assert FUERA not in set(r["Reg_PRAIS"])
    assert r["pobla_total"].sum() == 160


def test_referencia_distinta_corta(tmp_path: Path, insumos: Path) -> None:
    cfg = _config(tmp_path, **{"referencia.poblacion_integrada": 999})
    with pytest.raises(ControlFallido) as e:
        ejecutar(cfg, insumos=insumos, salida=tmp_path / "ejecuciones")
    assert (e.value.carpeta / "controles.csv").exists()


def test_falta_criterio_no_arranca(tmp_path: Path, insumos: Path) -> None:
    cfg = _config(tmp_path, **{"region.umbral_vecino_km": None})
    with pytest.raises(ErrorConfig):
        ejecutar(cfg, insumos=insumos, salida=tmp_path / "ejecuciones")
