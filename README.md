# poblar

Calcula la **población expuesta a la degradación de tierras** a partir de un censo por radio, una cobertura del suelo y un mapa de degradación. Produce los indicadores del Objetivo Estratégico 2 de la CNULD (SO2-1 pobreza, SO2-2 agua, SO2-3 población expuesta) como rasters y tablas, con cada criterio escrito en un archivo de configuración y cada paso controlado y registrado.

Se desarrolló para el OE2 del Informe Nacional PRAIS 2026 de la Argentina (ONDTyD). El método de esa aplicación está en [`aplicaciones/prais2026/`](aplicaciones/prais2026/) y sirve para otros períodos con solo indicar el año y los archivos; con otro tipo de insumos (otra cobertura, otro mapa de degradación, otro país) se adapta el método ([guía](docs/nueva_aplicacion.md)).

## Qué necesita y qué produce

| Entra | Sale |
|---|---|
| Tabla censal por radio: población total, por sexo y urbana/rural, NBI y agua de red | Rasters de población y de cada variable en una grilla métrica |
| Cartografía de radios censales | Tablas de población por región, ámbito y categoría de degradación |
| Cobertura del suelo (por ejemplo, MapBiomas) | Capas de entrega en la grilla de la cobertura (EPSG:4326) |
| Mapa de degradación de tierras | Tablas de indicadores (país y tierras degradadas) con la fórmula de la CNULD |
| Regiones de reporte | Controles, balance y sha256 de todo lo producido |

## Cómo se usa

Una ejecución se arma con tres cosas: el **método** (un YAML con los criterios, igual para todos los períodos), el **año** y los **insumos**, cada uno con su ruta, se llame como se llame:

```python
from poblar import ejecutar

ejecutar("aplicaciones/prais2026/metodo.yaml",
         anio=2030,
         insumos={
             "tabla_censo": "datos/censo_2030_por_radio.xlsx",
             "radios":      "datos/radios_2030.gpkg",
             "regiones":    "datos/regiones.gpkg",
             "cobertura":   "datos/cobertura_2029.tif",
             "degradacion": "datos/degradacion_2030.tif",
         },
         salida="ejecuciones",            # se crea ejecuciones/<aplicacion>_<año>/
         trabajo="/content/trabajo")      # opcional: procesar en disco local y copiar al final
```

Solo hacen falta los insumos de las etapas que se quieran correr: sin mapa de degradación, se producen los rasters de población y sus capas publicadas, y se omiten el cruce y las tablas (`pipeline.log` dice por qué). Al repetir una ejecución con el mismo nombre se retoma la carpeta existente; por ejemplo, para agregar después el cruce alcanza con `insumos={"degradacion": ...}`.

Para reproducir un período ya publicado, `registro=` agrega las huellas (sha256) de los insumos oficiales y las cifras esperadas: si un archivo no es el oficial, la ejecución se detiene; si una cifra no se reproduce, queda una advertencia. Ver [`aplicaciones/prais2026/`](aplicaciones/prais2026/).

En Colab: [`cuadernos/ejecutar_en_colab.ipynb`](cuadernos/ejecutar_en_colab.ipynb) (formulario con el año y los archivos, informe y mapas al final).

## Etapas

| # | Etapa | Hace |
|---|---|---|
| 0 | `insumos` | Verifica que existan, registra sha256 y metadatos, compara con el sha256 del registro |
| 1 | `radios` | Une tabla y cartografía, repara geometrías, asigna región, ordena para rasterizar |
| 2 | `grilla` | Lleva la cobertura a la grilla de trabajo y la reclasifica en urbano / no urbano / no habitable |
| 3 | `dasimetria` | Distribuye la población de cada radio en sus píxeles habitables y genera un raster por variable |
| 4 | `cruce` | Cruza la población con el mapa de degradación por región, ámbito y categoría |
| 5 | `publicacion` | Reproyecta los rasters a la grilla de entrega conservando el total de personas |
| 6 | `tablas` | Calcula los indicadores del país y de las tierras degradadas con la fórmula declarada |

Insumos que necesita cada etapa: `radios` → tabla censal, radios y regiones; `grilla` y `publicacion` → cobertura; `cruce` → mapa de degradación.

Detalle de cada etapa: [`docs/metodo.md`](docs/metodo.md). Todas las claves del método y de los insumos: [`docs/configuracion.md`](docs/configuracion.md).

## Controles

Cada etapa verifica lo que produce y lo deja en `controles.csv`: población conservada en total y por radio, sexo y ámbito que cierran con el total, clases de la cobertura y del mapa de degradación todas declaradas, grillas alineadas, masa conservada al reproyectar. Un control **bloqueante** que falla detiene la ejecución (o solo advierte, con `controles.modo: advertir`); los no bloqueantes quedan como advertencia. Un registro de período (`registro=`) permite fijar cifras conocidas, por ejemplo las oficiales, y avisa si una ejecución deja de reproducirlas.

## Productos de una ejecución

```
ejecuciones/<nombre>/
  informe_<nombre>.html               controles, cifras, mapas y tablas, para abrir en el navegador
  config.yaml                         configuración efectiva (método + año + insumos)
  metodo.yaml, registro.yaml          copias de los archivos usados
  entorno.txt                         versiones de Python, librerías, GDAL y commit de poblar
  controles.csv, balance.csv          controles y conteos de cada paso
  manifiesto.csv                      sha256 de todos los archivos
  pipeline.log
  0_insumos/   insumos.csv
  1_radios/    radios.parquet y radios descartados o reasignados (CSV)
  2_grilla/    cobertura.tif (metacategorías), grilla.json
  3_dasimetria/ poblacion_dasimetrica_<año>.tif, <variable>_dasimetrico_<año>.tif, ponderadores.csv, contingencias.csv
  4_cruce/     cruce_largo.csv, cruce_binario.csv, cruce_ancho.csv, resumen_expuesta.csv
  5_publicacion/ capas de entrega y publicacion.csv
  6_tablas/    indicadores.csv y una tabla por indicador
```

Para mirar un producto en un cuaderno: `poblar.vista.mapa(carpeta, "expuesta", region="Chaco")`. Con dos años ejecutados, `poblar.tablas.unir_periodos` arma las tablas con una columna por período, y `poblar.verificar.comparar_raster` compara dos rasters píxel por píxel (por ejemplo, la misma capa con dos configuraciones).

## Instalación

```bash
pip install "git+https://github.com/AugustoBellanich/poblar@main"
```

Requiere Python 3.10 o posterior y las herramientas de línea de comandos de GDAL (`gdalwarp`, `gdal_rasterize`; en Colab y Ubuntu: `apt-get install gdal-bin`).

Desarrollo y pruebas (caso sintético con resultado conocido):

```bash
pip install -e ".[dev]"
python -m pytest -q
```

## Datos

Los datos no se guardan en este repositorio. Cada configuración registra el nombre, el origen y el sha256 de sus insumos.

## Licencia

[Apache 2.0](LICENSE). La licencia cubre el código; los insumos conservan sus propias licencias. Autoría: [`AUTORES.md`](AUTORES.md).
