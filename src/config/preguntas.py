"""
Guion de la entrevista de clima laboral.

Las preguntas ahora son EDITABLES desde la pestaña "Configuración" de la
interfaz; este módulo expone funciones que leen la configuración vigente en
cada llamada. Las constantes al final existen por retrocompatibilidad (pruebas
y scripts): reflejan los valores al momento de importar, no ediciones en vivo.
"""

from src.config.configuracion import cargar


def obtener_preguntas() -> list[dict]:
    return cargar()["preguntas"]


def obtener_dimensiones() -> list[str]:
    vistas, orden = set(), []
    for p in obtener_preguntas():
        if p["dimension"] not in vistas:
            vistas.add(p["dimension"])
            orden.append(p["dimension"])
    return orden


def total_preguntas() -> int:
    return len(obtener_preguntas())


# Retrocompatibilidad (valores congelados al importar)
PREGUNTAS = obtener_preguntas()
DIMENSIONES = obtener_dimensiones()
TOTAL_PREGUNTAS = total_preguntas()
