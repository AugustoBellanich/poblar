# Guía de estilo y glosario

Rige para el código, los comentarios, los mensajes, los cuadernos y la documentación de `poblar` y de sus aplicaciones. El objetivo es que cualquier persona que quiera verificar un resultado entienda cada término sin ambigüedad.

## Registro

- **Español neutro y formal.** Sin voseo en la documentación pública: en las instrucciones se usa el infinitivo («Ejecutar las celdas en orden»), no el imperativo («Corré las celdas»).
- **Impersonal y en presente**: «se calcula», «la etapa asigna». Sin primera persona.
- **Sin coloquialismos ni metáforas**: «se detiene» y no «corta» ni «frena»; «no comienza» y no «no arranca»; «control» y no «chequeo».
- **Oraciones cortas**: una idea por oración.
- **Términos oficiales tal como los usa la fuente**: INDEC para el censo, CNULD para los indicadores, IGN para la cartografía de referencia.

## Glosario

| Término | Definición | En el código | No usar |
|---|---|---|---|
| **ejecución** | Una aplicación completa del flujo con una configuración. Deja una carpeta con sus productos y su registro. | `Ejecucion`, `ejecutar()`, carpeta `ejecuciones/` | corrida |
| **configuración** | Archivo YAML que define insumos, criterios, grilla, controles y productos de una ejecución. | `config.yaml` | config (en prosa) |
| **criterio** | Decisión metodológica que cambia un resultado (por ejemplo, la clase asignada a los humedales). Siempre explícito en la configuración. | claves del YAML | parámetro oculto, valor por defecto |
| **insumo** | Archivo de datos de entrada (tabla censal, cartografía, coberturas, capas temáticas). | `insumos` | input |
| **producto** | Archivo generado por una etapa. | — | output, salida (en prosa) |
| **etapa** | Unidad del flujo con entradas, salidas y controles propios. | `0_insumos`, `1_radios`, … | cuaderno, paso |
| **control** | Verificación automática de un invariante. Puede ser bloqueante o no bloqueante. | `Control`, `controles.csv` | chequeo, validación |
| **control bloqueante** | Control cuyo incumplimiento detiene la ejecución en modo `detener`. | `bloqueante=True` | — |
| **modo** | Comportamiento ante un control bloqueante que falla: `detener` (por defecto) o `advertir`. | `controles.modo` | cortar, avisar |
| **balance** | Registro de qué entra y qué sale de cada paso (filas, píxeles, personas). | `balance.csv` | cuentas |
| **manifiesto** | Lista de productos con su tamaño y su sha256. | `manifiesto.csv` | — |
| **resultados esperados** | Valores de una ejecución publicada que la configuración debe reproducir. Controles no bloqueantes. | `resultados_esperados` | aceptación |
| **radio censal** | Unidad geoestadística mínima del censo (INDEC). | `id_radio` (9 dígitos) | — |
| **radio sin intersección** | Radio que no se superpone con ninguna región y se asigna a la región más cercana. | `radios_sin_interseccion.csv` | huérfano |
| **grilla de trabajo** | Grilla regular en la que se hace el mapeo dasimétrico y el cruce. | `grilla_trabajo` | malla |
| **grilla de publicación** | Grilla de los productos que se publican. | `grilla_publicacion` | — |
| **mapeo dasimétrico** | Redistribución de un conteo de una unidad areal a celdas, ponderada por información auxiliar (cobertura del suelo). | `dasimetria` | — |
| **ponderador** | Peso relativo de una clase de cobertura dentro de un radio. | `ponderadores` | — |
| **contingencia** | Tratamiento especial de radios sin píxeles habitables (nivel 2) o sin píxeles propios (nivel 3). | `contingencias` | — |
| **tierras degradadas (TD)** | Categoría de la capa de degradación del OE1. | `degradada` | — |
| **cuaderno** | Archivo Jupyter que invoca la librería. No contiene lógica de procesamiento. | `cuadernos/` | notebook (en prosa) |

## Números, fechas y unidades

- **Prosa y tablas para leer:** coma decimal y punto de miles (`3.808.137`; `12,6 %`), como en el informe.
- **Código, CSV y YAML:** punto decimal y sin separador de miles (`3808137`, `12.6`). Los CSV se escriben en UTF-8.
- **Fechas:** `22/09/2026` en prosa; ISO 8601 (`2026-09-22`) en nombres de archivo y metadatos.
- **Unidades del SI** con espacio: `80 m`, `50 km`, `0,001°`.
- **Sistemas de referencia** siempre con código EPSG: `EPSG:5347 (POSGAR 2007 / Argentina 4)`.

## Código

- Identificadores en español, sin tildes ni eñes (`anio`, `region`, `poblacion`); en los textos visibles, con tildes.
- Un mensaje de error dice qué falló, dónde y cómo corregirlo.
- Las referencias a los cuadernos originales del PRAIS 2026 (por ejemplo, «C2 1.4») van solo en `aplicaciones/prais2026/`, nunca en la librería.
