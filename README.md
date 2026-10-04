# CicloQA

Sistema web con agentes de IA para el ciclo de diseño de pruebas. Pegas una
historia de usuario y tres agentes la recorren — analizan el requisito,
diseñan los casos y escriben la automatización en Playwright — deteniéndose
a que una persona apruebe en cada etapa.

Corre en tu máquina. La llave de API no sale de tu equipo.

---

## Arrancarlo

**1. Python 3.11 o superior.** Compruébalo con `python --version`.

**2. Entorno virtual e instalación:**

```bash
python -m venv .venv
# Windows:        .\.venv\Scripts\Activate.ps1
# macOS o Linux:  source .venv/bin/activate
pip install -r requirements.txt
```

**3. La llave de API.** Consíguela en <https://console.anthropic.com>.

```powershell
# Windows PowerShell
$env:ANTHROPIC_API_KEY = "sk-ant-..."
```
```bash
# macOS o Linux
export ANTHROPIC_API_KEY="sk-ant-..."
```

Nunca la escribas en un archivo del proyecto. El `.gitignore` ya excluye
`.env`, pero la variable de entorno evita el problema de raíz.

**4. Arranca el servidor:**

```bash
uvicorn servidor.main:app --reload --port 8000
```

Abre <http://127.0.0.1:8000>.

---

## Antes de gastar tokens

```bash
python prueba_sin_api.py
```

Recorre el pipeline completo con un cliente simulado: comprueba la máquina
de estados, el versionado, la bitácora y el PDF sin hacer una sola llamada
a la API. Si esto falla, el problema es del código y no de tu configuración.

---

## Qué hace cada pieza

```
servidor/
  main.py              API HTTP y servidor web
  config.py            Carga de config.json; la llave vive en el entorno
  esquemas.py          Contratos Pydantic de cada agente
  claude_client.py     Llamadas con salida estructurada y reintento único
  db.py                SQLite append-only
  orquestador.py       Máquina de estados con las compuertas de aprobación
  reporte.py           PDF con casos, decisiones y bitácora
  agentes/
    analisis.py        Agente 1 · criterios, ambigüedades, riesgos
    casos.py           Agente 2 · casos en español con datos inventados
    automatizacion.py  Agente 3 · Playwright con Page Object Model
web/
  index.html           Interfaz
  app.js               Lógica de la interfaz
```

## Las reglas que el código hace cumplir

**El código decide el flujo, el modelo decide el contenido.** El orquestador
es una máquina de estados determinista. Ningún LLM decide qué paso sigue.

**Nunca se parsea texto libre.** Cada agente declara su salida como un modelo
Pydantic que viaja a la API como esquema de herramienta. Si la respuesta no
valida, hay un reintento con el error a la vista; si falla otra vez, fallo
explícito. Nunca se adivina.

**La bitácora solo inserta.** Un caso corregido no sobrescribe al anterior:
entra como versión nueva. Las únicas excepciones declaradas son el estado
actual del orquestador y los acumuladores de tokens, y el historial completo
de estados vive aparte en su propia tabla.

**El spec no contiene selectores.** `validar_pom()` los busca con expresiones
regulares en los archivos `.spec.ts`. Si los encuentra, le devuelve el
incumplimiento concreto al agente y lo hace regenerar una vez.

**Los tokens se leen, no se estiman.** Salen de `respuesta.usage` y alimentan
el costo real que ves en la interfaz y en el PDF.

---

## Endpoints

| Método | Ruta | Para qué |
| --- | --- | --- |
| GET | `/api/salud` | Estado de la llave, modelo y gasto del mes |
| GET | `/api/ejecuciones` | Lista de corridas |
| POST | `/api/ejecuciones` | Inicia una corrida y corre el agente de análisis |
| GET | `/api/ejecuciones/{id}` | Estado completo de una corrida |
| POST | `/api/ejecuciones/{id}/decision` | Aprobar, pedir cambios o rechazar |
| GET | `/api/ejecuciones/{id}/reporte.pdf` | Descarga el reporte |

La documentación interactiva de la API está en `/api/docs`.

---

## Costo

Con `claude-sonnet-5-5` a $2 por millón de tokens de entrada y $10 de salida,
una corrida de las tres etapas ronda los **$0.05 a $0.15 USD** según el
tamaño de la historia. El tope mensual está en `config.json` con aviso
automático al 70%.

## Lo que queda fuera de esta versión

- La ejecución real de las pruebas generadas. El sistema las escribe; correrlas
  es el siguiente agente.
- Múltiples proveedores de IA. Solo Claude.
- Varios usuarios. Corre local, para una persona.
