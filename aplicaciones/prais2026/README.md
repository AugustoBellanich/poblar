# PRAIS 2026 — OE2

Configuraciones con las que se produjeron las cifras y las capas oficiales del Objetivo Estratégico 2 del Informe Nacional PRAIS 2026 de la Argentina (ONDTyD, CNULD).

| Configuración | Censo | Mapa de degradación | Población | Radios |
|---|---|---|---|---|
| [`configs/2010.yaml`](configs/2010.yaml) | 2010 (período de referencia) | Degradación de la tierra para el período de referencia (2000-2015) | 40.114.872 | 52.378 |
| [`configs/2022.yaml`](configs/2022.yaml) | 2022 (período de reporte) | Condición final de la degradación de la tierra (2000-2023) | 45.618.784 | 66.421 |

## Insumos

Copiar en una carpeta (por ejemplo, `MyDrive/PRAIS/poblar/insumos`) con estos nombres:

| Archivo | Contenido | Origen |
|---|---|---|
| `tabla_censo2010.xlsx`, `tabla_censo2022.xlsx` | Población por radio: total, sexo, urbana/rural, NBI, agua de red; tipo de radio | INDEC, Redatam |
| `radios_2010.zip`, `radios_2022.zip` | Cartografía de radios censales | CONICET, repositorio institucional 11336/149711 |
| `MB_prais_2015_100m.tif`, `MB_prais_2023_100m.tif` | Cobertura del suelo, 100 m, EPSG:4326 | MapBiomas Argentina, colección PRAIS 2026 (OE1) |
| `degradacion_referencia_2010.tif`, `degradacion_reporte_2022.tif` | Mapas de degradación, EPSG:4326 | OE1 del PRAIS 2026 |
| `regiones_PRAIS.gpkg` | Regiones PRAIS 2026 | OE1 del PRAIS 2026 |

La etapa 0 compara el sha256 de cada archivo con el de la configuración: si alguien usa otra versión de un insumo, la ejecución se detiene.

## Resultados

| | 2010 | 2022 |
|---|---|---|
| Población en tierras degradadas | 3.808.137 (9,49 %) | 5.665.133 (12,42 %) |
| Personas con NBI en tierras degradadas | 695.923 | 712.654 |
| Personas con agua de red en tierras degradadas | 2.778.508 | 4.405.420 |
| Población en la capa publicada (EPSG:4326) | 40.114.695 | 45.618.854 |

En 2010, las 207 personas de los radios de la Antártida e islas del Atlántico Sur (región «Fuera de Región») quedan fuera de la grilla de la cobertura y no figuran en las capas publicadas (la capa rural pierde 207,0). El total publicado difiere en −177 porque el remuestreo por suma agrega diferencias menores en el resto del país (+30). En 2022 la diferencia es de +70 (0,00015 %).

Estas cifras están en `resultados_esperados` de cada configuración: una ejecución que no las reproduzca lo informa en `controles.csv`.

## Criterios de esta aplicación

Los criterios que cambian resultados, con su valor en estas configuraciones:

- **Cobertura:** humedales como no urbano (habitable); hielo, otras áreas no vegetadas, agua y sin dato como no habitables.
- **Grilla de trabajo:** EPSG:5347, resolución estimada por GDAL (80,93 m en 2010; 78,48 m en 2022), extensión de los radios.
- **Ponderadores:** mediana de la densidad por píxel habitable, por región y tipo de radio, relativa a la de los radios urbanos.
- **Ámbito en el cruce y en las tablas de tierras degradadas:** tipo de radio, con los radios mixtos informados como rurales. En las columnas del país, urbano/rural del censo. Ver `tablas.urbano_rural` en [`docs/configuracion.md`](../../docs/configuracion.md).
- **Degradación:** «Degradada» = clase 1; «No degradada» = clases 2, 3 y 9; la clase 0 (sin datos) queda fuera del binario.
- **Indicadores:** SO2-1 y SO2-2 como incidencia en cada grupo; SO2-3 como exposición (población del grupo en tierras degradadas ÷ población del grupo en el país).
- **Radios de la Antártida e islas:** se conservan, en la región «Fuera de Región (Antártida/Islas)».
