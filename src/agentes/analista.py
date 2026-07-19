"""
AGENTE 2 — ANALISTA

Rol: sincronizarse con los registros generados por el Entrevistador,
evaluar TODAS las entrevistas y producir un informe general de clima laboral.

Decisión de diseño clave:
- Las MÉTRICAS se calculan con código determinista (reproducibles y auditables).
- El LLM se usa solo para el ANÁLISIS CUALITATIVO (temas recurrentes,
  fortalezas, riesgos y recomendaciones).

Orquestación interna (LangGraph):
    START -> cargar_entrevistas -> [¿hay datos?]
                 | no -> reportar_vacio -> END
                 | sí -> calcular_metricas -> analizar_cualitativo
                          -> generar_informe -> END
"""

import glob
import json
import os
from collections import Counter
from datetime import datetime
from statistics import mean
from typing import Optional, TypedDict

from langgraph.graph import StateGraph, START, END

from src.config.configuracion import cargar as cargar_config
from src.utils.llm import invocar_llm
from src.utils.telemetria import registrar

DIRECTORIO_INFORMES = os.getenv("DIRECTORIO_INFORMES", "informes")


class EstadoAnalisis(TypedDict, total=False):
    directorio: str
    equipo: Optional[str]     # None = análisis de toda la compañía
    entrevistas: list
    metricas: dict
    analisis_cualitativo: str
    ruta_informe: Optional[str]
    mensaje: str


# --------------------------------------------------------------------------
# Nodos
# --------------------------------------------------------------------------

def cargar_entrevistas(estado: EstadoAnalisis) -> dict:
    """
    Lee los registros JSON generados por el Agente Entrevistador.
    Si el estado trae un equipo, filtra el corpus a ese equipo (ámbito).
    """
    rutas = sorted(glob.glob(os.path.join(estado["directorio"], "entrevista_*.json")))
    entrevistas = []
    for ruta in rutas:
        try:
            with open(ruta, encoding="utf-8") as f:
                entrevistas.append(json.load(f))
        except (json.JSONDecodeError, OSError) as e:
            # Manejo de errores: un archivo corrupto no detiene el análisis.
            print(f"[Analista] Aviso: se omitió {ruta} ({e})")
    equipo = estado.get("equipo")
    if equipo:
        entrevistas = [e for e in entrevistas if e.get("equipo") == equipo]
    return {"entrevistas": entrevistas}


def reportar_vacio(estado: EstadoAnalisis) -> dict:
    ambito = f" para el equipo '{estado['equipo']}'" if estado.get("equipo") else ""
    return {"mensaje": (f"No se encontraron entrevistas{ambito} en "
                        f"'{estado['directorio']}'. Ejecuta primero el "
                        "Agente Entrevistador.")}


def calcular_metricas(estado: EstadoAnalisis) -> dict:
    """Métricas deterministas: promedios, distribución, alertas y permanencia."""
    cfg = cargar_config()["analista"]
    umbral = float(cfg["umbral_alerta"])
    id_permanencia = int(cfg["pregunta_permanencia_id"])
    entrevistas = estado["entrevistas"]
    por_dimension: dict[str, list[int]] = {}
    sentimientos: Counter = Counter()
    temas: Counter = Counter()
    puntajes_totales: list[int] = []
    intencion_permanencia: list[int] = []   # pregunta 16 como proxy de retención

    for ent in entrevistas:
        for r in ent.get("respuestas", []):
            por_dimension.setdefault(r["dimension"], []).append(r["puntaje"])
            puntajes_totales.append(r["puntaje"])
            sentimientos[r.get("sentimiento", "neutral")] += 1
            for t in r.get("temas", []):
                temas[t.strip().lower()] += 1
            if r.get("pregunta_id") == id_permanencia:
                intencion_permanencia.append(r["puntaje"])

    promedios = {d: round(mean(v), 2) for d, v in por_dimension.items() if v}

    # Desglose por equipo (con umbral de anonimato: equipos con pocas
    # entrevistas no se reportan individualmente para evitar reidentificación)
    min_equipo = int(cfg["min_entrevistas_equipo"])
    grupos: dict[str, list] = {}
    for ent in entrevistas:
        grupos.setdefault(ent.get("equipo") or "General", []).append(ent)
    por_equipo = {}
    for nombre, grupo in sorted(grupos.items()):
        puntajes = [r["puntaje"] for e in grupo for r in e.get("respuestas", [])]
        por_equipo[nombre] = {
            "n_entrevistas": len(grupo),
            "reportable": len(grupo) >= min_equipo,
            "indice": round(mean(puntajes), 2) if puntajes else None,
        }

    equipo_filtro = estado.get("equipo")
    metricas = {
        "ambito": f"Equipo {equipo_filtro}" if equipo_filtro else "Compañía en general",
        "equipo": equipo_filtro,
        "bajo_umbral_anonimato": bool(equipo_filtro) and len(entrevistas) < min_equipo,
        "min_entrevistas_equipo": min_equipo,
        "por_equipo": por_equipo,
        "n_entrevistas": len(entrevistas),
        "n_completadas": sum(1 for e in entrevistas if e.get("completada")),
        "n_respuestas": len(puntajes_totales),
        "indice_general": round(mean(puntajes_totales), 2) if puntajes_totales else None,
        "promedio_por_dimension": promedios,
        "umbral_alerta": umbral,
        "dimensiones_en_riesgo": sorted(
            [d for d, p in promedios.items() if p < umbral],
            key=lambda d: promedios[d]),
        "dimension_mas_fuerte": max(promedios, key=promedios.get) if promedios else None,
        "dimension_mas_debil": min(promedios, key=promedios.get) if promedios else None,
        "distribucion_sentimientos": dict(sentimientos),
        "temas_recurrentes": temas.most_common(10),
        "indice_permanencia": (round(mean(intencion_permanencia), 2)
                               if intencion_permanencia else None),
    }
    return {"metricas": metricas}


def analizar_cualitativo(estado: EstadoAnalisis) -> dict:
    """El LLM sintetiza hallazgos cualitativos a partir de métricas y notas."""
    cfg = cargar_config()["analista"]
    metricas = estado["metricas"]
    notas = []
    for ent in estado["entrevistas"]:
        for r in ent.get("respuestas", []):
            if r.get("nota"):
                notas.append(f"- [{r['dimension']}] {r['nota']}")
    muestra_notas = "\n".join(notas[:int(cfg["max_notas_llm"])])  # límite de contexto

    prompt = f"""Eres un consultor experto en clima organizacional. Con base en las
métricas y observaciones de entrevistas ANÓNIMAS, escribe el análisis cualitativo
de un informe de clima laboral, en español y en Markdown.

MÉTRICAS:
{json.dumps(metricas, ensure_ascii=False, indent=2)}

OBSERVACIONES POR RESPUESTA (anonimizadas):
{muestra_notas or "(sin observaciones)"}

Estructura EXACTA de tu respuesta (usa estos encabezados de nivel 3):
### Síntesis general
### Fortalezas
### Riesgos y focos de atención
### Recomendaciones accionables

Reglas: máximo {cfg['max_palabras_analisis']} palabras en total, tono
profesional y constructivo, no inventes datos que no estén en las métricas,
no incluyas nombres ni datos identificables.
{cfg['instrucciones_adicionales']}"""

    try:
        analisis = invocar_llm(prompt, "analista", "analizar_cualitativo").strip()
    except Exception as e:
        analisis = f"*Análisis cualitativo no disponible por un error del modelo: {e}*"
    return {"analisis_cualitativo": analisis}


def generar_informe(estado: EstadoAnalisis) -> dict:
    """Arma el informe final en Markdown y lo guarda en /informes."""
    m = estado["metricas"]

    def barra(valor: float, ancho: int = 20) -> str:
        llenos = round((valor / 5) * ancho)
        return "█" * llenos + "░" * (ancho - llenos)

    filas_dim = "\n".join(
        f"| {d} | {p:.2f} | `{barra(p)}` |"
        for d, p in sorted(m["promedio_por_dimension"].items(),
                           key=lambda x: -x[1]))
    temas = "\n".join(f"- {t} ({n} menciones)" for t, n in m["temas_recurrentes"][:8])
    umbral = m.get("umbral_alerta", 3.0)
    riesgo = (", ".join(m["dimensiones_en_riesgo"])
              if m["dimensiones_en_riesgo"] else "Ninguna bajo el umbral de alerta")

    filas_equipo = ""
    if not m.get("equipo") and len(m.get("por_equipo", {})) > 1:
        filas = []
        for nombre, d in m["por_equipo"].items():
            indice = (f"{d['indice']:.2f}" if d["reportable"] and d["indice"] is not None
                      else f"— no reportado (menos de {m['min_entrevistas_equipo']} entrevistas)")
            filas.append(f"| {nombre} | {d['n_entrevistas']} | {indice} |")
        filas_equipo = ("\n## Resultados por equipo\n"
                        "| Equipo | Entrevistas | Índice (1–5) |\n|---|---|---|\n"
                        + "\n".join(filas) + "\n")

    aviso_anonimato = ""
    if m.get("bajo_umbral_anonimato"):
        aviso_anonimato = (f"\n> ⚠️ **Aviso de anonimato:** este equipo tiene menos de "
                           f"{m['min_entrevistas_equipo']} entrevistas; los resultados "
                           "podrían permitir reidentificar respuestas. Trátese con "
                           "confidencialidad reforzada.\n")

    informe = f"""# Informe de clima laboral — {m['ambito']}
**Generado por el Sistema Multiagente de Clima Laboral** · {datetime.now():%Y-%m-%d %H:%M}
{aviso_anonimato}
## 1. Alcance
- Ámbito del análisis: **{m['ambito']}**
- Entrevistas analizadas: **{m['n_entrevistas']}** (completadas: {m['n_completadas']})
- Respuestas interpretadas: **{m['n_respuestas']}**
- Metodología: entrevista conversacional anónima de 16 preguntas en 8 dimensiones,
  interpretadas por el Agente Entrevistador y consolidadas por el Agente Analista.

## 2. Indicadores generales
- **Índice general de clima:** {m['indice_general']} / 5.0
- **Intención de permanencia (2 años):** {m['indice_permanencia']} / 5.0
- **Dimensión más fuerte:** {m['dimension_mas_fuerte']}
- **Dimensión más débil:** {m['dimension_mas_debil']}
- **Dimensiones en riesgo (promedio < {umbral}):** {riesgo}
- **Sentimiento de las respuestas:** {m['distribucion_sentimientos']}

## 3. Resultados por dimensión
| Dimensión | Promedio | Escala 1–5 |
|---|---|---|
{filas_dim}

## 4. Temas más mencionados
{temas or "- (sin temas registrados)"}
{filas_equipo}

## 5. Análisis cualitativo
{estado['analisis_cualitativo']}

---
*Los registros de origen están seudonimizados (EMP-XXXX). Este informe presenta
resultados agregados: ninguna respuesta individual es atribuible a una persona.*
"""

    os.makedirs(DIRECTORIO_INFORMES, exist_ok=True)
    sufijo = (f"equipo_{m['equipo'].lower().replace(' ', '-')}"
              if m.get("equipo") else "general")
    ruta = os.path.join(DIRECTORIO_INFORMES,
                        f"informe_clima_{sufijo}_{datetime.now():%Y%m%d_%H%M%S}.md")
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(informe)
    registrar("analisis_ejecutado", n_entrevistas=m["n_entrevistas"],
              equipo=m.get("equipo"), indice_general=m["indice_general"])
    return {"ruta_informe": ruta,
            "mensaje": f"Informe generado: {ruta}"}


# --------------------------------------------------------------------------
# Enrutamiento y construcción del grafo
# --------------------------------------------------------------------------

def _hay_datos(estado: EstadoAnalisis) -> str:
    return "calcular_metricas" if estado["entrevistas"] else "reportar_vacio"


def construir_grafo_analista():
    grafo = StateGraph(EstadoAnalisis)
    grafo.add_node("cargar_entrevistas", cargar_entrevistas)
    grafo.add_node("reportar_vacio", reportar_vacio)
    grafo.add_node("calcular_metricas", calcular_metricas)
    grafo.add_node("analizar_cualitativo", analizar_cualitativo)
    grafo.add_node("generar_informe", generar_informe)

    grafo.add_edge(START, "cargar_entrevistas")
    grafo.add_conditional_edges("cargar_entrevistas", _hay_datos,
                                ["calcular_metricas", "reportar_vacio"])
    grafo.add_edge("calcular_metricas", "analizar_cualitativo")
    grafo.add_edge("analizar_cualitativo", "generar_informe")
    grafo.add_edge("generar_informe", END)
    grafo.add_edge("reportar_vacio", END)
    return grafo
