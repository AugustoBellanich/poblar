# PRAIS 2026 — OE2

Método y registros con los que se produjeron las cifras y las capas oficiales del Objetivo Estratégico 2 del Informe Nacional PRAIS 2026 de la Argentina (ONDTyD, CNULD).

| Archivo | Contenido |
|---|---|
| [`metodo.yaml`](metodo.yaml) | Criterios del método, iguales para los dos períodos (y para un período nuevo) |
| [`periodos/2010.yaml`](periodos/2010.yaml) | Período de referencia (censo 2010): huellas de los insumos oficiales y cifras publicadas |
| [`periodos/2022.yaml`](periodos/2022.yaml) | Período de reporte (censo 2022): ídem |

## Ejecutar

```python
from poblar import ejecutar

ejecutar("aplicaciones/prais2026/metodo.yaml",
         registro="aplicaciones/prais2026/periodos/2022.yaml",   # opcional: controla insumos y cifras oficiales
         insumos={"tabla_censo": ".../tabla_censo2022.xlsx", "radios": ".../radios_2022.zip",
                  "regiones": ".../regiones_PRAIS.gpkg", "cobertura": ".../MB_prais_2023_100m.tif",
                  "degradacion": ".../CondicionFinal_Estado_Reporte2_4326.tif"},
         salida="ejecuciones")
```

Para un período nuevo (por ejemplo, el próximo censo), el mismo método con `anio=` y los archivos nuevos, sin registro.

## Insumos oficiales

Los archivos pueden tener cualquier nombre; el registro los identifica por su huella (sha256).

| Rol | Período de referencia (2010) | Período de reporte (2022) | Origen |
|---|---|---|---|
| `tabla_censo` | Censo 2010 por radio | Censo 2022 por radio | INDEC, Redatam: población total, sexo, urbana/rural, NBI, agua de red, tipo de radio |
| `radios` | Radios 2010 (campo `COD_2010`) | Radios 2022 (campo `COD_2022`) | CONICET, repositorio institucional 11336/149711 |
| `cobertura` | MapBiomas 2015, 100 m | MapBiomas 2023, 100 m | MapBiomas Argentina, colección PRAIS 2026 (OE1) |
| `degradacion` | Degradación de la tierra para el período de referencia (2000-2015) | Condición final de la degradación de la tierra (2000-2023) | OE1 del PRAIS 2026 |
| `regiones` | Regiones PRAIS 2026 | ídem | OE1 del PRAIS 2026 |

| | 2010 | 2022 |
|---|---|---|
| Población integrada | 40.114.872 | 45.618.784 |
| Radios | 52.378 | 66.421 |

## Resultados

| | 2010 | 2022 |
|---|---|---|
| Población en tierras degradadas | 3.808.137 (9,49 %) | 5.665.133 (12,42 %) |
| Personas con NBI en tierras degradadas | 695.923 | 712.654 |
| Personas con agua de red en tierras degradadas | 2.778.508 | 4.405.420 |
| Población en la capa publicada (EPSG:4326) | 40.114.695 | 45.618.854 |

En 2010, las 207 personas de los radios de la Antártida e islas del Atlántico Sur (región «Fuera de Región») quedan fuera de la grilla de la cobertura y no figuran en las capas publicadas (la capa rural pierde 207,0). El total publicado difiere en −177 porque el remuestreo por suma agrega diferencias menores en el resto del país (+30). En 2022 la diferencia es de +70 (0,00015 %).

Estas cifras están en el registro de cada período: una ejecución que no las reproduzca lo informa en `controles.csv`.

## Criterios de esta aplicación

Los criterios que cambian resultados, con su valor en estas configuraciones:

- **Cobertura:** humedales como no urbano (habitable); hielo, otras áreas no vegetadas, agua y sin dato como no habitables.
- **Grilla de trabajo:** EPSG:5347, resolución estimada por GDAL (80,93 m en 2010; 78,48 m en 2022), extensión de los radios.
- **Ponderadores:** mediana de la densidad por píxel habitable, por región y tipo de radio, relativa a la de los radios urbanos.
- **Ámbito en el cruce y en las tablas de tierras degradadas:** tipo de radio, con los radios mixtos informados como rurales. En las columnas del país, urbano/rural del censo. Ver `tablas.urbano_rural` en [`docs/configuracion.md`](../../docs/configuracion.md).
- **Degradación:** «Degradada» = clase 1; «No degradada» = clases 2, 3 y 9; la clase 0 (sin datos) queda fuera del binario.
- **Indicadores:** SO2-1 y SO2-2 como incidencia en cada grupo; SO2-3 como exposición (población del grupo en tierras degradadas ÷ población del grupo en el país).
- **Radios de la Antártida e islas:** se conservan, en la región «Fuera de Región (Antártida/Islas)».
