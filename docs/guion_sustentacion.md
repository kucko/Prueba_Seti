# Guion de sustentación (30 min)

## Bloque 1 · Presentación (10 min)

1. **El problema (2 min).** Las encuestas de clima fallan en lo esencial: la
   sinceridad. Miedo a represalias + formato rígido = datos distorsionados.
   Anécdota corta y pregunta retórica: "¿de qué sirve medir si nadie dice la verdad?"
2. **La solución (2 min).** Conversación anónima con un agente que siempre cubre
   el mismo guion (16 preguntas / 8 dimensiones) pero en lenguaje natural +
   un agente analista que consolida métricas comparables e informe accionable.
   Valor: mejores datos → mejores decisiones de talento → retención.
3. **Arquitectura (4 min).** Mostrar el diagrama: orquestador (grafo padre),
   Entrevistador con `interrupt()` human-in-the-loop, Analista, y el bus de
   artefactos JSON seudonimizados. Subrayar: el grafo ES el diagrama.
4. **Decisiones clave (2 min).** Métricas deterministas vs. LLM cualitativo;
   privacidad por diseño (seudónimos); resiliencia (repregunta, modo offline).

## Bloque 2 · Demo en vivo (10 min)

Plan A (con API):
1. `python main.py entrevistar` — responder 4–5 preguntas mostrando: la
   reformulación conversacional, una respuesta evasiva ("no sé") para que
   repregunte, y `salir` para el cierre parcial. (5 min)
2. Abrir el JSON generado: mostrar seudónimo, puntajes, temas y resumen. (1 min)
3. `python main.py analizar --dir datos_ejemplo` — informe con 5 entrevistas
   sintéticas + la recién creada si se copió. Abrir el Markdown: métricas,
   barras por dimensión, alertas, análisis cualitativo. (4 min)

Plan B (contingencia sin internet/API): mismo flujo con `USAR_LLM_FALSO=1` —
decirlo con transparencia: "modo offline de pruebas, parte del diseño de
resiliencia".

Preparación previa: entorno activado, `.env` cargado, terminal con fuente
grande, `datos_ejemplo` intacto, un informe pre-generado abierto en pestaña
por si algo falla.

## Bloque 3 · Preguntas probables (10 min)

- **¿Por qué dos agentes y no uno solo?** Roles con objetivos distintos
  (empatía en tiempo real vs. rigor agregado), escalan y se auditan por
  separado; N entrevistas → 1 análisis.
- **¿Por qué LangGraph?** Orquestación explícita como grafo declarado,
  `interrupt` + checkpointer nativos para human-in-the-loop, comunidad y
  documentación. ADK/AgentCore exigen nube; AutoGen es más conversación libre
  entre agentes, aquí necesito control de flujo estricto (guion fijo).
- **¿Cómo garantizas que cubre las 16 preguntas si es "libre"?** El guion vive
  en el estado del grafo (código), no en el prompt: el LLM solo reformula la
  pregunta actual. El control de flujo es determinista.
- **¿Y si el LLM alucina o falla?** Interpretación con fallback neutral,
  métricas 100% en código, informe se genera aun sin análisis cualitativo,
  modo offline completo.
- **¿El anonimato es real?** Seudónimo aleatorio, identidad nunca almacenada,
  informe agregado. Limitación honesta: en equipos muy pequeños el estilo puede
  reidentificar; evolución declarada: k-anonimato y paráfrasis de citas.
- **¿Escala a 1.000 empleados?** Entrevistas paralelas por `thread_id`;
  análisis O(n); evolución: BD cifrada, cola de trabajos, canal Teams/Slack.
- **¿Sesgos del interpretador?** Rubrica explícita en el prompt (1–5 anclado),
  temperatura baja, y las métricas admiten auditoría porque cada puntaje
  conserva la respuesta textual que lo originó.
- **¿Cómo usaste IA para construirlo?** Remitir a `BITACORA_IA.md`: IA como par
  de ingeniería (andamiaje, prompts, docs), decisiones y validación propias.

## Cierre (30 s)

"El sistema no reemplaza al área de talento humano: le entrega, por primera
vez, datos en los que puede confiar."
