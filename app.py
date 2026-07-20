"""
Interfaz web del Sistema Multiagente de Clima Laboral (Streamlit).

Capa de presentación sobre los MISMOS grafos LangGraph que usa el CLI:
la lógica de los agentes no cambia; solo cambia el canal de interacción.

Ejecutar:  streamlit run app.py
"""

import os
import uuid
from datetime import datetime

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from langgraph.types import Command  # noqa: E402

from src.agentes.analista import (calcular_metricas,  # noqa: E402
                                  construir_grafo_analista)
from src.agentes.entrevistador import DIRECTORIO_ENTREVISTAS  # noqa: E402
from src.config import configuracion  # noqa: E402
from src.config.preguntas import total_preguntas  # noqa: E402
from src.orquestador import construir_orquestador  # noqa: E402
from src.utils.telemetria import cargar_eventos  # noqa: E402

st.set_page_config(page_title="Clima Laboral · Sistema Multiagente",
                   page_icon="💬", layout="wide")


# --------------------------------------------------------------------------
# Utilidades
# --------------------------------------------------------------------------

def _nuevo_empleado_id() -> str:
    import secrets
    return f"EMP-{secrets.token_hex(2).upper()}"


@st.cache_resource
def _orquestador():
    return construir_orquestador()


def _cargar_entrevistas(directorios: list[str]) -> list[dict]:
    import glob
    import json
    registros = []
    for d in directorios:
        for ruta in sorted(glob.glob(os.path.join(d, "entrevista_*.json"))):
            try:
                with open(ruta, encoding="utf-8") as f:
                    registros.append(json.load(f))
            except (json.JSONDecodeError, OSError):
                continue
    return registros


# --------------------------------------------------------------------------
# Pestaña 1 · Entrevista conversacional
# --------------------------------------------------------------------------

def vista_entrevista():
    st.subheader("Entrevista de clima laboral")
    st.caption("Conversación **anónima**: se te asigna un seudónimo aleatorio y "
               "tu nombre nunca se registra. Escribe *salir* para terminar antes.")

    ss = st.session_state
    if "mensajes" not in ss:
        ss.mensajes, ss.en_curso, ss.terminada = [], False, False

    if not ss.en_curso and not ss.terminada:
        ambito = st.radio("Ámbito de esta entrevista",
                          ["🏢 Compañía en general", "👥 Un equipo específico"],
                          horizontal=True)
        equipo = None
        if ambito.endswith("específico"):
            equipos_cfg = configuracion.cargar()["organizacion"]["equipos"]
            opciones = equipos_cfg + ["➕ Otro…"]
            eleccion = st.selectbox("Equipo", opciones) if equipos_cfg else "➕ Otro…"
            if eleccion == "➕ Otro…":
                equipo = st.text_input("Nombre del equipo").strip() or None
            else:
                equipo = eleccion
        if st.button("Iniciar entrevista", type="primary",
                     disabled=ambito.endswith("específico") and not equipo):
            ss.empleado_id = _nuevo_empleado_id()
            ss.equipo = equipo
            ss.config = {"configurable": {"thread_id": str(uuid.uuid4())},
                         "recursion_limit": 200}
            resultado = _orquestador().invoke(
                {"modo": "entrevista", "empleado_id": ss.empleado_id,
                 "equipo": equipo}, ss.config)
            datos = resultado["__interrupt__"][0].value
            ss.mensajes.append(("assistant",
                                f"**[{datos['numero']}/{datos['total']}]** {datos['pregunta']}"))
            ss.en_curso = True
            st.rerun()
        return

    etiqueta = (f" · Equipo: **{ss.equipo}**" if ss.get("equipo")
                else " · Ámbito: **compañía en general**")
    st.info(f"Seudónimo asignado: **{ss.empleado_id}**{etiqueta}")

    if ss.terminada:
        with st.expander(f"Ver conversación completa ({len(ss.mensajes)} mensajes)"):
            for rol, texto in ss.mensajes:
                with st.chat_message(rol):
                    st.markdown(texto)
        st.success(ss.get("cierre", "Entrevista finalizada. ¡Gracias!"))
        if st.button("Nueva entrevista"):
            for k in ("mensajes", "en_curso", "terminada", "empleado_id",
                      "config", "cierre", "equipo"):
                ss.pop(k, None)
            st.rerun()
        return

    # Bienvenida fija de la interfaz: no consume LLM y evita que la persona
    # responda al saludo en lugar de a la pregunta.
    st.success("👋 **Bienvenido/a a este espacio.** No hay respuestas correctas ni "
               "incorrectas: cuéntalo con tus propias palabras. Cuando quieras "
               "terminar, escribe *salir*.")

    # Modo enfocado: la pregunta actual siempre visible; lo ya respondido, plegado.
    anteriores = ss.mensajes[:-1]
    if anteriores:
        with st.expander(f"Ver conversación anterior ({len(anteriores)} mensajes)"):
            for rol, texto in anteriores:
                with st.chat_message(rol):
                    st.markdown(texto)
    if ss.mensajes:
        rol_actual, texto_actual = ss.mensajes[-1]
        with st.chat_message(rol_actual):
            st.markdown(texto_actual)

    respuesta = st.chat_input("Escribe tu respuesta…")
    if respuesta:
        ss.mensajes.append(("user", respuesta))
        with st.spinner("Clima está escuchando…"):
            resultado = _orquestador().invoke(Command(resume=respuesta), ss.config)
        if "__interrupt__" in resultado:
            datos = resultado["__interrupt__"][0].value
            ss.mensajes.append(("assistant",
                                f"**[{datos['numero']}/{datos['total']}]** {datos['pregunta']}"))
        else:
            salida = resultado.get("resultado", {})
            ss.cierre = (f"{salida.get('mensaje_cierre', '')}\n\n"
                         f"Registro seudonimizado: `{salida.get('ruta_archivo')}` · "
                         f"{salida.get('preguntas_respondidas')}/{total_preguntas()} preguntas")
            ss.terminada, ss.en_curso = True, False
        st.rerun()


# --------------------------------------------------------------------------
# Pestaña 2 · Dashboard de clima y observabilidad
# --------------------------------------------------------------------------

def vista_dashboard():
    st.subheader("Dashboard de clima y observabilidad")
    incluir_ejemplo = st.toggle("Incluir datos de ejemplo (5 entrevistas sintéticas)",
                                value=True)
    dirs = [DIRECTORIO_ENTREVISTAS] + (["datos_ejemplo"] if incluir_ejemplo else [])
    todas = _cargar_entrevistas(dirs)

    equipos_datos = sorted({e.get("equipo") for e in todas if e.get("equipo")})
    ambito_sel = st.selectbox("Ámbito del análisis",
                              ["🏢 Toda la compañía"] +
                              [f"👥 {eq}" for eq in equipos_datos])
    equipo_sel = ambito_sel[2:].strip() if ambito_sel.startswith("👥") else None
    entrevistas = ([e for e in todas if e.get("equipo") == equipo_sel]
                   if equipo_sel else todas)

    if not entrevistas:
        st.warning("Aún no hay entrevistas registradas. Realiza una en la pestaña "
                   "*Entrevista* o activa los datos de ejemplo.")
        return

    m = calcular_metricas({"entrevistas": entrevistas,
                           "equipo": equipo_sel})["metricas"]
    if m.get("bajo_umbral_anonimato"):
        st.warning(f"⚠️ Este equipo tiene menos de {m['min_entrevistas_equipo']} "
                   "entrevistas: los resultados podrían permitir reidentificar "
                   "respuestas. Trátalos con confidencialidad reforzada.")

    # ---- Participación -------------------------------------------------
    st.markdown("#### Participación")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Entrevistas respondidas", m["n_entrevistas"])
    c2.metric("Completadas", m["n_completadas"],
              delta=f"{m['n_entrevistas'] - m['n_completadas']} parciales",
              delta_color="off")
    c3.metric("Respuestas interpretadas", m["n_respuestas"])
    fechas = pd.to_datetime([e["fecha"] for e in entrevistas]).date
    c4.metric("Última entrevista", max(fechas).strftime("%d %b"))

    serie = (pd.Series(1, index=pd.to_datetime([e["fecha"] for e in entrevistas]))
             .resample("D").sum())
    st.caption("Entrevistas por día")
    st.bar_chart(serie, height=160, color="#028090")

    # ---- Clima laboral -------------------------------------------------
    st.markdown("#### Resultados de clima")
    c1, c2, c3 = st.columns(3)
    c1.metric("Índice general", f"{m['indice_general']} / 5.0")
    c2.metric("Intención de permanencia", f"{m['indice_permanencia']} / 5.0")
    c3.metric("Dimensiones en riesgo", len(m["dimensiones_en_riesgo"]),
              help=", ".join(m["dimensiones_en_riesgo"]) or "Ninguna")

    izq, der = st.columns([3, 2])
    with izq:
        df_dim = (pd.DataFrame(list(m["promedio_por_dimension"].items()),
                               columns=["Dimensión", "Promedio"])
                  .sort_values("Promedio"))
        st.caption("Promedio por dimensión (1–5)")
        st.bar_chart(df_dim.set_index("Dimensión"), horizontal=True,
                     height=320, color="#028090")
    with der:
        st.caption("Temas más mencionados")
        st.dataframe(pd.DataFrame(m["temas_recurrentes"],
                                  columns=["Tema", "Menciones"]).head(8),
                     hide_index=True, width="stretch")

    if not equipo_sel and len(m.get("por_equipo", {})) > 1:
        st.caption("Índice por equipo (equipos bajo el umbral de anonimato no se reportan)")
        filas_eq = []
        for nombre, d in m["por_equipo"].items():
            filas_eq.append({
                "Equipo": nombre,
                "Entrevistas": d["n_entrevistas"],
                "Índice (1–5)": (f"{d['indice']:.2f}"
                                 if d["reportable"] and d["indice"] is not None
                                 else "🔒 no reportado"),
            })
        st.dataframe(pd.DataFrame(filas_eq), hide_index=True, width="stretch")

    etiqueta_btn = (f"Generar informe del equipo {equipo_sel}" if equipo_sel
                    else "Generar informe general con el Agente Analista")
    if st.button(etiqueta_btn, type="primary"):
        with st.spinner("El Analista está trabajando…"):
            grafo = construir_grafo_analista().compile()
            # El grafo del Analista lee un solo directorio; para la demo
            # con datos de ejemplo se apunta directamente a esa carpeta.
            directorio = DIRECTORIO_ENTREVISTAS if _cargar_entrevistas(
                [DIRECTORIO_ENTREVISTAS]) else "datos_ejemplo"
            salida = grafo.invoke({"directorio": directorio,
                                   "equipo": equipo_sel})
        if salida.get("ruta_informe"):
            st.success(salida["mensaje"])
            with open(salida["ruta_informe"], encoding="utf-8") as f:
                contenido = f.read()
            st.download_button("Descargar informe (.md)", contenido,
                               file_name=os.path.basename(salida["ruta_informe"]))
            with st.expander("Ver informe"):
                st.markdown(contenido)
        else:
            st.error(salida.get("mensaje", "No fue posible generar el informe."))

    # ---- Observabilidad de los agentes ---------------------------------
    st.markdown("#### Observabilidad de los agentes")
    eventos = cargar_eventos()
    if not eventos:
        st.info("Sin eventos de telemetría todavía: se registran al usar los agentes.")
        return

    df = pd.DataFrame(eventos)
    llamadas = df[df["evento"] == "llamada_llm"]
    iniciadas = int((df["evento"] == "entrevista_iniciada").sum())
    finalizadas = df[df["evento"] == "entrevista_finalizada"]
    completadas = int(finalizadas.get("completada", pd.Series(dtype=bool)).sum())

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Llamadas al LLM", len(llamadas))
    lat = f"{llamadas['duracion_ms'].mean():.0f} ms" if len(llamadas) else "—"
    c2.metric("Latencia media LLM", lat)
    if len(llamadas):
        exitos = llamadas["exito"].fillna(False).astype(bool)
    else:
        exitos = pd.Series(dtype=bool)
    errores = int((~exitos).sum())
    c3.metric("Errores LLM", errores)
    tasa = f"{100 * completadas / iniciadas:.0f}%" if iniciadas else "—"
    c4.metric("Tasa de finalización", tasa,
              help="Entrevistas completadas / iniciadas (mide abandono)")

    if len(llamadas):
        st.caption("Desglose por agente")
        col_e, col_a = st.columns(2)
        for col, nombre_agente, titulo in (
                (col_e, "entrevistador", "🗣️ Agente Entrevistador"),
                (col_a, "analista", "📈 Agente Analista")):
            grupo = llamadas[llamadas["agente"] == nombre_agente]
            with col:
                st.markdown(f"**{titulo}**")
                m1, m2, m3 = st.columns(3)
                m1.metric("Llamadas", len(grupo))
                lat_g = (f"{grupo['duracion_ms'].mean():.0f} ms"
                         if len(grupo) else "—")
                m2.metric("Latencia media", lat_g)
                err_g = (int((~grupo["exito"].fillna(False).astype(bool)).sum())
                         if len(grupo) else 0)
                m3.metric("Errores", err_g)

        st.caption("Llamadas al LLM por agente y nodo (conteo y latencia media)")
        resumen = (llamadas.groupby(["agente", "nodo"])
                   .agg(llamadas=("evento", "count"),
                        latencia_media_ms=("duracion_ms", "mean"),
                        errores=("exito", lambda s: int((~s.fillna(False).astype(bool)).sum())))
                   .round(0).reset_index())
        st.dataframe(resumen, hide_index=True, width="stretch")




# --------------------------------------------------------------------------
# Pestaña 3 · Configuración del sistema
# --------------------------------------------------------------------------

def vista_configuracion():
    st.subheader("Configuración del sistema")
    st.caption("Los cambios guardados aplican de inmediato a las próximas "
               "entrevistas y análisis (los agentes leen la configuración en "
               "cada llamada). Se persisten en `config/configuracion.json`.")
    cfg = configuracion.cargar()

    # ---- Preguntas del guion ------------------------------------------
    with st.expander("📋 Preguntas del guion", expanded=True):
        st.caption("Edita el texto, cambia la dimensión, agrega filas con ➕ "
                   "o elimínalas seleccionándolas y presionando Supr. Los IDs "
                   "se reasignan en orden al guardar.")
        df = pd.DataFrame(cfg["preguntas"])[["dimension", "texto"]]
        editado = st.data_editor(
            df, num_rows="dynamic", width="stretch", key="editor_preguntas",
            column_config={
                "dimension": st.column_config.TextColumn("Dimensión", required=True),
                "texto": st.column_config.TextColumn("Pregunta base", required=True,
                                                     width="large"),
            })
        filas = [(str(r["dimension"]).strip(), str(r["texto"]).strip())
                 for _, r in editado.iterrows()
                 if str(r["dimension"]).strip() not in ("", "None", "nan")
                 and str(r["texto"]).strip() not in ("", "None", "nan")]
        opciones = list(range(1, len(filas) + 1))
        idx_defecto = min(int(cfg["analista"]["pregunta_permanencia_id"]),
                          len(filas)) - 1 if filas else 0
        permanencia = st.selectbox(
            "Pregunta usada como métrica de 'intención de permanencia' (rotación)",
            opciones, index=max(idx_defecto, 0),
            format_func=lambda i: f"{i}. {filas[i-1][1][:70]}") if filas else None
        if st.button("💾 Guardar preguntas", key="guardar_preguntas"):
            if len(filas) < 2:
                st.error("El guion necesita al menos 2 preguntas completas.")
            else:
                cfg["preguntas"] = [
                    {"id": i + 1, "dimension": d, "texto": t}
                    for i, (d, t) in enumerate(filas)]
                cfg["analista"]["pregunta_permanencia_id"] = int(permanencia)
                configuracion.guardar(cfg)
                st.success(f"Guion guardado: {len(filas)} preguntas en "
                           f"{len({d for d, _ in filas})} dimensiones.")
                st.rerun()

    # ---- Agente Entrevistador -----------------------------------------
    with st.expander("🗣️ Agente Entrevistador — prompt y comportamiento"):
        ce = cfg["entrevistador"]
        personalidad = st.text_area("Personalidad del agente",
                                    ce["personalidad"], height=80)
        reglas = st.text_area("Reglas de formulación (una por línea)",
                              ce["reglas"], height=170)
        c1, c2 = st.columns(2)
        with c1:
            ins_inicio = st.text_area("Instrucción de inicio",
                                      ce["instruccion_inicio"], height=110)
            ins_trans = st.text_area("Instrucción de transición",
                                     ce["instruccion_transicion"], height=110)
        with c2:
            ins_repreg = st.text_area("Instrucción de repregunta",
                                      ce["instruccion_repregunta"], height=110)
            max_rep = st.slider("Máx. repreguntas por pregunta", 0, 3,
                                int(ce["max_repreguntas"]),
                                help="0 = nunca repregunta; ante evasivas sigue adelante")
        if st.button("💾 Guardar Entrevistador", key="guardar_entrevistador"):
            cfg["entrevistador"].update({
                "personalidad": personalidad.strip(),
                "reglas": reglas.strip(),
                "instruccion_inicio": ins_inicio.strip(),
                "instruccion_transicion": ins_trans.strip(),
                "instruccion_repregunta": ins_repreg.strip(),
                "max_repreguntas": int(max_rep),
            })
            configuracion.guardar(cfg)
            st.success("Configuración del Entrevistador guardada.")
            st.rerun()

    # ---- Organización: equipos ----------------------------------------
    with st.expander("👥 Equipos de la organización"):
        st.caption("Uno por línea. Aparecen como opciones al iniciar una "
                   "entrevista por equipo (también se puede escribir uno nuevo allí).")
        texto_equipos = st.text_area(
            "Equipos", "\n".join(cfg["organizacion"]["equipos"]),
            height=120, label_visibility="collapsed")
        if st.button("💾 Guardar equipos", key="guardar_equipos"):
            equipos = [e.strip() for e in texto_equipos.splitlines() if e.strip()]
            cfg["organizacion"]["equipos"] = equipos
            configuracion.guardar(cfg)
            st.success(f"{len(equipos)} equipos guardados.")
            st.rerun()

    # ---- Agente Analista ----------------------------------------------
    with st.expander("📈 Agente Analista — parámetros de análisis"):
        ca = cfg["analista"]
        c1, c2, c3 = st.columns(3)
        umbral = c1.slider("Umbral de alerta por dimensión", 1.0, 5.0,
                           float(ca["umbral_alerta"]), 0.1,
                           help="Dimensiones con promedio menor se marcan en riesgo")
        max_notas = c2.number_input("Máx. observaciones enviadas al LLM",
                                    10, 500, int(ca["max_notas_llm"]),
                                    help="Límite de contexto del análisis cualitativo")
        max_palabras = c3.number_input("Máx. palabras del análisis cualitativo",
                                       100, 800, int(ca["max_palabras_analisis"]))
        min_eq = st.slider(
            "Mín. entrevistas para reportar un equipo (umbral de anonimato)",
            1, 10, int(ca["min_entrevistas_equipo"]),
            help="Equipos con menos entrevistas no se reportan individualmente, "
                 "para evitar reidentificar respuestas")
        instr_extra = st.text_area(
            "Instrucciones adicionales para el análisis cualitativo (opcional)",
            ca["instrucciones_adicionales"], height=90,
            placeholder="Ej.: enfatiza recomendaciones para líderes de equipo…")
        if st.button("💾 Guardar Analista", key="guardar_analista"):
            cfg["analista"].update({
                "umbral_alerta": float(umbral),
                "min_entrevistas_equipo": int(min_eq),
                "max_notas_llm": int(max_notas),
                "max_palabras_analisis": int(max_palabras),
                "instrucciones_adicionales": instr_extra.strip(),
            })
            configuracion.guardar(cfg)
            st.success("Configuración del Analista guardada.")
            st.rerun()

    # ---- Modelo LLM ----------------------------------------------------
    with st.expander("🤖 Modelo de lenguaje"):
        cm = cfg["modelo"]
        c1, c2 = st.columns(2)
        nombre = c1.text_input("Modelo", cm["nombre"],
                               help="Si MODELO_LLM está definido en .env, ese valor "
                                    "tiene prioridad sobre este campo.")
        temperatura = c2.slider("Temperatura", 0.0, 1.0,
                                float(cm["temperatura"]), 0.05,
                                help="Menor = más consistente; mayor = más creativo")
        if os.getenv("MODELO_LLM"):
            st.info(f"⚠️ Tu .env define MODELO_LLM={os.getenv('MODELO_LLM')} y "
                    "tiene prioridad. Borra esa línea del .env para controlar "
                    "el modelo desde aquí.")
        if st.button("💾 Guardar modelo", key="guardar_modelo"):
            cfg["modelo"].update({"nombre": nombre.strip(),
                                  "temperatura": float(temperatura)})
            configuracion.guardar(cfg)
            st.success("Configuración del modelo guardada.")
            st.rerun()

    st.divider()
    confirmar = st.checkbox("Entiendo que se perderán todos los cambios guardados")
    if st.button("♻️ Restaurar valores de fábrica", disabled=not confirmar):
        configuracion.restaurar()
        st.success("Configuración restaurada a los valores por defecto.")
        st.rerun()


# --------------------------------------------------------------------------

st.title("💬 Sistema Multiagente de Clima Laboral")
tab1, tab2, tab3 = st.tabs(["🗣️ Entrevista", "📊 Dashboard", "⚙️ Configuración"])
with tab1:
    vista_entrevista()
with tab2:
    vista_dashboard()
with tab3:
    vista_configuracion()
