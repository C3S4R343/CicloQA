"""Contratos de salida de los agentes y modelos de la API.

Los modelos de agente no son documentacion: son el contrato. Si la
respuesta del modelo no encaja, se rechaza y se reintenta una vez.
Nunca se parsea texto libre.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# --------------------------------------------------------------------
# Agente 1 · Analisis
# --------------------------------------------------------------------


class CriterioIdentificado(BaseModel):
    id: str = Field(description="Identificador corto del criterio, por ejemplo CA-1")
    texto: str = Field(description="El criterio de aceptacion redactado en espanol")
    verificable: bool = Field(
        description="True si puede comprobarse con una prueba objetiva"
    )


class Ambiguedad(BaseModel):
    descripcion: str = Field(description="Que quedo ambiguo en el requisito")
    impacto: str = Field(description="Que riesgo implica para las pruebas")


class ResultadoAnalisis(BaseModel):
    resumen: str = Field(description="Dos o tres lineas sobre que pide la historia")
    criterios: list[CriterioIdentificado]
    ambiguedades: list[Ambiguedad] = Field(default_factory=list)
    riesgos: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------
# Agente 2 · Casos de prueba
# --------------------------------------------------------------------


class CasoDePrueba(BaseModel):
    id_caso: str = Field(description="Identificador, por ejemplo TC-0001")
    titulo: str = Field(description="Titulo del caso, en espanol")
    criterio_origen: str | None = Field(
        default=None,
        description="Id del criterio que respalda el caso, o null si no hay ninguno",
    )
    pasos: list[str] = Field(description="Pasos del caso, en espanol")
    datos: dict[str, str] = Field(
        default_factory=dict,
        description="Datos de prueba concretos inventados por el agente. Nunca TODO ni XXX.",
    )
    resultado_esperado: str = Field(description="Resultado esperado, en espanol")
    sin_respaldo: bool = Field(
        description="True si el caso no se desprende de ningun criterio de aceptacion"
    )
    razon_sin_respaldo: str | None = Field(
        default=None, description="Por que se propone pese a no tener respaldo"
    )


class ResultadoCasos(BaseModel):
    casos: list[CasoDePrueba]
    cobertura: str = Field(description="Que criterios quedaron cubiertos y cuales no")


# --------------------------------------------------------------------
# Agente 3 · Automatizacion
# --------------------------------------------------------------------


class ArchivoGenerado(BaseModel):
    ruta_relativa: str = Field(
        description="Ruta desde la raiz del proyecto, por ejemplo pages/LoginPage.ts"
    )
    tipo: Literal["page_object", "spec"] = Field(description="page_object o spec")
    contenido: str = Field(description="Contenido completo del archivo TypeScript")


class ResultadoAutomatizacion(BaseModel):
    archivos: list[ArchivoGenerado]
    clases_reutilizadas: list[str] = Field(
        default_factory=list,
        description="Page classes existentes que se reutilizaron sin duplicar",
    )
    notas: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------
# Modelos de la API web
# --------------------------------------------------------------------


class NuevaEjecucion(BaseModel):
    historia: str = Field(min_length=20)
    entorno: str = "qa"
    url: str | None = Field(
        default=None,
        pattern=r"^https?://\S+$",
        description="Pagina bajo prueba. Si falta, se usa entorno.url_base de config.json",
    )


class Decision(BaseModel):
    decision: Literal["aprobado", "cambios", "rechazado"]
    nota: str | None = None
    casos_excluidos: list[str] = Field(default_factory=list)


class Consumo(BaseModel):
    tokens_entrada: int = 0
    tokens_salida: int = 0
    costo_usd: float = 0.0

    def sumar(self, otro: "Consumo") -> "Consumo":
        return Consumo(
            tokens_entrada=self.tokens_entrada + otro.tokens_entrada,
            tokens_salida=self.tokens_salida + otro.tokens_salida,
            costo_usd=round(self.costo_usd + otro.costo_usd, 6),
        )
