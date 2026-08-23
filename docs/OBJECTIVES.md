# Objetivos activos

## OBJETIVO 001 — Unlock YouTube Watch Page Ads

**Baseline** (17 ago 2026):

| Métrica | Actual | Umbral | Gap |
|---|---:|---:|---:|
| Subscribers | 763 | 1,000 | +237 |
| Watch hours calificadas (público, 12 meses) | 1,860 | 4,000 | +2,140 |

**Estado:** activo, sin fecha límite fija todavía.

**Importante:** el CEO no recibe una estrategia predeterminada para cerrar
esta brecha. Debe estudiar el catálogo y las métricas reales (una vez
conectada la integración de solo-lectura de YouTube — ver la propuesta de
arquitectura) y proponer sus propias hipótesis dentro de
[NOBODY_CONSTITUTION.md](NOBODY_CONSTITUTION.md). Cualquier hipótesis que
implique publicar contenido nuevo queda registrada como `experiment`, no
como acción — v0.1 no tiene capacidad de publicación.

## Cómo se agregan objetivos nuevos

Un objetivo nuevo requiere: título, baseline verificable, target medible,
y — si aplica — fecha límite. Se registra en `brain/objectives` con un
snapshot JSON del baseline en el momento de creación, para que el progreso
futuro sea comparable contra un punto fijo y no contra un baseline que se
mueve.
