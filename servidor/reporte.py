"""Reporte PDF con evidencias, armado desde la bitacora.

El documento es el entregable que se manda a auditoria: muestra los
casos, quien aprobo cada etapa, con que nota y en que momento. No es un
resumen bonito: es el registro.
"""

from __future__ import annotations

import io
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from servidor import db

TINTA = colors.HexColor("#161A1F")
GRIS = colors.HexColor("#596270")
LINEA = colors.HexColor("#DCE2E9")
ACENTO = colors.HexColor("#2C56C6")
AMBAR = colors.HexColor("#8C5B00")
AMBAR_F = colors.HexColor("#FBEFD9")


def _estilos():
    base = getSampleStyleSheet()
    return {
        "titulo": ParagraphStyle(
            "titulo", parent=base["Title"], fontSize=18, leading=22,
            textColor=TINTA, alignment=TA_LEFT, spaceAfter=4,
        ),
        "sub": ParagraphStyle(
            "sub", parent=base["Normal"], fontSize=9.5, textColor=GRIS, spaceAfter=16
        ),
        "h2": ParagraphStyle(
            "h2", parent=base["Heading2"], fontSize=12.5, leading=15,
            textColor=TINTA, spaceBefore=16, spaceAfter=7,
        ),
        "h3": ParagraphStyle(
            "h3", parent=base["Heading3"], fontSize=10.5, leading=13,
            textColor=TINTA, spaceBefore=10, spaceAfter=4,
        ),
        "p": ParagraphStyle(
            "p", parent=base["Normal"], fontSize=9.5, leading=13.5,
            textColor=TINTA, spaceAfter=5,
        ),
        "gris": ParagraphStyle(
            "gris", parent=base["Normal"], fontSize=9, leading=12.5, textColor=GRIS
        ),
        "mono": ParagraphStyle(
            "mono", parent=base["Normal"], fontName="Courier", fontSize=8,
            leading=11, textColor=GRIS,
        ),
        "celda": ParagraphStyle(
            "celda", parent=base["Normal"], fontSize=8.5, leading=11.5, textColor=TINTA
        ),
    }


def _tabla(datos, anchos, est):
    t = Table(datos, colWidths=anchos, repeatRows=1)
    t.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("TEXTCOLOR", (0, 0), (-1, 0), GRIS),
                ("LINEBELOW", (0, 0), (-1, 0), 0.7, LINEA),
                ("LINEBELOW", (0, 1), (-1, -2), 0.4, LINEA),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return t


def generar(ejecucion_id: str) -> bytes:
    ej = db.ejecucion(ejecucion_id)
    if not ej:
        raise ValueError("No existe esa ejecucion.")

    est = _estilos()
    casos = db.casos(ejecucion_id)
    historial = db.casos(ejecucion_id, solo_ultimas=False)
    bit = db.bitacora(ejecucion_id)
    ent_a = db.ultima_entrega(ejecucion_id, "analisis")
    ent_s = db.ultima_entrega(ejecucion_id, "automatizacion")

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=letter,
        leftMargin=2.2 * cm, rightMargin=2.2 * cm,
        topMargin=2 * cm, bottomMargin=2 * cm,
        title=f"Reporte de pruebas {ejecucion_id}",
    )
    E: list = []

    # Portada ---------------------------------------------------------
    E.append(Paragraph("Reporte de diseño de pruebas", est["titulo"]))
    E.append(
        Paragraph(
            f"Ejecución {ejecucion_id} · entorno {ej['entorno']} · "
            f"generado el {datetime.now():%d/%m/%Y %H:%M}",
            est["sub"],
        )
    )

    sr = sum(1 for c in casos if c["sin_respaldo"])
    resumen = [
        ["Casos diseñados", str(len(casos))],
        ["Sin respaldo en criterios", str(sr)],
        ["Decisiones registradas", str(len(db.aprobaciones(ejecucion_id)))],
        ["Versiones en bitácora", str(len(historial))],
        ["Costo de la corrida", f"${ej['costo_usd']:.4f} USD"],
        ["Tokens", f"{ej['tokens_entrada']:,} entrada / {ej['tokens_salida']:,} salida"],
    ]
    E.append(_tabla([["Concepto", "Valor"]] + resumen, [8 * cm, 8.6 * cm], est))

    E.append(Paragraph("Historia de usuario", est["h2"]))
    for linea in ej["historia"].split("\n"):
        E.append(Paragraph(linea.replace("&", "&amp;").replace("<", "&lt;") or "&nbsp;", est["mono"]))

    # Analisis --------------------------------------------------------
    if ent_a and "criterios" in ent_a["payload"]:
        a = ent_a["payload"]
        E.append(Paragraph("Análisis del requisito", est["h2"]))
        E.append(Paragraph(a.get("resumen", ""), est["p"]))
        filas = [["Criterio", "Texto", "Verificable"]]
        for c in a.get("criterios", []):
            filas.append([
                c["id"],
                Paragraph(c["texto"], est["celda"]),
                "Sí" if c["verificable"] else "No",
            ])
        E.append(_tabla(filas, [2 * cm, 12.2 * cm, 2.4 * cm], est))
        if a.get("ambiguedades"):
            E.append(Paragraph("Ambigüedades detectadas", est["h3"]))
            for am in a["ambiguedades"]:
                E.append(Paragraph(f"• {am['descripcion']} <i>({am['impacto']})</i>", est["gris"]))

    # Casos -----------------------------------------------------------
    E.append(PageBreak())
    E.append(Paragraph("Casos de prueba", est["h2"]))
    E.append(
        Paragraph(
            "Los casos marcados <b>sin respaldo</b> no se desprenden de ningún criterio "
            "de aceptación: el agente los propuso por inferencia y el revisor los evaluó "
            "como tales.",
            est["gris"],
        )
    )
    E.append(Spacer(1, 8))

    for c in casos:
        bloque = [Paragraph(f"{c['id_caso']} · {c['titulo']}", est["h3"])]
        meta = c["criterio_origen"] or "sin respaldo en criterios"
        bloque.append(Paragraph(f"Origen: {meta} · versión {c['version']}", est["gris"]))
        if c["sin_respaldo"] and c["razon_sin_respaldo"]:
            t = Table(
                [[Paragraph(f"<b>Por qué se propone:</b> {c['razon_sin_respaldo']}", est["celda"])]],
                colWidths=[16.6 * cm],
            )
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), AMBAR_F),
                ("BOX", (0, 0), (-1, -1), 0.6, AMBAR),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]))
            bloque.append(Spacer(1, 3))
            bloque.append(t)
        bloque.append(Spacer(1, 4))
        for i, paso in enumerate(c["pasos"], 1):
            bloque.append(Paragraph(f"{i}. {paso}", est["p"]))
        if c["datos"]:
            datos = " · ".join(f"{k}: {v}" for k, v in c["datos"].items())
            bloque.append(Paragraph(f"Datos: {datos}", est["mono"]))
        bloque.append(Paragraph(f"<b>Esperado:</b> {c['resultado_esperado']}", est["p"]))
        E.append(KeepTogether(bloque))
        E.append(Spacer(1, 7))

    # Automatizacion --------------------------------------------------
    if ent_s and ent_s["payload"].get("archivos"):
        E.append(PageBreak())
        E.append(Paragraph("Automatización generada", est["h2"]))
        E.append(
            Paragraph(
                "Dos archivos por caso: la clase de página concentra los selectores, "
                "el escenario solo llama a sus métodos.",
                est["gris"],
            )
        )
        filas = [["Archivo", "Tipo"]]
        for a in ent_s["payload"]["archivos"]:
            filas.append([Paragraph(a["ruta_relativa"], est["celda"]),
                          "Page Object" if a["tipo"] == "page_object" else "Escenario"])
        E.append(_tabla(filas, [12.6 * cm, 4 * cm], est))
        reutil = ent_s["payload"].get("clases_reutilizadas") or []
        if reutil:
            E.append(Paragraph(f"Clases reutilizadas: {', '.join(reutil)}", est["gris"]))

    # Bitacora --------------------------------------------------------
    E.append(PageBreak())
    E.append(Paragraph("Bitácora de la ejecución", est["h2"]))
    E.append(
        Paragraph(
            "Registro de solo inserción: ninguna entrada se sobrescribe ni se elimina. "
            "Las correcciones aparecen como versiones nuevas junto a las anteriores.",
            est["gris"],
        )
    )
    E.append(Spacer(1, 6))
    filas = [["Fecha y hora", "Etapa", "Acción", "Nota del revisor"]]
    for b in bit:
        filas.append([
            Paragraph(b["fecha"].replace("T", " ")[:19], est["celda"]),
            Paragraph(ROTULO.get(b["etapa"], b["etapa"]), est["celda"]),
            Paragraph(b["accion"], est["celda"]),
            Paragraph(b["nota"] or "—", est["celda"]),
        ])
    E.append(_tabla(filas, [3.4 * cm, 3 * cm, 4.2 * cm, 6 * cm], est))

    if len(historial) > len(casos):
        E.append(Paragraph("Versiones anteriores de los casos", est["h3"]))
        E.append(
            Paragraph(
                f"La bitácora conserva {len(historial)} versiones de {len(casos)} casos. "
                "Las versiones superadas siguen disponibles para auditoría.",
                est["gris"],
            )
        )

    doc.build(E)
    return buf.getvalue()


ROTULO = {
    "analisis": "Análisis",
    "casos": "Casos de prueba",
    "automatizacion": "Automatización",
}
