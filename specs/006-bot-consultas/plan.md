# Plan 006 — Bot: consultas y deshacer

- Spec: `spec.md` (estado: aprobada)
- Servicios afectados: `services/api` (una ruta) y `services/bot`
- Estado: aprobado (aprobación previa del 2026-11-04)

La API gana una sola ruta de lectura y ninguna tabla. El resto es del bot:
tres comandos nuevos, cuatro llamadas más en el cliente de la API y el
registro del menú de comandos.

## Decisiones técnicas

| Decisión | Elegido | Por qué |
|---|---|---|
| Últimos gastos registrados | `GET /spaces/{space_id}/expenses/recent?limit=5&mine=false`, ordenada por `created_at` y luego por `id`, descendente | RF-1 y RF-2 en una sola ruta bajo `member_space`. Se descartó ordenar el listado por periodo con otro parámetro: ese listado siempre filtra por mes, y aquí se piden gastos de cualquier mes. |
| Orden de las rutas | `/recent` se declara antes de `/{expense_id}` | Starlette prueba las rutas en orden. Si `/{expense_id}` va primero, `recent` se toma como identificador y responde `422`. |
| `mine=true` | Filtro por `created_by` igual al usuario de la sesión | `/deshacer` necesita el último gasto propio, que puede no estar entre los cinco últimos del espacio (RF-2). |
| Buscar mi último gasto | El bot pide `recent?limit=1&mine=true` en cada espacio y se queda con el más reciente | Mantiene todas las rutas de datos bajo `/spaces/{space_id}`, filtradas por espacio (principio 13). Un usuario tiene pocos espacios. Se descartó una ruta `/me/last-expense`, que consultaría varios espacios a la vez fuera de `member_space`. |
| Botones sin estado | Los datos del botón llevan lo necesario: `sum:<espacio>:<AAAA-MM>`, `last:<espacio>`, `undo:<espacio>:<gasto>` y `undo:no` | Decisión 6 y RF-18. No ocupan el borrador del chat, así que no interrumpen un gasto, y sobreviven a un reinicio. Un botón manipulado no da más poder: la API comprueba la membresía, y cualquier miembro ya puede borrar cualquier gasto del espacio (decisión 4 de la 003). |
| Doble Borrar | El segundo `DELETE` recibe `404` y el bot responde "ese gasto ya no existe" | RF-15 sin estado: el borrado es por identificador, así que repetirlo nunca borra otro gasto. |
| Distinguir el gasto de otro miembro | `GET /me` una vez por comando, y comparar con `created_by` | La API ya da el `id` del autor (plan 003). No se muestra el correo (decisión 7). |
| Texto del resumen | Funciones puras en `bot/views.py` | Principio 10: el formato se prueba sin conversación ni red. La línea de presupuesto de la 005 reutiliza la misma función para "te quedan" o "te pasaste". |
| Menú de comandos | `Application.post_init` llama a `bot.set_my_commands` | Decisión 8 y principio 14: el menú queda en el código. Si Telegram no responde, se registra un aviso y el bot arranca igual. |
| ADR | No hace falta | Ninguna decisión cambia la arquitectura: es una ruta de lectura más y reglas del bot que este plan ya explica. |

## Dependencias

Ninguna nueva.

## Estructura de archivos

    services/api/
      app/routers/expenses.py         + GET /recent                              [RF-1 a RF-4]
      tests/test_expenses.py          + últimos registrados
      tests/test_isolation.py         + la ruta nueva en el aislamiento
    services/bot/
      bot/api.py                      + me, recent_expenses, delete_expense, NotFound  [RF-12, RF-15]
      bot/parsing.py                  + shift_period                             [RF-8]
      bot/views.py                    nuevo: textos de resumen y de gastos      [RF-6, RF-7, RF-9, RF-10]
      bot/conversation.py             + /resumen, /ultimos, /deshacer y sus botones
      bot/telegram_app.py             + comandos nuevos y menú                   [RF-20]
      tests/test_api.py, test_parsing.py, test_views.py (nuevo),
      test_conversation.py, test_telegram_app.py
    README.md                         + comandos de consulta (al cerrar la spec)

## API

`GET /spaces/{space_id}/expenses/recent`:

- `limit`: entero de 1 a 20, por defecto 5. Fuera de rango, `422`. [RF-1, RF-3]
- `mine`: booleano, por defecto `false`. Con `true`, solo `created_by` igual
  a quien llama. [RF-2]
- Respuesta: lista de `ExpenseOut`, la misma forma que el listado. [RF-1]
- Usa `member_space` y filtra por `space_id`: el test que recorre las rutas
  con `{space_id}` la vigila sin cambios. [RF-4]

## Bot

### Cliente (`bot/api.py`)

- `me(chat_id) -> dict` (`GET /me`).
- `recent_expenses(chat_id, space_id, limit=5, mine=False) -> list[dict]`.
- `delete_expense(chat_id, space_id, expense_id) -> None`, con
  `confirm=true`. Solo se llama tras tocar Borrar. [RF-14]
- `NotFound`, subclase de `ApiRejected`, para un `404` en una ruta de
  datos: es lo que distingue "ese gasto ya no existe". [RF-15]

### Textos (`bot/views.py`)

- `remaining_text(remaining)`: "Te quedan $ X." o "Te pasaste por $ X.".
  La usan el resumen y la línea de presupuesto de la 005.
- `summary_text(space_name, summary)`:

      Casa · noviembre de 2026
      Gastado: $ 450.000 de $ 500.000. Te quedan $ 50.000.

      Comida: $ 412.000 de $ 400.000. Te pasaste por $ 12.000.
      Transporte: $ 38.000. Sin presupuesto.
      Ocio: $ 0 de $ 100.000. Te quedan $ 100.000.

  Sin presupuestos, el total es "Gastado: $ X. Sin presupuesto.". Sin
  categorías que mostrar: "No hay gastos ni presupuesto este mes."
  [RF-6, RF-7]
- `expense_text(expense, category_name, today)`: "$ 20.000 · Comida · ayer,
  30 de octubre · Mercado". [RF-9, RF-12]
- `recent_text(space_name, expenses, names, my_id, today)`: la lista
  numerada; cada gasto de otro miembro termina en "· de otro miembro".
  [RF-9 a RF-11]

### Periodos (`bot/parsing.py`)

`shift_period("2026-01", -1) == "2025-12"`: suma o resta meses a un
periodo `AAAA-MM`. [RF-8]

### Conversación (`bot/conversation.py`)

- `/resumen`: con un espacio, muestra el resumen del mes actual en `TZ`;
  con varios, botones `sum:<espacio>:<mes actual>`. Cada resumen trae
  `‹ <mes anterior>` y `<mes siguiente> ›` como `sum:<espacio>:<mes>`.
  [RF-5 a RF-8]
- `/ultimos`: con un espacio, la lista; con varios, botones
  `last:<espacio>`. Pide categorías y `GET /me` para los nombres y la
  marca. [RF-9 a RF-11]
- `/deshacer`: `recent?limit=1&mine=true` en cada espacio, elige el de
  `created_at` mayor y muestra "¿Borro este gasto?" con el espacio y los
  botones `undo:<espacio>:<gasto>` y `undo:no`. [RF-12 a RF-16]
- Estos botones se atienden antes de mirar el borrador del gasto, y no lo
  tocan. [RF-18]
- Un chat no vinculado corta en la primera llamada con `NotLinked`, como en
  la 005. [RF-17]

### Adaptador (`bot/telegram_app.py`)

- `COMMANDS` suma `resumen`, `ultimos` y `deshacer`.
- `MENU`: pares (comando, descripción) en español. `post_init` los
  registra con `set_my_commands`; un `TelegramError` se registra como aviso
  y no impide arrancar. [RF-20]

## Tests

- **API**: criterio 1 en `test_expenses.py` (con el reloj de registro
  controlado para que el orden no dependa de milisegundos) y la ruta nueva
  en el criterio de aislamiento de `test_isolation.py`.
- **Bot**:
  - `test_views.py`: criterio 2 y los textos de `/ultimos`.
  - `test_parsing.py`: `shift_period`.
  - `test_api.py`: las rutas nuevas y `NotFound`.
  - `test_conversation.py`: criterios 3 a 8, con la API falsa ampliada.
  - `test_telegram_app.py`: comandos y menú.

## Riesgos y temas abiertos

- **`/deshacer` hace una llamada por espacio.** Con pocos espacios no
  importa; si un usuario llegara a decenas, convendría una ruta propia.
- **Un botón de Borrar viejo sigue sirviendo** (decisión 6): borra el gasto
  exacto que mostró, y solo si sigue existiendo. Es lo que se confirmó al
  tocarlo.
- **El menú de comandos se registra en cada arranque**: es idempotente, pero
  es una llamada a Telegram más al iniciar.

## Conceptos nuevos

- [`set_my_commands`](https://core.telegram.org/bots/api#setmycommands) — el menú de comandos que Telegram muestra al escribir `/`.
- [`callback_data`](https://core.telegram.org/bots/api#inlinekeyboardbutton) — hasta 64 bytes que el botón devuelve al bot al tocarlo.
- [Orden de las rutas en FastAPI](https://fastapi.tiangolo.com/tutorial/path-params/#order-matters) — por qué una ruta fija va antes que una con parámetro.
