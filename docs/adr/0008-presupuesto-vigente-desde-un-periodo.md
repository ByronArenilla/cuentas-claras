# ADR 0008 — El presupuesto rige desde un periodo

- Fecha: 2026-11-04
- Estado: reemplazada por ADR 0012
- Fase / spec: 1 / 004-presupuesto-mensual

## Contexto

La spec 004 añade el presupuesto: el monto máximo que un espacio quiere
gastar en una categoría cada mes. El glosario de `AGENTS.md` lo define
"para un periodo", pero no dice qué pasa al empezar un mes nuevo.

- Un hogar fija su presupuesto una vez y lo ajusta de vez en cuando. Casi
  nunca cambia de un mes al siguiente.
- El resumen del mes (`/resumen` en la 006, el dashboard en la 007) tiene
  que tener presupuesto desde el día 1, sin que nadie lo vuelva a escribir.
- Cambiar el presupuesto no debe reescribir lo que ya pasó: si en
  noviembre Comida sube a 500.000, el resumen de octubre sigue con su
  presupuesto de entonces.
- También hay que poder quitar el presupuesto de una categoría desde un
  mes (decisión 4 de la spec 004).

## Decisión

Cada cambio de presupuesto se guarda como **una fila "desde este periodo,
este monto"** en la tabla `budgets` (`category_id`, `starts_on`, `amount`).
El presupuesto vigente de una categoría en un periodo es el de la última
fila con `starts_on` igual o anterior a ese periodo.

- `starts_on` es el día 1 del periodo, para compararlo con los límites de
  `dates.period_bounds` igual que `spent_on` (ADR 0007).
- **Quitar el presupuesto es otra fila, con `amount` nulo.** No se borra
  la fila anterior: borrarla haría que el mes volviera a heredar el
  presupuesto de antes en lugar de quedarse sin presupuesto.
- Un índice único sobre (`space_id`, `category_id`, `starts_on`) deja una
  sola fila por categoría y periodo. Fijar dos veces el mismo mes
  reemplaza el monto.

## Alternativas descartadas

- **Una fila por mes, que empieza vacía cada mes**: obliga a repetir cada
  mes un dato que casi nunca cambia, y el día 1 el resumen sale sin
  presupuesto hasta que alguien lo fija.
- **Una fila por mes y una operación para copiar la del mes anterior**:
  resuelve la repetición, pero sigue dependiendo de que alguien se acuerde
  de copiar, y hay que decidir qué pasa si el mes anterior también estaba
  vacío. Rellenarlo automáticamente obligaría a escribir filas para meses
  que nadie ha tocado y a decidir hasta qué mes futuro llegar.
- **Un único presupuesto por categoría, sin periodo**: el más simple, pero
  cambiarlo reescribe el resumen de todos los meses pasados.

## Consecuencias

- La tabla crece una fila por cambio, no por mes. El presupuesto vigente se
  calcula leyendo las filas del espacio en orden y quedándose con la última
  de cada categoría (`app/summary.py`), sin subconsultas.
- **Cambiar un mes pasado cambia también los meses que lo heredan**, hasta
  el siguiente cambio. Es lo que pide la decisión 3 de la spec 004, pero la
  web (007) debería decir "desde este mes en adelante" al fijarlo.
- Para saber desde cuándo rige un presupuesto hay que mirar sus filas; el
  resumen de hoy no lo muestra.
- Qué aprendí: guardar los cambios y no los estados evita rellenar datos
  repetidos, a cambio de calcular el estado de cada mes al consultarlo.
