# Tareas 006 — Bot: consultas y deshacer

- Spec: `spec.md` (aprobada) · Plan: `plan.md` (aprobado)
- Regla: una tarea por vez, primero los tests y luego el código. Al
  terminarla, marcarla, ejecutar `make test` y `make lint`, y detenerse.

## [x] T1 — API: últimos gastos registrados
`GET /spaces/{space_id}/expenses/recent` en `app/routers/expenses.py`,
declarada antes de `/{expense_id}`.

- Test primero (`test_expenses.py` y `test_isolation.py`):
  - Criterio 1: con gastos de dos miembros, uno de ellos de septiembre
    registrado al final, la ruta devuelve los cinco últimos por momento de
    registro, con el de septiembre primero.
  - `limit=2` devuelve dos; `limit=0` y `limit=21` responden `422`.
  - `mine=true` devuelve solo los de quien llama.
  - No aparecen gastos de otro espacio, y un espacio ajeno responde `404`.
  - `GET /spaces/{id}/expenses/{expense_id}` sigue funcionando.
- Hecho cuando: los tests pasan y el test que recorre las rutas con
  `{space_id}` sigue en verde.
- RF: RF-1 a RF-4.

## [x] T2 — Cliente: rutas nuevas
`bot/api.py`: `me`, `recent_expenses`, `delete_expense` y `NotFound`.

- Test primero (`test_api.py`):
  - `recent_expenses` envía `limit` y `mine`.
  - `delete_expense` envía `confirm=true` y un `404` es `NotFound`.
  - `me` devuelve el usuario.
- Hecho cuando: los tests pasan sin red.
- RF: base de RF-10, RF-12 y RF-15.

## [x] T3 — Textos y periodos
`bot/views.py` y `shift_period` en `bot/parsing.py`. La línea de
presupuesto de la 005 pasa a usar `remaining_text`.

- Test primero (`test_views.py`, `test_parsing.py`):
  - Criterio 2: el texto del resumen con una categoría excedida, una
    dentro, una sin presupuesto con gastos y una sin nada, que no aparece.
  - Totales sin presupuesto, y mes sin nada que mostrar.
  - `expense_text` con y sin descripción.
  - `recent_text` marca el gasto de otro miembro y dice si no hay gastos.
  - `shift_period` hacia atrás y hacia adelante, cruzando de año.
  - Los tests de la línea de presupuesto de la 005 siguen en verde.
- Hecho cuando: los tests pasan.
- RF: RF-6, RF-7, RF-9 a RF-11.

## [ ] T4 — `/resumen`
- Test primero (`test_conversation.py`):
  - Con un espacio, el resumen del mes actual en `TZ` (con el reloj del 31
    de octubre a las 20:00 en Bogotá, es octubre).
  - Criterio 4: con dos espacios, primero los botones de espacio.
  - Criterio 3: ‹ y › piden el mes anterior y el siguiente del mismo
    espacio, también de enero a diciembre del año anterior.
  - Criterio 7: `/resumen` y sus botones en mitad de un gasto no lo
    descartan.
- Hecho cuando: los tests pasan.
- RF: RF-5 a RF-8, RF-18.

## [ ] T5 — `/ultimos`
- Test primero:
  - Con un espacio, la lista; con dos, primero los botones (criterio 4).
  - Criterio 5: marca el gasto de otro miembro; un espacio vacío lo dice.
- Hecho cuando: los tests pasan.
- RF: RF-9 a RF-11.

## [ ] T6 — `/deshacer`
- Test primero:
  - Criterio 6: con dos espacios propone el gasto propio más reciente de
    cualquiera de ellos, con su espacio; Cancelar no borra; Borrar borra
    solo ese; un segundo Borrar dice que ya no existe.
  - Sin gastos propios, dice que no hay nada que deshacer.
  - No se llama a borrar antes de tocar Borrar.
- Hecho cuando: los tests pasan.
- RF: RF-12 a RF-16.

## [ ] T7 — Comunes: chat no vinculado, API caída, ayuda y menú
- Test primero:
  - Criterio 8: los tres comandos en un chat no vinculado dan las
    instrucciones.
  - Con la API caída, los tres comandos lo avisan.
  - La ayuda nombra los tres comandos.
  - `test_telegram_app.py`: hay un manejador por comando nuevo, `MENU`
    tiene solo comandos de `COMMANDS` y `post_init` está configurado.
- Hecho cuando: los tests pasan.
- RF: RF-17, RF-19, RF-20.

## [ ] T8 — Cierre: README, roadmap y validación
- `README.md`: `/resumen`, `/ultimos` y `/deshacer` en la sección del bot,
  y que el menú se registra solo.
- Repasar los nueve criterios de validación.
- `docs/roadmap.md`: marcar la 006 y dejar la 007 activa.

- Test primero: no aplica.
- Hecho cuando: `make test` y `make lint` están en verde.
- RF: ninguno nuevo; cierra la spec.
