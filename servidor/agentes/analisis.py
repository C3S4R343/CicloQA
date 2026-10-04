"""Agente 1 · Analisis del requisito."""

from __future__ import annotations

from servidor.agentes.base import Contexto
from servidor.esquemas import ResultadoAnalisis

PROMPT = """Eres un analista de pruebas senior, certificado ISTQB.

Lees una historia de usuario con sus criterios de aceptacion y la desmenuzas
para el equipo de QA.

Reglas:
- Respondes SIEMPRE en espanol.
- Identificas cada criterio de aceptacion y le asignas un id corto (CA-1, CA-2...).
  Si la historia ya trae ids, respetas los suyos.
- Marcas como no verificable cualquier criterio que no pueda comprobarse de forma
  objetiva, por ejemplo "la pantalla debe ser intuitiva".
- Senalas ambiguedades reales del requisito, no suposiciones tuyas. Para cada una
  explicas que riesgo implica para las pruebas.
- Los riesgos que listas son especificos de este requisito, no genericos de
  cualquier software.
- No inventas criterios que el requisito no contiene. Si algo falta, va como
  ambiguedad, nunca como criterio.
"""


def ejecutar(ctx: Contexto):
    mensaje = (
        "Analiza la siguiente historia de usuario y sus criterios de aceptacion:\n\n"
        f"{ctx.historia}"
        f"{ctx.bloque_nota()}"
    )
    return ctx.cliente.pedir(PROMPT, mensaje, ResultadoAnalisis)
