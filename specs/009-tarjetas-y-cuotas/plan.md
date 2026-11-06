# Plan 009 — Tarjetas y cuotas

- Spec: `spec.md` (estado: aprobada)
- Servicio afectado: `services/api`
- Estado: aprobado (2026-11-06)

La spec añade tres tablas (`cards`, `card_statements`, `prepayments`) y
tres columnas a `expenses`, con una migración que solo añade (`0004`). No
convierte datos: los gastos existentes quedan sin tarjeta (decisión 8).

El plan tiene cuatro partes:

1. **Cálculo puro**: mes de pago y plan de cuotas con abonos, en funciones
   sin base de datos ni HTTP (principio 10). Es la parte con más reglas y
   la que más tests necesita, así que va primero.
2. **Tarjetas**: el CRUD con archivo y restauración, igual que las
   categorías de la 008, más el valor real del extracto.
3. **Compras con tarjeta y abonos**: las reglas nuevas de los gastos a
   crédito, las rutas de abonos y pagar todo.
4. **Deudas**: la sección del resumen, el estado de la tarjeta y la
   simulación.

Las decisiones de fondo quedan en un ADR nuevo, el
[**0013**](../../docs/adr/0013-compras-con-tarjeta-cuentan-al-pagar.md): las compras
con tarjeta cuentan el mes del pago, las cuotas se calculan al leer y no
se guardan, y el abono baja la cuota o el plazo.

## Decisiones técnicas

| Decisión | Elegido | Por qué |
|---|---|---|
| Cuotas guardadas o calculadas | **Calculadas al leer** con `app/installments.py`; no hay tabla de cuotas | La tasa de la tarjeta cambia las estimaciones (decisión 14) y cada abono rehace las cuotas siguientes (RF-25). Con una tabla habría que reescribir filas en cada cambio y mantenerlas de acuerdo con la compra. Calcular son como mucho 48 cuotas por compra. Se descartó una tabla `installments` materializada: es un caché que se puede desalinear. |
| Mes de pago | Columna `expenses.first_due_start` (`Date`, día 1), escrita por la API al registrar o al editar fecha, tarjeta, monto o cuotas | Decisión 13: cambiar los días de la tarjeta no mueve compras ya registradas. Es un `Date` del día 1, como `budget_items.period_start` (plan 008). |
| Tasa en la API | Campo `monthly_rate` de tipo [`Decimal`](https://docs.python.org/3/library/decimal.html) con `Field(gt=0, le=10, decimal_places=2)`: se escribe `1.89` y sale `1.89` | Decisión 27: se escribe como número decimal y nunca se calcula con `float`. Pydantic convierte el número JSON en `Decimal` y rechaza `1.895` por los decimales. Un `BeforeValidator` rechaza texto y booleanos, como `StrictInt` en los montos. |
| Tasa en la base de datos | Entero `monthly_rate_bp` en **puntos básicos** (centésimas de punto porcentual): `1.89` se guarda como `189` | SQLite no tiene un tipo decimal exacto: SQLAlchemy guarda un `Numeric` como `REAL` (un `float`) y lo avisa con un *warning*. Un entero es exacto en SQLite y en PostgreSQL. La conversión (`int(rate * 100)` al guardar, `Decimal(bp) / 100` al leer) vive en el esquema. El interés queda en enteros: `(saldo * bp + 5000) // 10000`, que redondea con el medio peso hacia arriba (decisión 15). Se descartó `Numeric(4, 2)`: exacto en PostgreSQL pero no en SQLite, que es la base hasta la fase 2. |
| Forma de una compra con tarjeta | `CheckConstraint` en `expenses`: o `card_id`, `installments` y `first_due_start` son nulos, o los tres tienen valor, `payment_type = 'credit'`, `budget_item_id` es nulo e `installments` va de 1 a 48 | Última defensa si algo salta la validación de la API, como los `CheckConstraint` de la 003. Los gastos existentes la cumplen: sus tres columnas nuevas quedan nulas. |
| Archivar tarjetas | `cards.deleted_at`, como `categories.deleted_at` (plan 008) | Decisiones 9 y 24. `UniqueConstraint(space_id, name_key)` incluye las archivadas, así que nunca hay dos con el mismo nombre y crear una con el nombre de una archivada la restaura. |
| Abonos | Tabla `prepayments` con `UniqueConstraint(expense_id, period_start)`. "Posterior al último abono" lo comprueba la API con `SELECT … FOR UPDATE` sobre la compra | RF-24 y decisión 18. El índice único frena dos abonos del mismo mes. Dos abonos de meses distintos a la vez los frena el bloqueo de la fila de la compra en PostgreSQL ([`with_for_update`](https://docs.sqlalchemy.org/en/20/core/selectable.html#sqlalchemy.sql.expression.Select.with_for_update)); en SQLite no hace nada, pero SQLite ya escribe de a una transacción. |
| Modo del abono | Columna `reduces` con `'installment'` (baja la cuota) o `'term'` (baja el plazo) y `CheckConstraint` | Decisión 7. Texto en lugar de booleano: se lee solo y admite otro modo si algún día hace falta. |
| Valor real del extracto | Tabla `card_statements` con `UniqueConstraint(card_id, period_start)`; `PUT` crea o reemplaza | RF-31. Si dos `PUT` del mismo mes chocan en el índice, la ruta vuelve a leer y actualiza: gana el último, como se espera de un `PUT`. |
| Deudas en el resumen | `app/debts.py` lee las compras de las tarjetas del espacio cuyo `first_due_start` cae en los 48 meses anteriores al periodo, calcula sus cuotas y toma la del periodo | 48 es el máximo de cuotas (decisión 10): una compra con primera cuota anterior no puede tener cuotas en el periodo. Así no se leen todas las compras de la historia. |
| Lo gastado por categoría | `spent_by_category` filtra `Expense.card_id IS NULL` | RF-37. `spent_by_item` no cambia: una compra con tarjeta nunca tiene rubro (`CheckConstraint`). |
| Totales | `TotalSummaryOut` añade `debts`; `planned = rubros + debts`, `spent = spent_planned + spent_unplanned + debts` | RF-38, decisión 3. `planned` y `spent` cambian de significado, pero ningún cliente los usa aún (la web es la 010). |
| Rutas de tarjetas | `app/routers/cards.py`: CRUD, estado, simulación, valor real del extracto y pagar todo | Todo lo que cuelga de una tarjeta en un mismo archivo, como `categories.py`. |
| Rutas de abonos y plan de cuotas | `app/routers/prepayments.py`, bajo `/expenses/{expense_id}` | El abono es de una compra, no de la tarjeta (decisión 7). Separadas de `expenses.py`, que ya es largo. |
| Pagar todo | `POST /cards/{card_id}/payoff` con `{"period"}`; `debts.pay_off` crea un abono por compra en una sola transacción, con `reduces = 'term'` | RF-29 y RF-30. Son abonos normales: el resumen, el estado y el borrado ya los entienden, y no hace falta otra tabla. Con un abono igual al saldo da igual el modo; se guarda `term`. Todo o nada: si una compra choca, no se crea ninguno. Bloquea con `FOR UPDATE` las compras que va a saldar, como un abono. |
| Descripción de una compra con tarjeta | Obligatoria: el `model_validator` de `ExpenseIn` la exige con `credit`, y el `PATCH` no deja quitarla | Decisión 26. Es el nombre de la cuota en Deudas. En los gastos a débito sigue opcional (la 008 no cambia). |
| Simulación | `POST /cards/{card_id}/simulate` con cuerpo; responde `200` y no guarda | RF-41. `POST` porque recibe los mismos datos que registrar una compra y los valida igual; `GET` con *query* duplicaría la validación. |
| Gasto sin cuotas en el plan de cuotas | `GET /expenses/{id}/installments` responde `404` "Este gasto no es una compra con tarjeta; no tiene cuotas." | RF-21. El gasto existe, pero su plan de cuotas no. Abonar a ese gasto responde `422`, porque el cuerpo pide algo que no se puede hacer. |
| Compra con abonos | Cambiar algo más que descripción o categoría, o borrarla, responde `409` | RF-16. Es un conflicto con el estado de la compra, no un dato mal escrito. |

## Dependencias

Ninguna nueva.

## Estructura de archivos

    services/api/
      app/
        dates.py                      + shift_period, first_due_period      [RF-13]
        installments.py               nuevo: capital, interés, plan de cuotas
                                      con abonos (sin BD ni HTTP)           [RF-19 a RF-26]
        debts.py                      nuevo: deudas del mes, estado de la
                                      tarjeta, plan de cuotas de una compra [RF-21, RF-34 a RF-36, RF-40]
        models.py                     + Card, CardStatement, Prepayment;
                                      Expense.card_id, installments,
                                      first_due_start
        schemas.py                    + tarjetas, extracto, abonos, cuotas,
                                      simulación, estado; gasto con tarjeta;
                                      resumen con deudas
        summary.py                    + deudas y totales nuevos; categorías
                                      sin compras con tarjeta               [RF-37 a RF-39]
        routers/
          cards.py                    nuevo                                 [RF-1 a RF-8, RF-29 a RF-33, RF-40, RF-41]
          prepayments.py              nuevo                                 [RF-21 a RF-28]
          expenses.py                 reglas de crédito con tarjeta         [RF-9 a RF-18]
        migrations/versions/
          0004_cards_and_installments.py                                    [RF-45]
      tests/
        test_dates.py                 + mes de pago                         (criterio 1)
        test_installments.py          nuevo, sin HTTP                       (criterios 2 y 3)
        test_models.py                + restricciones nuevas
        test_migrations.py            + 0004                                (criterio 11)
        test_cards.py                 nuevo                                 (criterios 7, 8, 10 y 13)
        test_expenses.py              + compras con tarjeta                 (criterios 5, 6 y 9)
        test_prepayments.py           nuevo                                 (criterio 3 por HTTP)
        test_summary.py, test_plan.py + deudas                              (criterio 4)
        test_isolation.py             + tarjetas, abonos y extractos        (criterio 12)
    docs/adr/0013-compras-con-tarjeta-cuentan-al-pagar.md
    docs/roadmap.md                   nota de la 009
    README.md                         tarjetas, compras a cuotas, abonos, deudas

## Modelo de datos

**`cards`** (tarjetas) — `id`, `space_id`, `name`, `name_key`, `cutoff_day`,
`due_day`, `monthly_rate_bp`, `created_at`, `deleted_at`.

- `space_id`: clave foránea a `spaces.id` con `ON DELETE CASCADE`. [RF-44]
- `name`: `String(50)`; `name_key` con `category_key` desde un
  `@validates("name")`, como `Category`. [RF-2]
- `cutoff_day`, `due_day`: `SmallInteger` con
  `CheckConstraint("… BETWEEN 1 AND 31")`. [RF-3]
- `monthly_rate_bp`: `Integer` nulo, la tasa en puntos básicos (la API la
  recibe y la devuelve como decimal), con
  `CheckConstraint("monthly_rate_bp IS NULL OR monthly_rate_bp BETWEEN 1 AND 1000")`.
  [RF-3]
- `deleted_at`: `UTCDateTime` nulo. Nulo es activa. [RF-6]
- `UniqueConstraint(space_id, name_key)`. [RF-2, RF-7]

**`expenses`** — se añaden:

- `card_id`: clave foránea nula a `cards.id`, sin `ON DELETE` (plan 003).
- `installments`: `SmallInteger` nulo.
- `first_due_start`: `Date` nulo, día 1 del mes de la primera cuota.
- `CheckConstraint` `ck_expenses_card_purchase` con la forma de la tabla de
  decisiones.
- Índice `ix_expenses_card_id_first_due_start` (`card_id`,
  `first_due_start`): Deudas busca las compras de cada tarjeta en una
  ventana de meses, y el estado, todas las de una tarjeta. [RF-34, RF-40]

**`card_statements`** (valor real del extracto) — `id`, `space_id`,
`card_id`, `period_start`, `amount`, `updated_at`.

- `space_id` con `ON DELETE CASCADE`; `card_id` sin `ON DELETE` (una
  tarjeta nunca se borra de verdad). [RF-44]
- `amount`: `BigInteger` con `CheckConstraint("amount >= 0")`. [RF-31]
- `UniqueConstraint(card_id, period_start)`. [RF-31]

**`prepayments`** (abonos) — `id`, `space_id`, `expense_id`,
`period_start`, `amount`, `reduces`, `created_by`, `created_at`.

- `space_id` con `ON DELETE CASCADE`; `expense_id` sin `ON DELETE`: borrar
  una compra con abonos se rechaza antes (RF-16), y borrar el espacio quita
  gastos y abonos en la misma sentencia (mismo razonamiento del plan 003).
- `amount`: `BigInteger` con `CheckConstraint("amount > 0")`. [RF-23]
- `reduces`: `String(11)` con `CheckConstraint("reduces IN ('installment', 'term')")`. [RF-25]
- `created_by`: clave foránea a `users.id`, como en los gastos. [RF-44]
- `UniqueConstraint(expense_id, period_start)`. [RF-24]

## Migración `0004_cards_and_installments`

| Qué hace | RF |
|---|---|
| Crea `cards`, `card_statements` y `prepayments`. | RF-45 |
| Con `batch_alter_table("expenses")`: añade `card_id`, `installments` y `first_due_start`, la clave foránea, el índice y `ck_expenses_card_purchase`. | RF-45 |

Solo añade. En SQLite, añadir una clave foránea y un `CHECK` hace que el
modo *batch* copie la tabla `expenses` entera (plan 008); los gastos
existentes cumplen el `CHECK` porque sus tres columnas nuevas son nulas.

## Cálculo sin base de datos

**`app/dates.py`**:

- `shift_period("2026-11", 2) == "2027-01"`; también con meses negativos.
- `first_due_period(spent_on, cutoff_day, due_day) -> str`: la regla de la
  decisión 12. El corte es el primer día de corte en `spent_on` o después,
  y el pago, el primer día límite estrictamente después del corte; un día
  que el mes no tiene pasa a ser el último del mes (`calendar.monthrange`).
  [RF-13]

**`app/installments.py`** (`dataclass` congeladas, sin SQLAlchemy):

    @dataclass(frozen=True)
    class PrepaymentPlan:     # abono que entra al cálculo
        period: str
        amount: int
        reduces: Literal["installment", "term"]

    @dataclass(frozen=True)
    class Installment:
        number: int           # 1, 2, …
        count: int            # total de cuotas, tras los abonos
        period: str
        capital: int
        interest: int
        balance_after: int    # saldo después de esta cuota (y de su abono)

    def split_capital(amount: int, count: int) -> list[int]: ...       # RF-19
    def interest(balance: int, rate_bp: int | None) -> int: ...        # RF-20
    def build_schedule(
        amount: int, count: int, rate_bp: int | None,
        first_period: str, prepayments: Sequence[PrepaymentPlan],
    ) -> list[Installment]: ...                                        # RF-19 a RF-26

`build_schedule` recorre los meses desde `first_period`:

1. El saldo empieza en `amount` y el capital de cada cuota sale de
   `split_capital(amount, count)`.
2. En cada mes: interés sobre el saldo (o `0` si `count == 1` o no hay
   tasa), se resta el capital de la cuota del saldo.
3. Si hay abono ese mes, se resta del saldo y se rehacen las cuotas que
   faltan:
   - `term`: cuotas con el capital de la siguiente cuota hasta cubrir el
     saldo; la última lleva el resto.
   - `installment`: `split_capital(saldo, cuotas_que_faltan)`.
4. Termina cuando el saldo llega a `0`. `count` de cada cuota es el total
   final, para que la cuota diga "2 de 4" tras un abono que baja el plazo.

La validación de un abono también es pura: `prepayment_limit(schedule,
period) -> int | None` da el `balance_after` de la cuota de ese mes sin su
abono, o `None` si ese mes no tiene cuota o no queda saldo. [RF-23]

## Cálculo con base de datos (`app/debts.py`)

Todas las consultas filtran por `space_id` (RF-43).

- `purchase_schedule(db, expense) -> list[Installment]`: lee la tasa de la
  tarjeta y los abonos de la compra y llama a `build_schedule`. [RF-21]
- `card_debts(db, space_id, period) -> list[CardDebtOut]`: tarjetas del
  espacio (activas y archivadas); de cada una, compras con
  `first_due_start` entre `shift_period(period, -47)` y `period`, sus
  cuotas del periodo, sus abonos del periodo y su valor real. Solo salen
  las tarjetas con algo en el periodo (decisión 21). [RF-34 a RF-36]
- `pay_off(db, card, period, user) -> list[Prepayment]`: con `FOR UPDATE`
  sobre las compras de la tarjeta con cuota en `period`, toma las que
  tienen saldo después de esa cuota (`prepayment_limit`), comprueba que
  ninguna tenga abonos en `period` o después, y crea un abono por cada
  saldo en la misma transacción. [RF-29, RF-30]
- `card_status(db, card, current_period) -> CardStatusOut`: compras de la
  tarjeta con cuotas desde `current_period`, saldo pendiente y la deuda de
  cada mes desde `current_period` hasta el último con cuota, abono o valor
  real. [RF-40]

`summary.build_summary` añade `debts=card_debts(...)` y los totales nuevos.

## Validación de entradas (`schemas.py`)

| Esquema | Campos y reglas | RF |
|---|---|---|
| `CardIn` | `name` (1 a 50 tras `strip`), `cutoff_day` y `due_day` (`StrictInt`, 1 a 31), `monthly_rate` (`Decimal` de 0,01 a 10 con hasta dos decimales, opcional; ni texto ni booleano) | RF-1 a RF-3 |
| `CardPatch` | Los mismos, opcionales; `null` se rechaza salvo en `monthly_rate`, que quita la tasa | RF-5 |
| `ExpenseIn` | Se añaden `card_id` (`StrictInt`) e `installments` (`StrictInt`, 1 a 48). Un `model_validator`: con `credit`, exige `card_id`, `description` y `category_id`, rechaza `budget_item_id` y pone `installments = 1` si falta; con `debit`, rechaza `card_id` e `installments` y aplica la regla de la 008 | RF-9 a RF-11 |
| `ExpensePatch` | Se añaden `card_id` e `installments`, sin `null`. Las reglas que cruzan campos las aplica la ruta | RF-14 a RF-17 |
| `PrepaymentIn` | `amount` (`Amount` de la 003), `period` (por defecto el actual), `reduces` (`"installment"` o `"term"`) | RF-22, RF-23 |
| `PayoffIn` | `period` (por defecto el actual) | RF-29 |
| `StatementIn` | `amount`: entero estricto de `0` a un billón | RF-31 |
| `SimulationIn` | `amount`, `installments` (por defecto 1) y `spent_on` (por defecto hoy, no futura), con los mismos tipos que `ExpenseIn` | RF-41 |

Mensajes:

- Crédito sin tarjeta: "Un gasto a crédito necesita la tarjeta con la que se
  pagó."
- Crédito con rubro: "Una compra con tarjeta no lleva rubro: cuenta en
  Deudas el mes en que se paga la tarjeta. Indica su categoría."
- Crédito sin descripción, o quitársela: "Una compra con tarjeta necesita
  una descripción: es el nombre con el que sus cuotas salen en Deudas."
- Débito con tarjeta o cuotas: "Un gasto a débito no lleva tarjeta ni
  cuotas."
- Cuotas fuera de rango: "Las cuotas deben ser un número entero de 1 a 48."
- Tarjeta de otro espacio o inexistente: `422` "La tarjeta no existe en este
  espacio."
- Tarjeta archivada: `422` "La tarjeta «Visa» fue eliminada. Para usarla de
  nuevo, créala otra vez con el mismo nombre."
- Aviso al eliminar (`message`): "Eliminaste «Visa». Sus cuotas pendientes
  siguen llegando a Deudas. Para volver a usarla en compras nuevas, créala
  de nuevo con el mismo nombre."
- Nombre repetido: `409` "Ya existe la tarjeta «Visa»."
- Compra con abonos: `409` "La compra tiene abonos: solo puedes cambiar su
  descripción y su categoría. Para cambiar lo demás o borrarla, borra
  primero sus abonos."
- Abono por encima del saldo: `422` "El saldo de la compra después de la
  cuota de 2026-12 es 1.000.000; el abono no puede pasar de ahí."
- Abono en un mes sin cuota o sin saldo después: `422` "La compra tiene
  cuotas de 2026-12 a 2027-05 y queda saldo después de las de 2026-12 a
  2027-04; elige uno de esos meses."
- Abono en un mes igual o anterior al último: `409` "La compra ya tiene un
  abono en 2027-02; un abono nuevo debe ser de un mes posterior."
- Abono a un gasto que no es compra con tarjeta: `422` "Solo se abona a una
  compra con tarjeta."
- Mes sin valor real: `404` "2026-12 no tiene valor del extracto para esta
  tarjeta."
- Pagar todo sin nada que saldar: `409` "La tarjeta «Visa» no tiene compras
  con saldo después de la cuota de 2026-12; no se creó ningún abono."
- Pagar todo con una compra que ya tiene abono en ese mes o después: `409`
  "«Compra TV» ya tiene un abono en 2027-02. Bórralo para pagar todo en
  2027-01; no se creó ningún abono."

Los montos de los mensajes van con separador de miles (`1.000.000`), con
una función `format_pesos` en `schemas.py`.

Salidas:

- `CardOut`: `id`, `name`, `cutoff_day`, `due_day`, `monthly_rate` (número
  JSON `1.89` o nulo; un `PlainSerializer` evita que Pydantic lo devuelva
  como texto), `deleted`.
- `CardDeletedOut`: `id`, `name`, `message`.
- `ExpenseOut`: se añaden `card_id`, `installments` y
  `first_due_period` (`YYYY-MM`), nulos si no es compra con tarjeta. [RF-18]
- `ScheduleOut` (plan de cuotas):

      {
        "expense_id": 12, "card_id": 1,
        "installments": [
          {"number": 1, "count": 6, "period": "2026-12", "capital": 200000,
           "interest": 22800, "amount": 222800, "balance_after": 1000000},
          ...
        ],
        "prepayments": [{"id": 3, "period": "2026-12", "amount": 400000, "reduces": "term"}]
      }

- `PrepaymentCreatedOut`: `{"prepayment": …, "schedule": ScheduleOut}`.
  [RF-22]
- `StatementOut`: `card_id`, `period`, `amount`.
- `PayoffOut`: `period`, `prepayments` (los abonos creados, con su compra y
  monto) y `debt` (la deuda de la tarjeta en ese mes, RF-35). [RF-29]
- `SimulationOut`: `first_due_period` y `installments` como en
  `ScheduleOut`. [RF-41]
- `SummaryOut` añade `debts` y `total.debts`:

      "debts": [
        {"card_id": 1, "name": "Visa", "deleted": false,
         "installments": [
           {"expense_id": 11, "name": "Mercado", "number": 1, "count": 1,
            "capital": 200000, "interest": 0, "amount": 200000},
           {"expense_id": 12, "name": "Compra TV", "number": 1, "count": 6,
            "capital": 200000, "interest": 22800, "amount": 222800}
         ],
         "prepayments": [{"id": 3, "expense_id": 12, "name": "Compra TV", "amount": 400000}],
         "estimated": 422800, "statement": 431500, "amount": 831500}
      ],
      "total": {"income": 5000000, "planned": 2331500, "debts": 831500,
                "spent_planned": 1500000, "spent_unplanned": 0,
                "spent": 2331500, "unassigned": 2668500, "balance": 2668500}

- `CardStatusOut`:

      {
        "card": {"id": 1, "name": "Visa", ...},
        "balance": 1000000,
        "purchases": [{"expense_id": 12, "name": "Compra TV", "amount": 1200000,
                       "spent_on": "2026-11-12", "count": 6, "next_number": 2,
                       "balance": 1000000}],
        "months": [{"period": "2027-01", "estimated": 219000, "statement": null,
                    "prepayments": 0, "amount": 219000}, ...]
      }

## Rutas

Todas cuelgan de `/spaces/{space_id}` y usan `member_space`; el test que
recorre las rutas con `{space_id}` las vigila sin cambios. [RF-42]

| Método y ruta | Qué hace | Respuestas | RF |
|---|---|---|---|
| `POST /cards` | Crea; si el nombre es de una archivada, la restaura | `201`; `200` restaurada; `409`; `422` | RF-1 a RF-3, RF-7 |
| `GET /cards` | Tarjetas activas en orden de creación | `200` | RF-4 |
| `PATCH /cards/{card_id}` | Edita nombre, días o tasa, activa o archivada | `200`; `404` "Tarjeta no encontrada."; `409`; `422` | RF-5, RF-8 |
| `DELETE /cards/{card_id}` | Archiva | `200` `CardDeletedOut`; `404` si no existe, es de otro espacio o ya está archivada | RF-6, RF-8 |
| `GET /cards/{card_id}/status` | Estado de la tarjeta | `200`; `404` | RF-40 |
| `POST /cards/{card_id}/simulate` | Simula una compra | `200` `SimulationOut`; `404`; `422` (también tarjeta archivada) | RF-41 |
| `PUT /cards/{card_id}/statements/{period}` | Escribe o reemplaza el valor real | `200`; `404`; `422` periodo o monto | RF-31 |
| `DELETE /cards/{card_id}/statements/{period}` | Quita el valor real | `204`; `404` | RF-32 |
| `POST /cards/{card_id}/payoff` | Paga todo en `period` | `201` `PayoffOut`; `404`; `409` sin saldo o con abono en conflicto; `422` periodo | RF-29, RF-30 |
| `POST /expenses`, `PATCH /expenses/{id}` | Reglas de compras con tarjeta | como en la 008; `409` compra con abonos | RF-9 a RF-17 |
| `DELETE /expenses/{id}` | Como en la 003 | `409` compra con abonos | RF-16 |
| `GET /expenses/{expense_id}/installments` | Plan de cuotas | `200` `ScheduleOut`; `404` | RF-21 |
| `POST /expenses/{expense_id}/prepayments` | Abona | `201` `PrepaymentCreatedOut`; `404` gasto; `409`; `422` | RF-22 a RF-28 |
| `DELETE /expenses/{expense_id}/prepayments/{prepayment_id}?confirm=true` | Borra un abono | `204`; `400` sin confirmación; `404` | RF-27 |
| `GET /summary` | Con Deudas y totales nuevos | como en la 008 | RF-36 a RF-39 |

**Editar un gasto** (`PATCH`), además de las reglas del plan 008. Primero
se arma el gasto como quedaría y luego se valida:

1. Si la compra tiene abonos y se envía algo que no sea `description` o
   `category_id`: `409` (RF-16).
2. Tipo de pago final `debit`: se quitan `card_id`, `installments` y
   `first_due_start`, y se aplican las reglas de rubro o categoría de la
   008. Si llegan `card_id` o `installments`, `422`.
3. Tipo de pago final `credit` con tarjeta (enviada o la que ya tenía): la
   tarjeta debe ser del espacio y estar activa si cambia; el gasto final no
   puede tener rubro (si lo tenía, la petición debe traer
   `budget_item_id: null`); `installments` es la enviada, la que tenía o
   `1`; la descripción final no puede quedar vacía (decisión 26).
4. Tipo de pago final `credit` sin tarjeta: solo vale si el gasto ya era a
   crédito sin tarjeta y la petición no trae tarjeta (RF-17); si no,
   `422` "Un gasto a crédito necesita la tarjeta…".
5. Si cambian `amount`, `spent_on`, `card_id` o `installments`, o el gasto
   pasa a ser compra con tarjeta, se recalcula `first_due_start` con los
   días actuales de la tarjeta (RF-14).

## Tests

- `test_dates.py`: `shift_period` y el criterio 1 con todos sus casos.
- `test_installments.py` (sin base de datos): criterios 2 y 3 sobre
  `build_schedule` y `prepayment_limit`; la suma de capital siempre es el
  monto, con varios montos y cuotas.
- `test_models.py`: los `CheckConstraint` nuevos (forma de compra con
  tarjeta, días, tasa, montos, `reduces`), los índices únicos y borrar un
  espacio con tarjetas, compras, abonos y extractos.
- `test_migrations.py`: criterio 11 y `compare_metadata` sin diferencias.
- `test_cards.py`: criterios 7, 8 y 10, valor real (`PUT` dos veces
  reemplaza; `DELETE` sin valor responde `404`), y `401` sin sesión.
- `test_expenses.py`: criterios 5, 6 y 9, las cinco reglas de "Editar un
  gasto" y el gasto devuelto con `card_id`, `installments` y
  `first_due_period`. Los tests que ya existen con `payment_type: credit`
  sin tarjeta cambian a `debit` o añaden una tarjeta, porque desde esta
  spec un gasto a crédito nuevo la exige (decisión 8); solo cambian sus
  datos de entrada, no lo que comprueban.
- `test_prepayments.py`: criterio 3 por HTTP, `GET /installments` de un
  gasto a débito responde `404`, abonar a uno responde `422`.
- `test_cards.py` (pagar todo): criterio 13.
- `test_summary.py` (sin HTTP) y `test_plan.py`: criterio 4, una tarjeta
  archivada con cuotas en el mes, un mes sin deudas con `debts` vacío.
- `test_isolation.py`: criterio 12.

## Riesgos y temas abiertos

- **La estimación no será igual al extracto.** El banco calcula el interés
  por días entre la compra y el corte, y cobra cuota de manejo y seguros.
  La decisión 4 lo resuelve con el valor real; la spec no promete exactitud.
- **Cambiar la tasa cambia meses pasados sin valor real** (decisión 14).
  Si molesta, la 011 puede sugerir escribir el valor real al cerrar un mes.
- **Cinco tests de `test_expenses.py` registran gastos a crédito sin
  tarjeta.** Desde esta spec se rechazan (decisión 8), así que esos tests
  pasan a usar una tarjeta o débito en la tarea de gastos, sin cambiar lo
  que comprueban.
- **La migración copia `expenses` en SQLite** (modo *batch*). Con una base
  local de cientos de gastos tarda nada; igual conviene la copia de la base
  antes de arrancar, como en la 008 (RF-38 de la 008).
- **El glosario de `AGENTS.md`** queda desactualizado hasta que se apruebe
  cambiarlo.

## Conceptos nuevos

- [Amortización](https://es.wikipedia.org/wiki/Amortizaci%C3%B3n): cómo se
  reparte el pago de una deuda en cuotas de capital e intereses; aquí con
  capital constante.
- [`Decimal`](https://docs.python.org/3/library/decimal.html): números
  decimales exactos en Python, sin los errores de redondeo de `float`.
- [Punto básico](https://es.wikipedia.org/wiki/Punto_b%C3%A1sico): la
  centésima parte de un punto porcentual; sirve para guardar la tasa como
  entero en la base de datos.
- [Ley 1555 de 2012](http://www.secretariasenado.gov.co/senado/basedoc/ley_1555_2012.html):
  derecho a abonar o pagar antes de tiempo y a elegir si baja la cuota o el
  plazo.
- Dato calculado frente a dato guardado: las cuotas se calculan al leer en
  lugar de guardarse, para que no puedan quedar desalineadas con la compra.
- [`dataclasses`](https://docs.python.org/3/library/dataclasses.html):
  estructuras simples para el cálculo puro, sin SQLAlchemy ni Pydantic.
- [`SELECT … FOR UPDATE`](https://docs.sqlalchemy.org/en/20/core/selectable.html#sqlalchemy.sql.expression.Select.with_for_update):
  bloquear una fila mientras se decide si se puede escribir.
- [Restricciones `CHECK`](https://www.postgresql.org/docs/current/ddl-constraints.html#DDL-CONSTRAINTS-CHECK-CONSTRAINTS)
  que cruzan varias columnas.
