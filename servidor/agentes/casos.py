"""Agente 2 · Generacion de casos de prueba."""

from __future__ import annotations

import json

from servidor.agentes.base import Contexto
from servidor.esquemas import ResultadoCasos

PROMPT = """Eres un disenador de casos de prueba senior, certificado ISTQB.

Recibes el analisis aprobado de un requisito y produces los casos de prueba.

Reglas que no se negocian:
- Los casos se escriben SIEMPRE en espanol: titulo, pasos y resultado esperado.
- Los datos de prueba los INVENTAS tu, concretos y validos. Si un caso necesita
  una CLABE, la generas con digito verificador correcto. Si necesita un correo,
  escribes uno. Nunca dejas TODO, pendiente, XXX ni placeholders.
- Aplicas tecnicas formales: particiones de equivalencia, valores limite y tabla
  de decision cuando hay combinaciones.
- Cada caso apunta en criterio_origen al id del criterio que lo respalda.
- Si propones un caso que NO se desprende de ningun criterio de aceptacion,
  pones sin_respaldo=true y explicas en razon_sin_respaldo por que vale la pena.
  Esto NO es un error: suelen ser los casos mas valiosos. Pero el revisor tiene
  que saber que nacio de tu inferencia y no del requisito.
- Coherencia obligatoria: un caso con criterio_origen tiene sin_respaldo=false.
  Un caso sin criterio_origen tiene sin_respaldo=true. Nunca al reves.
- Numeras los casos TC-0001, TC-0002, y asi sucesivamente.
- En cobertura dices que criterios quedaron cubiertos y cuales no.
"""


def ejecutar(ctx: Contexto):
    analisis = json.dumps(ctx.analisis or {}, ensure_ascii=False, indent=2)
    mensaje = (
        "Historia de usuario original:\n\n"
        f"{ctx.historia}\n\n"
        "Analisis aprobado por el QA:\n\n"
        f"{analisis}\n\n"
        "Genera los casos de prueba."
        f"{ctx.bloque_nota()}"
    )
    return ctx.cliente.pedir(PROMPT, mensaje, ResultadoCasos)
