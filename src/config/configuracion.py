"""
Configuración editable del sistema.

Los valores por defecto viven en este archivo (código versionado). Los cambios
hechos desde la pestaña "Configuración" de la interfaz se guardan en
config/configuracion.json y tienen prioridad sobre los defectos.

Los agentes leen la configuración EN CADA LLAMADA (no al importar), por lo que
un cambio guardado aplica de inmediato a la siguiente entrevista o análisis,
sin reiniciar la aplicación.
"""

import copy
import json
import os


def _ruta() -> str:
    return os.getenv("RUTA_CONFIG", os.path.join("config", "configuracion.json"))


PREGUNTAS_DEFECTO = [
    {"id": 1, "dimension": "Liderazgo",
     "texto": "¿Cómo es tu relación con tu líder directo y cómo te apoya en el día a día?"},
    {"id": 2, "dimension": "Liderazgo",
     "texto": "Cuando cometes un error, ¿cómo suele reaccionar tu líder?"},
    {"id": 3, "dimension": "Comunicación",
     "texto": "¿Te enteras a tiempo y con claridad de las decisiones que afectan tu trabajo?"},
    {"id": 4, "dimension": "Comunicación",
     "texto": "¿Sientes que tus ideas son escuchadas cuando las propones?"},
    {"id": 5, "dimension": "Reconocimiento y compensación",
     "texto": "¿Sientes que tu trabajo es reconocido y valorado?"},
    {"id": 6, "dimension": "Reconocimiento y compensación",
     "texto": "¿Consideras justa tu compensación frente a tus responsabilidades?"},
    {"id": 7, "dimension": "Desarrollo",
     "texto": "¿Ves oportunidades reales de crecer profesionalmente en la organización?"},
    {"id": 8, "dimension": "Desarrollo",
     "texto": "¿Has recibido formación o apoyo para desarrollar nuevas habilidades en el último año?"},
    {"id": 9, "dimension": "Trabajo en equipo",
     "texto": "¿Cómo describirías la colaboración dentro de tu equipo?"},
    {"id": 10, "dimension": "Trabajo en equipo",
     "texto": "Cuando necesitas ayuda de otras áreas, ¿qué tan fácil es conseguirla?"},
    {"id": 11, "dimension": "Balance y carga laboral",
     "texto": "¿Tu carga de trabajo te permite desconectarte y descansar?"},
    {"id": 12, "dimension": "Balance y carga laboral",
     "texto": "¿Con qué frecuencia sientes estrés laboral que afecta tu vida personal?"},
    {"id": 13, "dimension": "Seguridad psicológica",
     "texto": "¿Te sientes seguro expresando desacuerdos sin temor a consecuencias?"},
    {"id": 14, "dimension": "Seguridad psicológica",
     "texto": "¿Confías en que si reportas un problema será tratado de forma justa?"},
    {"id": 15, "dimension": "Pertenencia y propósito",
     "texto": "¿Sientes orgullo de trabajar en esta organización? ¿Por qué?"},
    {"id": 16, "dimension": "Pertenencia y propósito",
     "texto": "¿Te ves trabajando aquí dentro de dos años?"},
]

VALORES_DEFECTO = {
    "preguntas": PREGUNTAS_DEFECTO,
    "entrevistador": {
        "personalidad": ('Eres "Clima", un entrevistador virtual cálido, empático y '
                         "profesional que mide el clima laboral mediante conversación "
                         "(no encuesta)."),
        "reglas": ("- Reformula la PREGUNTA BASE en lenguaje natural, cercano y en español.\n"
                   "- NO cambies el sentido ni el alcance de la pregunta base.\n"
                   "- Máximo 2 frases. Sin viñetas, sin numeración, sin emojis.\n"
                   "- No inventes datos sobre el empleado ni sobre la organización.\n"
                   "- VARÍA tus transiciones: nunca inicies dos turnos seguidos con la misma fórmula.\n"
                   '- Evita muletillas de empatía como "Entiendo", "Comprendo" o '
                   '"Es comprensible"; a veces pasa directo a la pregunta sin preámbulo.'),
        "instruccion_inicio": ("Es el inicio: saluda brevemente, recuerda en una frase que la "
                               "conversación es anónima y confidencial, y formula la primera pregunta."),
        "instruccion_transicion": ("Haz una transición breve y variada desde lo que acaba de "
                                   "contar el empleado, o pasa directo a la pregunta."),
        "instruccion_repregunta": ("La respuesta anterior fue breve o evasiva. Agradece con "
                                   "calidez y pide amablemente un ejemplo concreto o un poco "
                                   "más de detalle, SIN presionar ni juzgar."),
        "max_repreguntas": 1,
    },
    "organizacion": {
        "equipos": ["Operaciones", "Tecnología", "Comercial"],
    },
    "analista": {
        "umbral_alerta": 3.0,
        "min_entrevistas_equipo": 2,
        "max_notas_llm": 80,
        "max_palabras_analisis": 350,
        "instrucciones_adicionales": "",
        "pregunta_permanencia_id": 16,
    },
    "modelo": {
        "nombre": "gemini-3-flash-preview",
        "temperatura": 0.4,
    },
}


def cargar() -> dict:
    """Devuelve la configuración vigente: defectos + cambios guardados."""
    cfg = copy.deepcopy(VALORES_DEFECTO)
    ruta = _ruta()
    if os.path.exists(ruta):
        try:
            with open(ruta, encoding="utf-8") as f:
                guardada = json.load(f)
            for seccion, valores in guardada.items():
                if seccion == "preguntas":
                    if isinstance(valores, list) and valores:
                        cfg["preguntas"] = valores
                elif seccion in cfg and isinstance(valores, dict):
                    cfg[seccion].update(valores)
        except (json.JSONDecodeError, OSError):
            pass  # un archivo corrupto no debe tumbar el sistema: se usan defectos
    return cfg


def guardar(cfg: dict) -> None:
    ruta = _ruta()
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def restaurar() -> dict:
    """Elimina la configuración guardada y vuelve a los valores de fábrica."""
    try:
        os.remove(_ruta())
    except OSError:
        pass
    return copy.deepcopy(VALORES_DEFECTO)
