# ADR 0012 — Plan del mes con rubros e ingresos

- Fecha: 2026-11-05
- Estado: aceptada
- Fase / spec: 1 / 008-rubros-e-ingresos
- Reemplaza a: ADR 0008

## Contexto

El ADR 0008 guardaba el presupuesto como "desde este mes, este monto" por
categoría, y descartó a propósito copiar el presupuesto del mes anterior:
obligaba a repetir un dato que casi nunca cambia.

Al prototipar la web (ADR 0010) el modelo cambió:

- Dentro de una categoría hay cosas que se planean por separado: en Hogar
  van el arriendo, la administración y el internet. Un monto por categoría
  no alcanza.
- Sin los ingresos del mes no se sabe cuánto queda sin asignar ni si el mes
  cierra en positivo.
- Planear es un paso de cada mes: se parte del anterior y se ajusta. Un
  presupuesto que se hereda solo no invita a revisarlo.
- Las categorías se tienen que poder eliminar sin perder la historia de los
  meses en que se usaron.

## Decisión

1. **Cada mes tiene su plan: rubros e ingresos.** Un rubro (`budget_items`)
   tiene nombre libre, una categoría y un monto planeado. Un ingreso
   (`incomes`) tiene nombre y monto. Los dos pertenecen a un espacio y a un
   mes, y ese mes no cambia.
2. **El plan se copia del mes anterior con una acción explícita**
   (`POST /plan/copy`), y solo hacia un mes sin rubros ni ingresos. La copia
   es todo o nada: nunca mezcla ni reemplaza.
3. **Un gasto planeado lleva su rubro y la categoría del rubro**; uno no
   planeado, solo su categoría. `expenses.category_id` sigue siendo
   obligatorio, y la API lo mantiene igual al del rubro, también cuando el
   rubro cambia de categoría.
4. **Eliminar una categoría la archiva** (`categories.deleted_at`). Deja de
   ofrecerse, pero los rubros y gastos que la tenían la conservan, y crearla
   de nuevo con el mismo nombre la restaura. La copia del plan omite sus
   rubros.
5. **Los nombres de categorías, rubros e ingresos se comparan sin
   mayúsculas ni tildes** (la regla del ADR 0006): "Acción" = "accion".
6. **Los presupuestos de la 004 se convierten en rubros** del mes desde el
   que regían, con el nombre de su categoría (migración `0003`, ADR 0011).

## Alternativas descartadas

- **Mantener el presupuesto con vigencia del ADR 0008 y añadir rubros
  debajo**: dos formas de planear que hay que conciliar en cada resumen.
- **Un rubro permanente con un monto por mes**: renombrarlo cambiaría todos
  los meses, también los pasados, y son dos tablas.
- **Copiar el plan solo al consultar un mes vacío**: una consulta escribiría
  datos, y habría que decidir hasta qué mes futuro rellenar. Es el mismo
  problema que el ADR 0008 vio al descartar la copia.
- **Dejar `category_id` nulo en los gastos planeados** y deducirlo del
  rubro: cambia una columna obligatoria de `main` y obliga a reescribir cada
  consulta por categoría.
- **Borrar de verdad las categorías**: dejaría rubros y gastos sin categoría
  (principio 8).

## Consecuencias

- **Lo que el ADR 0008 resolvía ahora es un paso explícito**: el día 1 un mes
  nuevo no tiene plan hasta que alguien lo copia o lo crea. La pantalla de
  planear (011) ofrece "Copiar del mes anterior".
- El resumen muestra sin asignar (ingresos − planeado) y balance (ingresos −
  gastado), que la 004 no podía calcular.
- La API mantiene dos columnas de acuerdo (`category_id` y la categoría del
  rubro); la base de datos no lo comprueba, igual que no comprueba que la
  categoría sea del espacio.
- La tabla de rubros crece una fila por rubro y por mes, no por cambio.
- Qué aprendí: la misma alternativa (copiar el mes anterior) puede ser mala
  para un modelo y buena para otro. El ADR 0008 la descartó porque el
  presupuesto casi no cambiaba; con rubros e ingresos, revisar el plan cada
  mes es justo lo que se busca.
