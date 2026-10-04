"""Agente 3 · Automatizacion con Page Object Model.

El riesgo aqui no es que el codigo no compile, sino que compile y sea
basura mantenible: una page class nueva por cada caso, tres versiones de
LoginPage, selectores duplicados. Por eso el inventario de clases
existentes se lee ANTES de generar, y por eso hay un validador mecanico
que rechaza cualquier spec que contenga un selector.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from servidor.agentes.base import Contexto
from servidor.esquemas import ResultadoAutomatizacion

PROMPT = """Eres un SDET senior especialista en Playwright con TypeScript.

Generas automatizacion siguiendo Page Object Model de forma estricta.

Reglas que no se negocian:
- Por cada caso de prueba generas DOS archivos: la page class en pages/ y el
  escenario en tests/. Nunca uno solo.
- TODOS los selectores viven en la page class. Un archivo .spec.ts que contenga
  un locator, un getBy, un page.click o cualquier selector se RECHAZA. El spec
  solo llama metodos de la page class y hace assertions sobre resultados.
- Antes de crear una page class nueva revisas el inventario de clases existentes
  que se te entrega. Si la pagina ya tiene clase, la REUTILIZAS o la EXTIENDES
  con metodos nuevos, devolviendo el archivo completo actualizado. Nunca duplicas.
  Las clases que reutilices las listas en clases_reutilizadas.
- Prefieres getByRole y getByLabel sobre selectores CSS o XPath.
- El codigo va en ingles por convencion, aunque los casos esten en espanol.
- Usas async/await correctamente y los assertions de @playwright/test.
- El nombre del test incluye el id del caso, por ejemplo:
  test('TC-0001 inicio de sesion valido', async ({ page }) => { ... })
"""

PATRONES_SELECTOR = [
    r"\bpage\.locator\(",
    r"\bgetBy(Role|Label|Text|TestId|Placeholder|AltText|Title)\(",
    r"\bpage\.(click|fill|type|check|selectOption|press)\(",
    r"['\"]#[\w-]+['\"]",
    r"\blocator\s*\(",
]


def leer_inventario(carpeta: Path) -> list[str]:
    """Lee las page classes existentes para que el agente no duplique."""
    if not carpeta.exists():
        return []
    return [
        f"=== {a.name} ===\n{a.read_text(encoding='utf-8')}"
        for a in sorted(carpeta.glob("*.ts"))
    ]


def validar_pom(resultado: ResultadoAutomatizacion) -> list[str]:
    """Rechaza specs que contengan selectores. Validacion mecanica."""
    problemas = []
    for archivo in resultado.archivos:
        es_spec = archivo.tipo == "spec" or archivo.ruta_relativa.endswith(".spec.ts")
        if not es_spec:
            continue
        for patron in PATRONES_SELECTOR:
            if re.search(patron, archivo.contenido):
                problemas.append(
                    f"{archivo.ruta_relativa} contiene un selector. "
                    "Los selectores van en la page class, no en el escenario."
                )
                break
    return problemas


def bloque_pagina(rec: dict | None) -> str:
    """Lo que el navegador vio al abrir la URL, o la advertencia de que no vio nada."""
    if not rec or rec.get("error") or not rec.get("estructura"):
        return (
            "No se pudo abrir la pagina antes de generar, asi que NO conoces su "
            "estructura real. Deja en notas que los selectores no estan verificados."
        )
    recorte = " (recortada por tamano)" if rec.get("estructura_recortada") else ""
    return (
        f"Estructura accesible REAL de {rec.get('url_final') or rec['url']}, leida con un "
        f"navegador sin iniciar sesion{recorte}. Titulo: {rec.get('titulo', '')}\n"
        "Los selectores de esta pagina deben salir de aqui: usa los roles y nombres "
        "tal como aparecen, no los inventes.\n\n"
        f"{rec['estructura']}\n\n"
        "Solo conoces esta pagina. Si un caso recorre otras pantallas (por ejemplo, las "
        "que aparecen despues de iniciar sesion), no viste su estructura: deja en notas "
        "que page classes tienen selectores sin verificar."
    )


def ejecutar(ctx: Contexto):
    casos = (ctx.casos or {}).get("casos", [])
    incluidos = [c for c in casos if c["id_caso"] not in ctx.casos_excluidos]

    carpeta = Path(ctx.cfg.get("proyecto", {}).get("carpeta_pages", "")) if ctx.cfg.get("proyecto") else None
    inventario = leer_inventario(carpeta) if carpeta else []

    if inventario:
        bloque_inv = (
            "Page classes que YA EXISTEN en el proyecto. Reutilizalas o extiendelas, "
            "no las dupliques:\n\n" + "\n\n".join(inventario)
        )
    else:
        bloque_inv = (
            "El proyecto todavia no tiene page classes. Esta es la primera "
            "generacion: crea las que hagan falta."
        )

    mensaje = (
        f"Sitio bajo prueba: {ctx.url}\n\n"
        f"{bloque_pagina(ctx.reconocimiento)}\n\n"
        f"Convenciones del equipo:\n{ctx.bloque_convenciones()}\n"
        f"{bloque_inv}\n\n"
        "Casos de prueba aprobados por el QA:\n\n"
        f"{json.dumps(incluidos, ensure_ascii=False, indent=2)}\n\n"
        "Genera la automatizacion siguiendo Page Object Model."
        f"{ctx.bloque_nota()}"
    )

    resultado, consumo = ctx.cliente.pedir(PROMPT, mensaje, ResultadoAutomatizacion)

    problemas = validar_pom(resultado)
    if problemas:
        # Un reintento dirigido: se le devuelve el incumplimiento concreto.
        mensaje_fix = (
            mensaje
            + "\n\nTu entrega anterior fue RECHAZADA por el validador de Page Object:\n"
            + "\n".join(f"- {p}" for p in problemas)
            + "\n\nMueve esos selectores a la page class y vuelve a entregar."
        )
        resultado, c2 = ctx.cliente.pedir(PROMPT, mensaje_fix, ResultadoAutomatizacion)
        consumo = consumo.sumar(c2)
        problemas = validar_pom(resultado)
        if problemas:
            resultado.notas.extend(f"Sigue incumpliendo POM: {p}" for p in problemas)

    return resultado, consumo


def escribir_archivos(resultado: ResultadoAutomatizacion, carpeta: Path) -> list[str]:
    """Escribe los archivos generados en disco. Sobrescribe si existen."""
    escritos = []
    for archivo in resultado.archivos:
        destino = carpeta / archivo.ruta_relativa
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(archivo.contenido, encoding="utf-8")
        escritos.append(str(destino))
    return escritos
