# Despliegue — Railway

El bot (`integrations/telegram/bot.py`) corre 24/7 como worker en Railway,
proyecto `nobody-ceo` bajo la cuenta `no.bodycolectivo@gmail.com` (aislada
de NÚCLEO/CLARA a propósito). Long-polling, sin puerto HTTP expuesto.

## Trampa de Windows + Git Bash: MSYS path conversion

Git Bash traduce automáticamente cualquier argumento de línea de comandos
que empiece con `/` a una ruta de Windows antes de pasarlo al binario —
incluso cuando ese `/` es una ruta remota de Linux (mount path de un
volumen, valor de una variable de entorno, ruta dentro del contenedor).
Esto ya rompió dos cosas en este proyecto:

- `railway volume add --mount-path /data` → sin la variable de abajo,
  falla o crea el volumen en un mount path corrupto.
- `railway variable set NOBODY_DB_PATH=/data/nobody.db` → sin la
  variable de abajo, guardó literalmente `C:/Program Files/Git/data/nobody.db`
  como valor, y el bot corrió meses (bueno, minutos) leyendo una base
  vacía sin que ningún error lo delatara.

**Regla:** cualquier comando de `railway` (o cualquier CLI) cuyo
argumento sea una ruta que empiece con `/` y esté destinada al lado
remoto/Linux, correrlo con `MSYS_NO_PATHCONV=1` por delante:

```bash
MSYS_NO_PATHCONV=1 railway variable set NOBODY_DB_PATH=/data/nobody.db --service nobody-ceo
MSYS_NO_PATHCONV=1 railway volume --service nobody-ceo files --volume nobody-ceo-volume upload data/nobody.db /nobody.db --overwrite
```

Después de tocar cualquier variable o archivo así, **verificar contra el
contenedor real**, nunca asumir por el mensaje de éxito del CLI:

```bash
railway ssh --service nobody-ceo "printenv NOBODY_DB_PATH"
railway ssh --service nobody-ceo "/opt/venv/bin/python -c \"import sqlite3; c=sqlite3.connect('/data/nobody.db'); print(c.execute('SELECT COUNT(*) FROM albums').fetchone())\""
```

## Actualizar NOBODY_BRAIN en producción

La ingesta de catálogo (`agents/capabilities/catalogue.py`) necesita leer
`D:\Users\Santiago\Desktop\NOBODY`, que solo existe en la máquina local —
no se puede correr dentro de Railway. El flujo hoy es manual:

1. Local: `python -m agents.capabilities.catalogue --root "D:\...\NOBODY"`
   (o `agents.capabilities.metrics` para refrescar solo métricas).
2. Subir la base actualizada al volumen:
   ```bash
   MSYS_NO_PATHCONV=1 railway volume --service nobody-ceo files --volume nobody-ceo-volume upload data/nobody.db /nobody.db --overwrite
   ```
3. Verificar con los comandos de arriba antes de darlo por hecho.

Esto es manual a propósito en v0.1 — automatizarlo (por ejemplo, con un
job que sincronice) es una capacidad futura, no construida todavía.

## Redeploy de código

```bash
railway up --ci -y --service nobody-ceo
```

Sube el directorio actual (respeta `.gitignore`) y reconstruye. Las
variables de entorno y el volumen persisten entre redeploys — no hay que
volver a configurarlos.

## Variables de entorno en Railway

Las mismas que en `.env.example`, cargadas manualmente vía
`railway variable set` (no vía archivo — `.env` nunca se commitea ni se
sube). Ver la nota de decisión en `.env` local sobre credenciales
reutilizadas del pipeline anterior (YouTube, Spotify).

Además, solo en Railway (no en `.env.example` — es específico del
contenedor):

```
NOBODY_RENDER_DIR=/data/render_output
```

Sin esto, `agents/capabilities/content.py` renderiza en
`render_output/` relativo al working directory del contenedor —
filesystem efímero, se borra en cada redeploy/restart. Los reels quedan
`pending_review` esperando aprobación por Telegram indefinidamente (ver
`docs/CEO_MANDATE.md`), así que el archivo tiene que sobrevivir un
redeploy o la aprobación falla al no encontrar el .mp4. Apuntarlo al
volumen (`/data`, ya montado) lo resuelve.
