"""Contrato comun de los agentes.

Cada agente expone UNA funcion con la misma firma:

    ejecutar(contexto) -> (ModeloPydantic, Consumo)

El orquestador no sabe nada de sus internos. Si manana quieres exponer
estos agentes como herramientas MCP, envuelves esta firma y ya.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Contexto:
    ejecucion_id: str
    historia: str
    cfg: dict[str, Any]
    cliente: Any  # ClienteClaude

    analisis: dict | None = None
    casos: dict | None = None
    nota_revisor: str | None = None
    casos_excluidos: list[str] = field(default_factory=list)

    def bloque_nota(self) -> str:
        if not self.nota_revisor:
            return ""
        return (
            "\n\nUn revisor humano pidio cambios sobre tu entrega anterior. "
            f"Su nota fue:\n{self.nota_revisor}\n"
            "Corrige exactamente eso y vuelve a entregar el resultado completo."
        )

    def bloque_convenciones(self) -> str:
        c = self.cfg.get("convenciones", {})
        return (
            f"Framework: {c.get('framework', 'Playwright con TypeScript')}\n"
            f"Patron: {c.get('patron', 'Page Object Model estricto')}\n"
            f"Selectores: {c.get('selectores', 'getByRole y getByLabel')}\n"
        )
