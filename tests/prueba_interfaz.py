"""
Prueba de la interfaz Streamlit con AppTest (sin navegador, sin API key).

Valida:
1. Que la app carga sin excepciones y el dashboard muestra métricas
   con los datos de ejemplo.
2. Que el flujo de entrevista por chat funciona: iniciar, responder dos
   preguntas y salir anticipadamente consolidando el registro.

Ejecutar desde la raíz del proyecto:
    python -m tests.prueba_interfaz
"""

import os
import shutil

os.environ["USAR_LLM_FALSO"] = "1"
os.environ["DIRECTORIO_ENTREVISTAS"] = "tests/_salida_ui/entrevistas"
os.environ["DIRECTORIO_INFORMES"] = "tests/_salida_ui/informes"
os.environ["RUTA_TELEMETRIA"] = "tests/_salida_ui/eventos.jsonl"
os.environ["RUTA_CONFIG"] = "tests/_salida_ui/config.json"

from streamlit.testing.v1 import AppTest  # noqa: E402


def probar_carga_y_dashboard():
    at = AppTest.from_file("app.py", default_timeout=30).run()
    assert not at.exception, at.exception
    textos = " ".join(m.value for m in at.metric)
    assert at.metric, "El dashboard no mostró métricas"
    assert any("5" == m.value for m in at.metric), textos  # 5 entrevistas de ejemplo
    print(f"[OK] App carga sin errores · {len(at.metric)} métricas en dashboard")


def probar_flujo_entrevista():
    shutil.rmtree("tests/_salida_ui", ignore_errors=True)
    at = AppTest.from_file("app.py", default_timeout=30).run()

    at.button[0].click().run()                       # Iniciar entrevista
    assert not at.exception, at.exception
    assert at.chat_message, "No apareció la primera pregunta"

    at.chat_input[0].set_value(
        "Mi líder me apoya con seguimiento semanal.").run()
    assert not at.exception, at.exception
    at.chat_input[0].set_value(
        "Los errores los conversamos con calma.").run()
    assert not at.exception, at.exception

    at.chat_input[0].set_value("salir").run()        # salida anticipada
    assert not at.exception, at.exception
    assert at.success, "No se mostró el mensaje de cierre"

    import glob
    archivos = glob.glob("tests/_salida_ui/entrevistas/entrevista_*.json")
    assert archivos, "No se consolidó el registro de la entrevista"
    print(f"[OK] Flujo de entrevista por chat -> {archivos[0]}")


def probar_configuracion():
    from src.config import configuracion
    cfg = configuracion.cargar()
    assert len(cfg["preguntas"]) == 16
    cfg["entrevistador"]["max_repreguntas"] = 2
    cfg["analista"]["umbral_alerta"] = 2.5
    configuracion.guardar(cfg)
    recargada = configuracion.cargar()
    assert recargada["entrevistador"]["max_repreguntas"] == 2
    assert recargada["analista"]["umbral_alerta"] == 2.5
    configuracion.restaurar()
    assert configuracion.cargar()["entrevistador"]["max_repreguntas"] == 1
    print("[OK] Configuración: guardar, aplicar y restaurar")


if __name__ == "__main__":
    probar_carga_y_dashboard()
    probar_configuracion()
    probar_flujo_entrevista()
    print("\n✔ Pruebas de interfaz superadas.")
