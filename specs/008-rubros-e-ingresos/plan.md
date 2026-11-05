# Plan 008 — Rubros e ingresos del mes

- Spec: `spec.md` (estado: aprobada)
- Servicio afectado: `services/api`
- Estado: aprobado (2026-11-05)

La spec cambia una tabla que ya está en `main` (`expenses`) y retira otra
(`budgets`), así que se cumple la condición de reemplazo del ADR 0004:
entra Alembic. El plan tiene dos mitades:

1. **Migraciones**: Alembic, una migración inicial que adopta cualquier
   base creada con `create_all`, y la API aplicándolas al arrancar.
2. **Plan del mes**: rubros, ingresos, copia del plan, gastos con rubro y
   el resumen nuevo, y el retiro del presupuesto de la 004.
3. **Categorías eliminadas**: eliminar una categoría la archiva, y crearla
   de nuevo la restaura.

Los cambios de esquema siguen el patrón **expandir y contraer**
([*parallel change*](https://martinfowler.com/bliki/ParallelChange.html)):
primero una migración que solo añade (tablas y columna nuevas), después el
código que las usa, y al final otra migración que convierte los datos
viejos y borra lo que sobra. Así cada tarea deja la API funcionando.

## Decisiones técnicas

| Decisión | Elegido | Por qué |
|---|---|---|
| Herramienta de migraciones | [Alembic](https://alembic.sqlalchemy.org/en/latest/tutorial.html), dependencia de ejecución | La nombra el ADR 0004 y es la de SQLAlchemy. Es de ejecución y no solo de desarrollo porque la API migra al arrancar. Deja el ADR 0011, que reemplaza al 0004. |
| Cuándo se migra | `run_migrations(engine)` en el `lifespan` de `main.py`, en lugar de `create_all` | Decisión 11: nadie tiene que acordarse de un comando. Se descartó un target `make migrate`: es un paso manual más, y los nombres de los targets no cambian (AGENTS.md). |
| Adoptar bases sin Alembic | Migración `0001` **idempotente**: crea cada tabla del esquema de la 007 solo si no existe, y borra las de Telegram si existen | RF-32: sirve igual para una base vacía, una de la 007 y una de la 003 a la que le falta `budgets`. Se descartó `alembic stamp`, que propone el ADR 0004: solo sirve si la base coincide exactamente con la migración inicial, y obliga a detectar y marcar a mano. |
| Tablas de Telegram | `DROP TABLE IF EXISTS` en la `0001` | Decisión 1 de la 007: "su primera migración las borra". Encaja en la `0001`, que deja la base en el esquema de la 007, y ese esquema no las tiene. |
| Dónde viven las migraciones | `app/migrations/` (`env.py`, `script.py.mako`, `versions/`) y un `alembic.ini` en `services/api/` | Dentro de `app/` viajan con el código cuando llegue Docker. El `alembic.ini` solo sirve para crear migraciones nuevas con la CLI; la API arma su configuración en código. |
| Conexión de las migraciones | `env.py` usa la conexión que le pasa `run_migrations` en `config.attributes`; si no hay, crea un motor con `settings.database_url` | Receta de Alembic para [compartir una conexión](https://alembic.sqlalchemy.org/en/latest/cookbook.html#connection-sharing): los tests migran su propia base y la API usa su motor, con las claves foráneas de SQLite activas. |
| `ALTER TABLE` en SQLite | `render_as_batch=True` en `env.py` y `op.batch_alter_table` | SQLite no puede añadir claves foráneas ni borrar columnas con `ALTER TABLE` ([límites](https://www.sqlite.org/lang_altertable.html)). El [modo *batch*](https://alembic.sqlalchemy.org/en/latest/batch.html) copia la tabla cuando hace falta. En PostgreSQL usa `ALTER TABLE` normal. |
| Identificadores de las migraciones | `0001`, `0002`, `0003` con `--rev-id` | Se leen en orden. Los que genera Alembic (`3f2a9c…`) no dicen nada. |
| `downgrade` | Lanza `NotImplementedError` con un mensaje que manda a restaurar la copia | La `0003` convierte datos y no se puede deshacer sin perder información. Mantener `downgrade` que nadie prueba daría una falsa seguridad. RF-38 pide la copia antes de migrar. |
| Tests y migraciones | Los tests siguen creando su base con `Base.metadata.create_all`; `test_migrations.py` comprueba que las migraciones dan el mismo esquema | Migrar en cada uno de los ~400 tests los haría mucho más lentos. El riesgo que vigilaba el ADR 0004 (modelos y base desalineados) lo cubre ahora [`compare_metadata`](https://alembic.sqlalchemy.org/en/latest/api/autogenerate.html#alembic.autogenerate.compare_metadata) (RF-36). |
| Periodo de un rubro o ingreso | Columna `Date` `period_start`, siempre el día 1 | Como `budgets.starts_on` (plan 004): se compara con `dates.period_bounds`. |
| Nombres únicos por mes | `name_key` con `category_key` de la 002 y `UniqueConstraint(space_id, period_start, name_key)` | Decisión 7, igual que las categorías (ADR 0006). El índice también protege la copia: dos copias a la vez chocan en el primer nombre (RF-14). |
| Categoría de un gasto planeado | `expenses.category_id` sigue obligatorio y la API lo copia del rubro; `expenses.budget_item_id` nuevo y nulo | Decisión 5. El listado, los últimos registrados y lo gastado por categoría no cambian. Se descartó dejar `category_id` nulo en los gastos planeados y deducirlo del rubro: cambia una columna obligatoria de `main` y obliga a reescribir cada consulta por categoría. A cambio, la API mantiene las dos columnas de acuerdo (RF-7, RF-20); la base de datos no lo comprueba, igual que no comprueba que la categoría sea del espacio (plan 003). |
| Cambiar la categoría de un rubro | Un `UPDATE expenses SET category_id = … WHERE budget_item_id = …` en la misma transacción | RF-7. |
| Borrar un rubro | `UPDATE expenses SET budget_item_id = NULL …` y luego `DELETE` del rubro, en la misma transacción | RF-8: los gastos ya tienen la categoría del rubro, así que solo se suelta el vínculo. `budget_item_id` no tiene `ON DELETE`, por la misma razón que `category_id` (plan 003). |
| Copiar el plan | `app/plan.py`: comprueba destino vacío y origen con plan, inserta todo y hace un solo `commit`; un `IntegrityError` se responde como destino con plan | RF-13 a RF-16. Todo o nada: o se copia el plan entero o no se crea ninguna fila. |
| Respuesta de la copia | `201` con `{"summary": …, "skipped": […]}`: el resumen del periodo destino y los rubros omitidos por categoría eliminada | Es lo que la pantalla de planear (011) muestra a continuación, y RF-13 pide decir qué se omitió. Se ahorra una segunda petición. |
| Eliminar una categoría | Columna nueva `categories.deleted_at` (nula), añadida en la `0002`; `DELETE` la rellena | Decisión 14: archivar, no borrar. Rubros y gastos siguen apuntando a la misma fila. Se descartaron borrar la fila (dejaría rubros y gastos sin categoría, principio 8) y una tabla aparte de eliminadas (mover la fila cambiaría su `id` y rompería las referencias). |
| Categorías que se pueden elegir | `check_category` y `GET /categories` filtran `deleted_at IS NULL`. Una eliminada del propio espacio responde `422` con su propio mensaje | RF-39 y RF-41. Una categoría de otro espacio sigue respondiendo como inexistente (RF-5 de la 003). Una eliminada es del propio espacio, así que no hay nada que ocultar y el mensaje puede decir cómo restaurarla. |
| Restaurar | En `POST /categories`, si el `name_key` es de una eliminada, se pone `deleted_at = NULL` y se responde `200` con la categoría, en lugar de `201` | RF-43 y decisión 21. El índice único `(space_id, name_key)` de la 002 ya incluye las eliminadas, así que nunca puede haber dos con el mismo nombre. El `200` dice "no se creó nada nuevo" sin cambiar la forma de la respuesta. |
| Respuesta al eliminar una categoría | `200` con `{"id", "name", "message"}` en lugar de `204` sin cuerpo | Decisión 23: el aviso lo arma la API, como el resto de los mensajes al usuario, y la web lo muestra tal cual. Es la única ruta `DELETE` que responde con cuerpo, porque es la única que tiene algo que avisar. |
| Comparación de nombres | `category_key` de la 002, sin cambios, también para rubros e ingresos | Decisión 22: ya ignora mayúsculas, tildes, diéresis y espacios alrededor, y respeta la ñ (ADR 0006). |
| Autocompletar el rubro al registrar | Ninguna ruta nueva | Decisión 13: la web (010) filtra los rubros que ya trae el resumen del mes. Un mes tiene pocas decenas de rubros. |
| Rutas para leer el plan | Ninguna aparte: el resumen trae rubros e ingresos con sus identificadores | Como en el plan 004, lo que la web necesita ya va en el resumen. Si la 011 necesita otra cosa, la añade. |
| Retiro del presupuesto | La `0003` convierte `budgets` en rubros con `INSERT … SELECT` y borra la tabla. Salen `Budget`, `BudgetIn`, `BudgetOut` y `app/routers/budgets.py` | Decisión 4 y RF-27. La conversión es SQL dentro de la migración: no puede importar los modelos, que ya no tienen `Budget`. |

## Dependencias

- **`alembic`** (de ejecución). Trae `Mako`, que usa para la plantilla de
  migraciones nuevas. Ninguna otra.

## Estructura de archivos

    services/api/
      pyproject.toml                  + alembic
      alembic.ini                     nuevo: solo para la CLI (crear migraciones)
      app/
        db.py                         − create_all; + run_migrations           [RF-31, RF-37]
        main.py                       lifespan con run_migrations; routers nuevos
        dates.py                      + previous_period                       [RF-13]
        models.py                     + BudgetItem, Income, Expense.budget_item_id,
                                      Category.deleted_at; − Budget
        schemas.py                    + rubros, ingresos, copia, resumen nuevo;
                                      ExpenseIn/Patch/Out con rubro; − BudgetIn/Out
        summary.py                    reescrito: resumen del plan             [RF-23 a RF-26]
        plan.py                       nuevo: copiar el plan                   [RF-13 a RF-16]
        routers/
          budget_items.py             nuevo: crear, editar y borrar rubros    [RF-1 a RF-9]
          incomes.py                  nuevo: crear, editar y borrar ingresos  [RF-10 a RF-12]
          plan.py                     nuevo: resumen y copia del plan
          expenses.py                 rubro al registrar y editar             [RF-17 a RF-22]
          categories.py               + DELETE; POST restaura una eliminada   [RF-39 a RF-44]
          budgets.py                  eliminado                               [RF-27]
        migrations/
          env.py, script.py.mako
          versions/
            0001_baseline.py          esquema de la 007, idempotente; − Telegram  [RF-32, RF-34]
            0002_budget_items_and_incomes.py   expandir                      [RF-31, RF-39]
            0003_budgets_to_budget_items.py    contraer y convertir          [RF-33, RF-35]
      tests/
        conftest.py                   Base.metadata.create_all
        test_migrations.py            nuevo                                   [RF-31 a RF-37]
        test_models.py                + rubros, ingresos, gasto con rubro; − Budget
        test_budget_items.py          nuevo
        test_incomes.py               nuevo
        test_plan.py                  nuevo: copia y resumen por HTTP
        test_summary.py               reescrito: cálculo sin HTTP
        test_expenses.py              + gastos con rubro
        test_categories.py            + eliminar y restaurar
        test_budgets.py               eliminado (sus casos pasan a los de arriba)
        test_isolation.py             + rubros, ingresos, copia y resumen
        test_retired_bot.py           el criterio 4 de la 007 pasa a test_migrations
    docs/adr/0011-migraciones-con-alembic.md            reemplaza al 0004
    docs/adr/0012-plan-mensual-con-rubros-e-ingresos.md reemplaza al 0008
    README.md                         rubros, ingresos, copia, resumen y migraciones

## Modelo de datos

**`budget_items`** (rubros) — `id`, `space_id`, `period_start`, `name`,
`name_key`, `category_id`, `amount`, `created_at`.

- `space_id`: clave foránea a `spaces.id` con `ON DELETE CASCADE`. [RF-30]
- `period_start`: `Date`, día 1 del periodo. Solo lo escribe la API.
  [RF-2, RF-6]
- `name`: `String(50)`. `name_key`: `String`, rellenada con `category_key`
  desde un `@validates("name")`, como en `Category`. [RF-3]
- `category_id`: clave foránea a `categories.id` sin `ON DELETE` (plan 003).
  [RF-5]
- `amount`: `BigInteger` con `CheckConstraint("amount > 0")`. [RF-4]
- `created_at`: `UTCDateTime`. El orden de creación es el de `id`.
- `UniqueConstraint(space_id, period_start, name_key)`. Su índice sirve
  también para leer los rubros de un mes. [RF-3, RF-14]

**`incomes`** (ingresos) — `id`, `space_id`, `period_start`, `name`,
`name_key`, `amount`, `created_at`, con las mismas reglas que
`budget_items` menos la categoría. [RF-10, RF-11]

**`expenses`** — se añade `budget_item_id`: clave foránea nula a
`budget_items.id`, sin `ON DELETE`, con índice
`ix_expenses_budget_item_id` para los `UPDATE` de RF-7 y RF-8 (PostgreSQL
no indexa solas las claves foráneas). `category_id` no cambia. [RF-17 a
RF-21]

Borrar un espacio: `ON DELETE CASCADE` quita gastos, rubros e ingresos en
la misma sentencia, y las claves foráneas sin `ON DELETE` (`NO ACTION`) se
comprueban al final, así que no chocan (mismo razonamiento del plan 003).

**`categories`** — se añade `deleted_at`: `UTCDateTime` nulo. Nulo es
activa; con fecha, eliminada desde ese momento. Ninguna fila se borra.
[RF-39, RF-40]

**`budgets`**: sale en la `0003`, después de convertir sus filas.

## Migraciones

`app/db.py`:

    def run_migrations(engine: Engine) -> None:
        """Aplica las migraciones pendientes (RF-31). Si una falla, la
        excepción sube y la API no arranca (RF-37)."""

Arma un `alembic.config.Config` en código con `script_location` apuntando a
`app/migrations`, abre una conexión del motor, la pasa en
`config.attributes["connection"]` y llama a `command.upgrade(config,
"head")`.

| Migración | Qué hace | RF |
|---|---|---|
| `0001_baseline` | Para cada tabla del esquema al cerrar la 007 (`users`, `spaces`, `memberships`, `invitations`, `sessions`, `categories`, `expenses`, `budgets`), `op.create_table` solo si `inspect(conn).has_table(...)` dice que falta. Luego `DROP TABLE IF EXISTS` de `telegram_chats` y `telegram_link_codes`. Las tablas se escriben a mano, no desde los modelos, que seguirán cambiando. | RF-32, RF-34 |
| `0002_budget_items_and_incomes` | Crea `budget_items` e `incomes`. Añade `expenses.budget_item_id`, su clave foránea y su índice, y `categories.deleted_at`, con `batch_alter_table`. Solo añade: ningún dato cambia y toda categoría queda activa. | RF-31, RF-39 |
| `0003_budgets_to_budget_items` | `INSERT INTO budget_items (...) SELECT b.space_id, b.starts_on, c.name, c.name_key, b.category_id, b.amount, b.updated_at FROM budgets b JOIN categories c ON c.id = b.category_id WHERE b.amount IS NOT NULL`, y después `op.drop_table("budgets")`. Los gastos no se tocan: su `budget_item_id` ya es nulo. | RF-33, RF-35 |

- **Por qué no chocan los nombres al convertir**: hay una sola fila de
  `budgets` por (espacio, categoría, mes), y dos categorías de un espacio
  nunca tienen el mismo `name_key`. Así que nunca salen dos rubros con el
  mismo nombre en el mismo mes.
- **Una base que ya tiene `alembic_version`** solo aplica lo que le falta.
  Arrancar dos veces no hace nada la segunda (RF-37).

## Validación de entradas (`schemas.py`)

| Esquema | Campos | RF |
|---|---|---|
| `BudgetItemIn` | `period` (`Period`, por defecto el actual), `name` (1 a 50 tras `strip`), `category_id` (`StrictInt`), `amount` (`Amount` de la 003) | RF-1 a RF-5 |
| `BudgetItemPatch` | `name`, `category_id`, `amount` opcionales; `null` se rechaza, como en `ExpensePatch`. Sin `period` | RF-6 |
| `IncomeIn` / `IncomePatch` | Igual, sin `category_id` | RF-10, RF-11 |
| `PlanCopyIn` | `period` destino, por defecto el actual | RF-13 |
| `ExpenseIn` | Se añade `budget_item_id` (`StrictInt`, opcional) y `category_id` pasa a opcional. Un `model_validator` exige exactamente uno: "Indica el rubro del gasto o, si no estaba planeado, su categoría, pero no los dos." | RF-17 |
| `ExpensePatch` | Se añade `budget_item_id`, que admite `null` (quitar el rubro) | RF-21 |

Salidas:

- `BudgetItemOut`: `id`, `period`, `name`, `category_id`, `amount`.
- `IncomeOut`: `id`, `period`, `name`, `amount`.
- `ExpenseOut`: se añade `budget_item_id` (nulo = no planeado). [RF-20]
- `SummaryOut` (reemplaza al de la 004):

      {
        "period": "2026-11",
        "incomes": [{"id": 1, "name": "Salario", "amount": 5000000}],
        "budget_items": [
          {"id": 3, "name": "Arriendo", "category_id": 1,
           "planned": 1500000, "spent": 1500000, "remaining": 0},
          {"id": 4, "name": "Mercado", "category_id": 2,
           "planned": 800000, "spent": 412000, "remaining": 388000}
        ],
        "categories": [
          {"category_id": 1, "name": "Hogar", "planned": 1500000, "spent": 1500000, "deleted": false},
          {"category_id": 2, "name": "Comida", "planned": 800000, "spent": 450000, "deleted": false},
          ...  las activas, también las que están en 0, y las eliminadas con datos en el mes
        ],
        "total": {
          "income": 5000000, "planned": 2300000,
          "spent_planned": 1912000, "spent_unplanned": 38000, "spent": 1950000,
          "unassigned": 2700000, "balance": 3050000
        }
      }

  Ningún campo es nulo: sin plan, las listas salen vacías y los montos en
  `0` (RF-25). `unassigned = income - planned` y `balance = income - spent`.
  [RF-23, RF-24]

## Rutas

Todas cuelgan de `/spaces/{space_id}` y usan `member_space`; el test que
recorre las rutas con `{space_id}` las vigila sin cambios. [RF-28]

| Método y ruta | Qué hace | Respuestas | RF |
|---|---|---|---|
| `POST /spaces/{space_id}/budget-items` | Crea un rubro | `201` `BudgetItemOut`; `409` nombre repetido; `422` categoría de otro espacio o datos inválidos | RF-1 a RF-5 |
| `PATCH /spaces/{space_id}/budget-items/{item_id}` | Edita nombre, categoría o monto; con categoría nueva, actualiza sus gastos | `200`; `404` "Rubro no encontrado."; `409`; `422` | RF-6, RF-7, RF-9 |
| `DELETE /spaces/{space_id}/budget-items/{item_id}` | Suelta sus gastos y borra el rubro | `204`; `404` | RF-8, RF-9 |
| `POST /spaces/{space_id}/incomes` | Crea un ingreso | `201` `IncomeOut`; `409`; `422` | RF-10 |
| `PATCH /spaces/{space_id}/incomes/{income_id}` | Edita nombre o monto | `200`; `404` "Ingreso no encontrado."; `409`; `422` | RF-11, RF-12 |
| `DELETE /spaces/{space_id}/incomes/{income_id}` | Borra el ingreso | `204`; `404` | RF-11, RF-12 |
| `POST /spaces/{space_id}/plan/copy` | Copia el plan del mes anterior al `period` del cuerpo, sin los rubros de categorías eliminadas | `201` `PlanCopyOut`; `409` destino con plan u origen sin nada que copiar | RF-13 a RF-16 |
| `DELETE /spaces/{space_id}/categories/{category_id}` | Elimina (archiva) la categoría | `200` `CategoryDeletedOut`; `404` "Categoría no encontrada." si no existe, es de otro espacio o ya está eliminada | RF-39, RF-40, RF-44 |
| `POST /spaces/{space_id}/categories` | Como en la 002; si el nombre es de una eliminada, la restaura | `201` creada; `200` restaurada; `409` nombre de una activa | RF-43 |
| `GET /spaces/{space_id}/summary?period=` | Resumen nuevo | `200` `SummaryOut`; `422` periodo mal escrito | RF-23 a RF-26 |

Mensajes:

- Nombre repetido: "Ya existe el rubro «Mercado» en 2026-11." / "Ya existe el
  ingreso «Salario» en 2026-11." Se nombra el que ya existe, con su
  escritura, como en las categorías.
- Destino con plan: "2026-12 ya tiene un plan; no se copió nada."
- Origen sin nada que copiar: "2026-11 no tiene un plan para copiar."
- Rubro del gasto que no está en el espacio: `422` "El rubro no existe en
  este espacio.", como la categoría.
- Rubro de otro mes: `422` "El rubro «Mercado» es de 2026-10 y el gasto es
  de 2026-11. Elige un rubro de 2026-11 o regístralo como no planeado."
- Cambiar la categoría de un gasto planeado: `422` "El gasto está en el
  rubro «Mercado» y usa su categoría. Para cambiarla, quítale el rubro."
- Aviso al eliminar una categoría (`message`): "Eliminaste «Mascotas». Sus
  rubros y gastos la conservan, pero sus rubros ya no se copiarán al
  planear. Para volver a usarla, créala de nuevo con el mismo nombre."
- Categoría eliminada en un rubro o un gasto: `422` "La categoría «Mascotas»
  fue eliminada. Para usarla de nuevo, créala otra vez con el mismo
  nombre."

**Editar un gasto** (`PATCH`), con los campos enviados:

1. `budget_item_id` con un número y también `category_id`: `422`, la regla
   de "exactamente uno".
2. `budget_item_id` con un número: se busca en el espacio, se comprueba el
   mes con la fecha que tendrá el gasto, y `category_id` pasa a ser la del
   rubro.
3. `budget_item_id: null`: el gasto queda no planeado. Su categoría es la
   enviada o, si no se envía, la que ya tenía.
4. Solo `category_id` en un gasto planeado: `422` (RF-21).
5. Solo `spent_on` en un gasto planeado: se comprueba el mes con su rubro
   (RF-19).

## Cálculo (`app/summary.py` y `app/plan.py`)

Funciones sin HTTP (principio 10), todas filtradas por `space_id`
(RF-29):

- `spent_by_category(db, space_id, start, end)`: la de la 004, sin cambios.
- `spent_by_item(db, space_id, start, end) -> dict[int, int]`: `SUM` de los
  gastos con rubro, agrupada por `budget_item_id`, con `int()` sobre cada
  suma (principio 6).
- `build_summary(db, space_id, period) -> SummaryOut`: lee ingresos y rubros
  del mes por `id`, las categorías del espacio por `id`, y arma filas y
  totales. De las categorías eliminadas solo incluye las que tienen rubros
  o gastos en el mes (decisión 18). `spent_unplanned = spent -
  spent_planned`.
- `plan.copy_previous_plan(db, space_id, period) -> list[SkippedItem]`:
  copia los ingresos y los rubros cuya categoría está activa, y devuelve
  los omitidos. Lanza `PlanNotEmpty` o `NothingToCopy` (también si todo se
  omitió y no hay ingresos), que la ruta convierte en `409`.
- `dates.previous_period("2026-01") == "2025-12"`.

## Tests

- `test_migrations.py` (base SQLite en un archivo de `tmp_path`):
  - base vacía → `head`, y `compare_metadata` contra `Base.metadata` sin
    diferencias (RF-36, criterio 10);
  - aplicar dos veces no cambia nada (RF-37);
  - base de la 007 sin `alembic_version` y con tablas de Telegram con filas
    → `head` conserva usuarios, espacios, categorías y gastos, y borra las
    de Telegram (RF-32, RF-34, criterio 8);
  - base de la 003, sin `budgets` → `head` (criterio 9);
  - presupuestos con monto y nulos → rubros convertidos (RF-33, criterio 8);
  - una migración que falla impide arrancar: el `lifespan` propaga el error
    (RF-37).
- `test_models.py`: `CheckConstraint` e índices únicos de rubros e
  ingresos, y borrar un espacio con gastos ligados a rubros.
- `test_budget_items.py`, `test_incomes.py`: un test por RF de las rutas,
  con el criterio 2 (nombres), el 5 (categoría y borrado) y el 7 (montos).
- `test_expenses.py`: los casos de "Editar un gasto" y el criterio 4. Los
  tests que ya existen siguen pasando: sus gastos se registran con
  `category_id`, que sigue siendo válido como gasto no planeado. Solo
  cambian las aserciones que comparan el gasto entero, porque ahora trae
  `budget_item_id`.
- `test_summary.py`: el criterio 1 sin HTTP, un mes sin plan (RF-25) y los
  bordes del periodo de la 004.
- `test_plan.py`: criterios 1, 3 y 6 por HTTP, y el `404` de la ruta de la
  004 (criterio 11).
- `test_categories.py`: eliminar con su aviso, el listado sin eliminadas,
  restaurar con el nombre original sin importar mayúsculas ni tildes, y los
  `404` (criterios 13 a 15). Los tests de la 002
  siguen en verde.
- `test_isolation.py`: criterio 12.
- `test_retired_bot.py`: el criterio 4 de la 007 (las tablas de Telegram
  siguen intactas) deja de ser cierto a propósito: lo reemplaza el test de
  `test_migrations.py` que comprueba que se borran. El criterio 5 pasa a
  comprobarse sobre `Base.metadata`.

## Base de datos local

Al arrancar con esta spec por primera vez, `budget.db` se migra sola. Antes
conviene copiarla (RF-38):

    cp services/api/budget.db services/api/budget.db.antes-008

Para volver atrás: detener la API, restaurar la copia y volver a la rama
anterior. El README lo explica.

## Riesgos y temas abiertos

- **En SQLite una migración que falla a la mitad puede dejar la base a
  medias.** El driver `sqlite3` de Python no abre transacción antes de un
  `CREATE` o un `DROP`, así que el DDL no es atómico sin una
  [receta](https://docs.sqlalchemy.org/en/20/dialects/sqlite.html#serializable-isolation-savepoints-transactional-ddl)
  que cambia cómo abre transacciones todo el motor. No se aplica: la base
  local es de desarrollo, la copia de RF-38 cubre el caso, y en
  PostgreSQL (fase 2 en adelante) el DDL sí es transaccional.
- **La `0001` no comprueba las columnas de las tablas que ya existen.** Si
  una base local tuviera una tabla con otra forma, la `0001` la dejaría
  así. Solo pasó con `invitations` antes de llegar a `main` (nota del ADR
  0004), y esa base ya se recreó.
- **`compare_metadata` en SQLite puede ver diferencias que no lo son**, como
  restricciones sin nombre. Si pasa, el test las filtra una a una con un
  comentario que diga por qué, nunca de forma general.
- **Borrar un rubro mientras otro miembro registra un gasto en él**: el
  `INSERT` del gasto choca con la clave foránea. La ruta lo responde como
  rubro inexistente (`422`), no como `500`.
- **Eliminar una categoría mientras otro miembro crea un rubro con ella**:
  el rubro puede quedar con una categoría recién eliminada. No rompe nada:
  es el mismo caso que un rubro creado justo antes de eliminarla
  (decisión 17).
- **Varias réplicas migrando a la vez** (fase 8): queda anotado en la spec.
- **El glosario de `AGENTS.md`** queda desactualizado hasta que se apruebe
  cambiarlo (spec, "Requisitos para otras specs y documentos").

## Conceptos nuevos

- [Tutorial de Alembic](https://alembic.sqlalchemy.org/en/latest/tutorial.html): migraciones, revisiones y `upgrade`.
- [Migraciones *batch* para SQLite](https://alembic.sqlalchemy.org/en/latest/batch.html): cómo Alembic cambia tablas que SQLite no puede alterar.
- [Compartir una conexión con Alembic](https://alembic.sqlalchemy.org/en/latest/cookbook.html#connection-sharing): correr migraciones desde el código de la aplicación.
- [`compare_metadata`](https://alembic.sqlalchemy.org/en/latest/api/autogenerate.html#alembic.autogenerate.compare_metadata): comparar el esquema real con el de los modelos.
- [Expandir y contraer (*parallel change*)](https://martinfowler.com/bliki/ParallelChange.html): cambiar un esquema en pasos que nunca rompen la aplicación.
- [`INSERT … SELECT`](https://www.sqlite.org/lang_insert.html): copiar filas de una tabla a otra en una sola sentencia.
- Borrado lógico (*soft delete*): marcar una fila como eliminada en lugar de borrarla; aquí con una columna `deleted_at` y un filtro en cada consulta.
- [`UPDATE` con SQLAlchemy](https://docs.sqlalchemy.org/en/20/tutorial/data_update.html): cambiar muchas filas sin cargarlas.
- [DDL transaccional en SQLite con SQLAlchemy](https://docs.sqlalchemy.org/en/20/dialects/sqlite.html#serializable-isolation-savepoints-transactional-ddl): por qué una migración en SQLite puede quedar a medias.
