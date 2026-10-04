"""Cliente de Claude con salida estructurada y validacion Pydantic.

Reglas que este archivo hace cumplir:
  - Nunca se parsea texto libre: se fuerza salida estructurada.
  - Si Pydantic rechaza, se reintenta UNA vez con el error a la vista.
    Si falla de nuevo, fallo explicito. No hay tercera ni se adivina.
  - Los tokens se LEEN de la respuesta, nunca se estiman.
  - Timeout explicito y backoff exponencial ante limite de tasa.
"""

from __future__ import annotations

import random
import time
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from servidor import config
from servidor.esquemas import Consumo

T = TypeVar("T", bound=BaseModel)


class FalloDelAgente(Exception):
    """El agente no pudo entregar una salida valida."""


class TopeDeGasto(Exception):
    """Se alcanzo el tope mensual configurado."""


def calcular_costo(modelo: str, entrada: int, salida: int, precios: dict) -> float:
    tarifa = precios.get(modelo)
    if not tarifa:
        return 0.0
    return round(
        entrada / 1_000_000 * tarifa["entrada"] + salida / 1_000_000 * tarifa["salida"],
        6,
    )


class ClienteClaude:
    def __init__(self, cfg: dict[str, Any] | None = None):
        self.cfg = cfg or config.cargar()
        self.modelo = self.cfg["modelo"]
        self.max_tokens = self.cfg.get("max_tokens", 8000)
        self.timeout = self.cfg.get("timeout_segundos", 180)
        self.max_429 = self.cfg.get("max_reintentos_429", 3)
        self.precios = self.cfg.get("precios_usd_por_millon", {})
        self._cliente = None

    def _obtener(self):
        if self._cliente is None:
            import anthropic

            workspace = config.workspace_id()
            self._cliente = anthropic.Anthropic(
                api_key=config.api_key(),
                timeout=float(self.timeout),
                default_headers={"anthropic-workspace-id": workspace} if workspace else None,
            )
        return self._cliente

    # ----------------------------------------------------------------

    def pedir(
        self,
        prompt_sistema: str,
        mensaje: str,
        modelo_salida: type[T],
        herramienta: str = "entregar_resultado",
    ) -> tuple[T, Consumo]:
        """Pide una respuesta que encaje en modelo_salida."""
        import anthropic

        definicion = {
            "name": herramienta,
            "description": (
                f"Entrega el resultado con la estructura de {modelo_salida.__name__}. "
                "Todos los campos obligatorios deben venir completos."
            ),
            "input_schema": modelo_salida.model_json_schema(),
        }

        consumo = Consumo()
        mensajes: list[dict] = [{"role": "user", "content": mensaje}]
        error = "sin detalle"

        for intento in range(2):  # original + un reintento por validacion
            respuesta = self._llamar(anthropic, prompt_sistema, mensajes, definicion, herramienta)

            entrada = respuesta.usage.input_tokens
            salida = respuesta.usage.output_tokens
            consumo = consumo.sumar(
                Consumo(
                    tokens_entrada=entrada,
                    tokens_salida=salida,
                    costo_usd=calcular_costo(self.modelo, entrada, salida, self.precios),
                )
            )

            if respuesta.stop_reason == "max_tokens":
                raise FalloDelAgente(
                    f"La respuesta se corto al llegar a max_tokens ({self.max_tokens}). "
                    "Sube max_tokens en config.json."
                )

            bloque = next((b for b in respuesta.content if b.type == "tool_use"), None)
            if bloque is None:
                error = "La respuesta no uso la herramienta de salida estructurada."
            else:
                try:
                    return modelo_salida.model_validate(bloque.input), consumo
                except ValidationError as exc:
                    error = str(exc)

            if intento == 0:
                correccion = (
                    "La salida anterior no cumple el esquema. Errores:\n"
                    f"{error}\n\nVuelve a entregar el resultado con la herramienta "
                    f"{herramienta} corrigiendo esos campos."
                )
                # Una llamada a herramienta exige su tool_result en el turno siguiente.
                if bloque is None:
                    contenido: Any = correccion
                else:
                    contenido = [
                        {
                            "type": "tool_result",
                            "tool_use_id": bloque.id,
                            "is_error": True,
                            "content": correccion,
                        }
                    ]
                mensajes = [
                    {"role": "user", "content": mensaje},
                    {"role": "assistant", "content": respuesta.content},
                    {"role": "user", "content": contenido},
                ]

        raise FalloDelAgente(
            f"El modelo no entrego una salida valida para {modelo_salida.__name__} "
            f"tras un reintento. Ultimo error:\n{error}"
        )

    # ----------------------------------------------------------------

    def _llamar(self, anthropic_mod, sistema, mensajes, definicion, herramienta):
        cliente = self._obtener()
        # Los modelos actuales rechazan tool_choice forzado ("tool"/"any"):
        # se usa "auto" y la obligacion de usar la herramienta va en el prompt.
        sistema = (
            f"{sistema}\n\nEntrega tu resultado llamando una sola vez a la herramienta "
            f"{herramienta}. No respondas con texto libre."
        )
        for intento in range(self.max_429 + 1):
            try:
                # Streaming: una entrega larga no choca con el timeout de la peticion.
                with cliente.messages.stream(
                    model=self.modelo,
                    max_tokens=self.max_tokens,
                    system=sistema,
                    messages=mensajes,
                    tools=[definicion],
                    tool_choice={"type": "auto", "disable_parallel_tool_use": True},
                ) as flujo:
                    return flujo.get_final_message()
            except anthropic_mod.RateLimitError:
                if intento == self.max_429:
                    raise FalloDelAgente(
                        f"Limite de tasa alcanzado tras {self.max_429} reintentos."
                    )
                espera = (2**intento) + random.uniform(0, 1)
                time.sleep(espera)
            except anthropic_mod.APITimeoutError:
                raise FalloDelAgente(f"La llamada supero el timeout de {self.timeout}s.")
            except anthropic_mod.AuthenticationError:
                raise FalloDelAgente(
                    "La llave de API fue rechazada. Revisa ANTHROPIC_API_KEY."
                )
            except anthropic_mod.APIStatusError as exc:
                raise FalloDelAgente(
                    f"La API respondio {exc.status_code}: {exc.message}"
                )
            except anthropic_mod.APIConnectionError as exc:
                raise FalloDelAgente(f"No se pudo conectar con la API: {exc}")
        raise FalloDelAgente("No se pudo completar la llamada.")


def revisar_tope(cfg: dict, gasto_mes: float) -> str | None:
    """Devuelve un aviso, o lanza si se llego al tope."""
    tope = cfg.get("gasto", {}).get("tope_mensual_usd", 0)
    pct = cfg.get("gasto", {}).get("porcentaje_aviso", 70)
    if not tope:
        return None
    if gasto_mes >= tope:
        raise TopeDeGasto(
            f"El gasto del mes (${gasto_mes:.2f}) alcanzo el tope de ${tope:.2f}. "
            "Sube el tope en config.json para continuar."
        )
    if gasto_mes >= tope * pct / 100:
        return (
            f"Llevas ${gasto_mes:.2f} de ${tope:.2f} "
            f"({gasto_mes / tope * 100:.0f}% del tope mensual)."
        )
    return None
