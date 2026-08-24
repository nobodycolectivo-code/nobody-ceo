"""Board Report semanal — a diferencia de agents.ceo.ask (modo pregunta,
breve, formato Telegram), esto genera un informe estructurado para la
Junta: royalties, HEROES, rising assets, oportunidades de
plataforma/país, cambios relevantes y recomendaciones del CEO.

Misma disciplina FACT/INFERENCE/RECOMMENDATION y el mismo NOBODY_BRAIN
que agents.ceo.ask — comparten CORE_RULES/ROYALTIES_GUIDANCE para que
los dos canales no diverjan con el tiempo. No dispara ningún ciclo ni
decide nada por sí solo; solo lee y reporta, igual que el modo pregunta.
"""

from __future__ import annotations

import json
import os

import anthropic

from agents.capabilities.board import board_context
from agents.ceo.ask import CORE_RULES, MODEL, ROYALTIES_GUIDANCE

REPORT_SYSTEM_PROMPT = f"""Eres el CEO de NØBØĐ¥ RECORDS, escribiendo el Board Report semanal para
la Junta (Santiago). A diferencia de una respuesta de Telegram, esto es
un informe — puede tener varias secciones con encabezados cortos.

{CORE_RULES}
5. Estructura obligatoria, en este orden — si una sección no tiene datos
   suficientes en el contexto, dilo explícitamente en esa sección en vez
   de omitirla o rellenarla:
   1. Royalties — revenue total y del mes más reciente, comparado con el mes anterior.
   2. HEROES — los tracks HERO actuales y por qué (hero_score, reason_codes).
   3. Rising assets — qué está creciendo (RISING), con su confidence.
   4. Oportunidades de plataforma/país — de dónde viene el dinero y dónde hay
      concentración o mercados con potencial sin explotar.
   5. Cambios relevantes — decisiones y aprendizajes recientes, y catálogo
      sin vincular (unmatched_catalogue) si es relevante.
   6. Recomendaciones del CEO — 2-3 acciones concretas, marcando cuáles son
      EXPERIMENT (hipótesis a validar) vs RECOMMENDATION con más respaldo.

{ROYALTIES_GUIDANCE}

Contexto actual de NOBODY_BRAIN (JSON):
{{context}}
"""


def generate_weekly_report() -> str:
    context = board_context()
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    response = client.messages.create(
        model=MODEL,
        max_tokens=3200,
        system=REPORT_SYSTEM_PROMPT.format(
            context=json.dumps(context, ensure_ascii=False, indent=2)
        ),
        messages=[{"role": "user", "content": "Genera el Board Report semanal."}],
    )
    return "".join(block.text for block in response.content if block.type == "text")


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    print(generate_weekly_report())
