# poblar

Distribuye datos censales (población, sexo, ámbito, NBI, agua de red) desde los radios censales a una grilla, usando la cobertura del suelo, y los cruza con capas temáticas (por ejemplo, degradación de tierras). Cada ejecución registra qué insumos se usaron, con qué criterios y qué controles cumplió.

Primera aplicación: **OE2 del Informe Nacional PRAIS 2026** (CNULD, ONDTyD). Ver [`aplicaciones/prais2026/`](aplicaciones/prais2026/).

## Cómo funciona

Una ejecución se define en un archivo de configuración YAML: insumos, criterios, grilla, tolerancias y productos. No hay valores implícitos en el código: si falta un criterio, la ejecución no comienza.

```python
from poblar import ejecutar
ejecutar("aplicaciones/prais2026/configs/2010.yaml", insumos="ruta/a/insumos", salida="ejecuciones")
```

En Colab: [`cuadernos/ejecutar_en_colab.ipynb`](cuadernos/ejecutar_en_colab.ipynb).

### Etapas

| # | Etapa | Estado |
|---|---|---|
| 0 | Registro de insumos (hash, metadatos, controles) | ✔ |
| 1 | Base de radios (tabla + cartografía, región, orden de rasterización) | ✔ |
| 2 | Grilla de trabajo y cobertura del suelo | ✔ |
| 3 | Mapeo dasimétrico | ✔ |
| 4 | Cruce con capas temáticas | ✔ |
| 5 | Publicación (rasters) | ✔ |
| 6 | Tablas de indicadores (país y TD, fórmulas de la CNULD) | ✔ |

### Productos de cada ejecución

```
ejecuciones/<nombre>/
  config.yaml, config_original.yaml   configuración ejecutada
  entorno.txt                         versiones de Python, librerías y GDAL
  0_insumos/insumos.csv               sha256 y metadatos de cada insumo
  1_radios/radios.parquet             radios listos para la grilla
  1_radios/*.csv                      radios sin cartografía, duplicados, sin intersección, fuera de región
  balance.csv                         qué entra y qué sale de cada paso
  controles.csv                       cada control, con su resultado
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

Las pruebas usan un caso sintético (cinco radios, dos regiones) con resultado conocido de antemano.

## Relación con otras herramientas

[`tobler`](https://pysal.org/tobler/stable/) (PySAL) implementa interpolación areal y mapeo dasimétrico general. `poblar` implementa el método específico del OE2 (ponderadores por región y ámbito, contingencias, cruce con degradación y publicación) y su trazabilidad.

## Datos

Los datos no se guardan en este repositorio: las configuraciones registran nombre, origen y sha256 de cada insumo.

## Documentación

- [`docs/guia_de_estilo.md`](docs/guia_de_estilo.md): glosario y convenciones de redacción.
- [`docs/decisiones.md`](docs/decisiones.md): registro de decisiones de diseño.
- [`docs/esquema_pipeline.html`](docs/esquema_pipeline.html): esquema del flujo completo.

## Licencia

[Apache 2.0](LICENSE). Motivos en [`docs/decisiones.md`](docs/decisiones.md#d-001--licencia-apache-20-27102026). La licencia cubre el código; los insumos conservan sus propias licencias.
