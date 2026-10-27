"""poblar: distribución de datos censales en una grilla y cruce con capas temáticas.

El flujo se define en un archivo de configuración (YAML). Cada corrida deja en su
carpeta la copia del config, el registro de insumos, las validaciones, el log y
el manifiesto de productos.

Uso típico (Colab o terminal)::

    from poblar import correr
    correr("aplicaciones/prais2026/configs/2010.yaml", insumos="ruta/a/insumos")
"""

from __future__ import annotations

__version__ = "0.1.0"

from poblar.correr import correr

__all__ = ["__version__", "correr"]
