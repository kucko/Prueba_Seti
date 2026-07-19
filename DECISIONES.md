# Documento de decisiones — Sistema Multiagente de Clima Laboral

## ¿Qué problema resuelvo?

Las encuestas de clima laboral producen datos poco sinceros: el formato rígido y
el miedo a represalias llevan a respuestas neutras o complacientes, incluso bajo
anonimato. Las organizaciones terminan decidiendo sobre información distorsionada.
Propongo medir el clima mediante una **conversación anónima con un agente**, que
cubre siempre el mismo guion (16 preguntas, 8 dimensiones) pero en lenguaje
natural, y un **segundo agente** que consolida todas las entrevistas en métricas
comparables y un informe general accionable.

## ¿Por qué este diseño?

- **Dos agentes con roles genuinamente distintos.** El Entrevistador optimiza
  empatía y cobertura del guion en tiempo real; el Analista optimiza rigor
  agregado sobre el corpus completo. Separarlos permite escalar (N entrevistas
  en paralelo, un solo análisis) y auditar cada rol por separado.
- **LangGraph** por su orquestación explícita: el flujo es un grafo declarado
  (nodos, aristas condicionales) que coincide 1:1 con el diagrama de
  arquitectura. `interrupt()` + checkpointer resuelven el *human-in-the-loop*
  de forma nativa: la conversación puede pausarse y reanudarse sin perder estado.
- **Orquestador como grafo padre** que valida y enruta hacia cada agente
  (subgrafos). La sincronización entre agentes es **asíncrona vía artefactos**
  (JSON seudonimizados): desacopla los agentes en el tiempo, que es exactamente
  como opera el caso real (se entrevista durante días, se analiza una vez).
- **Métricas con código determinista, LLM solo para lo cualitativo.** Los
  promedios, alertas y distribución deben ser reproducibles y auditables; el
  juicio interpretativo (temas, recomendaciones) es donde el LLM aporta valor.
- **Privacidad por diseño.** Seudónimo aleatorio por entrevista (`EMP-XXXX`);
  la identidad nunca se almacena; el informe solo agrega.
- **Observabilidad propia y auditable.** Telemetría JSONL local por cada
  llamada al LLM (agente, nodo, latencia, error) y por hitos de participación;
  el dashboard la expone (incluida la tasa de abandono). LangSmith queda como
  opción por variables de entorno.
- **Parametrización operativa sin tocar código.** Guion de preguntas, prompts
  del Entrevistador y parámetros del Analista viven en una configuración
  editable desde la propia interfaz (JSON con valores de fábrica en código);
  los agentes la leen en cada llamada, así el área de talento humano adapta el
  instrumento sin desplegar.
- **Resiliencia.** Repregunta ante respuestas evasivas (máx. 1), valores
  neutrales ante fallos del LLM, archivos corruptos que no detienen el análisis
  y un **modo offline** (LLM simulado) que permite probar todo el flujo sin API.

## ¿Qué sacrifiqué? (trade-offs)

- **Interfaz mínima (Streamlit) sin autenticación ni multi-sesión robusta:**
  suficiente para la demo; producción exigiría identidad anónima verificable y
  despliegue dedicado. El CLI se mantiene como plan B: los mismos grafos corren
  en ambos front-ends, prueba de que la lógica está desacoplada.
- **Archivos JSON en lugar de base de datos:** suficiente para el alcance y hace
  transparente el "bus" entre agentes; en producción sería una BD con cifrado.
- **Una sola repregunta por pregunta:** evita interrogatorios incómodos a costa
  de perder algo de profundidad.
- **Interpretación en línea (por turno):** da trazabilidad pregunta a pregunta,
  pero el costo/latencia crece con cada turno; en producción se evaluaría
  interpretar por lotes.
- **Anonimato práctico, no absoluto:** la medición por equipos incorpora un
  umbral mínimo de entrevistas para no reportar segmentos reidentificables;
  aun así, el estilo de redacción podría delatar a alguien en grupos muy
  pequeños — la paráfrasis automática de citas queda como evolución declarada.
