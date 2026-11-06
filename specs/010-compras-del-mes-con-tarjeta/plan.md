# Plan 010 — Compras del mes con tarjeta

- Spec: `spec.md` (estado: aprobada)
- Servicio afectado: `services/api`
- Estado: aprobado (2026-11-06)

Cambia la lógica de la 009 en tres sitios: la forma de una compra con
tarjeta (columna nueva y su `CHECK`), las reglas al registrar y editar, y
el cálculo de Deudas. Una migración (`0005`) añade la columna y marca como
deuda todo lo que ya existe. La decisión queda en el
[ADR 0014](../../docs/adr/0014-compras-del-mes-con-tarjeta.md), que cambia
la decisión 1 del 0013.

## Decisiones técnicas

| Decisión | Elegido | Por qué |
|---|---|---|
| Cómo se guarda | Columna `expenses.is_debt` (`Boolean`, nula): `true` deuda, `false` gasto del mes, nula sin tarjeta | RF-4. Un booleano dice exactamente la pregunta del formulario. Se descartó un texto (`kind`): solo hay dos clases. |
| Nombre en la API | Campo `is_debt` en `ExpenseIn`, `ExpensePatch` y `ExpenseOut` | Mismo nombre que la columna. Opcional al registrar (decisión 8). |
| Forma en la base de datos | `ck_expenses_card_purchase` pasa a exigir `is_debt` no nulo en una compra con tarjeta y nulo sin ella, `is_debt OR installments = 1` (varias cuotas, deuda), y rubro solo si `NOT is_debt` | Última defensa, como en la 009 (decisiones 1, 6 y 7). |
| Migración | `0005`: añade `is_debt`, pone `true` en toda fila con `card_id`, y reemplaza la `CHECK` en modo *batch* | RF-12, decisión 9. El `UPDATE` va entre añadir la columna y crear la `CHECK` nueva, porque esta exige el valor. |
| Lo gastado por categoría | `spent_by_category` cuenta los gastos sin tarjeta y los gastos del mes con tarjeta (`card_id IS NULL OR NOT is_debt`) | RF-6. `spent_by_item` no cambia: una deuda nunca tiene rubro. |
| Deudas de una tarjeta | `CardMonth` separa `installments` (cuotas de deudas) y `month_expenses` (gastos del mes con primera cuota en el periodo); `amount` es la deuda del mes y `to_pay` lo que hay que pagar | RF-7 y RF-8. Un gasto del mes tiene una sola cuota, sin intereses (decisión 15 de la 009), así que su monto es su cuota. |
| Deuda con valor real | `max(statement - gastos del mes, 0) + abonos` | Decisiones 4 y 10. |
| A pagar | `(statement si existe, si no cuotas de deudas + gastos del mes) + abonos` | RF-8. Con valor real, el extracto ya incluye los gastos del mes. |
| Totales | `TotalSummaryOut` añade `cards_to_pay`; `debts`, `planned` y `spent` no cambian de fórmula | RF-9. |
| Nombre de un gasto del mes | Descripción, o nombre del rubro, o nombre de la categoría | RF-10. Un gasto con rubro no lleva descripción desde la web (decisión 10 de la 011). |
| Validación al registrar | `ExpenseIn.payment_rules`: a crédito, `is_debt` se fija (`true` si hay varias cuotas, `false` por defecto a 1 cuota) y según eso se aplican las reglas de la 008 (gasto del mes) o las de la 009 (deuda) | RF-1 a RF-3. La regla de "rubro o categoría" de la 008 se reutiliza tal cual. |
| Validación al editar | `payment_changes` arma la compra como quedaría (cuotas e `is_debt` finales) y aplica la misma decisión; si el rubro final existe, comprueba el mes con `check_same_month` | RF-5. |

## Archivos

    services/api/app/
      models.py                     + Expense.is_debt; CHECK nueva
      migrations/versions/0005_debt_flag.py                       [RF-12]
      schemas.py                    is_debt en gastos; month_expenses y
                                    to_pay en Deudas; cards_to_pay; estado
      routers/expenses.py           reglas del gasto del mes o deuda [RF-1 a RF-5]
      debts.py                      CardMonth con gastos del mes y a pagar
                                    [RF-7, RF-8, RF-10, RF-11]
      summary.py                    categorías con gastos del mes; total a pagar
                                    [RF-6, RF-9]
    services/api/tests/
      test_models.py, test_migrations.py, test_expenses.py, test_summary.py,
      test_cards.py, test_prepayments.py
    docs/adr/0014-compras-del-mes-con-tarjeta.md
    docs/adr/0013-compras-con-tarjeta-cuentan-al-pagar.md   estado: decisión 1 cambiada por el 0014
    README.md

## Esquemas

- `ExpenseIn`: `is_debt: StrictBool | None = None`. En `payment_rules`, a
  crédito:
  - si `installments > 1`: `is_debt = False` se rechaza ("Una compra a
    varias cuotas siempre es deuda."); si no, `is_debt = True`;
  - a 1 cuota: `is_debt` por defecto `False`;
  - deuda: las reglas de la 009 (descripción, categoría, sin rubro);
  - gasto del mes: la regla de la 008 (rubro o categoría, exactamente uno).
  - A débito, `is_debt` se rechaza ("Un gasto a débito no lleva tarjeta ni
    cuotas.").
- `ExpensePatch`: `is_debt: StrictBool | None`, sin `null`.
- `ExpenseOut`: + `is_debt: bool | None`.
- `MonthExpenseOut`: `expense_id`, `name`, `amount`.
- `CardDebtOut`: + `month_expenses: list[MonthExpenseOut]` y `to_pay: int`.
- `TotalSummaryOut`: + `cards_to_pay: int`.
- `CardPurchaseStatusOut`: + `is_debt: bool`.
- `CardMonthOut`: + `month_expenses: int` y `to_pay: int`.

Mensajes nuevos:

- "Una compra a varias cuotas siempre es deuda."
- Deuda con rubro: "Una deuda no lleva rubro: cuenta en Deudas el mes en que
  se paga la tarjeta. Indica su categoría." (reemplaza el de la 009)
- Deuda sin descripción: el de la 009, que habla de "una compra con
  tarjeta", pasa a "Una deuda necesita una descripción: es el nombre con el
  que sus cuotas salen en Deudas."

## Editar (`payment_changes`)

Sobre las reglas del plan 009 ("Editar un gasto"), con tarjeta final:

1. `installments` final > 1 → `is_debt` final `true`; si la petición manda
   `is_debt: false`, `422`.
2. `is_debt` final = el enviado, o el que tenía, o (si pasa a ser compra con
   tarjeta) `false` a 1 cuota.
3. Deuda: sin rubro final (si lo tenía, la petición manda
   `budget_item_id: null`), con descripción final.
4. Gasto del mes: `item_changes` de la 008 decide rubro y categoría, con la
   fecha final.

## Deudas (`debts.py`)

    @dataclass(frozen=True)
    class CardMonth:
        card; installments; month_expenses; prepayments; statement
        estimated = suma de cuotas de deudas
        month_total = suma de gastos del mes
        debt_base = estimated si statement es None, si no max(statement - month_total, 0)
        amount = debt_base + abonos                  # deuda del mes   [RF-7]
        to_pay = (statement o estimated + month_total) + abonos       [RF-8]

`window_purchases` sigue leyendo todas las compras de la tarjeta; el reparto
se hace por `is_debt`. El estado de la tarjeta (`card_status`) usa las
mismas cuentas y marca cada compra.

## Tests

- `test_models.py`: la `CHECK` acepta gasto del mes con rubro a 1 cuota y
  rechaza: `is_debt` nulo con tarjeta, `is_debt` sin tarjeta, varias cuotas
  sin deuda, deuda con rubro.
- `test_migrations.py`: criterio 7.
- `test_expenses.py`: criterios 1, 4 y 5. Los tests de la 009 que registran
  compras a 1 cuota y las tratan como deuda mandan `is_debt: true`.
- `test_summary.py`: criterios 2 y 3, y que los tests de Deudas de la 009
  siguen pasando con sus compras marcadas como deuda.
- `test_cards.py`: criterio 6; pagar todo y estado con gastos del mes.

## Riesgos

- **Muchos tests de la 009 registran compras a 1 cuota** que daban por
  deuda. Con el valor por defecto nuevo pasarían a gasto del mes, así que
  tienen que mandar `is_debt: true`. Se hace en un commit aparte, sin
  cambiar lo que comprueban.
- **La web en borrador (011)** dice "el campo lo define la 010": al
  retomarla, su plan usa `is_debt`.

## Conceptos nuevos

- Ninguno de infraestructura. El cambio repite el patrón de la 008:
  [*expandir*](https://martinfowler.com/bliki/ParallelChange.html) con una
  columna nueva, rellenarla y endurecer la restricción.
