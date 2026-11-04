# Tareas 007 — Retirar el bot de Telegram

- Spec: `spec.md` (aprobada) · Plan: `plan.md` (aprobado)
- Regla: una tarea por vez, primero los tests y luego el código. Al
  terminarla, marcarla, ejecutar `make test` y `make lint`, y detenerse.

## [ ] T1 — API: quitar Telegram y la llave del bot
Router, modelos, esquemas, funciones de vinculación, `bot_client` y
`BOT_API_KEY`.

- Test primero (`test_retired_bot.py` nuevo y `test_config.py`):
  - Criterio 1: cada ruta de `/telegram` responde `404`, con y sin
    `X-Bot-Key`.
  - Criterio 2: una ruta de datos con `X-Bot-Key` y sin sesión responde
    `401`.
  - Criterio 3: la configuración carga sin `BOT_API_KEY`, y también con
    `BOT_API_KEY` y `TELEGRAM_BOT_TOKEN` definidas.
  - Criterio 4: una base con las tablas de Telegram y una fila en cada
    una sigue funcionando (registro, gasto y resumen), y las filas siguen
    ahí.
  - Criterio 5: `create_all` sobre una base vacía no crea tablas de
    Telegram.
- Salen `test_telegram.py` y los tests de modelos y de configuración que
  solo probaban lo retirado. `conftest.py` y `test_invitations.py` dejan
  de usar `BOT_API_KEY`.
- Hecho cuando: los tests pasan y el resto de los tests de la API sigue en
  verde con las mismas aserciones.
- RF: RF-1 a RF-6.

## [ ] T2 — Quitar el servicio del bot
Borrar `services/bot/`; el `Makefile` y `.env.example` quedan solo con la
API.

- Comprobación (no hay tests nuevos: es borrar un servicio):
  - `make install`, `make test` y `make lint` funcionan y solo tocan la
    API.
  - `make run-bot` ya no existe.
  - `make run-api` arranca con el `.env.example` copiado a `.env` y una
    llave de bot de más en el entorno.
- Hecho cuando: `services/bot/` no existe y los tres targets pasan.
- RF: RF-7, RF-8.

## [ ] T3 — Documentación y cierre
README sin la sección del bot y con cómo registrar gastos hasta la 010;
roadmap con la 007 hecha.

- Comprobación:
  - Criterio 7: el `grep` de `telegram` y `bot_api_key` sobre `Makefile`,
    `.env.example`, `services/` y el README solo deja menciones de
    historia justificadas.
  - El README dice que las variables del bot de un `.env` viejo se pueden
    borrar.
- Hecho cuando: la búsqueda queda limpia, la 007 está marcada en el
  roadmap y la spec activa es la 008.
- RF: RF-9.
