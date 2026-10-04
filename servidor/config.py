"""Carga de configuracion.

Aqui no hay credenciales. La llave de la API se lee de la variable de
entorno ANTHROPIC_API_KEY. Nunca se guarda en un archivo del proyecto.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parents[1]
RUTA_CONFIG = RAIZ / "config.json"
RUTA_DB = RAIZ / "cicloqa.db"
CARPETA_PROYECTOS = RAIZ / "proyectos"


class FaltaLlave(Exception):
    """No hay llave de API configurada."""


@lru_cache(maxsize=1)
def cargar() -> dict[str, Any]:
    with RUTA_CONFIG.open(encoding="utf-8") as archivo:
        return json.load(archivo)


def api_key() -> str:
    llave = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not llave:
        raise FaltaLlave(
            "No hay llave de API. Antes de arrancar el servidor:\n"
            '  Windows PowerShell:  $env:ANTHROPIC_API_KEY = "sk-ant-..."\n'
            '  macOS o Linux:       export ANTHROPIC_API_KEY="sk-ant-..."'
        )
    return llave


def workspace_id() -> str | None:
    """Solo hace falta si la llave no esta ligada a un workspace."""
    return os.environ.get("ANTHROPIC_WORKSPACE_ID", "").strip() or None


def hay_llave() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY", "").strip())
