"""poblar: distribución de datos censales en una grilla y cruce con capas temáticas.

El flujo se define en un archivo de configuración (YAML). Cada ejecución deja en su
carpeta la copia de la configuración, el registro de insumos, los controles,
el balance por etapa y el manifiesto de productos.

Uso típico (Colab o terminal)::

    from poblar import ejecutar
    ejecutar("aplicaciones/prais2026/configs/2010.yaml", insumos="ruta/a/insumos")
"""

from __future__ import annotations

__version__ = "0.1.0"

from poblar.ejecutar import ejecutar

__all__ = ["__version__", "ejecutar"]
