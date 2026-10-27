# PRAIS 2026 — OE2

Configuraciones que reproducen la ejecución final del OE2 del Informe Nacional PRAIS 2026 (22/09/2026), de la que provienen las tablas 2022 del informe y las capas de la plataforma.

| Configuración | Censo | Población integrada | Radios |
|---|---|---|---|
| [`configs/2010.yaml`](configs/2010.yaml) | 2010 (período de referencia) | 40.114.872 | 52.378 |
| [`configs/2022.yaml`](configs/2022.yaml) | 2022 (período de reporte) | 45.618.784 | 66.421 |

## Insumos

Copiar los siguientes archivos en una carpeta (por ejemplo, `MyDrive/PRAIS/poblar/insumos`):

| Archivo | Origen |
|---|---|
| `tabla_censo2010.xlsx`, `tabla_censo2022.xlsx` | Export de Redatam (INDEC), cuaderno C0, 15/05/2026 |
| `radios_2010.zip`, `radios_2022.zip` | CONICET, repositorio institucional 11336/149711, `RADIOS_AAAA_V2025-1` |
| `regiones_PRAIS.gpkg` | Regiones PRAIS 2026 (OE1) |

## Criterios de esta aplicación

Cada criterio figura en la configuración con su origen.

- **Unión tabla↔mapa:** `inner` (C1 de junio). Los radios solo en el mapa o solo en la tabla quedan registrados en `1_radios/`.
- **Región:** área mayoritaria; los radios sin intersección se asignan a la región más cercana si está a 50 km o menos, y el resto a «Fuera de Región (Antártida/Islas)» (C2 1.4). En esta aplicación se conservan.
- **CRS de trabajo:** EPSG:5347.
- **Orden de rasterización:** área descendente (C2 2.5).

## Resultados esperados

El bloque `resultados_esperados` compara la cantidad de radios, total y por región, con la ejecución final. Son controles no bloqueantes: una diferencia aparece como advertencia en `controles.csv`.

Comparación radio por radio con la caché del C2 original:

```python
from poblar.verificar import comparar_radios
comparar_radios("ejecuciones/prais2026_2010/1_radios/radios.parquet",
                "PRAIS/Cuadernos/C2/2010/cache/02_radios_curados_2010.parquet")
```
