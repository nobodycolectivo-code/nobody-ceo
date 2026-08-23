# DistroKid — restricción conocida

DistroKid no publica una API oficial. No existe un endpoint documentado para
leer streams, regalías ni estado de releases de forma programática.

Por eso, en v0.1 esta carpeta **no contiene un cliente de integración**. Las
dos rutas disponibles son:

1. **Importación manual de CSV/reporte** — DistroKid permite exportar datos
   de regalías; un capability de `agents/capabilities` puede leer ese
   archivo y escribirlo en `brain/ledger` y `brain/metrics`. Es la ruta
   recomendada para v0.1.
2. **Automatizar el dashboard web** — técnicamente posible, pero es scraping
   frágil contra una superficie que puede romperse sin aviso y probablemente
   contra los términos de servicio. No se construye sin aprobación explícita
   de Junta, y solo si la opción 1 resulta insuficiente.

Ver la sección de riesgos de la propuesta de arquitectura para más detalle.
