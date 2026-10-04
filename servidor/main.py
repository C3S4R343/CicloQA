"""API y servidor web de CicloQA.

Arranque:
    uvicorn servidor.main:app --reload --port 8000

La llave de la API se lee de ANTHROPIC_API_KEY. Corre en local: la llave
no sale de tu maquina.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from servidor import config, db, orquestador
from servidor.claude_client import ClienteClaude, FalloDelAgente, TopeDeGasto, revisar_tope
from servidor.esquemas import Decision, NuevaEjecucion
from servidor.reporte import generar as generar_pdf

WEB = Path(__file__).resolve().parents[1] / "web"

app = FastAPI(title="CicloQA", docs_url="/api/docs")


@app.on_event("startup")
def arrancar() -> None:
    db.inicializar()


def _orq() -> orquestador.Orquestador:
    cfg = config.cargar()
    return orquestador.Orquestador(cfg, ClienteClaude(cfg))


# --------------------------------------------------------------------
# API
# --------------------------------------------------------------------


@app.get("/api/salud")
def salud() -> dict:
    cfg = config.cargar()
    gasto = db.gasto_del_mes()
    aviso = None
    try:
        aviso = revisar_tope(cfg, gasto)
        tope_alcanzado = False
    except TopeDeGasto as e:
        aviso, tope_alcanzado = str(e), True
    return {
        "llave_configurada": config.hay_llave(),
        "modelo": cfg["modelo"],
        "entorno": cfg["entorno"],
        "gasto_mes_usd": round(gasto, 4),
        "tope_usd": cfg["gasto"]["tope_mensual_usd"],
        "aviso": aviso,
        "tope_alcanzado": tope_alcanzado,
    }


@app.get("/api/ejecuciones")
def listar() -> list[dict]:
    return db.listar_ejecuciones()


@app.post("/api/ejecuciones")
def crear(datos: NuevaEjecucion) -> dict:
    cfg = config.cargar()
    if not config.hay_llave():
        raise HTTPException(400, "No hay llave de API configurada en ANTHROPIC_API_KEY.")
    try:
        revisar_tope(cfg, db.gasto_del_mes())
    except TopeDeGasto as e:
        raise HTTPException(402, str(e))
    try:
        eid = _orq().iniciar(datos.historia.strip(), datos.entorno)
    except FalloDelAgente as e:
        raise HTTPException(502, str(e))
    return orquestador.vista(eid)


@app.get("/api/ejecuciones/{eid}")
def ver(eid: str) -> dict:
    try:
        return orquestador.vista(eid)
    except ValueError as e:
        raise HTTPException(404, str(e))


@app.post("/api/ejecuciones/{eid}/decision")
def decidir(eid: str, d: Decision) -> dict:
    try:
        _orq().continuar(eid, d.decision, (d.nota or "").strip() or None, d.casos_excluidos)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except FalloDelAgente as e:
        raise HTTPException(502, str(e))
    return orquestador.vista(eid)


@app.get("/api/ejecuciones/{eid}/reporte.pdf")
def reporte(eid: str) -> Response:
    try:
        pdf = generar_pdf(eid)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="reporte-{eid}.pdf"'},
    )


# --------------------------------------------------------------------
# Interfaz
# --------------------------------------------------------------------


@app.get("/")
def inicio() -> FileResponse:
    return FileResponse(WEB / "index.html")


app.mount("/web", StaticFiles(directory=WEB), name="web")
