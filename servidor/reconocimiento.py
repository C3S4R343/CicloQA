"""Reconocimiento de la pagina bajo prueba.

Abre la URL en un navegador real y captura dos cosas: la estructura
accesible (roles, etiquetas y campos) y un screenshot. La estructura
alimenta al agente de automatizacion para que los selectores salgan de
la pagina y no de su memoria; el screenshot queda como evidencia.

Aqui no interviene ningun modelo: es una lectura mecanica. Solo ve lo
que carga la URL sin iniciar sesion.
"""

from __future__ import annotations

from pathlib import Path

NOMBRE_CAPTURA = "reconocimiento.png"
MAX_ESTRUCTURA = 20_000
TIMEOUT_MS = 30_000


def reconocer(url: str, carpeta: Path) -> dict:
    """Devuelve el payload del reconocimiento. Si falla, trae 'error'."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {
            "url": url,
            "error": "Playwright no esta instalado. Corre: pip install -r requirements.txt "
            "y luego: playwright install chromium",
        }

    carpeta.mkdir(parents=True, exist_ok=True)
    try:
        with sync_playwright() as pw:
            navegador = pw.chromium.launch(headless=True)
            try:
                pagina = navegador.new_page(viewport={"width": 1280, "height": 800})
                pagina.goto(url, wait_until="load", timeout=TIMEOUT_MS)
                try:
                    pagina.wait_for_load_state("networkidle", timeout=5_000)
                except Exception:
                    pass  # paginas con trafico constante nunca quedan en reposo
                estructura = pagina.locator("body").aria_snapshot()
                pagina.screenshot(path=str(carpeta / NOMBRE_CAPTURA))
                titulo, url_final = pagina.title(), pagina.url
            finally:
                navegador.close()
    except Exception as exc:
        return {"url": url, "error": f"No se pudo abrir la pagina: {str(exc).splitlines()[0]}"}

    recortada = len(estructura) > MAX_ESTRUCTURA
    return {
        "url": url,
        "url_final": url_final,
        "titulo": titulo,
        "estructura": estructura[:MAX_ESTRUCTURA],
        "estructura_recortada": recortada,
        "captura": NOMBRE_CAPTURA,
    }
