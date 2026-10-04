"""Prueba el pipeline completo sin gastar un solo token.

Sustituye el cliente de Claude por uno simulado que devuelve respuestas
fijas. Comprueba la maquina de estados, la bitacora append-only, el
versionado y el PDF.

    python prueba_sin_api.py
"""

from __future__ import annotations

from servidor import config, db, orquestador
from servidor.esquemas import (
    Ambiguedad,
    ArchivoGenerado,
    CasoDePrueba,
    Consumo,
    CriterioIdentificado,
    ResultadoAnalisis,
    ResultadoAutomatizacion,
    ResultadoCasos,
)
from servidor.reporte import generar


class ClienteSimulado:
    """Devuelve respuestas fijas. No toca la red ni gasta tokens."""

    def __init__(self):
        self.llamadas = 0

    def pedir(self, sistema, mensaje, modelo_salida, herramienta="entregar_resultado"):
        self.llamadas += 1
        consumo = Consumo(tokens_entrada=1200, tokens_salida=900, costo_usd=0.0114)
        hay_nota = "pidio cambios" in mensaje

        if modelo_salida is ResultadoAnalisis:
            criterios = [
                CriterioIdentificado(id="CA-1", texto="Credenciales validas dan acceso al catalogo", verificable=True),
                CriterioIdentificado(id="CA-2", texto="Credenciales invalidas muestran error", verificable=True),
                CriterioIdentificado(id="CA-3", texto="Campo vacio indica cual falta", verificable=True),
            ]
            if hay_nota:
                criterios.append(
                    CriterioIdentificado(id="CA-4", texto="Se bloquea la cuenta tras varios intentos", verificable=True)
                )
            return (
                ResultadoAnalisis(
                    resumen="La historia cubre el inicio de sesion con tres condiciones de validacion.",
                    criterios=criterios,
                    ambiguedades=[Ambiguedad(descripcion="No dice cuantos intentos fallidos se permiten",
                                             impacto="No se puede disenar la prueba de bloqueo")],
                    riesgos=["La sesion podria no expirar"],
                ),
                consumo,
            )

        if modelo_salida is ResultadoCasos:
            return (
                ResultadoCasos(
                    casos=[
                        CasoDePrueba(
                            id_caso="TC-0001", titulo="Inicio de sesion con credenciales validas",
                            criterio_origen="CA-1", pasos=["Abrir el portal", "Capturar usuario", "Enviar"],
                            datos={"usuario": "standard_user", "password": "secret_sauce"},
                            resultado_esperado="Se muestra el listado de productos", sin_respaldo=False,
                        ),
                        CasoDePrueba(
                            id_caso="TC-0002", titulo="Bloqueo tras tres intentos fallidos",
                            criterio_origen=None, pasos=["Fallar el acceso tres veces"],
                            datos={"usuario": "standard_user", "password": "malo"},
                            resultado_esperado="La cuenta queda bloqueada", sin_respaldo=True,
                            razon_sin_respaldo="Ningun criterio lo menciona, pero es un control de seguridad habitual",
                        ),
                    ],
                    cobertura="CA-1 y CA-2 cubiertos. CA-3 pendiente.",
                ),
                consumo,
            )

        if modelo_salida is ResultadoAutomatizacion:
            return (
                ResultadoAutomatizacion(
                    archivos=[
                        ArchivoGenerado(
                            ruta_relativa="pages/LoginPage.ts", tipo="page_object",
                            contenido=(
                                "import { Page } from '@playwright/test';\n\n"
                                "export class LoginPage {\n"
                                "  constructor(private page: Page) {}\n"
                                "  async login(user: string, pass: string) {\n"
                                "    await this.page.getByLabel('Username').fill(user);\n"
                                "  }\n}\n"
                            ),
                        ),
                        ArchivoGenerado(
                            ruta_relativa="tests/TC-0001.spec.ts", tipo="spec",
                            contenido=(
                                "import { test, expect } from '@playwright/test';\n"
                                "import { LoginPage } from '../pages/LoginPage';\n\n"
                                "test('TC-0001 login valido', async ({ page }) => {\n"
                                "  const login = new LoginPage(page);\n"
                                "  await login.login('standard_user', 'secret_sauce');\n"
                                "});\n"
                            ),
                        ),
                    ],
                    clases_reutilizadas=[],
                ),
                consumo,
            )
        raise AssertionError(f"Modelo no simulado: {modelo_salida}")


def main() -> int:
    db.inicializar()
    cfg = config.cargar()
    cli = ClienteSimulado()
    orq = orquestador.Orquestador(cfg, cli)

    print("\n=== 1. Inicio y primera entrega ===")
    eid = orq.iniciar("Historia de prueba para validar el pipeline completo.", "qa")
    v = orquestador.vista(eid)
    assert v["estado"] == "EsperaAnalisis", v["estado"]
    assert len(v["analisis"]["criterios"]) == 3
    print(f"  Estado: {v['estado']} · {len(v['analisis']['criterios'])} criterios")

    print("\n=== 2. Pedir cambios: vuelve a la misma etapa y sube version ===")
    orq.continuar(eid, "cambios", "Falta el caso de bloqueo de cuenta", [])
    v = orquestador.vista(eid)
    assert v["estado"] == "EsperaAnalisis", v["estado"]
    assert v["versiones"]["analisis"] == 2, v["versiones"]
    assert len(v["analisis"]["criterios"]) == 4
    print(f"  Estado: {v['estado']} · version {v['versiones']['analisis']} · "
          f"{len(v['analisis']['criterios'])} criterios")

    print("\n=== 3. Aprobar: avanza a casos ===")
    orq.continuar(eid, "aprobado", None, [])
    v = orquestador.vista(eid)
    assert v["estado"] == "EsperaCasos", v["estado"]
    casos = db.casos(eid)
    sr = [c for c in casos if c["sin_respaldo"]]
    assert len(casos) == 2 and len(sr) == 1
    print(f"  Estado: {v['estado']} · {len(casos)} casos, {len(sr)} sin respaldo")

    print("\n=== 4. Excluir un caso y aprobar: avanza a scripts ===")
    orq.continuar(eid, "aprobado", None, ["TC-0002"])
    v = orquestador.vista(eid)
    assert v["estado"] == "EsperaScripts", v["estado"]
    print(f"  Estado: {v['estado']} · {len(v['automatizacion']['archivos'])} archivos")

    print("\n=== 5. Aprobar la ultima etapa: termina ===")
    orq.continuar(eid, "aprobado", None, [])
    v = orquestador.vista(eid)
    assert v["estado"] == "Terminado", v["estado"]
    print(f"  Estado: {v['estado']} · costo ${v['consumo']['costo_usd']:.4f} "
          f"· {cli.llamadas} llamadas simuladas")

    print("\n=== 6. Bitacora ===")
    for b in v["bitacora"]:
        nota = f" — {b['nota']}" if b["nota"] else ""
        print(f"  {b['fecha'][11:16]}  {b['etapa']:16} {b['accion']:28}{nota}")
    assert len(v["bitacora"]) == 8, len(v["bitacora"])

    print("\n=== 7. Append-only: ninguna version se perdio ===")
    hist = db.casos(eid, solo_ultimas=False)
    print(f"  {len(hist)} registros historicos de casos")

    print("\n=== 8. Rechazo corta el proceso ===")
    eid2 = orq.iniciar("Segunda historia para probar el rechazo.", "qa")
    orq.continuar(eid2, "rechazado", "Los criterios no son claros", [])
    v2 = orquestador.vista(eid2)
    assert v2["estado"] == "Cancelado", v2["estado"]
    print(f"  Estado: {v2['estado']}")

    print("\n=== 9. Reporte PDF ===")
    pdf = generar(eid)
    assert pdf[:4] == b"%PDF", pdf[:8]
    print(f"  PDF generado: {len(pdf):,} bytes")

    print("\nTODO CORRECTO. Pipeline, bitacora, versionado y reporte funcionan "
          "sin gastar tokens.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
