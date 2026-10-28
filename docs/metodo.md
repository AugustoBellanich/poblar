# Método

Qué hace cada etapa, qué controla y qué produce. Las claves citadas están en [`configuracion.md`](configuracion.md).

Con `etapas="todas"` se corren las etapas que el método define, que tienen sus insumos y cuya etapa anterior se corre o ya está en la carpeta de la ejecución. Las omitidas quedan en `pipeline.log` con el motivo.

## 0. Insumos (`insumos`)

Para cada insumo indicado: verifica que exista, calcula su sha256 y lo compara con la huella del registro o la indicada en el insumo (si hay una), y registra metadatos (filas y columnas de tablas; registros, CRS y campos de vectores; tamaño, resolución, CRS y nodata de rasters).

- **Controles:** el archivo existe; el sha256 coincide; los vectores no están vacíos (cuenta registros reales, no solo los metadatos).
- **Produce:** `0_insumos/insumos.csv` y `insumos.json`.

## 1. Radios (`radios`)

1. Lee la tabla censal (código de radio como texto de 9 dígitos) y la cartografía.
2. Identifica el campo de código de radio en la cartografía (el indicado, o el que coincide con más códigos de la tabla) y une tabla y mapa por código (`radios.union`: `inner` o `left`). Los radios que están solo en la tabla o solo en el mapa quedan registrados.
3. Quita duplicados por código, descarta geometrías vacías, pasa al CRS de trabajo y repara geometrías inválidas.
4. Asigna región por área mayoritaria de intersección. Un radio sin intersección va a la región más cercana si está a `region.umbral_vecino_km` o menos; si no, a `region.etiqueta_fuera` (o se excluye, con `region.excluir_fuera: true`).
5. Ordena los radios por área descendente y les asigna `raster_id`: al rasterizar, el último radio que toca un píxel se lo queda, así los radios chicos no desaparecen bajo los grandes.

- **Controles:** sin códigos repetidos; población integrada igual a la de referencia (`referencia.poblacion_integrada`); todos los radios con región; mujeres + varones = total y urbana + rural = total por radio; NBI y agua de red ≤ población.
- **Produce:** `1_radios/radios.parquet` y CSV de radios sin cartografía, duplicados, sin intersección y fuera de región; `resumen_regiones.csv`.

## 2. Grilla y cobertura (`grilla`)

1. Lleva la cobertura del suelo a la grilla de trabajo con `gdalwarp` (CRS `grilla_trabajo.crs`, extensión de los radios o de las regiones, vecino más cercano). Con `modo: gdal_auto` la resolución la estima GDAL; con `modo: fija`, `resolucion_m` alineada a la grilla.
2. Reclasifica cada clase de la cobertura en una metacategoría según `cobertura.clases`: **0 no habitable, 1 urbano, 2 no urbano**.

- **Controles:** todas las clases presentes en la cobertura están en la tabla de clases.
- **Produce:** `2_grilla/cobertura.tif` (metacategorías), `cobertura_trabajo.tif`, `grilla.json`, `clases_presentes.json`.

## 3. Mapeo dasimétrico (`dasimetria`)

Distribuye la población de cada radio entre sus píxeles, con más peso donde la cobertura indica asentamiento.

1. **Raster de radios:** `gdal_rasterize` del `raster_id` sobre la grilla de trabajo, con todos los píxeles que toca cada polígono.
2. **Composición:** píxeles urbanos, no urbanos y totales de cada radio. Densidad del radio = población ÷ píxeles habitables (un radio sin píxeles habitables cuenta como 1 píxel no urbano).
3. **Ponderadores:** para cada región y tipo de radio (`dasimetria.campo_ambito`), la mediana de la densidad. El peso del píxel no urbano es esa mediana dividida por la de los radios urbanos de la región (`normalizar_por`); el del píxel urbano es 1 − ese valor (`peso_urbano: complemento`) o 1 (`uno`). En los radios urbanos los dos pesos valen 1. Los píxeles no habitables pesan 0.
4. **Factor:** población del radio ÷ suma de los pesos de sus píxeles. Población del píxel = peso × factor.
5. **Contingencias:**
   - *Nivel 2:* radio con población y píxeles, pero ninguno habitable → la población se reparte en partes iguales en todos sus píxeles.
   - *Nivel 3:* radio con población y sin ningún píxel propio (lo taparon radios vecinos) → la población se reparte en partes iguales en los píxeles que toca su polígono y se suma a lo que ya hay.
6. **Variables:** para cada entrada de `dasimetria.variables`, raster = población del píxel × (variable ÷ población del radio dueño del píxel).

- **Controles:** población del raster = población integrada (total y por radio, salvo contingencia de nivel 3); conservación de cada variable (advertencia).
- **Nota:** la población de nivel 3 queda en píxeles de otro radio y recibe las tasas de ese radio. Por eso los totales de las variables pueden diferir del censo en unos cientos de personas aunque la población total se conserve exacta.
- **Produce:** `poblacion_dasimetrica_<año>.tif`, `<variable>_dasimetrico_<año>.tif`, `raster_ids_radios.tif`, `pesos_dasimetricos.tif`, `ponderadores.csv`, `contingencias.csv`, `radios_factores.parquet`.

## 4. Cruce con degradación (`cruce`)

1. Lleva el mapa de degradación a la grilla de trabajo (vecino más cercano; banda `cruce.banda`).
2. A cada píxel le asigna la zona región × tipo de radio del radio dueño del píxel.
3. Suma cada variable (`cruce.variables`) por zona y clase del mapa de degradación.
4. Agrupa las clases según `cruce.clases` (columna `binario`; las clases sin grupo, como «sin datos», no entran en el binario) y los tipos de radio según `cruce.ambito_reporte`.
5. Calcula variables derivadas en la tabla (por ejemplo, agua sin red = población − agua de red).

- **Controles:** mapa alineado a la grilla; todas sus clases declaradas; población no cruzada (píxeles sin radio o sin dato de degradación) informada.
- **Produce:** `cruce_largo.csv` (región × ámbito × clase × variable), `cruce_binario.csv`, `cruce_ancho.csv`, `resumen_expuesta.csv` (grupo expuesto, nacional y por región) y, si se pide (`rasters_por_grupo`), un raster por variable con valor solo en el grupo.

## 5. Publicación (`publicacion`)

Reproyecta cada raster de `publicacion.productos` a la grilla de un insumo de referencia (por ejemplo, la cobertura en EPSG:4326) con remuestreo por suma, recorriendo el destino por bloques. Los rasters se procesan en paralelo; cada uno se guarda al terminar y, si la ejecución se corta, al retomarla se saltean los ya publicados.

- **Controles:** grilla igual a la de referencia; suma publicada vs. suma de origen (advertencia si supera `tolerancia_masa_pct`). La población de radios que quedan fuera de la extensión de la grilla de referencia no se publica.
- **Produce:** las capas con el nombre de `plantilla_nombre` y `publicacion.csv`.

## 6. Tablas (`tablas`)

Para cada variable (población, NBI, agua de red), grupo (total, mujeres, varones, urbano, rural) y región, la cantidad en el país (suma de la tabla censal sobre los radios integrados) y en el grupo expuesto del cruce. Con esas cantidades calcula tres porcentajes, siempre por separado:

| Porcentaje | Fórmula | Uso |
|---|---|---|
| `incidencia` | variable del grupo ÷ población del mismo grupo, en el mismo ámbito | SO2-1 (pobreza), SO2-2 (agua) |
| `exposicion` | cantidad en tierras degradadas ÷ cantidad en el país, misma variable y grupo | SO2-3 (población expuesta) |
| `composicion` | grupo ÷ total de la variable, en el mismo ámbito | estructura de la población expuesta |

Urbano/rural se define por persona (campos urbana/rural del censo) o por tipo de radio (`cruce.ambito_reporte`), por separado para el país y para las tierras degradadas (`tablas.urbano_rural`). Para comparar país y tierras degradadas por ámbito, conviene la misma definición en los dos.

- **Controles:** mujeres + varones = total y urbano + rural = total, en el país y en tierras degradadas; suma de regiones = nacional.
- **Produce:** `indicadores.csv` (formato largo con los tres porcentajes) y una tabla por entrada de `tablas.salidas`, con la fórmula indicada.

## Informe de la ejecución

Al terminar (o al detenerse por un control), cada ejecución escribe `informe_<nombre>.html` (por ejemplo `informe_prais2026_2022.html`), un archivo único que se abre en cualquier navegador:

- **Estado general** al principio: completa, completa con advertencias o detenida.
- **Controles:** cumplidos, advertencias y fallas bloqueantes; por etapa, una barra y la lista de controles con su resultado (las etapas con algo para revisar aparecen abiertas). Las advertencias conocidas se explican con cifras de la propia ejecución.
- **Resultados:** población, NBI y agua sin red en tierras degradadas (nacional y por región) y las capas publicadas.
- **Mapas de vista rápida:** población (personas por km², escala logarítmica), tierras degradadas y población en tierras degradadas, del país y de cada región. Se leen reducidos; son para revisar, no para publicar.
- **Tablas de indicadores**, con la fórmula de cada una.
- **Ejecución:** versión de poblar, Python y GDAL, e insumos con su sha256.

Para regenerarlo sobre una ejecución existente: `poblar.informe.generar(carpeta)`. Para mirar un producto en un cuaderno: `poblar.vista.mapa(carpeta, "expuesta", region="Chaco")`; `poblar.vista.productos(carpeta)` lista los disponibles.
