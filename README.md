# poblar

Distribuye datos censales (población, sexo, ámbito, NBI, agua de red) desde los radios censales a una grilla, usando la cobertura del suelo, y los cruza con capas temáticas (por ejemplo, degradación de tierras). Cada corrida deja registro de qué insumos entraron, con qué criterios y qué validaciones pasó.

Primera aplicación: **OE2 del Informe Nacional PRAIS 2026** (CNULD, ONDTyD). Ver [`aplicaciones/prais2026/`](aplicaciones/prais2026/).

## Cómo funciona

Una corrida se define en un archivo YAML: insumos, criterios, grilla, tolerancias y productos. No hay valores escondidos en el código: si falta un criterio, la corrida no arranca.

```python
from poblar import correr
correr("aplicaciones/prais2026/configs/2010.yaml", insumos="ruta/a/insumos", salida="corridas")
```

En Colab: [`cuadernos/correr_en_colab.ipynb`](cuadernos/correr_en_colab.ipynb).

### Etapas

| # | Etapa | Estado |
|---|---|---|
| 0 | Registro de insumos (hash, metadatos, chequeos) | ✔ |
| 1 | Base de radios (tabla + cartografía, región, orden de rasterización) | ✔ |
| 2 | Grilla de trabajo y cobertura del suelo | pendiente |
| 3 | Mapeo dasimétrico | pendiente |
| 4 | Cruce con capas temáticas | pendiente |
| 5 | Publicación (rasters y tablas) | pendiente |

### Qué deja cada corrida

```
corridas/<corrida>/
  config.yaml, config_original.yaml   lo que se corrió
  entorno.txt                         versiones de Python, librerías y GDAL
  0_insumos/insumos.csv               sha256 y metadatos de cada insumo
  1_radios/radios.parquet             radios listos para la grilla
  1_radios/*.csv                      radios sin cartografía, duplicados, huérfanos, fuera de región
  cuentas.csv                         qué entra y qué sale de cada paso
  validaciones.csv                    cada chequeo, con su resultado
  manifiesto.csv                      sha256 de todos los productos
  pipeline.log
```

## Instalación

```bash
pip install "git+https://github.com/AugustoBellanich/poblar@main"
```

Desarrollo y pruebas:

```bash
pip install -e ".[dev]"
python -m pytest -q
```

Las pruebas usan un caso sintético chico (cinco radios, dos regiones) donde el resultado se conoce de antemano.

## Relación con otras herramientas

[`tobler`](https://pysal.org/tobler/stable/) (PySAL) implementa interpolación areal y mapeo dasimétrico general. `poblar` implementa el método específico del OE2 (ponderadores por región y ámbito, contingencias, cruce con degradación y publicación) y su trazabilidad.

## Datos

Los datos no se guardan en este repositorio: los configs registran nombre, origen y sha256 de cada insumo.
