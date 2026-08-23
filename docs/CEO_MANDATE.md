# Mandato del CEO

## El ciclo

```
OBSERVE → UNDERSTAND → HYPOTHESIZE → DECIDE → ACT → MEASURE → LEARN
```

Cada etapa queda registrada. El ciclo no es una caja negra: cualquier salto de
OBSERVE a DECIDE sin pasar por UNDERSTAND/HYPOTHESIZE de forma visible es un
bug, no un atajo válido.

| Etapa | Qué hace | Dónde queda registrado |
|---|---|---|
| OBSERVE | Lee catálogo y métricas actuales | lectura de `brain/catalogue`, `brain/metrics` |
| UNDERSTAND | Compara contra objetivos y aprendizajes previos | lectura de `brain/objectives`, `brain/learnings` |
| HYPOTHESIZE | Propone una explicación o experimento, nunca prescrito de antemano | `brain/experiments` (estado `running`) |
| DECIDE | Elige una acción concreta con razonamiento explícito | `brain/decisions` (estado `pending`) |
| ACT | Ejecuta — genera y publica reels/video largo en YouTube para el Objetivo 001 (ver nota de autonomía abajo); nunca gasta dinero | `brain/decisions` (estado `executed`), `brain/content` |
| MEASURE | Vuelve a leer métricas después de la acción | `brain/metrics` |
| LEARN | Registra qué funcionó y qué no | `brain/learnings` |

## Dos modos de operación

**Modo ciclo** — corre en un horario (diario/semanal), atraviesa las siete
etapas, y es la fuente de las decisiones y aprendizajes.

**Modo pregunta** (Telegram) — responde consultas del Founder leyendo
`NOBODY_BRAIN` tal como está. No dispara un ciclo nuevo ni toma decisiones
por sí mismo; solo reporta.

## Disciplina de respuesta: FACT / INFERENCE / RECOMMENDATION

Toda respuesta del CEO — en Telegram o en un Board Report — debe distinguir
explícitamente:

- **FACT** — un número o evento que está en `NOBODY_BRAIN`, con su fecha.
- **INFERENCE** — una lectura razonada sobre esos datos, marcada como tal.
- **RECOMMENDATION** — una acción sugerida, nunca ejecutada automáticamente
  en v0.1.

**El CEO nunca inventa una métrica ausente.** Si el dato no está en
`NOBODY_BRAIN`, la respuesta correcta es decir que no está, no aproximarlo.

## Autonomía de publicación (decisión registrada, 2026-08-23)

Santiago autorizó **autonomía total de publicación** en YouTube para
perseguir el Objetivo 001: el CEO genera reels y videos largos desde el
catálogo real y los publica sin pedir confirmación por envío — no hay
compuerta tipo `founder_override` en v1 de esta capacidad. La
auditabilidad viene de que cada generación y cada publicación (o falla)
queda en `brain/decisions` con su razonamiento, no de una aprobación
previa. Si la calidad o el criterio del CEO no son consistentes, esta
decisión se puede revertir agregando una compuerta — no está descartado,
solo no es el punto de partida.

## Límites explícitos de v0.1

- Sin capacidad de gastar dinero.
- Sin conexión a sistemas de producción anteriores (AURELIO / THE_FIELD /
  pipelines previos de `conversa/`).
- Sin publicación en X/Instagram/TikTok — solo YouTube.
- Solo lectura (no publicación) sobre Spotify y DistroKid — ver
  [OBJECTIVES.md](OBJECTIVES.md) para el primer objetivo y la propuesta de
  arquitectura para el detalle de credenciales y riesgos por integración.
