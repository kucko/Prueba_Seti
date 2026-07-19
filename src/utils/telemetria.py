"""
Telemetría ligera para observabilidad del sistema.

Cada evento relevante se registra como una línea JSON (JSONL) en
observabilidad/eventos.jsonl:
- llamada_llm: agente, nodo, duración y éxito de cada invocación al modelo
- entrevista_iniciada / entrevista_finalizada: participación y abandono
- analisis_ejecutado: corridas del Agente Analista

Decisión de diseño: telemetría local sin dependencias (auditable y funciona
offline). Para observabilidad avanzada, LangSmith se activa solo con
variables de entorno (ver README), sin tocar el código.
"""

import json
import os
from datetime import datetime


def _ruta() -> str:
    return os.getenv("RUTA_TELEMETRIA", os.path.join("observabilidad", "eventos.jsonl"))


def registrar(evento: str, **datos) -> None:
    """Registra un evento. Nunca interrumpe el flujo principal si falla."""
    try:
        ruta = _ruta()
        os.makedirs(os.path.dirname(ruta), exist_ok=True)
        linea = {"ts": datetime.now().isoformat(timespec="seconds"),
                 "evento": evento, **datos}
        with open(ruta, "a", encoding="utf-8") as f:
            f.write(json.dumps(linea, ensure_ascii=False) + "\n")
    except OSError:
        pass


def cargar_eventos() -> list[dict]:
    """Lee todos los eventos registrados (para el dashboard)."""
    ruta = _ruta()
    if not os.path.exists(ruta):
        return []
    eventos = []
    with open(ruta, encoding="utf-8") as f:
        for linea in f:
            try:
                eventos.append(json.loads(linea))
            except json.JSONDecodeError:
                continue
    return eventos
