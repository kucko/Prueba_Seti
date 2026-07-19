"""
Sistema Multiagente de Medición de Clima Laboral
Punto de entrada (CLI).

Uso:
    python main.py entrevistar            # inicia una entrevista conversacional
    python main.py analizar               # analiza /entrevistas y genera informe
    python main.py analizar --dir datos_ejemplo   # demo con datos sintéticos

Variables de entorno (.env):
    GOOGLE_API_KEY=...       # API key de Google AI Studio (gratuita)
    USAR_LLM_FALSO=1         # opcional: prueba todo el flujo sin API ni internet
"""

import argparse
import secrets
import sys
import uuid

from dotenv import load_dotenv

load_dotenv()

from langgraph.types import Command  # noqa: E402

from src.orquestador import construir_orquestador  # noqa: E402

LINEA = "─" * 62


def _nuevo_empleado_id() -> str:
    """Seudónimo aleatorio: la identidad del empleado nunca se registra."""
    return f"EMP-{secrets.token_hex(2).upper()}"


def ejecutar_entrevista(equipo=None) -> None:
    orquestador = construir_orquestador()
    empleado_id = _nuevo_empleado_id()
    config = {"configurable": {"thread_id": str(uuid.uuid4())},
              "recursion_limit": 200}

    ambito = f"equipo {equipo}" if equipo else "compañía en general"
    print(LINEA)
    print(f"  ENTREVISTA DE CLIMA LABORAL — conversación anónima · ámbito: {ambito}")
    print(f"  Registro seudónimo: {empleado_id}  (tu nombre no se guarda)")
    print("  Escribe 'salir' para terminar antes de tiempo.")
    print(LINEA)

    resultado = orquestador.invoke(
        {"modo": "entrevista", "empleado_id": empleado_id, "equipo": equipo}, config)

    # Bucle human-in-the-loop: cada interrupt() del Entrevistador llega aquí.
    while "__interrupt__" in resultado:
        datos = resultado["__interrupt__"][0].value
        print(f"\n[{datos['numero']}/{datos['total']}] Clima: {datos['pregunta']}")
        try:
            respuesta = input("Tú: ").strip()
        except (KeyboardInterrupt, EOFError):
            respuesta = "salir"
        resultado = orquestador.invoke(Command(resume=respuesta or "salir"), config)

    salida = resultado.get("resultado", {})
    print(f"\nClima: {salida.get('mensaje_cierre', 'Entrevista finalizada.')}")
    print(LINEA)
    print(f"  Registro guardado en: {salida.get('ruta_archivo')}")
    print(f"  Preguntas respondidas: {salida.get('preguntas_respondidas')}")
    print(LINEA)


def ejecutar_analisis(directorio: str, equipo=None) -> None:
    orquestador = construir_orquestador()
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}

    ambito = f"equipo {equipo}" if equipo else "toda la compañía"
    print(LINEA)
    print(f"  AGENTE ANALISTA — '{directorio}/' · ámbito: {ambito}")
    print(LINEA)

    resultado = orquestador.invoke(
        {"modo": "analisis", "directorio": directorio, "equipo": equipo}, config)
    salida = resultado.get("resultado", {})

    metricas = salida.get("metricas")
    if metricas:
        print(f"  Entrevistas analizadas : {metricas['n_entrevistas']}")
        print(f"  Índice general de clima: {metricas['indice_general']} / 5.0")
        print(f"  Dimensión más fuerte   : {metricas['dimension_mas_fuerte']}")
        print(f"  Dimensión más débil    : {metricas['dimension_mas_debil']}")
        riesgo = metricas["dimensiones_en_riesgo"]
        print(f"  Dimensiones en riesgo  : {', '.join(riesgo) if riesgo else 'ninguna'}")
    print(LINEA)
    print(f"  {salida.get('mensaje')}")
    print(LINEA)


def principal() -> None:
    parser = argparse.ArgumentParser(
        description="Sistema multiagente de medición de clima laboral")
    sub = parser.add_subparsers(dest="comando", required=True)

    p_entrevistar = sub.add_parser(
        "entrevistar", help="Inicia una entrevista conversacional (Agente Entrevistador)")
    p_entrevistar.add_argument("--equipo", default=None,
                               help="Nombre del equipo (omitir = medición general)")
    p_analizar = sub.add_parser(
        "analizar", help="Consolida entrevistas y genera informe (Agente Analista)")
    p_analizar.add_argument("--dir", default="entrevistas",
                            help="Directorio con los JSON de entrevistas")
    p_analizar.add_argument("--equipo", default=None,
                            help="Analizar solo un equipo (omitir = toda la compañía)")

    args = parser.parse_args()
    try:
        if args.comando == "entrevistar":
            ejecutar_entrevista(args.equipo)
        else:
            ejecutar_analisis(args.dir, args.equipo)
    except Exception as e:
        print(f"\n[Error] {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    principal()
