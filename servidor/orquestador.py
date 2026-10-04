"""El orquestador: una maquina de estados en codigo plano.

PRINCIPIO CENTRAL: el modelo decide contenido, el codigo decide flujo.

Ningun LLM decide que paso sigue. Los estados Espera* son el aporte real
del sistema: el orquestador entra en ellos, guarda todo en SQLite y se
detiene. Lo que lo reanuda es una peticion HTTP nueva disparada por una
persona que aprueba, pide cambios o rechaza.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from servidor import db
from servidor.agentes import analisis, automatizacion, casos
from servidor.agentes.base import Contexto
from servidor.claude_client import ClienteClaude, FalloDelAgente
from servidor.esquemas import Consumo


class Estado(str, Enum):
    ANALIZANDO = "Analizando"
    ESPERA_ANALISIS = "EsperaAnalisis"
    GENERANDO_CASOS = "GenerandoCasos"
    ESPERA_CASOS = "EsperaCasos"
    GENERANDO_SCRIPTS = "GenerandoScripts"
    ESPERA_SCRIPTS = "EsperaScripts"
    TERMINADO = "Terminado"
    CANCELADO = "Cancelado"
    FALLIDO = "Fallido"


# estado de espera -> (etapa, estado si piden cambios, estado si aprueban)
ETAPAS = {
    Estado.ESPERA_ANALISIS: ("analisis", Estado.ANALIZANDO, Estado.GENERANDO_CASOS),
    Estado.ESPERA_CASOS: ("casos", Estado.GENERANDO_CASOS, Estado.GENERANDO_SCRIPTS),
    Estado.ESPERA_SCRIPTS: ("automatizacion", Estado.GENERANDO_SCRIPTS, Estado.TERMINADO),
}

ROTULO_ETAPA = {
    "analisis": "Analisis",
    "casos": "Casos de prueba",
    "automatizacion": "Automatizacion",
}


class Orquestador:
    def __init__(self, cfg: dict[str, Any], cliente: ClienteClaude | None = None):
        self.cfg = cfg
        self.cliente = cliente or ClienteClaude(cfg)

    # ----------------------------------------------------------------

    def iniciar(self, historia: str, entorno: str) -> str:
        db.inicializar()
        eid = db.crear_ejecucion(historia, entorno)
        self._correr_etapa(eid, "analisis", None)
        return eid

    def continuar(self, eid: str, decision: str, nota: str | None, excluidos: list[str]) -> None:
        ej = db.ejecucion(eid)
        if not ej:
            raise ValueError("No existe esa ejecucion.")

        estado = Estado(ej["estado"])
        if estado not in ETAPAS:
            raise ValueError(f"El estado {estado.value} no espera una decision.")

        etapa, estado_reintento, estado_siguiente = ETAPAS[estado]
        db.registrar_aprobacion(eid, etapa, decision, nota)

        if decision == "rechazado":
            db.fijar_estado(eid, Estado.CANCELADO.value)
            return

        if decision == "cambios":
            if not nota:
                raise ValueError("Pedir cambios requiere una nota para el agente.")
            self._correr_etapa(eid, etapa, nota, excluidos)
            return

        # aprobado
        if estado_siguiente == Estado.TERMINADO:
            db.fijar_estado(eid, Estado.TERMINADO.value)
            return
        siguiente = {"GenerandoCasos": "casos", "GenerandoScripts": "automatizacion"}[
            estado_siguiente.value
        ]
        self._correr_etapa(eid, siguiente, None, excluidos)

    # ----------------------------------------------------------------

    def _contexto(self, eid: str, nota: str | None, excluidos: list[str]) -> Contexto:
        ej = db.ejecucion(eid)
        ctx = Contexto(
            ejecucion_id=eid,
            historia=ej["historia"],
            cfg=self.cfg,
            cliente=self.cliente,
            nota_revisor=nota,
            casos_excluidos=excluidos or [],
        )
        ent_a = db.ultima_entrega(eid, "analisis")
        if ent_a:
            ctx.analisis = ent_a["payload"]
        ent_c = db.ultima_entrega(eid, "casos")
        if ent_c:
            ctx.casos = ent_c["payload"]
        return ctx

    def _correr_etapa(
        self, eid: str, etapa: str, nota: str | None, excluidos: list[str] | None = None
    ) -> None:
        en_curso = {
            "analisis": Estado.ANALIZANDO,
            "casos": Estado.GENERANDO_CASOS,
            "automatizacion": Estado.GENERANDO_SCRIPTS,
        }[etapa]
        espera = {
            "analisis": Estado.ESPERA_ANALISIS,
            "casos": Estado.ESPERA_CASOS,
            "automatizacion": Estado.ESPERA_SCRIPTS,
        }[etapa]

        db.fijar_estado(eid, en_curso.value)
        ctx = self._contexto(eid, nota, excluidos or [])
        agente = {"analisis": analisis, "casos": casos, "automatizacion": automatizacion}[etapa]

        try:
            resultado, consumo = agente.ejecutar(ctx)
        except FalloDelAgente as error:
            db.fijar_estado(eid, Estado.FALLIDO.value)
            db.guardar_entrega(eid, etapa, {"error": str(error)}, nota)
            raise

        payload = resultado.model_dump()
        db.sumar_consumo(eid, consumo.tokens_entrada, consumo.tokens_salida, consumo.costo_usd)
        db.guardar_entrega(eid, etapa, payload, nota)

        if etapa == "casos":
            for caso in payload.get("casos", []):
                db.insertar_caso(eid, caso)

        db.fijar_estado(eid, espera.value)


def vista(eid: str) -> dict:
    """Todo lo que la interfaz necesita de una ejecucion."""
    ej = db.ejecucion(eid)
    if not ej:
        raise ValueError("No existe esa ejecucion.")
    estado = ej["estado"]
    etapa_actual = None
    for est, (etapa, _, _) in ETAPAS.items():
        if est.value == estado:
            etapa_actual = etapa
    entregas = {e["etapa"]: e["version"] for e in db.entregas(eid)}
    return {
        "id": eid,
        "estado": estado,
        "etapa": etapa_actual,
        "historia": ej["historia"],
        "entorno": ej["entorno"],
        "versiones": entregas,
        "analisis": (db.ultima_entrega(eid, "analisis") or {}).get("payload"),
        "casos": (db.ultima_entrega(eid, "casos") or {}).get("payload"),
        "automatizacion": (db.ultima_entrega(eid, "automatizacion") or {}).get("payload"),
        "nota_vigente": (db.ultima_entrega(eid, etapa_actual) or {}).get("nota_previa")
        if etapa_actual
        else None,
        "bitacora": db.bitacora(eid),
        "consumo": {
            "tokens_entrada": ej["tokens_entrada"],
            "tokens_salida": ej["tokens_salida"],
            "costo_usd": round(ej["costo_usd"], 4),
        },
    }
