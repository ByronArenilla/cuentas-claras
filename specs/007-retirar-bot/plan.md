# Plan 007 — Retirar el bot de Telegram

- Spec: `spec.md` (estado: aprobada)
- Servicios afectados: `services/api` y `services/bot`, que se elimina
- Estado: aprobado (2026-11-04)

Es una spec de quitar código: no hay rutas ni tablas nuevas. La API pierde
el router de Telegram, la llave del bot y los modelos de la vinculación. El
repositorio pierde el servicio del bot y lo que lo arrancaba, lo probaba y
lo configuraba.

## Decisiones técnicas

| Decisión | Elegido | Por qué |
|---|---|---|
| Rutas `/telegram/*` | Se borra `app/routers/telegram.py` y su `include_router` | Sin el router, FastAPI responde `404` por sí solo (RF-1). No hace falta una ruta que diga "retirado": no queda ningún cliente que la llame. |
| Llave del bot | Sale `BOT_API_KEY` de `REQUIRED_VARIABLES`, de `Settings` y de su validación; sale `bot_client` de `deps.py` | RF-2 y RF-3. `load_settings` solo lee las variables que conoce, así que una `BOT_API_KEY` que sobra en el entorno se ignora sin código extra (decisión 2). |
| Modelos | Salen `TelegramLinkCode` y `TelegramChat` de `models.py` | Con `create_all` (ADR 0004), una base nueva ya no crea esas tablas (RF-6). En una base vieja, `create_all` no borra las que sobran (RF-5). |
| Tablas en bases viejas | No se tocan | Decisión 1: las borra la primera migración de la 008. SQLAlchemy solo conoce las tablas de sus modelos, así que ninguna consulta las lee ni escribe. |
| Funciones de la vinculación | Salen `generate_link_code`, `normalize_link_code` y sus constantes de `security.py`, y los esquemas de Telegram de `schemas.py` | Solo las usaba el router. Dejarlas sería código muerto. |
| Lo que se queda | `create_session(db, user_id, lifetime)`, la ruta `recent` y `hash_token` | Decisión 4. `hash_token` también lo usan las sesiones y las invitaciones. |
| Pruebas de lo retirado | Un archivo nuevo, `tests/test_retired_bot.py` | Reúne en un sitio los criterios 1 a 5. Sale `test_telegram.py` y salen los tests de modelos y de configuración del bot. |
| Makefile | Un solo servicio en `install`, `test` y `lint`; sale `run-bot` y las variables `BOT_*` | RF-7. Los nombres de los targets que quedan no cambian (AGENTS.md). |
| ADR | No hace falta otro | El ADR 0010 ya decide el retiro, y este plan solo lo ejecuta. |

## Dependencias

Ninguna nueva. Desaparecen las del bot (`python-telegram-bot`, `httpx` como
dependencia de ejecución del bot) junto con su `pyproject.toml`. La API
sigue teniendo `httpx` en desarrollo, porque lo necesita `TestClient`.

## Estructura de archivos

    services/api/
      app/main.py                     − include_router(telegram)               [RF-1]
      app/routers/telegram.py         eliminado                                [RF-1]
      app/config.py                   − BOT_API_KEY                            [RF-2]
      app/deps.py                     − bot_key_header, bot_client             [RF-3]
      app/models.py                   − TelegramLinkCode, TelegramChat         [RF-5, RF-6]
      app/schemas.py                  − esquemas de Telegram
      app/security.py                 − generate_link_code, normalize_link_code
      tests/conftest.py               − BOT_API_KEY
      tests/test_config.py            − tests de la llave; + variables que sobran  [RF-2]
      tests/test_invitations.py       − BOT_API_KEY al armar la configuración  [RF-4]
      tests/test_models.py            − tests de Telegram
      tests/test_telegram.py          eliminado
      tests/test_retired_bot.py       nuevo: criterios 1 a 5                   [RF-1 a RF-6]
    services/bot/                     eliminado entero                         [RF-7]
    Makefile                          solo la API; sin run-bot                 [RF-7]
    .env.example                      sin TELEGRAM_BOT_TOKEN ni BOT_API_KEY    [RF-8]
    README.md                         sin la sección del bot                   [RF-9]

## Cómo se prueba RF-5

El test crea un motor SQLite en memoria y, antes de `create_all`, ejecuta
el `CREATE TABLE` de las dos tablas de Telegram tal como las dejó la 005,
con una fila en cada una. Después llama a `create_all`, levanta un
`TestClient` con esa base y hace un recorrido corto: registrarse, crear un
gasto y pedir el resumen. Al final cuenta las filas de las dos tablas.

El `CREATE TABLE` se escribe a mano en el test porque los modelos ya no
existen. Así el test reproduce de verdad una base vieja.

## Riesgos

- **Un `.env` local con `BOT_API_KEY`**: no rompe nada (decisión 2), pero
  puede confundir. El README dice que se borra.
- **Un bot que siga corriendo en otra terminal**: sus llamadas reciben
  `404` y responde con errores. Basta con detenerlo. No es un riesgo para
  los datos: ya no puede pedir sesiones.
- **Referencias sueltas**: el criterio 7 se comprueba con `grep` al cerrar.
