# Tareas 009 — Tarjetas y cuotas

- Spec: `spec.md` (aprobada) · Plan: `plan.md` (aprobado)
- Regla: una tarea por vez, primero los tests y luego el código. Al
  terminarla, marcarla, ejecutar `make test` y `make lint`, y detenerse.
- Orden: primero el cálculo puro (T1), después el esquema (T2), las rutas
  (T3 a T9), el aislamiento (T10) y el cierre (T11 y T12). Cada tarea deja
  la API funcionando.

## [x] T1 — Mes de pago y plan de cuotas (cálculo puro)
`dates.py`: `shift_period` y `first_due_period`. `app/installments.py`:
`PrepaymentPlan`, `Installment`, `split_capital`, `interest`,
`build_schedule` y `prepayment_limit`. Nada de base de datos ni HTTP.

- Test primero (`test_dates.py` y `test_installments.py`):
  - `shift_period`: `2026-11` + 2 → `2027-01`; `2026-01` − 1 → `2025-12`.
  - Criterio 1: los seis meses de pago de la decisión 12, incluidos el día
    de corte, el pago en el mismo mes, febrero y el corte 31.
  - Criterio 2: la "Compra TV" (1.200.000, 6 cuotas, 190 puntos básicos,
    primera en `2026-12`) con capital de 200.000 e intereses de 22.800 a
    3.800; 1.000.000 a 3 cuotas da 333.334, 333.333 y 333.333; 1 cuota y
    tasa nula dan interés `0`.
  - Para varios montos y cuotas (1 a 48), la suma del capital es el monto.
  - El interés redondea el medio peso hacia arriba.
  - Criterio 3 sin HTTP: abono de 400.000 en `2026-12` bajando el plazo y
    bajando la cuota, con los valores de la spec; abono por el saldo
    completo cancela la compra; `count` de cada cuota es el total tras el
    abono.
  - `prepayment_limit`: `1.000.000` en `2026-12`; `None` en `2026-11` y en
    `2027-05`.
- Hecho cuando: los tests pasan.
- RF: RF-13, RF-19, RF-20, RF-23, RF-25, RF-26.

## [x] T2 — Modelos y migración `0004` (expandir)
`Card`, `CardStatement`, `Prepayment` y las columnas `card_id`,
`installments` y `first_due_start` de `Expense`, con sus restricciones e
índices, y la migración `0004_cards_and_installments`.

- Test primero (`test_models.py` y `test_migrations.py`):
  - Una tarjeta, un valor del extracto y un abono válidos se guardan;
    `name_key` se rellena.
  - La base de datos rechaza: días fuera de 1 a 31, tasa `0` o `1001`,
    valor del extracto negativo, abono `0`, `reduces` distinto de
    `installment` o `term`.
  - `ck_expenses_card_purchase` rechaza una compra con tarjeta a débito,
    con rubro, sin `installments`, con 49 cuotas o sin `first_due_start`, y
    un gasto sin tarjeta con `installments`.
  - Dos tarjetas con nombres equivalentes en el mismo espacio chocan; dos
    abonos de la misma compra y mes chocan; dos valores del extracto de la
    misma tarjeta y mes chocan.
  - Borrar un espacio con tarjetas, compras, abonos y extractos no choca
    con las claves foráneas y no toca otro espacio.
  - Criterio 11: una base en `0003` con gastos a crédito y a débito queda
    en `head` con los gastos iguales y sin tarjeta, y `compare_metadata` no
    ve diferencias.
- Hecho cuando: los tests pasan y ninguna ruta cambió de comportamiento.
- RF: RF-45; base de RF-2, RF-3, RF-11, RF-24, RF-31 y RF-44.

## [x] T3 — Rutas de tarjetas
`app/routers/cards.py` con `POST`, `GET`, `PATCH` y `DELETE` de tarjetas,
montado en `main.py`. `CardIn`, `CardPatch`, `CardOut` y `CardDeletedOut`.

- Test primero (`test_cards.py`):
  - Crear responde `201` con `CardOut`; sin tasa, `monthly_rate` es nulo.
  - Validación: nombre vacío o de 51 caracteres, días `0`, `32`, `"5"` y
    `5.0`, tasa `0`, `10.01`, `1.895`, `"1.89"` y `true` se rechazan
    con `422`.
  - La tasa `1.89` se guarda como `189` y sale como el número `1.89`.
  - Criterio 7, parte de tarjetas: "visa" choca con "Visa" (`409`,
    nombrando la que existe); eliminar responde `200` con el aviso y la
    tarjeta deja de salir en el listado; crear "VISA" la restaura con el
    mismo `id`, nombre, días y tasa (`200`).
  - Editar cambia solo lo enviado; `monthly_rate: null` quita la tasa;
    `null` en los demás campos se rechaza. Una tarjeta archivada se puede
    editar.
  - El listado sale en orden de creación y sin archivadas.
  - Una tarjeta inexistente o de otro espacio responde `404` "Tarjeta no
    encontrada." al editar y al eliminar; eliminar una archivada, también.
  - Sin sesión, `401`.
- Hecho cuando: los tests pasan y el test que recorre las rutas con
  `{space_id}` sigue en verde.
- RF: RF-1 a RF-8.

## [x] T4 — Compras con tarjeta
`ExpenseIn`, `ExpensePatch` y `ExpenseOut` con `card_id`, `installments`
y `first_due_period`, y las rutas de gastos con las reglas de "Editar un
gasto" del plan (salvo la 1, de abonos, que es de T6).

- Primero, en un commit aparte: los cinco tests de `test_expenses.py` que
  registran gastos a crédito sin tarjeta pasan a usar débito o una
  tarjeta, sin cambiar lo que comprueban.
- Test primero (`test_expenses.py`):
  - Registrar a crédito con tarjeta guarda `installments` (por defecto 1) y
    `first_due_period` según la decisión 12, y devuelve los tres campos; a
    débito, salen nulos.
  - Criterio 6: crédito sin tarjeta, con rubro, sin descripción (o solo
    con espacios) o sin categoría; `description: null` en el `PATCH` de una
    compra con tarjeta; débito con
    tarjeta o con cuotas; cuotas `0`, `49`, `"3"`, `3.0` y `true`; tarjeta
    archivada (con su mensaje); tarjeta de otro espacio aunque quien llama
    sea miembro de los dos. Todo `422` y sin guardar nada.
  - Editar: cambiar monto, fecha, tarjeta o cuotas recalcula
    `first_due_period`; cambiar solo descripción o categoría, no.
  - Criterio 8, primera parte: con la Visa en corte 25, la "Compra TV" del
    12 de noviembre va a `2026-12`; tras cambiar el corte a 5, sigue en
    `2026-12`; al cambiarle la fecha al 3 de noviembre, pasa a `2026-11`
    (corte 5 de noviembre, pago 10 de noviembre), cuando con el corte
    viejo habría seguido en `2026-12`.
  - Débito → crédito: exige tarjeta, descripción (la que ya tenía o una
    enviada) y, si tenía rubro, `budget_item_id: null` en la misma
    petición. Crédito con tarjeta → débito: quita
    tarjeta y cuotas y queda no planeado con su categoría, o planeado si se
    envía un rubro.
  - Criterio 5, parte de gastos: un gasto a crédito sin tarjeta creado
    directamente en la base se edita sin tarjeta (monto, rubro, fecha) y,
    al ponerle tarjeta, pasa a ser compra con tarjeta.
  - El listado por periodo sigue usando la fecha de la compra.
- Hecho cuando: los tests pasan y los de la 003, la 006 y la 008 siguen en
  verde.
- RF: RF-9 a RF-15, RF-17, RF-18.

## [x] T5 — Plan de cuotas y valor real del extracto
`app/debts.py` con `purchase_schedule`; `app/routers/prepayments.py` con
`GET /expenses/{expense_id}/installments`; en `cards.py`, `PUT` y
`DELETE /cards/{card_id}/statements/{period}`.

- Test primero (`test_prepayments.py` y `test_cards.py`):
  - El plan de cuotas de la "Compra TV" por HTTP trae las 6 cuotas del
    criterio 2, con `balance_after`, y `prepayments` vacío.
  - El de un gasto a débito o a crédito sin tarjeta responde `404` "Este
    gasto no es una compra con tarjeta; no tiene cuotas.".
  - Cambiar la tasa de la tarjeta cambia los intereses del plan de cuotas
    (decisión 14).
  - `PUT` de un valor responde `200`; un segundo `PUT` del mismo mes lo
    reemplaza; `0` se acepta; `-1`, decimales, texto y más de un billón se
    rechazan; `period=2026-13` responde `422`. Funciona con una tarjeta
    archivada.
  - `DELETE` responde `204` y, sin valor en ese mes, `404`.
  - Copiar el plan del mes no copia el valor real (RF-33).
- Hecho cuando: los tests pasan.
- RF: RF-20, RF-21, RF-31 a RF-33.

## [x] T6 — Abonos
`POST` y `DELETE /expenses/{expense_id}/prepayments` en
`app/routers/prepayments.py`, con `SELECT … FOR UPDATE` sobre la compra; en
`expenses.py`, la regla 1 de "Editar un gasto" y el borrado rechazado de
una compra con abonos.

- Test primero (`test_prepayments.py` y `test_expenses.py`):
  - Criterio 3 por HTTP: abonar 400.000 en `2026-12` responde `201` con el
    abono y el plan nuevo, bajando el plazo y bajando la cuota; 1.000.000
    cancela la compra; 1.000.001, `2026-11` y `2027-05` responden `422` con
    su mensaje; un segundo abono en `2026-12` o uno en `2027-01` con otro
    en `2027-02` responden `409`.
  - Sin `period`, con el reloj fijado, el abono es del mes actual.
  - Abonar a un gasto a débito o a crédito sin tarjeta responde `422`; a
    una compra con tarjeta archivada, funciona.
  - Borrar sin `confirm=true` responde `400` y no cambia nada; con él,
    `204`, y el plan de cuotas vuelve al original.
  - Criterio 9: una compra con abonos acepta cambios de descripción y
    categoría; cambiar el monto, la fecha, la tarjeta, las cuotas o el tipo
    de pago responde `409` sin cambiar nada; borrarla responde `409` hasta
    borrar sus abonos.
  - Un abono nunca cambia el gasto (RF-28).
- Hecho cuando: los tests pasan.
- RF: RF-16, RF-22 a RF-28.

## [x] T7 — Pagar todo
`debts.pay_off` y `POST /cards/{card_id}/payoff` en `cards.py`, con
`PayoffIn` y `PayoffOut`. Se apoya en los abonos de T6.

- Test primero (`test_cards.py`):
  - Criterio 13, parte de abonos: con la "Compra TV", el "Mercado" y los
    "Zapatos" (30 de noviembre, después del corte), pagar todo en
    `2026-12` responde `201` con un solo abono, de 1.000.000, a la "Compra
    TV", con `reduces = "term"`; el plan de cuotas de la TV termina en
    diciembre; el "Mercado" y los "Zapatos" no tienen abonos.
  - Pagar todo otra vez en `2026-12` responde `409` sin compras con saldo,
    y no crea nada.
  - Con un abono de la "Compra TV" en `2027-02`, pagar todo en `2027-01`
    responde `409` nombrando la compra, y ninguna otra compra de la
    tarjeta recibe abono (todo o nada).
  - Sin `period`, con el reloj fijado, paga el mes actual.
  - Funciona con una tarjeta archivada; con una inexistente o de otro
    espacio responde `404`.
  - Los abonos creados se borran uno a uno con `confirm=true` y la compra
    vuelve a tener sus cuotas.
- Hecho cuando: los tests pasan.
- RF: RF-29, RF-30.

## [x] T8 — Deudas en el resumen
`debts.card_debts`; `summary.py` con Deudas, `spent_by_category` sin
compras con tarjeta y los totales nuevos; `SummaryOut` y `TotalSummaryOut`
ampliados.

- Test primero (`test_summary.py` sin HTTP y `test_plan.py`):
  - Criterio 4 completo: noviembre sin las compras; diciembre con la Visa,
    sus dos cuotas, deuda de 422.800, Hogar sin la cuota de la TV, y los
    totales; luego con valor real (431.500), con abono (831.500) y sin
    valor real (822.800).
  - Criterio 5, parte del resumen: un gasto a crédito sin tarjeta cuenta en
    su rubro el día del gasto; al ponerle tarjeta, sale de ahí y aparece en
    Deudas en su mes de pago.
  - Criterio 7, parte del resumen: una tarjeta archivada con cuotas en el
    mes sale en Deudas marcada como eliminada.
  - Criterio 8, segunda parte: con la tasa en 2 %, cambian las cuotas
    estimadas de un mes sin valor real y no la deuda de un mes con valor
    real.
  - Cada cuota se nombra con la descripción de su compra.
  - Criterio 13, parte del resumen: tras pagar todo en `2026-12`, la deuda
    de la Visa en diciembre es 1.422.800 y en enero solo trae "Zapatos · 1
    de 1" por 150.000.
  - Un mes sin deudas trae `debts` vacío y `total.debts` en `0`; todos los
    montos son `int`; pedir el resumen no crea nada.
- Hecho cuando: los tests pasan y los del resumen de la 008 siguen en
  verde (sin compras con tarjeta, sus totales no cambian).
- RF: RF-34 a RF-39.

## [ ] T9 — Estado de la tarjeta y simulación
`debts.card_status`; `GET /cards/{card_id}/status` y
`POST /cards/{card_id}/simulate`.

- Test primero (`test_cards.py`):
  - Criterio 10: con el reloj en el 15 de enero de 2027, el estado de la
    Visa da saldo 1.000.000, la "Compra TV" con siguiente cuota 2 de 6 y
    saldo 1.000.000, sin el "Mercado", y la deuda de enero a mayo.
  - Un valor real o un abono en un mes futuro sale en `months`.
  - El estado de una tarjeta archivada funciona.
  - La simulación de la "Compra TV" da `2026-12` y las cuotas del criterio
    2, y no crea ningún gasto; con una tarjeta archivada, cuotas `49` o una
    fecha futura responde `422`.
  - Una tarjeta inexistente o de otro espacio responde `404` en las dos
    rutas.
- Hecho cuando: los tests pasan.
- RF: RF-40, RF-41.

## [ ] T10 — Aislamiento y ciclo de vida
`test_isolation.py`: amplía los criterios con tarjetas, compras con
tarjeta, abonos, pagar todo, extractos, estado y simulación. Si T3 a T9
están bien hechas, no debería hacer falta código nuevo; si algún test
falla, se corrige aquí.

- Test primero:
  - Criterio 12: Ana y Bea, en espacios distintos, no pueden crear,
    editar, eliminar ni ver tarjetas, abonos, valores del extracto, estado
    o simulación de la otra, ni pagar todo en sus tarjetas; todo responde `404` y nada de una aparece en
    las Deudas de la otra.
  - Una tarjeta del espacio B no sirve para una compra del espacio A
    aunque quien llama sea miembro de los dos.
  - Borrar un espacio borra sus tarjetas, abonos y extractos y no los de
    otro; tras salir Bea de un espacio, sus tarjetas y abonos siguen en el
    resumen de Ana.
- Hecho cuando: los tests pasan.
- RF: RF-8, RF-12, RF-42 a RF-44.

## [ ] T11 — ADR 0013
`docs/adr/0013-compras-con-tarjeta-cuentan-al-pagar.md`: las compras con
tarjeta cuentan el mes del pago (también a 1 cuota) y no en su categoría;
la deuda cuenta sola en planeado y gastado; capital fijo con interés sobre
el saldo; cuotas calculadas al leer y no guardadas; mes de pago guardado
al registrar; tasa decimal en la API y en puntos básicos en la base de
datos; descripción obligatoria en las compras con tarjeta; abonos que bajan
cuota o plazo, y pagar todo como un abono por compra.
Alternativas descartadas de la spec y del plan.

- Test primero: no aplica, es documentación.
- Hecho cuando: el ADR existe con la plantilla `0000-plantilla.md` y el
  plan lo cita.
- RF: ninguno; principio 4.

## [ ] T12 — Cierre: README y validación
- Comprobar con una **copia** de la base local que `make run-api` la migra
  a `0004` y conserva sus gastos.
- `README.md`: tarjetas, compras con tarjeta y su mes de pago, plan de
  cuotas, abonos, pagar todo, valor real del extracto, Deudas en el
  resumen, estado y simulación, con ejemplos `curl`; los ejemplos de gastos a crédito pasan
  a llevar tarjeta.
- Repasar los catorce criterios de validación de la spec.
- Proponer el cambio del glosario de `AGENTS.md` (tarjeta, cuota, abono,
  deuda, valor del extracto y gasto) y aplicarlo solo con aprobación
  explícita.
- `docs/roadmap.md`: marcar `009-tarjetas-y-cuotas` como terminada y dejar
  `010-app-web` como spec activa.

- Test primero: no aplica, es documentación y validación.
- Hecho cuando: `make test` y `make lint` están en verde y los ejemplos
  `curl` del README funcionan contra `make run-api`.
- RF: cierra la spec.
