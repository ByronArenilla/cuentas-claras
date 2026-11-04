# Plan 005 — Bot: vinculación y registro guiado

- Spec: `spec.md` (estado: aprobada)
- Servicios afectados: `services/api` y `services/bot` (nuevo)
- Estado: aprobado (aprobación previa del 2026-11-04)

La spec tiene dos mitades. En la API, dos tablas nuevas (`telegram_link_codes`
y `telegram_chats`) y cuatro rutas para vincular chats y darle sesiones al
bot. Ninguna tabla existente cambia, así que `create_all` sigue bastando
(ADR 0004). En el bot, el servicio entero: configuración, cliente de la API,
la conversación y el adaptador de Telegram.

## Decisiones técnicas

| Decisión | Elegido | Por qué |
|---|---|---|
| Cómo se identifica el bot ante la API | Llave compartida `BOT_API_KEY` en la cabecera `X-Bot-Key`, comparada con `hmac.compare_digest` | Es lo más simple que separa "el bot" de "cualquiera". La comparación en tiempo constante no deja adivinar la llave midiendo cuánto tarda la respuesta. Deja el ADR 0009. |
| Cómo actúa el bot en nombre de un usuario | Pide a `POST /telegram/sessions` una sesión normal del usuario del chat, que dura una hora | Todas las rutas existentes siguen igual: el bot manda `Authorization: Bearer`, como la web. Se descartó que `current_user` aceptara la llave más un `chat_id` en cada petición: tocaría la pieza central de la autenticación de la 001. |
| Revocar el acceso del bot | Sesión de una hora y `/desvincular` cierra la sesión que el bot tenga en memoria (`POST /auth/logout`) | La tabla `sessions` no sabe de qué chat viene una sesión, y añadírselo cambia una tabla que ya está en `main` (ADR 0004). Con una hora, el peor caso queda acotado (decisión 7). |
| Código de vinculación | 8 caracteres del alfabeto Crockford base32 (sin `I`, `L`, `O` ni `U`), mostrado como `ABCD-EFGH` | 40 bits: con 10 minutos de vida, probar códigos a través de Telegram no llega a ninguno. Sin letras que se confunden con números al copiarlo. Al recibirlo se ignoran mayúsculas, espacios y guiones. |
| Guardar el código | Solo su hash SHA-256 (`hash_token` de la 001) y `UPDATE ... WHERE used_at IS NULL` al usarlo | RF-2 y RF-4, con el mismo patrón que el canje de invitaciones: dos usos simultáneos, solo uno actualiza la fila. |
| Qué es la conversación | Un motor propio en `bot/conversation.py` que recibe eventos (comando, texto, botón) y devuelve respuestas (texto y botones), sin importar nada de Telegram | Principio 10: la conversación se prueba sin Telegram ni red. El adaptador de `python-telegram-bot` solo traduce. Se descartó el `ConversationHandler` de la librería: su estado vive dentro de la librería y probarlo exige fabricar objetos `Update`. |
| Botones viejos | Cada borrador tiene un número y cada botón lleva `número:paso:valor` | RF-24: un botón de un borrador anterior o de otro paso no coincide y no cambia nada. También evita el doble Confirmar (RF-20). |
| Reloj del bot | El motor recibe `clock` (función que devuelve el instante en UTC) y la zona de `TZ` | "Hoy" y "Ayer" en `TZ` (principio 7), y los tests fijan el reloj pasando otra función, sin `monkeypatch`. |
| Llamadas a la API | `httpx.AsyncClient` con 10 s de espera, y en los tests `httpx.MockTransport` | `httpx` ya está en el stack; `MockTransport` viene incluido y simula la API sin red ni dependencias nuevas. |
| Tests asíncronos | Los tests llaman a `asyncio.run(...)` | Se evita añadir `pytest-asyncio`: con unos pocos `asyncio.run` basta. |
| Recibir mensajes | *Polling* con `Application.run_polling()` | No necesita URL pública ni HTTPS, que llegan en las fases 3 y 9. |

## Dependencias

- Bot: `python-telegram-bot` (22.x) y `httpx`, ya previstas en el stack de
  `AGENTS.md`. Desarrollo: `pytest` y `ruff`, como la API.
- API: ninguna nueva.

## Estructura de archivos

    .env.example                    + BOT_API_KEY
    Makefile                        install, test y lint también del bot; + run-bot
    services/api/
      app/
        config.py                   + bot_api_key (obligatoria, 32 caracteres o más)  [RF-9]
        models.py                   + TelegramLinkCode, TelegramChat                    [RF-2, RF-5]
        security.py                 + generate_link_code, normalize_link_code           [RF-1, RF-2]
        deps.py                     + bot_client (comprueba X-Bot-Key)                  [RF-9]
        schemas.py                  + LinkCodeOut, ChatLinkIn, ChatLinkOut, ChatIn      [RF-1, RF-3]
        routers/
          auth.py                   create_session compartida con el bot                [RF-10]
          telegram.py               nuevo: códigos, vincular, desvincular y sesiones
        main.py                     monta el router de Telegram
      tests/
        conftest.py                 + BOT_API_KEY de prueba
        test_config.py              + BOT_API_KEY obligatoria y larga
        test_models.py              + tablas de Telegram
        test_telegram.py            nuevo
    services/bot/
      pyproject.toml                nuevo
      bot/
        __init__.py
        __main__.py                 `python -m bot`
        config.py                   TELEGRAM_BOT_TOKEN, API_URL, BOT_API_KEY, TZ        [RF-28]
        parsing.py                  montos, fechas y formato en pesos                   [RF-13, RF-17, RF-28]
        api.py                      cliente de la API con sesiones por chat             [RF-7, RF-10, RF-11, RF-25]
        conversation.py             motor de la conversación                            [RF-12 a RF-27]
        telegram_app.py             adaptador de python-telegram-bot                    [RF-8]
      tests/
        test_config.py, test_parsing.py, test_api.py,
        test_conversation.py, test_telegram_app.py
    docs/adr/0009-vinculacion-del-chat-y-llave-del-bot.md
    README.md                       + sección del bot (al cerrar la spec)

## API

### Configuración

`BOT_API_KEY` entra en las variables obligatorias de `config.py`. Además
debe tener 32 caracteres o más; si no, la API no arranca y lo dice
(`InvalidSettingError`), igual que con una `TZ` inválida. `.env.example`
explica cómo generarla:
`python3 -c "import secrets; print(secrets.token_urlsafe(32))"`. [RF-9]

### Modelo de datos

**`telegram_link_codes`**: `id`, `code_hash` (único), `user_id`
(`ON DELETE CASCADE`), `expires_at`, `used_at` (nulo hasta usarse),
`created_at`. [RF-1, RF-2, RF-4]

**`telegram_chats`**: `id`, `chat_id` (`BigInteger`, único), `user_id`
(`ON DELETE CASCADE`), `created_at`. El índice único sobre `chat_id` hace
que un chat sea de un solo usuario (RF-5). `BigInteger` porque Telegram
documenta identificadores de hasta 52 bits.

### Rutas (`app/routers/telegram.py`)

| Método y ruta | Quién | Qué hace | RF |
|---|---|---|---|
| `POST /telegram/link-codes` | usuario (`current_user`) | Código nuevo: `201` con `code` (`ABCD-EFGH`) y `expires_at` | RF-1, RF-2 |
| `POST /telegram/chats` | bot (`bot_client`) | Cuerpo `{chat_id, code}`. Usa el código y vincula el chat: `200` con `email` | RF-3 a RF-5 |
| `DELETE /telegram/chats/{chat_id}` | bot | Quita la vinculación: `204`, también si no existía | RF-6 |
| `POST /telegram/sessions` | bot | Cuerpo `{chat_id}`. Sesión de una hora del usuario del chat: `201` con el token, o `404` | RF-10 |

- **Código no válido, usado o caducado**: `400` "El código no es válido, ya
  se usó o caducó.", el mismo en los tres casos. [RF-4]
- **Vincular un chat ya vinculado**: se cambia el `user_id` de su fila.
  [RF-5]
- **Sin llave o con una equivocada**: `401` "Llave del bot no válida.",
  antes de leer el cuerpo o la base de datos. [RF-9]
- **Chat no vinculado al pedir sesión**: `404` "Este chat no está
  vinculado.". [RF-10]
- **`create_session(db, user_id, lifetime)`** sale de `login` en
  `auth.py`: el inicio de sesión la usa con 15 días y el bot con una hora.
  [RF-10]

## Bot

### Configuración (`bot/config.py`)

Lee `TELEGRAM_BOT_TOKEN`, `API_URL`, `BOT_API_KEY` y `TZ`, y si falta
alguna el bot no arranca y las nombra, como la API (RF-33 de la 001).
Comprueba que `TZ` sea una zona real.

### Formato y lectura (`bot/parsing.py`)

Funciones puras:

- `parse_amount(text) -> int | None`: acepta `20000`, `20.000`, `$20.000`
  y `$ 20.000`; con puntos, solo en grupos de tres. Rechaza decimales, comas,
  cero, negativos y más de un billón. [RF-13]
- `parse_day(text, today) -> date | None` con `DD/MM` o `DD/MM/AAAA`, y
  también con `-` como separador. [RF-17]
- `format_money(amount) -> str`: `$ 20.000`. [RF-28]
- `format_day(day, today) -> str`: "hoy, 4 de noviembre", "ayer, 3 de
  noviembre", "1 de octubre" o "1 de octubre de 2025". [RF-19]

### Cliente de la API (`bot/api.py`)

`ApiClient` envuelve un `httpx.AsyncClient` y guarda en memoria el token de
cada chat:

- `link_chat`, `unlink_chat`: con la llave del bot. `unlink_chat` cierra
  antes la sesión guardada de ese chat (`POST /auth/logout`). [RF-3, RF-6]
- `spaces`, `categories`, `create_expense` y `summary`: con el token del
  chat. Si no hay token, lo pide a `/telegram/sessions`; si la API responde
  `401`, lo descarta, pide otro y repite una vez. [RF-10, RF-11]
- Errores propios: `NotLinked` (`404` de la sesión), `InvalidCode`,
  `ApiRejected(detalle)` (otro `4xx`) y `ApiUnavailable` (sin conexión,
  tiempo agotado o `5xx`). [RF-7, RF-25]

### Conversación (`bot/conversation.py`)

`Conversations.handle(chat_id, event) -> list[Reply]`, donde un evento es
`Command(name, args)`, `Text(text)` o `Press(data)`, y una respuesta es un
texto con filas de botones (`Button(label, data)`).

Los pasos del borrador son: monto → espacio (si hay más de uno) →
categoría → tipo de pago → fecha (→ otra fecha) → descripción →
confirmación. Reglas:

- El borrador guarda su número, su paso y cuándo se tocó por última vez. Si
  pasaron más de 10 minutos, se descarta antes de atender el evento y se
  avisa. [RF-23]
- Un `Press` cuyo número o paso no coincide con el borrador actual responde
  "Esa conversación ya terminó…" y no cambia nada. [RF-24]
- Al confirmar, el borrador pasa a "guardando" antes de llamar a la API.
  Si la API no responde, vuelve a la confirmación; si lo rechaza o lo
  registra, se descarta. [RF-20, RF-25]
- Tras registrar, pide el resumen del mes del gasto (`spent_on[:7]`) y arma
  la línea del presupuesto; si esa llamada falla, la omite. [RF-21]
- Hoy y ayer salen de `clock()` convertido a `TZ`. Para "Hoy" no se envía
  `spent_on` y la API usa su propio hoy; para "Ayer" y Otra fecha se envía
  el día. [RF-17]
- El bot comprueba el formato y los límites de cada paso para avisar en el
  momento. La API sigue siendo quien decide: si rechaza el gasto, el bot
  muestra su mensaje. [RF-13, RF-17, RF-18, RF-25]

### Adaptador de Telegram (`bot/telegram_app.py`)

- Un manejador por comando (`start`, `ayuda`, `vincular`, `desvincular`,
  `gasto`, `cancelar`), uno para texto y uno para botones, todos filtrados
  a chats privados. [RF-8]
- `to_markup(reply)` convierte los botones en un `InlineKeyboardMarkup`.
- Al tocar un botón, responde a Telegram (`query.answer()`) y quita el
  teclado de ese mensaje, para que no se pueda tocar dos veces.
- `python -m bot` construye `Application` con el token y arranca el
  *polling*.

## Tests

- **API** (`test_telegram.py`, `test_config.py`, `test_models.py`):
  criterios 1 a 3, la sesión de una hora, el `401` sin llave en las tres
  rutas del bot y que el código se guarda solo como hash.
- **Bot**:
  - `test_parsing.py`: criterio 5 y los formatos de fecha.
  - `test_api.py`: con `MockTransport`, el token por chat, el reintento
    tras `401` y la traducción de errores.
  - `test_conversation.py`: con una API falsa en memoria, los criterios 4
    y 6 a 9.
  - `test_telegram_app.py`: `to_markup` y el filtro de chats privados.

## Verificación a mano

Hace falta un bot real de Telegram, creado con
[@BotFather](https://core.telegram.org/bots/tutorial#obtain-your-bot-token).
El README explica los pasos: crear el bot, poner su token y la llave en
`.env`, `make run-api` y `make run-bot`, pedir un código con `curl`,
`/vincular` y registrar un gasto.

## Riesgos y temas abiertos

- **La llave del bot es un secreto maestro**: con ella se obtiene una
  sesión de cualquier chat vinculado. Vive solo en `.env` (principio 12) y
  la 009 debe pasarla como secreto.
- **Si la API registra el gasto pero la respuesta no llega**, el bot
  conserva el borrador y un reintento lo duplicaría. El mensaje lo advierte;
  `/deshacer` (006) lo resuelve.
- **Las sesiones del bot se acumulan** en `sessions` hasta caducar, una por
  chat y hora de uso. Limpiar sesiones caducadas no lo cubre ninguna spec
  todavía, igual que con las de la 001.
- **Los borradores se pierden al reiniciar el bot** (decisión 8).
- **El código se pide con `curl`** hasta que la web lo muestre (007/008).

## Conceptos nuevos

- [Bots de Telegram](https://core.telegram.org/bots) y [botones en línea](https://core.telegram.org/bots/features#inline-keyboards).
- [`python-telegram-bot`](https://docs.python-telegram-bot.org/) — `Application`, manejadores y *polling*.
- [*Polling* frente a *webhooks*](https://core.telegram.org/bots/api#getting-updates) — dos formas de recibir mensajes.
- [`httpx.MockTransport`](https://www.python-httpx.org/advanced/transports/#mock-transports) — simular un servidor HTTP en los tests.
- [`hmac.compare_digest`](https://docs.python.org/3/library/hmac.html#hmac.compare_digest) — comparar secretos sin filtrar información por el tiempo.
- [`APIKeyHeader` de FastAPI](https://fastapi.tiangolo.com/reference/security/#fastapi.security.APIKeyHeader) — leer una llave de una cabecera y declararla en `/docs`.
