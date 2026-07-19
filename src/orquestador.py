"""
ORQUESTADOR — Grafo padre del sistema multiagente

Mecanismo de orquestación explícito:
1. Un grafo LangGraph de nivel superior recibe el modo de operación y
   enruta hacia el agente correspondiente (Entrevistador o Analista),
   cada uno implementado como su propio StateGraph (subgrafo).
2. Los agentes se sincronizan de forma asíncrona a través de un
   almacén compartido de artefactos: los JSON de /entrevistas que
   escribe el Entrevistador son la entrada que consume el Analista.

    START -> decidir -> agente_entrevistador -> END
                    \\-> agente_analista     -> END
"""

from typing import Optional, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import StateGraph, START, END

from src.agentes.analista import construir_grafo_analista
from src.agentes.entrevistador import construir_grafo_entrevistador, estado_inicial


class EstadoOrquestador(TypedDict, total=False):
    modo: str                    # "entrevista" | "analisis"
    empleado_id: Optional[str]   # requerido en modo entrevista (seudónimo)
    equipo: Optional[str]        # ámbito: None = compañía general
    directorio: Optional[str]    # requerido en modo análisis
    resultado: dict              # salida del agente ejecutado


# Subgrafos compilados. checkpointer=True => heredan la persistencia del padre,
# lo que permite que el interrupt() del Entrevistador pause TODO el sistema
# y se reanude exactamente donde iba la conversación.
_grafo_entrevistador = construir_grafo_entrevistador().compile(checkpointer=True)
_grafo_analista = construir_grafo_analista().compile(checkpointer=True)


def decidir(estado: EstadoOrquestador) -> dict:
    """Valida la solicitud antes de delegar en un agente."""
    modo = estado.get("modo")
    if modo not in ("entrevista", "analisis"):
        raise ValueError(f"Modo no soportado: {modo!r}. Usa 'entrevista' o 'analisis'.")
    if modo == "entrevista" and not estado.get("empleado_id"):
        raise ValueError("El modo entrevista requiere un empleado_id (seudónimo).")
    if modo == "analisis" and not estado.get("directorio"):
        raise ValueError("El modo análisis requiere un directorio de entrevistas.")
    return {}


def _ruta(estado: EstadoOrquestador) -> str:
    return ("agente_entrevistador" if estado["modo"] == "entrevista"
            else "agente_analista")


def agente_entrevistador(estado: EstadoOrquestador) -> dict:
    salida = _grafo_entrevistador.invoke(
        estado_inicial(estado["empleado_id"], estado.get("equipo")))
    return {"resultado": {
        "ruta_archivo": salida.get("ruta_archivo"),
        "mensaje_cierre": salida.get("mensaje_cierre"),
        "preguntas_respondidas": len(salida.get("respuestas", [])),
    }}


def agente_analista(estado: EstadoOrquestador) -> dict:
    salida = _grafo_analista.invoke(
        {"directorio": estado["directorio"], "equipo": estado.get("equipo")})
    return {"resultado": {
        "ruta_informe": salida.get("ruta_informe"),
        "mensaje": salida.get("mensaje"),
        "metricas": salida.get("metricas"),
    }}


def construir_orquestador(checkpointer=None):
    grafo = StateGraph(EstadoOrquestador)
    grafo.add_node("decidir", decidir)
    grafo.add_node("agente_entrevistador", agente_entrevistador)
    grafo.add_node("agente_analista", agente_analista)

    grafo.add_edge(START, "decidir")
    grafo.add_conditional_edges("decidir", _ruta,
                                ["agente_entrevistador", "agente_analista"])
    grafo.add_edge("agente_entrevistador", END)
    grafo.add_edge("agente_analista", END)
    return grafo.compile(checkpointer=checkpointer or InMemorySaver())
