"""
Prueba de humo end-to-end SIN API key ni internet (USAR_LLM_FALSO=1).

Valida:
1. Que el Agente Entrevistador recorre las 16 preguntas con human-in-the-loop
   (interrupt/resume) a través del orquestador y guarda el registro JSON.
2. Que el Agente Analista carga las entrevistas, calcula métricas y genera
   el informe en Markdown.

Ejecutar desde la raíz del proyecto:
    python -m tests.prueba_humo
"""

import json
import os
import shutil
import uuid

os.environ["USAR_LLM_FALSO"] = "1"
os.environ["DIRECTORIO_ENTREVISTAS"] = "tests/_salida/entrevistas"
os.environ["DIRECTORIO_INFORMES"] = "tests/_salida/informes"
os.environ["RUTA_CONFIG"] = "tests/_salida/config.json"

from langgraph.types import Command  # noqa: E402

from src.config.preguntas import TOTAL_PREGUNTAS  # noqa: E402
from src.orquestador import construir_orquestador  # noqa: E402

RESPUESTAS_SIMULADAS = [
    "Mi líder me apoya bastante, hacemos seguimiento semanal.",
    "Se molesta a veces, pero luego lo hablamos con calma.",
    "Casi siempre me entero tarde de los cambios importantes.",
    "Sí, en las reuniones puedo proponer y me escuchan.",
    "Siento que mi esfuerzo pasa desapercibido.",
    "El salario está por debajo del mercado para mi rol.",
    "Hay pocas vacantes internas, no veo mucho crecimiento.",
    "Este año hice un curso que pagó la empresa.",
    "Mi equipo es lo mejor de la empresa, nos apoyamos mucho.",
    "Otras áreas se demoran, pero al final ayudan.",
    "A veces trabajo de noche para alcanzar las entregas.",
    "Semana de por medio siento bastante estrés.",
    "Prefiero callar en algunas reuniones para evitar problemas.",
    "Confío en RRHH, han manejado bien los casos que conozco.",
    "Sí, la empresa tiene buen nombre y eso me enorgullece.",
    "Depende de si mejora el tema salarial, pero creo que sí.",
]


def probar_entrevista() -> str:
    shutil.rmtree("tests/_salida", ignore_errors=True)
    orq = construir_orquestador()
    config = {"configurable": {"thread_id": str(uuid.uuid4())},
              "recursion_limit": 200}

    resultado = orq.invoke({"modo": "entrevista", "empleado_id": "EMP-TEST",
                            "equipo": "Tecnología"}, config)

    turnos = 0
    while "__interrupt__" in resultado:
        datos = resultado["__interrupt__"][0].value
        assert 1 <= datos["numero"] <= TOTAL_PREGUNTAS, datos
        assert datos["pregunta"], "La pregunta formulada llegó vacía"
        respuesta = RESPUESTAS_SIMULADAS[datos["numero"] - 1]
        resultado = orq.invoke(Command(resume=respuesta), config)
        turnos += 1
        assert turnos < 60, "Demasiados turnos: posible bucle infinito"

    salida = resultado["resultado"]
    assert salida["preguntas_respondidas"] == TOTAL_PREGUNTAS, salida
    ruta = salida["ruta_archivo"]
    assert ruta and os.path.exists(ruta), f"No se creó el registro: {ruta}"

    with open(ruta, encoding="utf-8") as f:
        registro = json.load(f)
    assert registro["empleado_id"] == "EMP-TEST"
    assert registro["ambito"] == "equipo" and registro["equipo"] == "Tecnología"
    assert len(registro["respuestas"]) == TOTAL_PREGUNTAS
    assert all(1 <= r["puntaje"] <= 5 for r in registro["respuestas"])
    print(f"[OK] Entrevista completa ({turnos} turnos) -> {ruta}")
    return os.path.dirname(ruta)


def probar_analisis(directorio: str) -> None:
    orq = construir_orquestador()
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}
    resultado = orq.invoke({"modo": "analisis", "directorio": directorio}, config)

    salida = resultado["resultado"]
    metricas = salida["metricas"]
    assert metricas["n_entrevistas"] == 1
    assert metricas["n_respuestas"] == TOTAL_PREGUNTAS
    assert metricas["indice_general"] is not None
    ruta = salida["ruta_informe"]
    assert ruta and os.path.exists(ruta), "No se generó el informe"
    contenido = open(ruta, encoding="utf-8").read()
    assert "Informe de clima laboral" in contenido and "Compañía en general" in contenido
    print(f"[OK] Análisis y informe -> {ruta}")


def probar_analisis_por_equipo(directorio: str) -> None:
    orq = construir_orquestador()
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}
    resultado = orq.invoke({"modo": "analisis", "directorio": directorio,
                            "equipo": "Tecnología"}, config)
    m = resultado["resultado"]["metricas"]
    assert m["equipo"] == "Tecnología" and m["n_entrevistas"] == 1
    assert m["bajo_umbral_anonimato"] is True  # 1 < min_entrevistas_equipo (2)
    assert "equipo_tecnología" in resultado["resultado"]["ruta_informe"].lower()
    # Un equipo sin entrevistas cae en la rama de vacío
    config2 = {"configurable": {"thread_id": str(uuid.uuid4())}}
    r2 = orq.invoke({"modo": "analisis", "directorio": directorio,
                     "equipo": "NoExiste"}, config2)
    assert "No se encontraron entrevistas" in r2["resultado"]["mensaje"]
    print("[OK] Análisis segmentado por equipo (con umbral de anonimato)")


def probar_analisis_vacio() -> None:
    orq = construir_orquestador()
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}
    resultado = orq.invoke(
        {"modo": "analisis", "directorio": "tests/_no_existe"}, config)
    assert "No se encontraron entrevistas" in resultado["resultado"]["mensaje"]
    print("[OK] Manejo de directorio vacío")


if __name__ == "__main__":
    directorio = probar_entrevista()
    probar_analisis(directorio)
    probar_analisis_por_equipo(directorio)
    probar_analisis_vacio()
    print("\n✔ Todas las pruebas de humo pasaron. El sistema está operativo.")
