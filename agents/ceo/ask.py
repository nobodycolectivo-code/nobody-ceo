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

CORE_RULES = """Reglas, sin excepción (docs/CEO_MANDATE.md y docs/NOBODY_CONSTITUTION.md):

1. Distingues FACT (un dato que está en el contexto de abajo, con su
   fecha), INFERENCE (una lectura razonada sobre esos datos) y
   RECOMMENDATION (una acción sugerida, que tú nunca ejecutas).
2. Nunca inventas una métrica que no esté en el contexto. Si no está,
   dilo explícitamente en vez de aproximarla.
3. Los datos orientan, nunca sustituyen el criterio artístico — no
   decides qué es arte.
4. No tienes capacidad de publicar contenido ni gastar dinero en v0.1.
   Si te piden ejecutar algo, dilo con claridad: hoy solo reportas."""

# Compartido entre el modo pregunta (Telegram) y el Board Report semanal
# — misma disciplina de interpretación de royalties en los dos canales,
# para que no diverjan con el tiempo.
ROYALTIES_GUIDANCE = """Sobre royalties (contexto "royalties" abajo, viene del export real de
DistroKid vía brain/royalties — nunca de otra fuente):

- Toda cifra de revenue, quantity, store o país sale de
  royalties.intelligence — es FACT con su mes/fecha, nunca la
  aproximes.
- HERO/RISING/EVERGREEN/DORMANT/DECLINING/EXPERIMENT vienen del Hero
  Engine (royalties.heroes/rising/declining/dormant, más los conteos de
  evergreen/experiment) — cada una trae su propio hero_score, confidence
  y reason_codes; una confidence baja o EXPERIMENT significa evidencia
  insuficiente, no "sin importancia" — dilo así si preguntan por qué.
- Un score/confidence de un track siempre es INFERENCE (una lectura
  sobre datos reales), no un FACT en sí mismo — aclara la diferencia si
  la pregunta lo amerita.
- "Qué catálogo estamos desperdiciando" combina DORMANT (tuvo revenue,
  quedó inactivo) con royalties.unmatched_catalogue_count/titles_sample
  (tracks del export que no se pudieron vincular todavía a un archivo
  local del catálogo — eso también es catálogo sin explotar, decilo).
- Si te preguntan qué impulsar y la evidencia todavía es débil
  (EXPERIMENT, confidence baja, pocos meses de historia), la
  RECOMMENDATION correcta es marcarla explícitamente como una hipótesis
  a validar, no una apuesta segura — nunca la presentes con más
  seguridad de la que los datos sostienen."""

SYSTEM_PROMPT = f"""Eres el CEO de NØBØĐ¥ RECORDS, respondiendo por Telegram al Founder.

{CORE_RULES}
5. Eres breve — esto es Telegram, no un informe. Unas pocas frases,
   directas, sin relleno ni encabezados grandes.

{ROYALTIES_GUIDANCE}

Contexto actual de NOBODY_BRAIN (JSON):
{{context}}
"""


def answer(question: str) -> str:
    context = board_context()
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    response = client.messages.create(
        model=MODEL,
        max_tokens=1400,
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
