# Tareas 008 — Rubros e ingresos del mes

- Spec: `spec.md` (aprobada) · Plan: `plan.md` (aprobado)
- Regla: una tarea por vez, primero los tests y luego el código. Al
  terminarla, marcarla, ejecutar `make test` y `make lint`, y detenerse.
- Orden: primero las migraciones (T1), después expandir el esquema (T2), el
  código nuevo (T3 a T9), contraer el esquema (T10) y cerrar (T11 a T13).
  Cada tarea deja la API funcionando.

## [x] T1 — Alembic y migración inicial
`alembic` en `pyproject.toml`; `alembic.ini`; `app/migrations/` con
`env.py` (conexión compartida, `render_as_batch=True`) y la migración
`0001_baseline` idempotente, que también borra las tablas de Telegram;
`run_migrations` en `app/db.py` y el `lifespan` usándola en lugar de
`create_all`. `conftest.py` crea las tablas con `Base.metadata.create_all`.

- Test primero (`test_migrations.py`):
  - Una base vacía migrada a `head` coincide con `Base.metadata` según
    `compare_metadata` (en este punto, el esquema de la 007).
  - Migrar dos veces no cambia nada.
  - Una base de la 007 creada con `create_all`, sin `alembic_version` y con
    las tablas de Telegram con una fila cada una, queda en `head`, conserva
    usuarios, espacios, categorías, gastos y presupuestos, y ya no tiene
    tablas de Telegram.
  - Una base sin `budgets` (de la 003) queda en `head` con `budgets` creada.
  - Si una migración falla, `run_migrations` propaga el error.
- `test_retired_bot.py`: el criterio 4 de la 007 se quita (lo reemplaza el
  test de Telegram de arriba) y el 5 se comprueba sobre `Base.metadata`.
- Hecho cuando: los tests pasan, el resto sigue en verde, y `make run-api`
  arranca sobre una **copia** de la base local y la deja en `0001`.
- RF: RF-31, RF-32, RF-34, RF-37; base de RF-36.

## [x] T2 — Modelos de rubros, ingresos y categorías eliminadas (expandir)
`BudgetItem`, `Income`, `Expense.budget_item_id` y `Category.deleted_at` en
`models.py`, como los describe el plan, y la migración
`0002_budget_items_and_incomes`.

- Test primero (`test_models.py` y `test_migrations.py`):
  - Un rubro y un ingreso válidos se guardan con `period_start` como `date`
    y `name_key` rellenada.
  - La base de datos rechaza montos `0` y negativos.
  - Dos rubros con nombres equivalentes en el mismo espacio y mes chocan;
    en otro mes o en otro espacio, no. Lo mismo con los ingresos.
  - Un gasto se guarda con y sin `budget_item_id`.
  - Una categoría se guarda con `deleted_at` nulo por defecto.
  - Borrar un espacio con rubros, ingresos y gastos ligados a rubros no
    choca con las claves foráneas y no toca otro espacio.
  - Tras la `0002`, las categorías que ya existían quedan activas, y
    `compare_metadata` sigue sin diferencias.
- Hecho cuando: los tests pasan y ninguna ruta cambió de comportamiento.
- RF: base de RF-3, RF-4, RF-10, RF-30, RF-36 y RF-39.

## [x] T3 — Eliminar y restaurar categorías
`DELETE /spaces/{space_id}/categories/{category_id}`; el listado sin
eliminadas; `POST /categories` restaurando una eliminada; `check_category`
rechazando una eliminada con su propio mensaje.

- Test primero (`test_categories.py` y `test_expenses.py`):
  - Eliminar responde `200` con `id`, `name` y el aviso de que se puede
    volver a usar creándola de nuevo, y la categoría deja de salir en el
    listado.
  - Los gastos que la tenían siguen iguales, con la misma categoría.
  - Un gasto nuevo con la categoría eliminada, o cambiar a ella la de un
    gasto, responde `422` "La categoría «Mascotas» fue eliminada…"; editar
    otro campo de un gasto que ya la tiene funciona.
  - Criterio 14: eliminar una categoría ya eliminada, de otro espacio o
    inexistente responde `404`; las predefinidas se pueden eliminar.
  - Crear "mascotas" con "Mascotas" eliminada responde `200` con el mismo
    `id` y el nombre "Mascotas", y vuelve a salir en el listado. Crear el
    nombre de una activa sigue respondiendo `409`.
  - Criterio 15: con "Acción" eliminada, crear "accion", "Accion" o
    "ACCIÓN" la restaura como "Acción"; con "Ahorro" activa, "ahorro"
    responde `409`; "Año" y "Ano" conviven.
  - Los tests de la 002 siguen en verde.
- Hecho cuando: los tests pasan.
- RF: RF-39 a RF-41, RF-43, RF-44; decisiones 22 y 23.

## [x] T4 — Esquemas y `previous_period`
`schemas.py`: `BudgetItemIn`, `BudgetItemPatch`, `BudgetItemOut`,
`IncomeIn`, `IncomePatch`, `IncomeOut` y `PlanCopyIn`. `dates.py`:
`previous_period`.

- Test primero (validando sin HTTP):
  - Nombres: se guardan sin espacios alrededor; vacío, solo espacios o de
    51 caracteres se rechazan.
  - Criterio 7: montos `800000.0`, `"800000"`, `true`, `0`, `-1` y
    `1_000_000_000_001` se rechazan en rubros e ingresos; un billón se
    acepta.
  - Sin `period`, con el reloj fijado el 31 de octubre de 2026 a las 20:00
    en Bogotá, se usa `2026-10`. `2026-13` se rechaza con el mensaje del
    formato.
  - Los `Patch` rechazan `null` y no tienen `period`.
  - `previous_period`: `2026-11` → `2026-10`, `2026-01` → `2025-12`.
- Hecho cuando: los tests pasan.
- RF: RF-2, RF-3, RF-4, RF-6, RF-10, RF-11; base de RF-13.

## [ ] T5 — Rutas de rubros
`app/routers/budget_items.py` con `POST`, `PATCH` y `DELETE`, montado en
`main.py`.

- Test primero (`test_budget_items.py`):
  - Crear responde `201` con `BudgetItemOut`; un periodo pasado y uno futuro
    funcionan.
  - Criterio 2: "mercado" choca con "Mercado" y "accion" con "Acción"
    (`409`, nombrando el que existe); en otro mes, no.
  - Una categoría de otro espacio responde `422` y no guarda nada; una
    eliminada, `422` con su mensaje, al crear y al cambiar la categoría.
  - Editar cambia solo lo enviado; el periodo no se puede cambiar. Un rubro
    con categoría eliminada acepta cambios de nombre y monto.
  - Criterio 5 (con gastos creados directamente en la base, porque la ruta
    de gastos aún no acepta rubros): cambiar la categoría del rubro cambia
    la de sus gastos; borrarlo responde `204` y sus gastos quedan sin rubro,
    con la misma categoría, monto y fecha.
  - Un rubro inexistente o de otro espacio responde `404` "Rubro no
    encontrado." al editar y al borrar.
  - Sin sesión, `401`.
- Hecho cuando: los tests pasan y el test que recorre las rutas con
  `{space_id}` sigue en verde.
- RF: RF-1 a RF-9, RF-41, RF-42.

## [ ] T6 — Rutas de ingresos
`app/routers/incomes.py` con `POST`, `PATCH` y `DELETE`, montado en
`main.py`.

- Test primero (`test_incomes.py`):
  - Crear responde `201` con `IncomeOut`; "salario" choca con "Salario" y
    "bonificacion" con "Bonificación" en el mismo mes (`409`), y no en
    otro.
  - Editar cambia solo lo enviado; borrar responde `204` sin confirmación.
  - Un ingreso inexistente o de otro espacio responde `404` "Ingreso no
    encontrado.".
  - Sin sesión, `401`.
- Hecho cuando: los tests pasan.
- RF: RF-10 a RF-12.

## [ ] T7 — Gastos con rubro
`ExpenseIn`, `ExpensePatch` y `ExpenseOut` con `budget_item_id`, y las
rutas de gastos con las reglas de "Editar un gasto" del plan.

- Test primero (`test_expenses.py`):
  - Registrar con rubro guarda la categoría del rubro y devuelve
    `budget_item_id`; con categoría, `budget_item_id` es nulo.
  - Criterio 4: con los dos o con ninguno, `422`; un gasto del 3 de
    noviembre con un rubro de octubre, `422` con los dos periodos; cambiar
    la fecha de un gasto planeado a otro mes, `422`.
  - Un rubro de otro espacio responde `422` "El rubro no existe en este
    espacio.", aunque quien llama sea miembro de los dos.
  - Un rubro cuya categoría se eliminó acepta gastos de su mes (RF-42).
  - Editar: ligar a otro rubro cambia la categoría; `budget_item_id: null`
    lo deja no planeado con su categoría o con la enviada; cambiar solo la
    categoría de un gasto planeado, `422`.
  - El listado por periodo y los últimos registrados traen
    `budget_item_id`.
  - Los tests que ya existían siguen en verde; solo cambian las aserciones
    que comparan el gasto entero.
- Hecho cuando: los tests pasan.
- RF: RF-17 a RF-22, RF-42.

## [ ] T8 — Resumen nuevo
`app/summary.py` reescrito (`spent_by_item`, `build_summary`) con el
`SummaryOut` nuevo; `app/routers/plan.py` con `GET /summary`. Sale
`app/routers/budgets.py` y con él el `PUT` de la 004.

- Test primero (`test_summary.py` sin HTTP y `test_plan.py`):
  - Criterio 1: cada fila y cada total con rubros, ingresos, gastos
    planeados y no planeados, un rubro excedido y un mes con sin asignar
    negativo.
  - Una categoría eliminada sale, marcada, en los meses donde tiene rubros
    o gastos, y no sale en los demás.
  - Un mes sin plan sale con listas vacías y montos en `0`, y no crea nada.
  - Los gastos del 30 de septiembre y del 1 de noviembre no cuentan en
    octubre.
  - Todos los montos son `int`.
  - Sin `period`, con el reloj fijado, el resumen es el de `2026-10`;
    `period=2026-13` responde `422`.
  - Criterio 11: `PUT /spaces/{id}/budgets/{category_id}` responde `404`.
  - Salen de `test_budgets.py` y `test_summary.py` los tests del
    presupuesto de la 004; los de validación del monto y del periodo ya
    los cubre T4.
- Hecho cuando: los tests pasan.
- RF: RF-23 a RF-27, RF-40.

## [ ] T9 — Copiar el plan
`app/plan.py` con `copy_previous_plan` y `POST /plan/copy` en
`app/routers/plan.py`.

- Test primero (`test_plan.py`):
  - Criterio 3: copiar noviembre a diciembre crea los mismos rubros e
    ingresos con los mismos montos, en el mismo orden, y responde `201` con
    el resumen de diciembre y `skipped` vacío; noviembre y sus gastos no
    cambian.
  - Copiar otra vez a diciembre responde `409` "2026-12 ya tiene un plan;
    no se copió nada." y no crea nada; también si diciembre solo tiene un
    ingreso.
  - Copiar a enero con diciembre vacío responde `409` "2026-12 no tiene un
    plan para copiar.". Lo mismo si diciembre solo tiene rubros de
    categorías eliminadas.
  - Un rubro de una categoría eliminada no se copia y sale en `skipped` con
    su nombre y su categoría.
  - Criterio 6: sin `period`, con el reloj fijado, copia de `2026-09` a
    `2026-10`.
  - Si el `INSERT` choca con el índice único (otra copia a la vez), la
    ruta responde `409` y no queda ninguna fila a medias.
  - Criterio 13 de punta a punta: eliminar "Mascotas", copiar, restaurarla
    y comprobar que desde entonces sus rubros se copian de nuevo.
- Hecho cuando: los tests pasan.
- RF: RF-13 a RF-16, RF-43.

## [ ] T10 — Retirar el presupuesto de la 004 (contraer)
Migración `0003_budgets_to_budget_items`; salen `Budget`, `BudgetIn`,
`BudgetOut` y sus tests de modelo.

- Test primero (`test_migrations.py`):
  - Criterio 8: una base en `0002` con un presupuesto de Comida de 400.000
    desde `2026-09`, otro que lo quita desde `2026-12`, y gastos; tras
    `head` hay un rubro "Comida" de 400.000 en `2026-09` con la categoría
    Comida, ninguno en `2026-12`, los gastos siguen iguales y sin rubro, y
    la tabla `budgets` ya no existe.
  - Usuarios, espacios, membresías, invitaciones, sesiones, categorías y
    gastos tienen las mismas filas antes y después (RF-35).
  - `compare_metadata` sigue sin diferencias (RF-36).
- Hecho cuando: los tests pasan y `grep -rn "Budget\b\|budgets"` en
  `app/` solo encuentra la migración `0003` y la `0001`.
- RF: RF-33, RF-35, RF-36.

## [ ] T11 — Aislamiento y ciclo de vida
`test_isolation.py`: amplía los criterios con rubros, ingresos, la copia,
el resumen y la eliminación de categorías. Si T3 a T9 están bien hechas, no
debería hacer falta código nuevo; si algún test falla, se corrige aquí.

- Test primero:
  - Criterio 12: Ana y Bea, en espacios distintos, no pueden crear, editar,
    borrar ni copiar rubros o ingresos de la otra, ni eliminar sus
    categorías; todo responde `404` y nada de una aparece en el resumen de
    la otra.
  - Un rubro del espacio B no sirve para un gasto del espacio A aunque
    quien llama sea miembro de los dos.
  - Borrar un espacio borra sus rubros e ingresos y no los de otro; tras
    salir Bea de un espacio, sus rubros e ingresos siguen en el resumen de
    Ana.
- Hecho cuando: los tests pasan.
- RF: RF-9, RF-12, RF-18, RF-28 a RF-30, RF-44.

## [ ] T12 — ADR 0011 y ADR 0012
- `docs/adr/0011-migraciones-con-alembic.md`: Alembic al arrancar, la
  `0001` idempotente en lugar de `alembic stamp`, sin `downgrade`, los
  tests con `create_all` vigilados por `compare_metadata`, y el riesgo del
  DDL no transaccional en SQLite. Reemplaza al 0004, que pasa a "reemplazada
  por ADR 0011".
- `docs/adr/0012-plan-mensual-con-rubros-e-ingresos.md`: rubros por mes,
  copia explícita, ingresos en el plan, gasto planeado con la categoría del
  rubro, categorías eliminadas como archivo, y por qué ahora sí se copia
  del mes anterior cuando el ADR 0008 lo descartó. Reemplaza al 0008, que
  pasa a "reemplazada por ADR 0012".

- Test primero: no aplica, es documentación.
- Hecho cuando: los dos ADR existen con la plantilla `0000-plantilla.md` y
  el plan los cita.
- RF: ninguno; principio 4.

## [ ] T13 — Cierre: README y validación
- Comprobar con una **copia** de la base local que `make run-api` la migra
  a `head`, convierte sus presupuestos y conserva sus gastos.
- `README.md`: sale la sección "Presupuesto y resumen" de la 004; entran
  rubros, ingresos, copiar el plan, gastos planeados y no planeados,
  eliminar y restaurar categorías, y el resumen nuevo, con ejemplos `curl`;
  una sección de migraciones con la copia de la base antes de la 008 y
  cómo volver atrás (RF-38).
- Repasar los dieciséis criterios de validación de la spec.
- Proponer el cambio del glosario de `AGENTS.md` y aplicarlo solo con
  aprobación explícita.
- `docs/roadmap.md`: marcar `008-rubros-e-ingresos` como terminada y dejar
  `009-tarjetas-y-cuotas` como spec activa.

- Test primero: no aplica, es documentación y validación.
- Hecho cuando: `make test` y `make lint` están en verde y los ejemplos
  `curl` del README funcionan contra `make run-api`.
- RF: RF-38; cierra la spec.
