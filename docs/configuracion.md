# Configuración

Una ejecución se define en un archivo YAML. Las claves marcadas **obligatoria** deben estar si se corre la etapa correspondiente; si falta alguna, la ejecución no comienza y el error lista todas las que faltan. Las demás tienen el valor por defecto indicado.

Ejemplo completo: [`aplicaciones/prais2026/configs/2022.yaml`](../aplicaciones/prais2026/configs/2022.yaml).

## General

| Clave | Tipo | | Descripción |
|---|---|---|---|
| `nombre` | texto | obligatoria | Nombre de la ejecución y de su carpeta de salida |
| `anio_censo` | entero | obligatoria | Año del censo; se usa en los nombres de los productos |

## `insumos`

Un bloque por insumo. Las rutas relativas se resuelven contra la carpeta `insumos=` de `ejecutar`.

| Clave | Descripción |
|---|---|
| `<insumo>.ruta` | Archivo. Obligatorias: `tabla_censo`, `radios`, `regiones`; las etapas 2, 4 y 5 usan los insumos que nombran (`cobertura.insumo`, `cruce.insumo`, `publicacion.grilla_referencia`) |
| `<insumo>.sha256` | Huella esperada. Si no coincide, la ejecución se detiene. `null` = solo se registra |
| `<insumo>.capa` | Capa de un GeoPackage (vectores) |
| `<insumo>.archivo_interno` | Archivo dentro de un `.zip` (vectores) |
| `<insumo>.hoja` | Hoja de un Excel (tabla censal; por defecto la primera) |
| `<insumo>.encoding` | Codificación de un CSV (por defecto `utf-8`) |

La tabla censal debe tener `id_radio`, el campo de tipo de radio (`dasimetria.campo_ambito`) y los campos que nombran `dasimetria.variables` y `tablas.variables` (en la aplicación PRAIS 2026: `pobla_total`, `pobla_mujer`, `pobla_varon`, `pobla_total_urbana`, `pobla_total_rural`, `nbi_*`, `agua_red_*`).

## `radios`

| Clave | | Valores | Descripción |
|---|---|---|---|
| `campo_codigo_mapa` | obligatoria | texto | Campo con el código de radio en la cartografía |
| `union` | obligatoria | `inner` \| `left` | `inner`: radios en tabla y mapa. `left`: todos los del mapa; los que no tienen dato censal quedan con población 0 |
| `id_desde` | obligatoria | `tabla` \| `mapa` | De dónde se toma el código del radio integrado |
| `orden` | | `area_desc` (defecto) \| `area_desc_estable` | Orden de rasterización. `area_desc_estable` desempata por código |
| `exportar_gpkg` | | `false` | Además del parquet, escribe un GeoPackage |

## `region`

| Clave | | Descripción |
|---|---|---|
| `campo` | obligatoria | Campo de región en la capa de regiones |
| `umbral_vecino_km` | obligatoria | Distancia máxima para asignar un radio sin intersección a la región más cercana |
| `etiqueta_fuera` | obligatoria | Región de los radios sin intersección y más lejos que el umbral |
| `excluir_fuera` | obligatoria | `true`: esos radios se excluyen (y su población se informa) |

## `grilla_trabajo`

| Clave | | Valores | Descripción |
|---|---|---|---|
| `crs` | obligatoria | código EPSG | CRS métrico de trabajo |
| `modo` | obligatoria | `gdal_auto` \| `fija` | Resolución estimada por GDAL o fija |
| `resolucion_m` | con `modo: fija` | metros | Tamaño de píxel |
| `extension` | obligatoria | `radios` \| `regiones` | Extensión de la grilla |
| `remuestreo_cobertura` | obligatoria | `near` \| `mode` | Remuestreo de la cobertura a la grilla |

## `cobertura`

| Clave | | Descripción |
|---|---|---|
| `insumo` | obligatoria | Nombre del insumo de cobertura |
| `codigo_nodata` | obligatoria | Valor de la cobertura que significa sin dato (se trata como no habitable) |
| `clases` | obligatoria | Lista `{clase, descripcion, meta}`; `meta`: `no_habitable` \| `urbano` \| `no_urbano`. Todas las clases presentes deben estar |

## `dasimetria`

| Clave | | Descripción |
|---|---|---|
| `campo_ambito` | obligatoria | Campo de tipo de radio en la tabla censal |
| `ambitos` | obligatoria | Valores de ese campo (por ejemplo `[Urbano, Mixto, Rural]`) |
| `ponderadores.normalizar_por` | obligatoria | Ámbito de referencia: su densidad mediana vale 1 |
| `ponderadores.peso_urbano` | obligatoria | `complemento` (1 − peso no urbano) \| `uno` |
| `producto_poblacion` | | Nombre del raster de población (defecto `poblacion_dasimetrica`) |
| `variables` | obligatoria | Lista `{producto, numerador}`: raster `<producto>_dasimetrico_<año>.tif` = población × numerador ÷ población del radio |

## `cruce`

| Clave | | Descripción |
|---|---|---|
| `insumo` | obligatoria | Nombre del insumo del mapa de degradación (u otra capa categórica) |
| `banda` | | Banda a leer (defecto 1) |
| `clases` | obligatoria | Lista `{clase, etiqueta, binario}`; `binario`: grupo de la clase (por ejemplo `degradada`) o `null` para dejarla fuera del binario. Todas las clases presentes deben estar |
| `grupo_expuesto` | obligatoria para `tablas` | Grupo de `binario` que se informa como expuesto |
| `ambito_reporte` | | Agrupación de tipos de radio para informar (por ejemplo `{Mixto: Rural}`) |
| `variables` | | Productos de la etapa 3 a cruzar (defecto: todos) |
| `derivadas` | | Lista `{nombre, total, resta}`: variable = total − resta, calculada en la tabla |
| `rasters_por_grupo` | | Lista de grupos: genera un raster por variable con valor solo en ese grupo |

## `publicacion`

| Clave | | Descripción |
|---|---|---|
| `grilla_referencia` | obligatoria | Insumo cuya grilla se usa para publicar |
| `remuestreo` | obligatoria | `sum` (conserva cantidades) \| `average` \| `near` |
| `productos` | obligatoria | Producto de la etapa 3 → nombre de entrega |
| `plantilla_nombre` | | Nombre del archivo (defecto `{nombre}_{anio}.tif`; también acepta `{producto}`) |
| `bloque` | | Tamaño del bloque de destino en píxeles (defecto 1024; no cambia resultados) |
| `compresion` | | Compresión del GeoTIFF (defecto `deflate`) |
| `procesos` | | Rasters en paralelo (defecto: todos los núcleos; no cambia resultados) |
| `tolerancia_masa_pct` | | Diferencia de suma admitida antes de advertir (defecto 0,001 %) |

## `tablas`

| Clave | | Descripción |
|---|---|---|
| `urbano_rural.pais`, `urbano_rural.td` | obligatoria | `persona` (campos urbana/rural del censo) \| `radio` (tipo de radio con `cruce.ambito_reporte`) |
| `variables` | obligatoria | Por variable: `censo` (campos de la tabla censal por grupo: `total`, `mujer`, `varon`, `urbano`, `rural`) y `td` (productos del cruce por grupo) |
| `variable_poblacion` | | Variable que es la población (defecto `poblacion`); denominador de la incidencia |
| `salidas` | obligatoria | Lista `{nombre, variable, por: grupos \| regiones, formula: incidencia \| exposicion \| composicion, grupos}` |

## Control y rendimiento

| Clave | Defecto | Descripción |
|---|---|---|
| `referencia.poblacion_integrada` | — | Población esperada después de integrar tabla y mapa (control bloqueante) |
| `controles.modo` | `detener` | `detener`: un control bloqueante que falla detiene la ejecución; `advertir`: solo lo registra |
| `controles.tolerancia_personas` | 0 | Diferencia admitida en controles de conteo de la etapa 1 |
| `controles.tolerancia_conservacion_pct` | 0,001 | Diferencia relativa admitida en la conservación de la población (etapa 3) |
| `controles.tolerancia_radio_personas` | 0,5 | Diferencia admitida por radio (etapa 3) |
| `controles.tolerancia_personas_cruce` | 1 | Población no cruzada admitida antes de advertir (etapa 4) |
| `controles.consistencia_bloqueante` | `true` | Si los cierres sexo/ámbito de la etapa 1 detienen la ejecución |
| `rendimiento.filas_por_bloque` | 512 | Filas por bloque al recorrer rasters (memoria; no cambia resultados) |
| `resultados_esperados` | — | Cifras conocidas a reproducir (no bloqueantes): `radios.total`, `radios.por_region`, `grilla.ancho`/`alto`, `poblacion_raster`, `cruce.<variable>` (en el grupo expuesto), `publicacion.<producto>` |
