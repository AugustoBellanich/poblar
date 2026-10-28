# Una aplicación nueva

Cómo usar poblar con otros insumos: otro censo, otra cobertura, otro mapa de degradación u otras regiones. Se parte de la configuración del PRAIS 2026 y se cambia lo que corresponde.

## 1. Preparar los insumos

| Insumo | Requisitos |
|---|---|
| Tabla censal | Una fila por radio. Código de radio (`id_radio`, se completa a 9 dígitos), tipo de radio (por ejemplo Urbano/Mixto/Rural) y los conteos: población total, por sexo, urbana y rural, y las variables a distribuir (NBI, agua de red u otras). Excel o CSV |
| Radios | Polígonos con el mismo código de radio. Shapefile en `.zip`, GeoPackage o cualquier formato que lea GDAL |
| Cobertura del suelo | Raster categórico |
| Mapa de degradación | Raster categórico (u otra capa temática categórica) |
| Regiones | Polígonos con un campo de región |

## 2. Crear la carpeta de la aplicación

```
aplicaciones/<aplicacion>/
  README.md        qué es, de dónde salen los insumos, criterios elegidos
  configs/
    <año>.yaml     una configuración por año o período
```

Copiar `aplicaciones/prais2026/configs/2022.yaml` y cambiar:

1. `nombre` y `anio_censo`.
2. `insumos`: nombres de archivo. Dejar `sha256: null` en la primera ejecución; la etapa 0 calcula los valores (están en `0_insumos/insumos.csv`) y conviene copiarlos a la configuración para fijar la versión de cada insumo.
3. `radios.campo_codigo_mapa` y `region.campo`.
4. `cobertura.clases`: una fila por cada clase de la cobertura nueva, con su metacategoría. Si falta alguna, la etapa 2 lo informa con la lista de clases sin mapear.
5. `cruce.clases`: lo mismo para el mapa de degradación, con el grupo binario de cada clase.
6. `dasimetria.variables`, `cruce.variables`, `tablas.variables` y `publicacion.productos`: según las variables de la tabla censal.
7. Borrar `referencia` y `resultados_esperados` (son las cifras del PRAIS 2026). Después de una ejecución revisada, se pueden completar con los valores obtenidos para que las siguientes ejecuciones los controlen.

Todas las claves: [`configuracion.md`](configuracion.md).

## 3. Ejecutar por partes

Conviene correr primero `["insumos", "radios"]` y revisar `controles.csv` y los CSV de `1_radios/` (radios sin cartografía, sin intersección, fuera de región). Después `["grilla"]` para revisar las clases y la resolución, y recién entonces el resto. Cada llamada retoma la misma carpeta.

```python
from poblar import ejecutar
ejecutar("aplicaciones/<aplicacion>/configs/<año>.yaml", insumos="...", salida="ejecuciones",
         etapas=["insumos", "radios"])
```

## 4. Comparar criterios

Para medir el efecto de un criterio (por ejemplo, otra resolución o otra definición de urbano/rural), copiar la configuración con otro `nombre`, cambiar solo ese criterio y ejecutar. `poblar.verificar.comparar_raster` compara los rasters píxel por píxel; las tablas de `6_tablas/` se comparan directamente.
