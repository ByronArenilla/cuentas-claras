# Tareas 005 — Bot: vinculación y registro guiado

- Spec: `spec.md` (aprobada) · Plan: `plan.md` (aprobado)
- Regla: una tarea por vez, primero los tests y luego el código. Al
  terminarla, marcarla, ejecutar `make test` y `make lint`, y detenerse.

## [x] T1 — `BOT_API_KEY` en la API
`config.py` exige `BOT_API_KEY` con 32 caracteres o más; `conftest.py` usa
una llave de prueba; `.env.example` la documenta.

- Test primero (`test_config.py`):
  - Sin `BOT_API_KEY`, o vacía, la configuración no carga y el error la
    nombra.
  - Con 31 caracteres falla con `InvalidSettingError` y el error la nombra;
    con 32 carga.
- Hecho cuando: los tests pasan y el resto de la suite sigue en verde.
- RF: base de RF-9.

## [x] T2 — Tablas de Telegram
`models.py`: `TelegramLinkCode` y `TelegramChat` como las describe el plan.

- Test primero (`test_models.py`):
  - Dos códigos con el mismo hash chocan.
  - Dos filas con el mismo `chat_id` chocan; un usuario con dos chats, no.
  - Un `chat_id` de 52 bits se guarda.
- Hecho cuando: los tests pasan.
- RF: base de RF-2 y RF-5.

## [x] T3 — Pedir un código de vinculación
`security.py`: `generate_link_code` y `normalize_link_code`. Rutas:
`POST /telegram/link-codes` y el router montado en `main.py`.

- Test primero (`test_telegram.py`):
  - El código tiene la forma `ABCD-EFGH` con el alfabeto del plan.
  - `normalize_link_code(" abcd-efgh ")` es `ABCDEFGH`.
  - Con sesión, `201` con `code` y `expires_at` a 10 minutos.
  - En la base de datos solo está el hash, nunca el código.
  - Sin sesión, `401`.
- Hecho cuando: los tests pasan.
- RF: RF-1, RF-2.

## [x] T4 — Vincular, desvincular y sesiones del bot
`deps.py`: `bot_client`. `auth.py`: `create_session`. Rutas
`POST /telegram/chats`, `DELETE /telegram/chats/{chat_id}` y
`POST /telegram/sessions`.

- Test primero (`test_telegram.py`):
  - Criterio 1: un código vigente vincula el chat a Ana y responde su
    correo; usarlo otra vez, uno inexistente o uno caducado responden `400`
    con el mismo mensaje.
  - Dos usos del mismo código: solo el primero vincula (se simula como en
    las invitaciones).
  - Un chat vinculado a Ana pasa a Bea con un código de Bea.
  - Criterio 2: sin `X-Bot-Key` o con una equivocada, las tres rutas
    responden `401` y no cambian nada.
  - Criterio 3: la sesión del bot sirve para `GET /spaces`, caduca a la
    hora y, tras desvincular, el chat recibe `404`.
  - Desvincular un chat que no estaba vinculado responde `204`.
  - El inicio de sesión sigue dando 15 días.
- Hecho cuando: los tests pasan.
- RF: RF-3 a RF-6, RF-9, RF-10.

## [x] T5 — Esqueleto del bot y `Makefile`
`services/bot/pyproject.toml`, `bot/__init__.py`, `bot/config.py` y el
`Makefile`: `install`, `test` y `lint` cubren la API y el bot, y aparece
`run-bot`.

- Test primero (`services/bot/tests/test_config.py`):
  - Si faltan variables, el error las nombra todas.
  - Una `TZ` inválida falla nombrando `TZ`.
- Hecho cuando: `make install`, `make test` y `make lint` funcionan con los
  dos servicios.
- RF: base de RF-28.

## [ ] T6 — Montos, fechas y formato
`bot/parsing.py` con `parse_amount`, `parse_day`, `format_money` y
`format_day`.

- Test primero (`test_parsing.py`):
  - Se aceptan `20000`, `20.000`, `$20.000`, `$ 20.000` y `1.000.000`.
  - Criterio 5: se rechazan `20,5`, `20.000,50`, `20000.5`, `2.00`, `0`,
    `-5`, `abc` y `1.000.000.000.001`.
  - `parse_day`: `30/10`, `30/10/2026` y `30-10-2026`; se rechazan
    `31/02`, `2026-10-30` y `ayer`.
  - `format_money(1240000)` es `$ 1.240.000`.
  - `format_day` con hoy, ayer, otro día del mismo año y otro año.
- Hecho cuando: los tests pasan sin red.
- RF: RF-13, RF-17, RF-28.

## [ ] T7 — Cliente de la API
`bot/api.py` con `ApiClient` y sus errores.

- Test primero (`test_api.py`, con `httpx.MockTransport`):
  - La primera llamada de un chat pide sesión con `X-Bot-Key` y las
    siguientes reutilizan el token.
  - Un `401` descarta el token, pide otro y repite una sola vez.
  - `404` de la sesión es `NotLinked`; `400` al vincular es `InvalidCode`;
    otro `4xx` es `ApiRejected` con el detalle; sin conexión o `5xx` es
    `ApiUnavailable`.
  - `unlink_chat` cierra la sesión guardada antes de desvincular.
- Hecho cuando: los tests pasan sin red.
- RF: RF-6, RF-10, RF-11; base de RF-7 y RF-25.

## [ ] T8 — Conversación: ayuda y vinculación
`bot/conversation.py`: eventos, respuestas, `/start`, `/ayuda`,
`/vincular` y `/desvincular`.

- Test primero (`test_conversation.py`, con una API falsa):
  - `/start` en un chat sin vincular explica cómo vincularlo.
  - `/vincular ABCD-EFGH` confirma con el correo; un código inválido lo
    dice; `/vincular` sin código explica el uso.
  - `/desvincular` lo confirma.
  - Criterio 9: `/gasto` y un monto en un chat sin vincular reciben las
    instrucciones y no llaman a rutas de datos.
  - Un texto que no se entiende recibe la ayuda.
- Hecho cuando: los tests pasan.
- RF: RF-3, RF-6, RF-7, RF-27.

## [ ] T9 — Conversación: registrar un gasto
El borrador completo en `bot/conversation.py`.

- Test primero (`test_conversation.py`):
  - Criterio 4: el recorrido completo con dos espacios, `$20.000`, Ayer y
    descripción. La API recibe un gasto con esos datos y la respuesta trae
    la línea del presupuesto.
  - Criterio 6: con un espacio no se pregunta.
  - `/gasto 20000` y `20.000` empiezan con el monto.
  - Criterio 5 en la conversación: un monto inválido se pide de nuevo.
  - Criterio 7: con el reloj fijado, Ayer es el 30 de octubre, Hoy no envía
    `spent_on` y el 1 de noviembre se rechaza por futuro.
  - Omitir la descripción, y una de 201 caracteres se pide de nuevo.
  - Criterio 8: doble Confirmar registra uno; un botón tras cancelar o tras
    10 minutos no registra nada.
  - Las tres formas de la línea del presupuesto, y sin la línea si el
    resumen falla.
  - API caída al confirmar: aviso y el borrador sigue en la confirmación.
    API que rechaza: el motivo y el borrador se descarta.
  - `/cancelar` en cualquier paso; `/gasto` con un borrador empieza otro;
    un texto en un paso de botones recibe la indicación.
- Hecho cuando: los tests pasan.
- RF: RF-12 a RF-26, RF-28.

## [ ] T10 — Adaptador de Telegram
`bot/telegram_app.py` y `bot/__main__.py`, y `make run-bot`.

- Test primero (`test_telegram_app.py`):
  - `to_markup` convierte filas de botones en `InlineKeyboardMarkup` con
    los mismos textos y datos; sin botones, `None`.
  - `build_application` registra manejadores solo para chats privados.
- Hecho cuando: los tests pasan y `make run-bot` sin variables falla
  nombrándolas.
- RF: RF-8.

## [ ] T11 — ADR 0009: vinculación del chat y llave del bot
`docs/adr/0009-vinculacion-del-chat-y-llave-del-bot.md` con la plantilla:
por qué la vinculación se adelanta a la 005, la llave del bot, la sesión de
una hora, y las alternativas descartadas (chat fijo en `.env`, llave más
`chat_id` en cada petición, sesión de 15 días).

- Test primero: no aplica, es documentación.
- Hecho cuando: el ADR existe y el plan lo cita.
- RF: ninguno; principios 4, 12 y 13.

## [ ] T12 — Cierre: README, roadmap y validación
- `README.md`: sección del bot: crear el bot con @BotFather, variables de
  `.env`, `make run-bot`, pedir el código, `/vincular` y registrar un
  gasto.
- Comprobar que `make run-api` crea las tablas nuevas sin borrar datos.
- Repasar los diez criterios de validación.
- `docs/roadmap.md`: marcar la 005, dejar la 006 activa, y anotar en la
  008 que la vinculación del chat se hizo en la 005.

- Test primero: no aplica.
- Hecho cuando: `make test` y `make lint` están en verde.
- RF: ninguno nuevo; cierra la spec.
