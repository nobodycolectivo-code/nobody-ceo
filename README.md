# NØBØĐ¥ CEO

El sistema operativo agéntico de NØBØĐ¥ RECORDS. Un CEO, capacidades
especializadas, sin teatro multiagente.

- **Propósito y visión:** [docs/NOBODY_CONSTITUTION.md](docs/NOBODY_CONSTITUTION.md)
- **Cómo se gobierna:** [docs/GOVERNANCE.md](docs/GOVERNANCE.md)
- **Qué puede hacer el CEO y cómo:** [docs/CEO_MANDATE.md](docs/CEO_MANDATE.md)
- **Qué está persiguiendo ahora:** [docs/OBJECTIVES.md](docs/OBJECTIVES.md)

## Estado: v0.1, foundation

Este repositorio está en construcción. La primera meta no es cantidad de
código — es que el Founder pueda escribir en Telegram *"CEO, ¿cómo vamos?"*
y recibir una respuesta breve, fundamentada en datos reales de catálogo,
métricas, decisiones y aprendizajes registrados.

## Estructura

```
docs/           Constitución, mandato, gobierno, objetivos
brain/          Memoria operacional (catálogo, métricas, decisiones,
                 experimentos, aprendizajes, regalías) — schema.sql
                 propone el modelo, data/ (gitignored) guarda la base real
agents/ceo/     El ciclo OBSERVE→...→LEARN y el modo de pregunta por Telegram
agents/capabilities/  Funciones que el CEO puede invocar sobre brain/
integrations/   Clientes de solo lectura: telegram, youtube, spotify
                 (distrokid no tiene API oficial — ver su README)
data/           Runtime, gitignored — nunca se commitea
tests/
```

## Principios de v0.1

- Solo lectura contra sistemas externos. Nada publica, nada gasta.
- Credenciales nuevas y dedicadas — nunca reutiliza claves de otros
  proyectos de `conversa/`.
- No toca el catálogo original (`Desktop\NOBODY`) más que para leerlo.
- No se conecta a AURELIO, THE_FIELD ni ningún pipeline anterior.

## Desarrollo

```bash
uv venv
uv pip install -e ".[dev]"
cp .env.example .env   # llenar con credenciales nuevas
pytest
```
