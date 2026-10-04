"""Bitacora append-only en SQLite.

REGLA CENTRAL: solo INSERT. Nunca UPDATE ni DELETE sobre casos,
aprobaciones ni entregas.

Un caso corregido no sobrescribe al anterior: se inserta como version
nueva que apunta al original con deriva_de. Eso es lo que convierte
esto en una trazabilidad defendible y no en una base de datos cualquiera.

Unica excepcion declarada: los acumuladores de tokens y costo en la
tabla ejecuciones, y el estado actual del orquestador. El historial
completo de estados vive en la tabla estados, que si es append-only.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime
from typing import Any

from servidor.config import RUTA_DB

ESQUEMA = """
CREATE TABLE IF NOT EXISTS ejecuciones (
    id               TEXT PRIMARY KEY,
    fecha_inicio     TEXT NOT NULL,
    historia         TEXT NOT NULL,
    entorno          TEXT NOT NULL,
    estado           TEXT NOT NULL,
    tokens_entrada   INTEGER NOT NULL DEFAULT 0,
    tokens_salida    INTEGER NOT NULL DEFAULT 0,
    costo_usd        REAL    NOT NULL DEFAULT 0.0
);

CREATE TABLE IF NOT EXISTS entregas (
    id            TEXT PRIMARY KEY,
    ejecucion_id  TEXT NOT NULL,
    etapa         TEXT NOT NULL,
    version       INTEGER NOT NULL,
    payload       TEXT NOT NULL,
    nota_previa   TEXT,
    fecha         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS casos (
    id                 TEXT PRIMARY KEY,
    ejecucion_id       TEXT NOT NULL,
    version            INTEGER NOT NULL,
    id_caso            TEXT NOT NULL,
    titulo             TEXT NOT NULL,
    criterio_origen    TEXT,
    pasos              TEXT NOT NULL,
    datos              TEXT NOT NULL,
    resultado_esperado TEXT NOT NULL,
    sin_respaldo       INTEGER NOT NULL DEFAULT 0,
    razon_sin_respaldo TEXT,
    deriva_de          TEXT,
    fecha              TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS aprobaciones (
    id            TEXT PRIMARY KEY,
    ejecucion_id  TEXT NOT NULL,
    etapa         TEXT NOT NULL,
    decision      TEXT NOT NULL,
    nota          TEXT,
    fecha         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS estados (
    id            TEXT PRIMARY KEY,
    ejecucion_id  TEXT NOT NULL,
    estado        TEXT NOT NULL,
    fecha         TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_entregas ON entregas(ejecucion_id, etapa);
CREATE INDEX IF NOT EXISTS ix_casos ON casos(ejecucion_id);
CREATE INDEX IF NOT EXISTS ix_aprob ON aprobaciones(ejecucion_id);
CREATE INDEX IF NOT EXISTS ix_estados ON estados(ejecucion_id);
"""


def _ahora() -> str:
    # Microsegundos a proposito: la bitacora se ordena por esta marca y
    # varios eventos pueden caer dentro del mismo segundo.
    return datetime.now().isoformat(timespec="microseconds")


def _nid() -> str:
    return uuid.uuid4().hex[:12]


def conectar() -> sqlite3.Connection:
    cx = sqlite3.connect(RUTA_DB, check_same_thread=False)
    cx.row_factory = sqlite3.Row
    return cx


def inicializar() -> None:
    with conectar() as cx:
        cx.executescript(ESQUEMA)


# --------------------------------------------------------------------
# Escrituras
# --------------------------------------------------------------------


def crear_ejecucion(historia: str, entorno: str) -> str:
    eid = _nid()
    with conectar() as cx:
        cx.execute(
            "INSERT INTO ejecuciones (id, fecha_inicio, historia, entorno, estado) "
            "VALUES (?,?,?,?,?)",
            (eid, _ahora(), historia, entorno, "Analizando"),
        )
        cx.execute(
            "INSERT INTO estados (id, ejecucion_id, estado, fecha) VALUES (?,?,?,?)",
            (_nid(), eid, "Analizando", _ahora()),
        )
    return eid


def fijar_estado(ejecucion_id: str, estado: str) -> None:
    """El estado actual se actualiza; el historial se inserta."""
    with conectar() as cx:
        cx.execute("UPDATE ejecuciones SET estado=? WHERE id=?", (estado, ejecucion_id))
        cx.execute(
            "INSERT INTO estados (id, ejecucion_id, estado, fecha) VALUES (?,?,?,?)",
            (_nid(), ejecucion_id, estado, _ahora()),
        )


def guardar_entrega(ejecucion_id: str, etapa: str, payload: dict, nota_previa: str | None) -> int:
    with conectar() as cx:
        fila = cx.execute(
            "SELECT COALESCE(MAX(version),0) v FROM entregas WHERE ejecucion_id=? AND etapa=?",
            (ejecucion_id, etapa),
        ).fetchone()
        version = fila["v"] + 1
        cx.execute(
            "INSERT INTO entregas (id, ejecucion_id, etapa, version, payload, nota_previa, fecha) "
            "VALUES (?,?,?,?,?,?,?)",
            (
                _nid(),
                ejecucion_id,
                etapa,
                version,
                json.dumps(payload, ensure_ascii=False),
                nota_previa,
                _ahora(),
            ),
        )
    return version


def insertar_caso(ejecucion_id: str, caso: dict, deriva_de: str | None = None) -> str:
    rid = _nid()
    with conectar() as cx:
        fila = cx.execute(
            "SELECT COALESCE(MAX(version),0) v FROM casos WHERE ejecucion_id=? AND id_caso=?",
            (ejecucion_id, caso["id_caso"]),
        ).fetchone()
        cx.execute(
            "INSERT INTO casos (id, ejecucion_id, version, id_caso, titulo, criterio_origen, "
            "pasos, datos, resultado_esperado, sin_respaldo, razon_sin_respaldo, deriva_de, fecha) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                rid,
                ejecucion_id,
                fila["v"] + 1,
                caso["id_caso"],
                caso["titulo"],
                caso.get("criterio_origen"),
                json.dumps(caso["pasos"], ensure_ascii=False),
                json.dumps(caso.get("datos", {}), ensure_ascii=False),
                caso["resultado_esperado"],
                1 if caso.get("sin_respaldo") else 0,
                caso.get("razon_sin_respaldo"),
                deriva_de,
                _ahora(),
            ),
        )
    return rid


def registrar_aprobacion(ejecucion_id: str, etapa: str, decision: str, nota: str | None) -> None:
    with conectar() as cx:
        cx.execute(
            "INSERT INTO aprobaciones (id, ejecucion_id, etapa, decision, nota, fecha) "
            "VALUES (?,?,?,?,?,?)",
            (_nid(), ejecucion_id, etapa, decision, nota, _ahora()),
        )


def sumar_consumo(ejecucion_id: str, entrada: int, salida: int, costo: float) -> None:
    with conectar() as cx:
        cx.execute(
            "UPDATE ejecuciones SET tokens_entrada=tokens_entrada+?, "
            "tokens_salida=tokens_salida+?, costo_usd=costo_usd+? WHERE id=?",
            (entrada, salida, costo, ejecucion_id),
        )


# --------------------------------------------------------------------
# Lecturas
# --------------------------------------------------------------------


def ejecucion(ejecucion_id: str) -> dict | None:
    with conectar() as cx:
        f = cx.execute("SELECT * FROM ejecuciones WHERE id=?", (ejecucion_id,)).fetchone()
    return dict(f) if f else None


def ultima_entrega(ejecucion_id: str, etapa: str) -> dict | None:
    with conectar() as cx:
        f = cx.execute(
            "SELECT * FROM entregas WHERE ejecucion_id=? AND etapa=? "
            "ORDER BY version DESC LIMIT 1",
            (ejecucion_id, etapa),
        ).fetchone()
    if not f:
        return None
    d = dict(f)
    d["payload"] = json.loads(d["payload"])
    return d


def entregas(ejecucion_id: str) -> list[dict]:
    with conectar() as cx:
        filas = cx.execute(
            "SELECT etapa, version, nota_previa, fecha FROM entregas "
            "WHERE ejecucion_id=? ORDER BY fecha",
            (ejecucion_id,),
        ).fetchall()
    return [dict(f) for f in filas]


def casos(ejecucion_id: str, solo_ultimas: bool = True) -> list[dict]:
    with conectar() as cx:
        filas = cx.execute(
            "SELECT * FROM casos WHERE ejecucion_id=? ORDER BY id_caso, version",
            (ejecucion_id,),
        ).fetchall()
    out = []
    for f in filas:
        d = dict(f)
        d["pasos"] = json.loads(d["pasos"])
        d["datos"] = json.loads(d["datos"])
        d["sin_respaldo"] = bool(d["sin_respaldo"])
        out.append(d)
    if not solo_ultimas:
        return out
    ultimas: dict[str, dict] = {}
    for c in out:
        ultimas[c["id_caso"]] = c
    return list(ultimas.values())


def aprobaciones(ejecucion_id: str) -> list[dict]:
    with conectar() as cx:
        filas = cx.execute(
            "SELECT * FROM aprobaciones WHERE ejecucion_id=? ORDER BY fecha",
            (ejecucion_id,),
        ).fetchall()
    return [dict(f) for f in filas]


def bitacora(ejecucion_id: str) -> list[dict]:
    """Linea de tiempo unificada: entregas y decisiones, en orden."""
    eventos: list[dict] = []
    for e in entregas(ejecucion_id):
        eventos.append(
            {
                "fecha": e["fecha"],
                "etapa": e["etapa"],
                "accion": f"Entrega generada (v{e['version']})",
                "nota": e["nota_previa"],
                "clase": "nota",
            }
        )
    for a in aprobaciones(ejecucion_id):
        rotulo = {
            "aprobado": "Entrega aprobada",
            "cambios": "Cambios solicitados",
            "rechazado": "Entrega rechazada",
        }[a["decision"]]
        eventos.append(
            {
                "fecha": a["fecha"],
                "etapa": a["etapa"],
                "accion": rotulo,
                "nota": a["nota"],
                "clase": a["decision"],
            }
        )
    eventos.sort(key=lambda x: x["fecha"])
    return eventos


def gasto_del_mes() -> float:
    prefijo = datetime.now().strftime("%Y-%m")
    with conectar() as cx:
        f = cx.execute(
            "SELECT COALESCE(SUM(costo_usd),0) t FROM ejecuciones WHERE fecha_inicio LIKE ?",
            (f"{prefijo}%",),
        ).fetchone()
    return float(f["t"])


def listar_ejecuciones(limite: int = 20) -> list[dict]:
    with conectar() as cx:
        filas = cx.execute(
            "SELECT id, fecha_inicio, entorno, estado, costo_usd, "
            "substr(historia,1,80) resumen FROM ejecuciones "
            "ORDER BY fecha_inicio DESC LIMIT ?",
            (limite,),
        ).fetchall()
    return [dict(f) for f in filas]
