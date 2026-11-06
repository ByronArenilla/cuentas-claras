# Tareas 010 — Compras del mes con tarjeta

- Spec: `spec.md` (aprobada) · Plan: `plan.md` (aprobado)
- Regla: una tarea por vez, primero los tests y luego el código. Al
  terminarla, marcarla, ejecutar `make test` y `make lint`.

## [x] T1 — Marca de deuda y migración `0005`
`Expense.is_debt`, la `CHECK` nueva y la migración `0005_debt_flag`.

- Test primero (`test_models.py`, `test_migrations.py`):
  - Un gasto del mes con tarjeta a 1 cuota se guarda con y sin rubro.
  - La base rechaza: `is_debt` nulo con tarjeta, `is_debt` sin tarjeta,
    varias cuotas con `is_debt` falso y deuda con rubro.
  - Criterio 7: una base en `0004` con compras con tarjeta a 1 y a 6 cuotas
    queda en `head` con las dos como deuda y `compare_metadata` sin
    diferencias.
  - Los ayudantes de los tests de la 009 que crean compras directamente en
    la base ponen `is_debt=True`.
- Hecho cuando: los tests pasan y ninguna ruta cambió de comportamiento.
- RF: RF-12.

## [x] T2 — Registrar y editar como gasto del mes o deuda
`is_debt` en los esquemas y las reglas de `payment_rules` y
`payment_changes`.

- Primero, en un commit aparte: los tests de la 009 que registran compras a
  1 cuota como deuda por HTTP mandan `is_debt: true`.
- Test primero (`test_expenses.py`):
  - Criterio 1, parte de registro: el "Mercado" a 1 cuota con rubro, sin
    `is_debt`, se guarda como gasto del mes con la categoría del rubro.
  - Criterio 4: varias cuotas con `is_debt: false`, deuda con rubro o sin
    descripción, gasto del mes con rubro y categoría, sin ninguno o con un
    rubro de otro mes: `422` y nada guardado.
  - Un gasto del mes sin rubro lleva categoría y descripción opcional.
  - Un gasto a débito con `is_debt` se rechaza.
  - `ExpenseOut` trae `is_debt` (nulo a débito).
  - Criterio 5: editar el "Mercado" a deuda sin quitar el rubro se rechaza;
    con `budget_item_id: null` y descripción pasa; a 3 cuotas queda como
    deuda; los "Zapatos" pasan a gasto del mes en el rubro "Mercado".
- Hecho cuando: los tests pasan y los de la 003, la 008 y la 009 siguen en
  verde.
- RF: RF-1 a RF-5.

## [x] T3 — Resumen: gastos del mes, deuda y a pagar
`spent_by_category`, `CardMonth` con gastos del mes y a pagar, Deudas y
totales.

- Test primero (`test_summary.py`):
  - Criterio 1, parte del resumen: el "Mercado" suma en su rubro y en
    Comida en noviembre y no está en Deudas.
  - Criterio 2: Deudas de diciembre con cuotas, gastos del mes, deuda
    372.800, a pagar 572.800 y los totales.
  - Criterio 3: con valor real, con abono y con un valor real menor que los
    gastos del mes.
  - El nombre de un gasto del mes: descripción, rubro o categoría (RF-10).
  - Los tests de Deudas de la 009 siguen en verde.
- Hecho cuando: los tests pasan.
- RF: RF-6 a RF-10.

## [x] T4 — Estado de la tarjeta y pagar todo
`card_status` con gastos del mes; `PayoffOut` sin cambios de reglas.

- Test primero (`test_cards.py`):
  - Criterio 6: el saldo pendiente incluye el "Mercado" marcado como gasto
    del mes; diciembre trae deuda y a pagar.
  - Pagar todo no crea abonos a un gasto del mes.
- Hecho cuando: los tests pasan.
- RF: RF-11; decisión 11.

## [x] T5 — ADR 0014
`docs/adr/0014-compras-del-mes-con-tarjeta.md`, y el 0013 marcado con su
decisión 1 cambiada por el 0014.

- Test primero: no aplica, es documentación.
- Hecho cuando: el ADR existe con la plantilla y el plan lo cita.
- RF: ninguno; principio 4.

## [ ] T6 — Cierre: README y roadmap
- `README.md`: en "Tarjetas y compras a cuotas", gasto del mes o deuda,
  `is_debt`, a pagar y la deuda con valor real; los ejemplos `curl`
  probados contra la API.
- Repasar los nueve criterios de validación.
- Proponer el cambio del glosario de `AGENTS.md` y aplicarlo solo con
  aprobación explícita.
- `docs/roadmap.md`: marcar `010-compras-del-mes-con-tarjeta` como terminada
  y dejar `011-app-web` como spec activa.

- Test primero: no aplica.
- Hecho cuando: `make test` y `make lint` están en verde.
- RF: cierra la spec.
