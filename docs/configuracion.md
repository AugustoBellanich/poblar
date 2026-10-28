# Configuración

Una ejecución combina tres partes:

| Parte | Dónde | Qué tiene |
|---|---|---|
| **Método** | YAML (`metodo=`) | Los criterios: todas las secciones de abajo salvo `insumos`. Es el mismo para todos los períodos de una aplicación |
| **Año e insumos** | Al ejecutar (`anio=`, `insumos=`) | Los archivos de esta ejecución, por rol, con cualquier nombre |
| **Registro** (opcional) | YAML (`registro=`) | Datos fijos de un período publicado: `anio`, `nombre`, huella y datos de cada insumo, `referencia`, `resultados_esperados` |

Las claves marcadas **obligatoria** deben estar en el método si se corre la etapa correspondiente; con `etapas="todas"`, una etapa que el método no define se omite. Las demás claves tienen el valor por defecto indicado.

Ejemplo: [`aplicaciones/prais2026/metodo.yaml`](../aplicaciones/prais2026/metodo.yaml) y [`periodos/2022.yaml`](../aplicaciones/prais2026/periodos/2022.yaml).

## General

| Clave | Dónde | Descripción |
|---|---|---|
| `aplicacion` | método | Nombre de la aplicación; la ejecución se llama `<aplicacion>_<año>` |
| `anio` | `anio=` o registro | Año del período; se usa en los nombres de los productos |
| `nombre` | `nombre=` o registro | Otro nombre para la ejecución (opcional) |

## Insumos

Se pasan al ejecutar como `{rol: ruta}`; solo los que necesitan las etapas a correr.

| Rol | Etapas que lo usan | Contenido |
|---|---|---|
| `tabla_censo` | `radios` | Una fila por radio: `id_radio`, tipo de radio (`dasimetria.campo_ambito`) y los conteos que nombran `dasimetria.variables` y `tablas.variables`. Excel o CSV |
| `radios` | `radios` | Polígonos de los radios con su código |
| `regiones` | `radios` | Polígonos con el campo `region.campo` |
| `cobertura` | `grilla`, `publicacion` | Raster categórico de cobertura del suelo |
| `degradacion` | `cruce` | Raster categórico de degradación (u otra capa temática) |

En lugar de la ruta sola, cada insumo acepta un bloque con datos del archivo:

| Dato | Insumo | Descripción |
|---|---|---|
| `ruta` | todos | Archivo |
| `sha256` | todos | Huella esperada; si no coincide, la ejecución se detiene (suele venir del registro) |
| `campo_codigo` | `radios` | Campo con el código de radio. Si no se indica, se detecta: el campo cuyos valores coinciden con más códigos de la tabla censal (al menos la mitad) |
| `banda` | `degradacion` | Banda a leer (defecto 1) |
| `capa` | vectores | Capa de un GeoPackage |
| `archivo_interno` | vectores | Archivo dentro de un `.zip` |
| `hoja` | `tabla_censo` | Hoja de un Excel (defecto la primera) |
| `encoding` | `tabla_censo` | Codificación de un CSV (defecto `utf-8`) |

`insumos=` también puede ser una carpeta: entonces las rutas son los nombres sugeridos del registro, dentro de esa carpeta.

## `radios`

| Clave | | Valores | Descripción |
|---|---|---|---|
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
| `clases` | obligatoria | Lista `{clase, etiqueta, binario}`; `binario`: grupo de la clase (por ejemplo `degradada`) o `null` para dejarla fuera del binario. Todas las clases presentes deben estar |
| `grupo_expuesto` | obligatoria para `tablas` | Grupo de `binario` que se informa como expuesto |
| `ambito_reporte` | | Agrupación de tipos de radio para informar (por ejemplo `{Mixto: Rural}`) |
| `variables` | | Productos de la etapa 3 a cruzar (defecto: todos) |
| `derivadas` | | Lista `{nombre, total, resta}`: variable = total − resta, calculada en la tabla |
| `rasters_por_grupo` | | Lista de grupos: genera un raster por variable con valor solo en ese grupo |

## `publicacion`

| Clave | | Descripción |
|---|---|---|
| `grilla_referencia` | | Insumo cuya grilla se usa para publicar (defecto `cobertura`) |
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
| `referencia.poblacion_integrada` | — | Población esperada después de integrar tabla y mapa (control bloqueante; suele ir en el registro) |
| `controles.modo` | `detener` | `detener`: un control bloqueante que falla detiene la ejecución; `advertir`: solo lo registra |
| `controles.tolerancia_personas` | 0 | Diferencia admitida en controles de conteo de la etapa 1 |
| `controles.tolerancia_conservacion_pct` | 0,001 | Diferencia relativa admitida en la conservación de la población (etapa 3) |
| `controles.tolerancia_radio_personas` | 0,5 | Diferencia admitida por radio (etapa 3) |
| `controles.tolerancia_personas_cruce` | 1 | Población no cruzada admitida antes de advertir (etapa 4) |
| `controles.consistencia_bloqueante` | `true` | Si los cierres sexo/ámbito de la etapa 1 detienen la ejecución |
| `rendimiento.filas_por_bloque` | 512 | Filas por bloque al recorrer rasters (memoria; no cambia resultados) |
| `resultados_esperados` | — | Cifras conocidas a reproducir (no bloqueantes; suelen ir en el registro): `radios.total`, `radios.por_region`, `grilla.ancho`/`alto`, `poblacion_raster`, `cruce.<variable>` (en el grupo expuesto), `publicacion.<producto>` |
