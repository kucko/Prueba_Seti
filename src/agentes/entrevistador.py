"""
AGENTE 1 — ENTREVISTADOR ("Clima")

Rol: conducir la entrevista de clima laboral de forma conversacional.
- Cubre SIEMPRE las 16 preguntas del guion, en orden, pero reformuladas
  en lenguaje natural y enlazadas con lo que el empleado va contando.
- Interpreta cada respuesta (puntaje 1-5, sentimiento, temas) en el momento.
- Si una respuesta es evasiva o vacía, repregunta UNA vez con amabilidad.
- Al finalizar, consolida un registro seudonimizado en /entrevistas.

Orquestación interna (LangGraph):
    START -> formular_pregunta -> escuchar (interrupt) -> interpretar
                 ^                                            |
                 |___________ repreguntar / avanzar __________|
                                                              |
                                              consolidar -> END
"""

import json
import os
from datetime import datetime
from typing import Optional, TypedDict

from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt

from src.config.configuracion import cargar as cargar_config
from src.config.preguntas import obtener_preguntas, total_preguntas
from src.utils.llm import invocar_llm, extraer_json
from src.utils.telemetria import registrar

DIRECTORIO_ENTREVISTAS = os.getenv("DIRECTORIO_ENTREVISTAS", "entrevistas")
COMANDOS_SALIDA = {"salir", "terminar", "cancelar"}


class EstadoEntrevista(TypedDict, total=False):
    empleado_id: str          # seudónimo, p. ej. EMP-4F7A (nunca el nombre)
    equipo: Optional[str]     # None = medición general de la compañía
    indice: int               # índice de la pregunta actual (0..15)
    reintentos: int           # repreguntas usadas en la pregunta actual
    historial: list           # [{"rol": "agente"|"empleado", "texto": str}]
    respuestas: list          # respuestas ya interpretadas
    siguiente_paso: str       # "avanzar" | "repreguntar" | "consolidar"
    salida_anticipada: bool
    ruta_archivo: Optional[str]
    mensaje_cierre: str


# --------------------------------------------------------------------------
# Nodos
# --------------------------------------------------------------------------

def formular_pregunta(estado: EstadoEntrevista) -> dict:
    """Reformula la pregunta base del guion en tono conversacional."""
    cfg = cargar_config()["entrevistador"]
    pregunta = obtener_preguntas()[estado["indice"]]
    ultima_respuesta = next(
        (m["texto"] for m in reversed(estado.get("historial", []))
         if m["rol"] == "empleado"), None)

    if estado.get("reintentos", 0) > 0:
        instruccion_extra = cfg["instruccion_repregunta"]
    elif estado["indice"] == 0:
        instruccion_extra = cfg["instruccion_inicio"]
    else:
        instruccion_extra = cfg["instruccion_transicion"]

    prompt = f"""{cfg['personalidad']}

REGLAS:
{cfg['reglas']}

{instruccion_extra}

CONTEXTO — última respuesta del empleado: {ultima_respuesta or "(aún no hay)"}
PREGUNTA BASE: {pregunta['texto']}

Devuelve únicamente el texto que dirá el entrevistador."""

    if estado["indice"] == 0 and not estado.get("historial"):
        registrar("entrevista_iniciada", empleado_id=estado["empleado_id"])

    texto = invocar_llm(prompt, "entrevistador", "formular_pregunta").strip()
    historial = estado.get("historial", []) + [{"rol": "agente", "texto": texto}]
    return {"historial": historial}


def escuchar(estado: EstadoEntrevista) -> dict:
    """
    Pausa el grafo (human-in-the-loop) y espera la respuesta del empleado.
    LangGraph persiste el estado con el checkpointer y se reanuda con
    Command(resume=<respuesta>).
    """
    respuesta = interrupt({
        "pregunta": estado["historial"][-1]["texto"],
        "numero": estado["indice"] + 1,
        "total": total_preguntas(),
    })
    respuesta = str(respuesta).strip()
    historial = estado["historial"] + [{"rol": "empleado", "texto": respuesta}]
    return {"historial": historial}


def interpretar(estado: EstadoEntrevista) -> dict:
    """Analiza la respuesta y decide el siguiente paso del flujo."""
    respuesta_texto = estado["historial"][-1]["texto"]

    # Salida anticipada solicitada por el empleado
    if respuesta_texto.lower() in COMANDOS_SALIDA:
        return {"siguiente_paso": "consolidar", "salida_anticipada": True}

    pregunta = obtener_preguntas()[estado["indice"]]
    prompt = f"""Analiza la respuesta de un empleado en una entrevista de clima laboral.

PREGUNTA BASE: {pregunta['texto']}
DIMENSIÓN EVALUADA: {pregunta['dimension']}
RESPUESTA DEL EMPLEADO: \"\"\"{respuesta_texto}\"\"\"

Devuelve SOLO un objeto JSON (sin texto adicional) con estas claves:
- "puntaje": entero 1-5. Percepción del empleado sobre la dimensión
  (1=muy negativa, 3=neutral/mixta, 5=muy positiva).
- "sentimiento": "positivo" | "neutral" | "negativo".
- "temas": lista de 1 a 3 temas breves mencionados (strings).
- "respuesta_suficiente": booleano. false SOLO si la respuesta está vacía,
  es evasiva o no aborda la pregunta.
- "nota": una frase objetiva que resuma la respuesta, sin datos identificables."""

    try:
        datos = extraer_json(invocar_llm(prompt, "entrevistador", "interpretar"))
    except Exception:
        # Manejo de errores: si el LLM falla, registramos neutral y seguimos.
        datos = {"puntaje": 3, "sentimiento": "neutral", "temas": [],
                 "respuesta_suficiente": True,
                 "nota": "No fue posible interpretar automáticamente."}

    max_repreguntas = int(cargar_config()["entrevistador"]["max_repreguntas"])
    suficiente = bool(datos.get("respuesta_suficiente", True))
    if not suficiente and estado.get("reintentos", 0) < max_repreguntas:
        return {"reintentos": estado.get("reintentos", 0) + 1,
                "siguiente_paso": "repreguntar"}

    registro = {
        "pregunta_id": pregunta["id"],
        "dimension": pregunta["dimension"],
        "pregunta_base": pregunta["texto"],
        "pregunta_formulada": next(
            m["texto"] for m in reversed(estado["historial"]) if m["rol"] == "agente"),
        "respuesta": respuesta_texto,
        "puntaje": int(datos.get("puntaje") or 3),
        "sentimiento": datos.get("sentimiento", "neutral"),
        "temas": datos.get("temas", []),
        "nota": datos.get("nota", ""),
    }
    respuestas = estado.get("respuestas", []) + [registro]
    nuevo_indice = estado["indice"] + 1
    paso = "consolidar" if nuevo_indice >= total_preguntas() else "avanzar"
    return {"respuestas": respuestas, "indice": nuevo_indice,
            "reintentos": 0, "siguiente_paso": paso}


def consolidar(estado: EstadoEntrevista) -> dict:
    """Genera el registro seudonimizado de la entrevista y lo guarda en disco."""
    respuestas = estado.get("respuestas", [])
    resumen_base = "\n".join(
        f"- {r['dimension']}: {r['nota']} (puntaje {r['puntaje']})" for r in respuestas
    ) or "- (entrevista sin respuestas registradas)"

    prompt = f"""Escribe un resumen de máximo 3 frases sobre la percepción general
del colaborador en esta entrevista de clima laboral, en tono objetivo y sin
datos identificables. Base:
{resumen_base}"""
    try:
        resumen = invocar_llm(prompt, "entrevistador", "consolidar").strip()
    except Exception:
        resumen = "Resumen no disponible."

    registro = {
        "empleado_id": estado["empleado_id"],       # seudónimo, no identidad
        "ambito": "equipo" if estado.get("equipo") else "general",
        "equipo": estado.get("equipo"),
        "fecha": datetime.now().isoformat(timespec="seconds"),
        "completada": not estado.get("salida_anticipada", False),
        "preguntas_respondidas": len(respuestas),
        "total_preguntas": total_preguntas(),
        "resumen": resumen,
        "respuestas": respuestas,
    }

    os.makedirs(DIRECTORIO_ENTREVISTAS, exist_ok=True)
    ruta = os.path.join(DIRECTORIO_ENTREVISTAS,
                        f"entrevista_{estado['empleado_id']}.json")
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(registro, f, ensure_ascii=False, indent=2)

    registrar("entrevista_finalizada", empleado_id=estado["empleado_id"],
              equipo=estado.get("equipo"), completada=registro["completada"],
              preguntas_respondidas=len(respuestas))
    cierre = ("Gracias por tu tiempo y tu sinceridad. Tus respuestas quedaron "
              "registradas de forma anónima y ayudarán a mejorar el ambiente "
              "de trabajo para todos.")
    return {"ruta_archivo": ruta, "mensaje_cierre": cierre}


# --------------------------------------------------------------------------
# Enrutamiento y construcción del grafo
# --------------------------------------------------------------------------

def _ruta_despues_de_interpretar(estado: EstadoEntrevista) -> str:
    if estado["siguiente_paso"] == "consolidar":
        return "consolidar"
    return "formular_pregunta"   # cubre "avanzar" y "repreguntar"


def construir_grafo_entrevistador():
    grafo = StateGraph(EstadoEntrevista)
    grafo.add_node("formular_pregunta", formular_pregunta)
    grafo.add_node("escuchar", escuchar)
    grafo.add_node("interpretar", interpretar)
    grafo.add_node("consolidar", consolidar)

    grafo.add_edge(START, "formular_pregunta")
    grafo.add_edge("formular_pregunta", "escuchar")
    grafo.add_edge("escuchar", "interpretar")
    grafo.add_conditional_edges("interpretar", _ruta_despues_de_interpretar,
                                ["formular_pregunta", "consolidar"])
    grafo.add_edge("consolidar", END)
    return grafo


def estado_inicial(empleado_id: str, equipo: Optional[str] = None) -> EstadoEntrevista:
    return {"empleado_id": empleado_id, "equipo": equipo, "indice": 0,
            "reintentos": 0, "historial": [], "respuestas": [],
            "salida_anticipada": False}
