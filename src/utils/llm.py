"""
Punto único de acceso al modelo de lenguaje.

Dos modos:
- Real: Gemini (API gratuita de Google AI Studio) vía langchain-google-genai.
- Falso (USAR_LLM_FALSO=1): respuestas deterministas sin conexión, para
  probar todo el flujo del sistema sin API key ni costos.

Decisión de diseño: los agentes nunca importan el proveedor directamente;
siempre llaman a obtener_llm(). Cambiar de proveedor = cambiar una línea aquí.
"""

import json
import os
import re
import time

from src.utils.telemetria import registrar


def obtener_llm():
    """Devuelve el modelo de chat según la configuración del entorno."""
    if os.getenv("USAR_LLM_FALSO") == "1":
        return LLMFalso()

    from langchain_google_genai import ChatGoogleGenerativeAI

    from src.config.configuracion import cargar
    cfg = cargar()["modelo"]
    modelo = os.getenv("MODELO_LLM") or cfg["nombre"]
    return ChatGoogleGenerativeAI(model=modelo, temperature=float(cfg["temperatura"]))


def invocar_llm(prompt: str, agente: str, nodo: str) -> str:
    """
    Invoca el LLM registrando telemetría (agente, nodo, latencia, éxito).
    Punto único de observabilidad de todas las llamadas al modelo.
    """
    inicio = time.perf_counter()
    try:
        contenido = obtener_llm().invoke(prompt).content
        # Modelos recientes (p. ej. Gemini 3) devuelven bloques, no texto plano
        if isinstance(contenido, list):
            partes = [b.get("text", "") if isinstance(b, dict) else str(b)
                      for b in contenido]
            contenido = "\n".join(p for p in partes if p)
        registrar("llamada_llm", agente=agente, nodo=nodo, exito=True,
                  duracion_ms=round((time.perf_counter() - inicio) * 1000))
        return contenido
    except Exception as e:
        registrar("llamada_llm", agente=agente, nodo=nodo, exito=False,
                  duracion_ms=round((time.perf_counter() - inicio) * 1000),
                  error=str(e)[:200])
        raise


def extraer_json(texto: str) -> dict:
    """
    Extrae el primer objeto JSON de una respuesta del LLM.
    Tolera cercos de código (```json ... ```) y texto adicional.
    """
    limpio = re.sub(r"```(?:json)?", "", texto).strip()
    inicio = limpio.find("{")
    fin = limpio.rfind("}")
    if inicio == -1 or fin == -1:
        raise ValueError(f"No se encontró JSON en la respuesta: {texto[:200]}")
    return json.loads(limpio[inicio : fin + 1])


class _RespuestaFalsa:
    """Imita la interfaz mínima de un mensaje de LangChain (.content)."""

    def __init__(self, content: str):
        self.content = content


class LLMFalso:
    """
    Modelo simulado para pruebas offline y demo de contingencia.
    Detecta por el contenido del prompt qué tipo de salida se espera.
    """

    _contador = 0

    def invoke(self, entrada):
        texto = self._a_texto(entrada)

        if "SOLO un objeto JSON" in texto and "puntaje" in texto:
            # Interpretación de una respuesta del empleado
            respuesta = re.search(r'RESPUESTA DEL EMPLEADO: """(.*?)"""', texto, re.S)
            if respuesta and len(respuesta.group(1).strip()) < 8:
                return _RespuestaFalsa(json.dumps({
                    "puntaje": 3, "sentimiento": "neutral", "temas": [],
                    "respuesta_suficiente": False,
                    "nota": "Respuesta demasiado breve (simulado).",
                }, ensure_ascii=False))
            LLMFalso._contador += 1
            puntaje = (LLMFalso._contador % 5) + 1  # rota 2,3,4,5,1,...
            sentimiento = {1: "negativo", 2: "negativo", 3: "neutral",
                           4: "positivo", 5: "positivo"}[puntaje]
            return _RespuestaFalsa(json.dumps({
                "puntaje": puntaje,
                "sentimiento": sentimiento,
                "temas": ["tema simulado"],
                "respuesta_suficiente": True,
                "nota": "Interpretación simulada (modo offline).",
            }, ensure_ascii=False))

        if "informe" in texto.lower() or "análisis cualitativo" in texto.lower():
            return _RespuestaFalsa(
                "### Síntesis general (simulada)\n"
                "El clima laboral muestra fortalezas en colaboración y oportunidades "
                "de mejora en comunicación. *Texto generado en modo offline para pruebas.*"
            )

        if "resumen" in texto.lower():
            return _RespuestaFalsa(
                "El colaborador expresó una percepción mixta, con aspectos positivos "
                "en su equipo y oportunidades de mejora en reconocimiento. (Simulado)"
            )

        # Por defecto: formulación conversacional de una pregunta
        base = re.search(r"PREGUNTA BASE:\s*(.+)", texto)
        pregunta = base.group(1).strip() if base else "¿Podrías contarme un poco más?"
        return _RespuestaFalsa(f"Cuéntame, {pregunta[0].lower()}{pregunta[1:]}")

    @staticmethod
    def _a_texto(entrada) -> str:
        if isinstance(entrada, str):
            return entrada
        if isinstance(entrada, list):
            partes = []
            for m in entrada:
                partes.append(m.get("content", "") if isinstance(m, dict)
                              else getattr(m, "content", str(m)))
            return "\n".join(partes)
        return str(entrada)
