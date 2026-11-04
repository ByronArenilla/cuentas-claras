# Tareas 003 — API de gastos

- Spec: `spec.md` (aprobada) · Plan: `plan.md` (aprobado)
- Regla: una tarea por vez, primero los tests y luego el código. Al
  terminarla, marcarla, ejecutar `make test` y `make lint`, y detenerse.

## [x] T1 — Reloj, periodos y `TZ` válida
`app/dates.py` con `now()`, `today()`, `period_of()` y `period_bounds()`.
`config.py` comprueba que `ZoneInfo(TZ)` funcione y, si no, falla al
arrancar nombrando la variable.

- Test primero:
  - `test_dates.py`: `period_bounds` de febrero de 2026 (28 días), febrero
    de 2028 (29), abril (30), octubre (31) y diciembre (el siguiente es
    enero del año siguiente).
  - `period_bounds` rechaza con `ValueError` `2026-13`, `2026-00`,
    `2026-1`, `26-10`, `2026-10-01` y `octubre`.
  - `period_of(date(2026, 10, 31))` es `"2026-10"`.
  - Con `dates.now` fijado en el 1 de noviembre de 2026 a la 01:00 UTC,
    `today()` es el 31 de octubre en `America/Bogota`.
  - `test_config.py`: `TZ=Marte/Olimpo` impide cargar la configuración y el
    error nombra `TZ`.
- Hecho cuando: los tests pasan sin HTTP y el resto de la suite sigue en
  verde.
- RF: base de RF-2, RF-6, RF-9, RF-10 y RF-11; principio 7.

## [x] T2 — Modelo `Expense`
`app/models.py`: la tabla `expenses` como la describe el plan
(`space_id` con `ON DELETE CASCADE`, `category_id` sin `ON DELETE`,
`created_by`, `amount` `BigInteger`, `payment_type`, `spent_on` `Date`,
`description` `String(200)`, `created_at`), las dos `CheckConstraint` y
el índice sobre (`space_id`, `spent_on`).

- Test primero (`test_models.py`):
  - Un gasto válido se guarda y se lee con `spent_on` como `date` y
    `created_at` en UTC.
  - La base de datos rechaza `amount` `0` y negativo, y un `payment_type`
    distinto de `credit` o `debit`.
  - Se guarda un monto de un billón (`1_000_000_000_000`).
  - Borrar un espacio con gastos y categorías no choca con la clave foránea
    de `category_id` y borra sus gastos, pero no los de otro espacio.
- Hecho cuando: los tests pasan con la base de datos en memoria del
  `conftest.py`.
- RF: base de RF-1, RF-3, RF-4 y RF-21.

## [x] T3 — Esquemas de gastos
`schemas.py`: `ExpenseIn`, `ExpensePatch` y `ExpenseOut`, con las
validaciones compartidas de la tabla del plan y mensajes en español.

- Test primero (en `test_expenses.py`, validando los esquemas sin HTTP):
  - `amount`: se rechazan `20000.0`, `"20000"`, `true`, `0`, `-1` y
    `1_000_000_000_001`, y se acepta `1_000_000_000_000`. El mensaje del
    tope indica el máximo.
  - `payment_type`: se rechaza `"efectivo"` y el mensaje nombra `credit` y
    `debit`.
  - `spent_on`: con el reloj fijado, se acepta hoy y se rechaza mañana. Sin
    `spent_on`, `ExpenseIn` usa `today()`.
  - `description`: `"  café  "` pasa a `"café"`, y `""` o solo espacios
    pasan a `None`. 201 caracteres se rechazan con el límite.
  - `ExpensePatch`: un campo no enviado no aparece en `model_fields_set`;
    `"description": null` sí aparece y vale `None`; `null` en `amount`,
    `payment_type`, `category_id` o `spent_on` se rechaza.
  - `space_id` y `created_by` en la entrada se ignoran.
- Hecho cuando: los tests pasan.
- RF: RF-3, RF-4, RF-6, RF-7; base de RF-13 y RF-14.

## [ ] T4 — Registrar gastos
`app/routers/expenses.py` con `POST /spaces/{space_id}/expenses`,
`member_space`, la comprobación de la categoría por `id` y `space_id`, y
el router montado en `main.py`.

- Test primero:
  - Registrar un gasto válido responde `201` con todos los campos de
    `ExpenseOut`, incluido `created_by`, el `id` de quien lo registró.
  - Criterio 4: con el reloj fijado el 31 de octubre de 2026 a las 20:00
    en Bogotá, un gasto sin fecha se guarda con `spent_on` `2026-10-31`.
  - Una categoría de otro espacio y una inexistente responden `422` "La
    categoría no existe en este espacio." y no se crea nada.
  - Criterio 5: cada monto inválido de T3 responde `422` y no guarda nada.
  - Sin sesión, `401`.
- Hecho cuando: los tests pasan y el test que recorre las rutas con
  `{space_id}` sigue en verde con la ruta nueva.
- RF: RF-1, RF-2, RF-3, RF-5, RF-6, RF-7.

## [ ] T5 — Consultar y listar
`GET /spaces/{space_id}/expenses/{expense_id}`, con la dependencia
`space_expense`, y `GET /spaces/{space_id}/expenses?period=YYYY-MM`.

- Test primero:
  - Un gasto se consulta con todos sus campos.
  - Un `expense_id` inexistente responde `404` "Gasto no encontrado.".
  - El listado de `2026-10` incluye los gastos del 1 y del 31 de octubre y
    excluye los del 30 de septiembre y el 1 de noviembre.
  - El orden es por `spent_on` descendente y, a igual día, el registrado
    después va primero.
  - Sin `period`, con el reloj fijado, se usa el mes actual en `TZ`.
  - `period=2026-13` y `period=octubre` responden `422` con el formato
    esperado.
  - Parte del criterio 3: dos miembros del mismo espacio reciben la misma
    lista.
- Hecho cuando: los tests pasan.
- RF: RF-8, RF-9, RF-10, RF-11; parte de RF-12.

## [ ] T6 — Editar gastos
`PATCH /spaces/{space_id}/expenses/{expense_id}` aplicando solo
`model_fields_set`, con las mismas validaciones y la misma comprobación de
categoría que al registrar.

- Test primero:
  - Cambiar solo `amount` deja el resto de campos igual.
  - `"description": null` y `""` quitan la descripción; no enviarla la
    deja como estaba.
  - Un cuerpo vacío no cambia nada y responde `200`.
  - Un monto inválido, una fecha futura o una categoría de otro espacio
    responden como al registrar y no cambian nada.
  - Enviar `space_id` o `created_by` no cambia el espacio ni el autor.
  - Criterio 3: Bea edita el gasto que registró Ana y el autor sigue siendo
    Ana.
- Hecho cuando: los tests pasan.
- RF: RF-13, RF-14, RF-15.

## [ ] T7 — Borrar gastos
`DELETE /spaces/{space_id}/expenses/{expense_id}?confirm=true`.

- Test primero:
  - Con `confirm=true`, `204`, y el gasto ya no se consulta ni se lista.
  - Sin `confirm` o con `confirm=false`, `400` con el mensaje del plan, y
    el gasto sigue.
  - Borrar un gasto no toca los demás gastos del espacio ni sus categorías.
  - Cualquier miembro borra el gasto que registró otro.
- Hecho cuando: los tests pasan.
- RF: RF-15, RF-16, RF-17, RF-18.

## [ ] T8 — Aislamiento y ciclo de vida con gastos
`test_isolation.py`: amplía los criterios de aislamiento con gastos reales
y actualiza su docstring. Si T4 a T7 están bien hechas, no debería hacer
falta código nuevo; si algún test falla, se corrige en esta tarea.

- Test primero:
  - Criterio 1: Ana y Bea, en espacios distintos, no pueden consultar,
    listar, editar ni borrar el gasto de la otra, y todo responde `404`.
  - Criterio 2: Ana, miembro de dos espacios, pide el gasto del espacio A
    por la ruta del espacio B y recibe `404` en las cuatro operaciones.
  - Criterio 6: borrar un espacio borra sus gastos y no toca los de otro
    espacio del mismo usuario.
  - Criterio 7: tras salir Bea de un espacio, los gastos que registró
    siguen en la lista de Ana con `created_by` de Bea.
- Hecho cuando: los tests pasan.
- RF: RF-12, RF-19, RF-20, RF-21.

## [ ] T9 — ADR 0007: la fecha del gasto es un día calendario
`docs/adr/0007-fecha-del-gasto-como-dia-calendario.md` con la plantilla
`0000-plantilla.md`. Explica cómo se cumple el principio 7 con un día sin
hora ni zona (los instantes van en UTC y "hoy" se calcula en `TZ`), por
qué se descartó guardar un instante en UTC y que cambiar `TZ` no mueve
gastos de mes.

- Test primero: no aplica, es documentación.
- Hecho cuando: el ADR existe y el plan lo cita.
- RF: ninguno; principios 4 y 7.

## [ ] T10 — Cierre: README y validación
- Comprobar que `make run-api` crea la tabla `expenses` en la base de datos
  local sin borrar los datos que ya tiene. Esta vez no se borra nada
  (plan, "Base de datos local").
- `README.md`: sección de gastos con ejemplos `curl` de registrar, listar
  por periodo, editar y borrar con confirmación.
- Repasar los ocho criterios de validación de la spec.
- `docs/roadmap.md`: marcar `003-api-gastos` como terminada y dejar
  `004-presupuesto-mensual` como spec activa.

- Test primero: no aplica, es documentación y validación.
- Hecho cuando: `make test` y `make lint` están en verde y los ejemplos
  `curl` del README funcionan contra `make run-api`.
- RF: ninguno nuevo; cierra la spec.
