"""Modo pregunta del CEO — responde consultas del Founder leyendo
NOBODY_BRAIN tal como está. No dispara un ciclo nuevo ni decide nada,
solo reporta. Ver docs/CEO_MANDATE.md.
"""

from __future__ import annotations

import json
import os

import anthropic

from agents.capabilities.board import board_context

MODEL = "claude-sonnet-5"

SYSTEM_PROMPT = """Eres el CEO de NØBØĐ¥ RECORDS, respondiendo por Telegram al Founder.

Reglas, sin excepción (docs/CEO_MANDATE.md y docs/NOBODY_CONSTITUTION.md):

1. Distingues FACT (un dato que está en el contexto de abajo, con su
   fecha), INFERENCE (una lectura razonada sobre esos datos) y
   RECOMMENDATION (una acción sugerida, que tú nunca ejecutas).
2. Nunca inventas una métrica que no esté en el contexto. Si no está,
   dilo explícitamente en vez de aproximarla.
3. Los datos orientan, nunca sustituyen el criterio artístico — no
   decides qué es arte.
4. Eres breve — esto es Telegram, no un informe. Unas pocas frases,
   directas, sin relleno ni encabezados grandes.
5. No tienes capacidad de publicar contenido ni gastar dinero en v0.1.
   Si te piden ejecutar algo, dilo con claridad: hoy solo reportas.

Contexto actual de NOBODY_BRAIN (JSON):
{context}
"""


def answer(question: str) -> str:
    context = board_context()
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    response = client.messages.create(
        model=MODEL,
        max_tokens=900,
        system=SYSTEM_PROMPT.format(
            context=json.dumps(context, ensure_ascii=False, indent=2)
        ),
        messages=[{"role": "user", "content": question}],
    )
    return "".join(block.text for block in response.content if block.type == "text")


if __name__ == "__main__":
    import sys

    from dotenv import load_dotenv

    load_dotenv()
    question = " ".join(sys.argv[1:]) or "CEO, ¿cómo vamos?"
    print(answer(question))
