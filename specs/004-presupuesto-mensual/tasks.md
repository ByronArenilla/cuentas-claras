# Tareas 004 — Presupuesto mensual

- Spec: `spec.md` (aprobada) · Plan: `plan.md` (aprobado)
- Regla: una tarea por vez, primero los tests y luego el código. Al
  terminarla, marcarla, ejecutar `make test` y `make lint`, y detenerse.

## [x] T1 — Modelo `Budget`
`app/models.py`: la tabla `budgets` como la describe el plan (`space_id`
con `ON DELETE CASCADE`, `category_id` sin `ON DELETE`, `starts_on` `Date`,
`amount` `BigInteger` nulo, `updated_at`), la `CheckConstraint` y la
`UniqueConstraint(space_id, category_id, starts_on)`.

- Test primero (`test_models.py`):
  - Un presupuesto válido se guarda y se lee con `starts_on` como `date`.
  - Se guarda con `amount` nulo y con un billón (`1_000_000_000_000`).
  - La base de datos rechaza `amount` `0` y negativo.
  - Dos filas con el mismo espacio, categoría y `starts_on` chocan; el
    mismo `starts_on` en otra categoría o en otro espacio, no.
  - Borrar un espacio con categorías, gastos y presupuestos no choca con
    las claves foráneas, borra sus presupuestos y no toca los de otro
    espacio.
- Hecho cuando: los tests pasan con la base de datos en memoria del
  `conftest.py`.
- RF: base de RF-5, RF-6, RF-7 y RF-20.

## [x] T2 — Esquemas de presupuesto y resumen
`schemas.py`: `BudgetIn`, `BudgetOut` y `SummaryOut` (con sus filas por
categoría y sus totales), con mensajes en español.

- Test primero (en `test_budgets.py`, validando los esquemas sin HTTP):
  - `amount`: se rechazan `400000.0`, `"400000"`, `true`, `0`, `-1` y
    `1_000_000_000_001`; se aceptan `1_000_000_000_000` y `null`.
  - Un cuerpo sin `amount` se rechaza.
  - `period`: se rechazan `2026-13`, `2026-1` y `octubre` con el mensaje del
    formato; se aceptan `1990-01` y `2030-12`.
  - Sin `period`, con el reloj fijado el 31 de octubre de 2026 a las 20:00
    en Bogotá, `BudgetIn` usa `2026-10`.
- Hecho cuando: los tests pasan.
- RF: RF-2, RF-7, RF-8, RF-10; base de RF-6 y RF-16.

## [x] T3 — Cálculo de vigencia y resumen sin HTTP
`app/summary.py` con `effective_budgets`, `spent_by_category` y
`build_summary`, como los describe el plan.

- Test primero (`test_summary.py`, con la sesión del `conftest.py`):
  - Criterio 1: con 400.000 desde `2026-09`, `2026-08` no tiene presupuesto
    y `2026-09` a `2026-12` tienen 400.000. Con 500.000 desde `2026-11`,
    septiembre y octubre siguen en 400.000, y noviembre y diciembre pasan
    a 500.000.
  - Criterio 2: con una fila nula desde `2026-12`, diciembre en adelante
    queda sin presupuesto y noviembre sigue en 500.000.
  - Criterio 3: con gastos del 30 de septiembre, el 1 y el 31 de octubre y
    el 1 de noviembre, lo gastado en `2026-10` solo suma los dos de
    octubre.
  - `build_summary` devuelve todas las categorías en orden de creación,
    con gastado `0` las que no tienen gastos, `remaining` negativo en una
    excedida y nulo en una sin presupuesto.
  - Los totales suman lo gastado de todas las categorías, también las que
    no tienen presupuesto; sin ningún presupuesto, el total presupuestado y
    el que queda son nulos.
  - Ninguna función cuenta gastos ni presupuestos de otro espacio.
  - Todos los montos del resumen son `int`.
- Hecho cuando: los tests pasan sin HTTP.
- RF: RF-3, RF-4, RF-6, RF-11 a RF-14, RF-16, RF-18.

## [x] T4 — Fijar y quitar el presupuesto
`app/routers/budgets.py` con `PUT /spaces/{space_id}/budgets/{category_id}`,
`member_space`, la búsqueda de la categoría por `id` y `space_id`, el
"buscar y actualizar, o insertar" con su reintento ante `IntegrityError`,
y el router montado en `main.py`.

- Test primero (`test_budgets.py`):
  - Fijar un presupuesto válido responde `200` con `category_id`, `period`
    y `amount`.
  - Fijar dos veces la misma categoría desde el mismo periodo deja una sola
    fila con el último monto.
  - `"amount": null` responde `200` y la categoría queda sin presupuesto
    desde ese periodo; los gastos no cambian.
  - Fijar un presupuesto desde un periodo pasado y desde uno futuro
    funciona.
  - Una categoría inexistente o de otro espacio responde `404` "Categoría
    no encontrada." y no se guarda nada.
  - Criterio 5: cada monto inválido de T2 y un cuerpo `{}` responden `422`
    y no guardan ni quitan nada.
  - Parte del criterio 4: con el reloj fijado, un presupuesto sin periodo
    rige desde `2026-10`.
  - Sin sesión, `401`.
- Hecho cuando: los tests pasan y el test que recorre las rutas con
  `{space_id}` sigue en verde con la ruta nueva.
- RF: RF-1, RF-2, RF-5 a RF-10.

## [x] T5 — Resumen del periodo
`requested_period` en `app/deps.py`, el listado de gastos usándola, y
`GET /spaces/{space_id}/summary?period=YYYY-MM` llamando a `build_summary`.

- Test primero (`test_budgets.py`):
  - El resumen responde `200` con la forma de `SummaryOut` del plan.
  - Criterios 1 y 2 de punta a punta: fijar y quitar con `PUT` y leer el
    resultado con el resumen de cada mes.
  - Parte del criterio 4: sin `period`, con el reloj fijado, el resumen es
    el de `2026-10`.
  - `period=2026-13` y `period=octubre` responden `422` con el mismo
    mensaje que el listado de gastos.
  - Criterio 8: dos miembros reciben el mismo resumen, y Bea cambia el
    presupuesto que fijó Ana.
  - Los tests de `test_expenses.py` siguen en verde sin tocarlos.
- Hecho cuando: los tests pasan.
- RF: RF-11 a RF-16.

## [x] T6 — Aislamiento y ciclo de vida con presupuestos
`test_isolation.py`: amplía los criterios de aislamiento con presupuestos
y resúmenes, y actualiza su docstring. Si T4 y T5 están bien hechas, no
debería hacer falta código nuevo; si algún test falla, se corrige en esta
tarea.

- Test primero:
  - Criterio 6: Ana y Bea, en espacios distintos, no pueden fijar
    presupuestos ni pedir el resumen del espacio de la otra, todo responde
    `404`, y los gastos y presupuestos de una no aparecen en el resumen de
    la otra.
  - Criterio 7: Ana, miembro de dos espacios, fija el presupuesto de una
    categoría del espacio B por la ruta del espacio A y recibe `404`.
  - Criterio 9: borrar un espacio borra sus presupuestos y no toca los de
    otro espacio del mismo usuario; tras salir Bea de un espacio, sus
    presupuestos siguen en el resumen de Ana.
- Hecho cuando: los tests pasan.
- RF: RF-9, RF-17, RF-18, RF-19, RF-20.

## [x] T7 — ADR 0008: el presupuesto rige desde un periodo
`docs/adr/0008-presupuesto-vigente-desde-un-periodo.md` con la plantilla
`0000-plantilla.md`. Explica que se guarda una fila por cambio y no una por
mes, que quitar el presupuesto es una fila sin monto y no un borrado, por
qué se descartaron el presupuesto por mes y copiar el del mes anterior, y
la consecuencia de que cambiar un mes pasado cambia también los que lo
heredan.

- Test primero: no aplica, es documentación.
- Hecho cuando: el ADR existe y el plan lo cita.
- RF: ninguno; principio 4 y decisión 1.

## [ ] T8 — Cierre: README y validación
- Comprobar que `make run-api` crea la tabla `budgets` en la base de datos
  local sin borrar los datos que ya tiene (plan, "Base de datos local").
- `README.md`: sección de presupuesto con ejemplos `curl` de fijar,
  quitar y pedir el resumen, y una frase que explique que el presupuesto
  rige desde ese mes en adelante.
- Repasar los diez criterios de validación de la spec.
- `docs/roadmap.md`: marcar `004-presupuesto-mensual` como terminada y dejar
  `005-bot-registro-guiado` como spec activa.

- Test primero: no aplica, es documentación y validación.
- Hecho cuando: `make test` y `make lint` están en verde y los ejemplos
  `curl` del README funcionan contra `make run-api`.
- RF: ninguno nuevo; cierra la spec.
