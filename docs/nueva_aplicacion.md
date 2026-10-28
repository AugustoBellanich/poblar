# Otros períodos y otras aplicaciones

## Un período nuevo con el mismo método

Por ejemplo, el PRAIS con un censo nuevo: el método no cambia; se indican el año y los archivos.

```python
from poblar import ejecutar

ejecutar("aplicaciones/prais2026/metodo.yaml",
         anio=2030,
         insumos={"tabla_censo": "...", "radios": "...", "regiones": "...",
                  "cobertura": "...", "degradacion": "..."},
         salida="ejecuciones")
```

Antes de ejecutar, revisar que los insumos nuevos cumplan lo que el método supone:

| Insumo | Qué revisar |
|---|---|
| Tabla censal | Columna `id_radio` y los mismos nombres de columnas (`pobla_total`, `pobla_mujer`, `nbi_total`, …) y del tipo de radio (`ambito`: Urbano/Mixto/Rural). Si cambian, adaptar `dasimetria.variables` y `tablas.variables` en una copia del método |
| Radios | El campo de código se detecta solo; si hay ambigüedad, indicarlo: `"radios": {"ruta": ..., "campo_codigo": "COD_2030"}` |
| Cobertura | Las mismas clases. Si la colección nueva tiene otras, la etapa 2 lo informa con la lista de clases sin mapear y hay que agregarlas a `cobertura.clases` |
| Mapa de degradación | Las mismas clases (0, 1, 2, 3, 9). Ídem en la etapa 4 con `cruce.clases`. Si tiene varias bandas, indicar cuál: `"degradacion": {"ruta": ..., "banda": 1}` |
| Regiones | El campo `Reg_PRAIS` |

Conviene ejecutar por partes: primero `etapas=["insumos", "radios"]` y revisar `controles.csv` y los CSV de `1_radios/` (radios sin cartografía, sin intersección, fuera de región); después `["grilla"]` para revisar las clases y la resolución; después el resto. Cada llamada retoma la misma carpeta.

Una vez revisado, se puede crear un registro del período (copiar `aplicaciones/prais2026/periodos/2022.yaml`) con las huellas de `0_insumos/insumos.csv` y las cifras obtenidas, para que ejecuciones posteriores controlen que se usan los mismos archivos y se obtienen las mismas cifras.

## Una aplicación distinta

Con otro tipo de insumos (otra cobertura, otra capa temática, otro país, otras regiones), se crea una carpeta nueva con su propio método:

```
aplicaciones/<aplicacion>/
  README.md        qué es, de dónde salen los insumos, criterios elegidos
  metodo.yaml      copia adaptada de aplicaciones/prais2026/metodo.yaml
  periodos/        registros opcionales
```

En el método, cambiar `aplicacion` y revisar cada sección contra [`configuracion.md`](configuracion.md): clases de la cobertura y de la capa temática, campos de región y tipo de radio, variables, nombres de las capas de entrega y tablas. Una etapa que el método no define (por ejemplo, sin `publicacion`) se omite.

## Comparar criterios

Para medir el efecto de un criterio (otra resolución, otra definición de urbano/rural), copiar el método, cambiar solo ese criterio y ejecutar con otro `nombre=`. `poblar.verificar.comparar_raster` compara los rasters píxel por píxel; las tablas de `6_tablas/` se comparan directamente.
