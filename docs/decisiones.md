# Registro de decisiones

Cada decisión de diseño del proyecto, con su fecha, su motivo y las alternativas consideradas.

## D-001 · Licencia: Apache 2.0 (27/10/2026)

**Decisión.** El código se publica bajo la Licencia Apache 2.0 (`LICENSE`, `NOTICE`).

**Motivos.**
1. **Reutilización amplia.** Es permisiva: organismos nacionales y provinciales, observatorios, universidades y privados pueden usar, modificar e integrar el código sin obligación de liberar su propio trabajo. Esto favorece que otros verifiquen los resultados y apliquen el método a otros censos o capas.
2. **Atribución y registro de cambios.** Exige conservar el aviso de autoría (`NOTICE`) y señalar los archivos modificados. Esto preserva el reconocimiento institucional y es coherente con el objetivo de trazabilidad del proyecto.
3. **Concesión explícita de patentes.** A diferencia de la licencia MIT, otorga una licencia de patentes a quienes usan el código y la revoca a quien inicie un litigio de patentes. Da seguridad jurídica a instituciones públicas que adopten la herramienta.
4. **Compatibilidad.** Es compatible con GPL 3.0 y con las licencias de las dependencias principales (GDAL/rasterio, geopandas, numpy, pandas).

**Alternativas descartadas.**
- **MIT:** igual de permisiva y más corta, pero sin concesión de patentes ni obligación de señalar cambios.
- **GPL 3.0:** obliga a publicar las modificaciones bajo la misma licencia; limita la integración en sistemas institucionales o productos de terceros.

**Titularidad.** El código pertenece al grupo de trabajo del OE2, no a una institución en particular. `NOTICE` lo atribuye a «los autores de poblar» y `AUTORES.md` lista a las personas. Pendiente: acordar en el grupo la incorporación de otros autores y la mención de las instituciones participantes.

**Alcance.** La licencia cubre solo el código. Los insumos (censos de INDEC, cartografía de CONICET, MapBiomas, capas del OE1) conservan sus propias licencias y no se distribuyen en el repositorio.

## D-002 · Terminología formal (27/10/2026)

**Decisión.** Se adopta la `docs/guia_de_estilo.md` para el código y la documentación. Términos coloquiales reemplazados: «corrida» → «ejecución», «chequeo/validación» → «control», «cortar/avisar» → modos `detener`/`advertir`, «cuentas» → «balance», «huérfano» → «radio sin intersección», «aceptación» → «resultados esperados».

**Motivo.** La librería es pública y está pensada para que terceros verifiquen resultados oficiales. Un vocabulario definido y estable evita ambigüedades.

## D-003 · Separar librería y aplicación (27/10/2026)

**Decisión.** El repositorio se llama `poblar` y contiene una librería genérica. El PRAIS 2026 es una aplicación (`aplicaciones/prais2026/`) con sus configuraciones.

**Motivo.** El método sirve para otros censos, otros años y otras capas temáticas (observatorio, provincias). El nombre del proyecto no debe atarse a un informe.

## D-004 · Unión tabla↔mapa en la configuración PRAIS 2026: `inner` (27/10/2026)

**Decisión.** Las configuraciones de `aplicaciones/prais2026` usan `radios.union: inner`.

**Motivo.** Es la unión del C1 que alimentó la ejecución final del 22/09/2026 (52.378 radios en 2010; 66.421 en 2022). La prueba del 25/10/2026 con `left` agregó una fila sin dato censal (52.379 / 66.422). Para nuevas aplicaciones se recomienda `left` con `id_desde: mapa`, que conserva los radios sin dato censal con población 0 y los registra.
