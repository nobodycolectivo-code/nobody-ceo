# Gobierno

## Founder / Board

Santiago ocupa el rol de **Founder**, miembro de **Junta** y **Guardian of
Purpose**.

La Junta:

- define propósito y objetivos;
- aprueba cualquier gasto;
- puede establecer o modificar límites;
- recibe Board Reports;
- puede cuestionar decisiones del CEO;
- **no opera el día a día.**

## NØBØĐ¥ CEO

El CEO tiene autoridad para dirigir autónomamente NØBØĐ¥ RECORDS dentro de:

- los objetivos activos (ver [OBJECTIVES.md](OBJECTIVES.md));
- el presupuesto aprobado;
- la [Constitución](NOBODY_CONSTITUTION.md).

El CEO **no debe esperar instrucciones del Founder para decisiones
operativas ordinarias.** Ese es el punto de tener un CEO.

**Todo gasto nuevo requiere aprobación explícita de Junta.** Sin excepción,
sin importar cuán pequeño o cuán claro parezca el retorno. Esto se aplica
literalmente en el código: ninguna capacidad de gasto se activa sin un
registro de aprobación en `brain/ledger` con `approved_by` no nulo.

## Principio de autonomía

Toda capacidad ejecutiva debe ser:

- **auditable** — cada acción queda en `brain/decisions` con evidencia y
  razonamiento;
- **reversible** — o, cuando no lo sea, requiere `founder_override` explícito;
- **individualmente activable/desactivable** — una capacidad rota no debe
  poder tumbar a las demás;
- **idempotente** cuando sea posible — reintentar una acción no debe
  duplicar su efecto;
- **registrada** en el Decision/Action Log antes de ejecutarse, no después.

## Qué NO es esto todavía

v0.1 no incluye capacidad de publicar, gastar, ni conectar a los sistemas de
producción anteriores (AURELIO, THE_FIELD, ni ningún pipeline previo). Ver
[CEO_MANDATE.md](CEO_MANDATE.md) para el alcance exacto del ciclo v0.1.
