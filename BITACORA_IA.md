# Bitácora de uso de IA en el proceso de construcción

> Criterio del reto: "Uso deliberado de herramientas de IA en el flujo de
> construcción, explicado en la sustentación." Esta bitácora registra qué se
> delegó a la IA, qué decidió el autor y cómo se validó cada resultado.

## Principio de trabajo

La IA se usó como **par de ingeniería**: acelera diseño, código base y
documentación; las **decisiones de producto y arquitectura, la validación y los
ajustes finales son del autor**. Todo artefacto generado se revisó y probó antes
de incorporarse.

## Registro

| Fecha | Herramienta | Qué se delegó a la IA | Qué decidió/validó el autor |
|---|---|---|---|
| 2026-07-17 | Claude (Anthropic) | Propuesta de plan por etapas para abordar el reto; ideas candidatas de problemática | Definió la problemática propia (clima laboral conversacional) y el diseño de dos agentes; descartó las ideas propuestas |
| 2026-07-17 | Claude | Redacción del guion de 16 preguntas en 8 dimensiones | Revisó y aprobó dimensiones y preguntas |
| 2026-07-17 | Claude | Comparación de frameworks permitidos y guía de instalación en Windows 11 | Eligió LangGraph |
| 2026-07-18 | Claude | Andamiaje completo del proyecto: grafos de los dos agentes, orquestador, CLI, prompts, datos sintéticos, pruebas de humo y documentación inicial | Definió los requisitos del comportamiento (guion fijo, repregunta, registro por empleado, informe general); pendiente: revisión línea a línea, ejecución local y ajustes |
| 2026-07-18 | Claude | Identificación del trade-off de anonimato (seudonimización vs. archivo con nombre) | Adoptó la seudonimización `EMP-XXXX` como decisión de diseño |
| 2026-07-18 | Claude | Borrador de la presentación de sustentación (10 slides con notas de orador) y workflow de CI en GitHub Actions | Pendiente: revisar slides, personalizar y ensayar |
| 2026-07-18 | Claude | Interfaz web Streamlit (chat + dashboard), telemetría JSONL de observabilidad y pruebas AppTest | Decidió agregar interfaz gráfica y dashboard de observabilidad/participación; pendiente probar localmente |
| _(continuar)_ | | | |

## Uso de IA dentro del producto

Además del proceso, el sistema **usa IA en runtime** con límites deliberados:
el LLM formula preguntas, interpreta respuestas y redacta el análisis
cualitativo; las métricas se calculan con código determinista para que sean
auditables (ver `DECISIONES.md`).
