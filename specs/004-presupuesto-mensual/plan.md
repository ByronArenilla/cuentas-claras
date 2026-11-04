# Plan 004 — Presupuesto mensual

- Spec: `spec.md` (estado: aprobada)
- Servicio afectado: `services/api`
- Estado: aprobado

La spec añade una tabla nueva, `budgets`, y no cambia ninguna tabla que ya
esté en `main`, así que `create_all` sigue bastando (ADR 0004). Reutiliza
el reloj y los periodos de `app/dates.py` (plan 003) y la validación del
monto de los gastos.

## Decisiones técnicas

| Decisión | Elegido | Por qué |
|---|---|---|
| Cómo se guarda la vigencia | Una fila por cambio: (`category_id`, `starts_on`, `amount`) | Es la decisión 1 tal cual: la fila dice "desde este mes, este monto". Se descartó una fila por mes, que obliga a escribir filas para meses que nadie ha tocado y a decidir hasta qué mes futuro rellenar. Deja el ADR 0008. |
| Tipo del periodo de inicio | Columna `Date` `starts_on`, siempre el día 1 del mes | Se compara con el `start` que ya devuelve `dates.period_bounds`, igual que `spent_on` en el listado de gastos. Se descartó un texto `YYYY-MM`: se ordena bien, pero la base de datos lo trataría como texto cualquiera. |
| Quitar el presupuesto | Fila con `amount` nulo | La decisión 4 dice que quitar es fijar "sin monto" desde un periodo. Borrar la fila no serviría: el mes volvería a heredar el presupuesto anterior en lugar de quedarse sin presupuesto. |
| Monto | `BigInteger` nulo con `CheckConstraint("amount IS NULL OR amount > 0")`, y `check_amount` de la 003 en el esquema | Mismas reglas y mismo tope que el monto de un gasto (decisión 4). La restricción es la última defensa, como en `expenses`. |
| `amount` en la petición | Obligatorio, aunque admite `null` | Un cuerpo `{}` o con el campo mal escrito no debe quitar el presupuesto por accidente: quitarlo exige escribir `"amount": null`. |
| Fijar dos veces el mismo mes | `UniqueConstraint(space_id, category_id, starts_on)` y "buscar y actualizar, o insertar" | RF-5: el índice único impide dos filas aunque lleguen dos peticiones a la vez. Si el `INSERT` choca, se hace `rollback` y se actualiza la fila que creó la otra petición: gana la última, como en cualquier `PUT`. Se descartó `INSERT ... ON CONFLICT`, que en SQLAlchemy depende del motor (`sqlite.insert` frente a `postgresql.insert`). |
| Presupuesto vigente | Se leen en Python las filas del espacio con `starts_on <= start`, ordenadas por `starts_on`, y la última de cada categoría gana | Un espacio tiene pocas filas (una por cambio). Se descartó una subconsulta correlacionada o una función de ventana: hacen lo mismo en SQL, pero son más difíciles de leer y de probar. |
| Gastado | Una consulta `SUM(amount) ... GROUP BY category_id` con el filtro `start <= spent_on < end` de la 003, y `int()` sobre cada suma | RF-12 con la misma regla de periodo. En PostgreSQL, `SUM` de un `bigint` devuelve `numeric`, que llega a Python como `Decimal`; el `int()` mantiene el principio 6 cuando cambie la base de datos. |
| Dónde vive el cálculo | Módulo nuevo `app/summary.py` | Principio 10: la vigencia y el resumen se prueban con una sesión de base de datos, sin HTTP. Las rutas solo validan, llaman y devuelven. |
| Periodo en la consulta | Dependencia `requested_period` en `app/deps.py`, usada por el resumen y por el listado de gastos | El listado de la 003 ya lee `?period=`, usa el actual por defecto y responde `422` si está mal escrito. Moverlo a una dependencia evita copiar esa lógica. No cambia el comportamiento del listado: lo vigilan sus tests. |
| Rutas | Un solo módulo `app/routers/budgets.py` con prefijo `/spaces/{space_id}` | El test que recorre las rutas con `{space_id}` lee `module.router` de cada módulo: un módulo con un router mantiene ese patrón. |

## Dependencias

Ninguna nueva.

## Estructura de archivos

    services/api/
      app/
        deps.py                   + requested_period                   [RF-15]
        models.py                 + Budget                             [RF-5, RF-6, RF-20]
        schemas.py                + BudgetIn, BudgetOut, SummaryOut    [RF-2, RF-7, RF-8, RF-16]
        summary.py                nuevo: vigencia, gastado y resumen   [RF-3, RF-4, RF-6, RF-11 a RF-14]
        routers/
          budgets.py              nuevo: fijar o quitar y resumen
          expenses.py             el listado usa requested_period
        main.py                   monta el router de presupuestos
      tests/
        test_models.py            + restricciones y cascada de budgets
        test_summary.py           nuevo: cálculo sin HTTP
        test_budgets.py           nuevo: rutas
        test_isolation.py         + presupuestos y resumen en los criterios de aislamiento
    docs/adr/0008-presupuesto-vigente-desde-un-periodo.md
    README.md                     + sección de presupuesto (al cerrar la spec)

## Modelo de datos

**`budgets`** — `id`, `space_id`, `category_id`, `starts_on`, `amount`,
`updated_at`.

- `space_id`: clave foránea a `spaces.id` con `ON DELETE CASCADE`. Borrar
  un espacio borra sus presupuestos y nunca los de otro. [RF-20]
- `category_id`: clave foránea a `categories.id`, **sin** `ON DELETE`, por
  la misma razón que en `expenses` (plan 003): al borrar el espacio, la
  misma sentencia borra categorías y presupuestos sin chocar, y el día que
  se borren categorías no se llevará presupuestos por delante sin una
  decisión. [RF-9, RF-20]
- `starts_on`: `Date`, el día 1 del periodo desde el que rige. Solo lo
  escribe la API, a partir de `dates.period_bounds`. [RF-1, RF-3]
- `amount`: `BigInteger`, nulo si la fila quita el presupuesto, con
  `CheckConstraint("amount IS NULL OR amount > 0")`. [RF-6, RF-7]
- `updated_at`: `UTCDateTime`, con `default` y `onupdate`: cuándo se fijó
  por última vez ese mes. No es un historial; solo ayuda a depurar.
  [principio 7]
- `UniqueConstraint(space_id, category_id, starts_on)`. Su índice también
  sirve para leer las filas de un espacio en el resumen. [RF-5]

No guarda quién lo fijó: la spec deja fuera el historial de cambios.
Ninguna tabla existente cambia.

## Cálculo (`app/summary.py`)

Funciones que reciben la sesión, el `space_id` y el periodo, sin nada de
HTTP:

- `effective_budgets(db, space_id, start) -> dict[int, int | None]`:
  presupuesto vigente de cada categoría que tiene alguna fila con
  `starts_on <= start`. Recorre las filas por `starts_on` ascendente y cada
  una pisa a la anterior de su categoría. Una categoría sin filas no
  aparece; una cuya última fila es nula aparece con `None`. Las dos
  significan "sin presupuesto". [RF-3, RF-4, RF-6]
- `spent_by_category(db, space_id, start, end) -> dict[int, int]`: la suma
  de RF-12, con `int()` sobre cada valor. [RF-12, RF-16]
- `build_summary(db, space_id, period) -> SummaryOut`: recorre las
  categorías del espacio en orden de `id` (el de la 002) y arma cada fila y
  los totales. [RF-11, RF-13, RF-14]

Para cada categoría, `remaining = budget - spent` si `budget` no es nulo;
si no, `remaining` es nulo. En los totales, `budget` es la suma de los
presupuestos no nulos, o nulo si no hay ninguno; `spent` suma todo, también
lo gastado en categorías sin presupuesto (decisión 2); `remaining` sigue la
misma regla que en cada categoría.

Todas las consultas filtran por `space_id`, incluida la de categorías.
[RF-18]

## Validación de entradas (`schemas.py`)

`BudgetIn`:

| Campo | Regla | RF |
|---|---|---|
| `period` | Texto que `dates.period_bounds` acepta. Si no se envía, `dates.period_of(dates.today())`. Mensaje: "El periodo debe tener el formato AAAA-MM, por ejemplo 2026-10.", el mismo del listado de gastos. | RF-2, RF-8, RF-10 |
| `amount` | Obligatorio. `null` quita el presupuesto; si no, `check_amount` de la 003: `type(value) is int` y `1 <= amount <= 1_000_000_000_000`. | RF-6, RF-7 |

No se pone ningún límite al periodo más allá de que sea un mes válido
(decisión 3).

Salidas:

- `BudgetOut`: `category_id`, `period` (`YYYY-MM`) y `amount` (nulo si se
  quitó). [RF-1]
- `SummaryOut`:

      {
        "period": "2026-10",
        "categories": [
          {"category_id": 2, "name": "Comida", "budget": 400000, "spent": 412000, "remaining": -12000},
          {"category_id": 3, "name": "Transporte", "budget": null, "spent": 38000, "remaining": null}
        ],
        "total": {"budget": 400000, "spent": 450000, "remaining": -50000}
      }

  A diferencia de `ExpenseOut`, cada fila lleva el nombre de la categoría:
  el resumen es justo lo que el bot y la web van a mostrar. [RF-11, RF-16]

## Rutas

Las dos cuelgan de `/spaces/{space_id}` y usan `member_space`: espacio
ajeno o inexistente, `404` "Espacio no encontrado."; sin sesión, `401`. El
test que recorre las rutas con `{space_id}` las vigila sin cambios. [RF-17]

| Método y ruta | Qué hace | RF |
|---|---|---|
| `PUT /spaces/{space_id}/budgets/{category_id}` | Fija o quita el presupuesto de la categoría desde `period`: `200` con `BudgetOut` | RF-1 a RF-10 |
| `GET /spaces/{space_id}/summary?period=YYYY-MM` | Resumen del periodo, por defecto el actual en `TZ` | RF-11 a RF-16 |

- **`PUT` y no `POST`**: enviar dos veces la misma petición deja el mismo
  estado, que es lo que pide RF-5. [RF-5]
- **Categoría de la ruta**: se busca por `id` **y** por el `space_id` que
  ya validó `member_space`. Una inexistente y una de otro espacio, aunque
  quien llama sea miembro de los dos, responden igual: `404` "Categoría no
  encontrada.". Aquí es `404` y no `422` como al registrar un gasto, porque
  la categoría está en la ruta, no en el cuerpo. [RF-9]
- **Periodo mal escrito en el resumen**: `requested_period` responde `422`
  con el mismo mensaje que el listado de gastos. [RF-15]
- Ninguna ruta lista las filas de `budgets` por separado: lo que el bot y
  la web necesitan es el presupuesto vigente, y ya va en el resumen.

## Tests

- `test_models.py`: la `CheckConstraint` (rechaza `0` y negativos, admite
  nulo), el índice único (dos filas iguales chocan; el mismo mes en otra
  categoría o en otro espacio no), y que borrar un espacio con categorías,
  gastos y presupuestos no choca con las claves foráneas y no toca otro
  espacio.
- `test_summary.py`, con la sesión del `conftest.py` y sin HTTP:
  `effective_budgets` con los criterios 1 y 2 (heredar, cambiar desde un
  mes, quitar desde un mes, mes anterior al primer presupuesto);
  `spent_by_category` con el criterio 3 (bordes del mes); `build_summary`
  con categorías sin presupuesto, sin gastos, excedidas y los totales,
  incluido el caso sin ningún presupuesto.
- `test_budgets.py`: un test por RF de las rutas. Entre ellos el criterio 4
  (reloj fijado el 31 de octubre a las 20:00 en Bogotá), el criterio 5
  (montos inválidos), el criterio 8 (dos miembros) y que `{}` o un cuerpo
  sin `amount` responde `422` y no quita nada.
- `test_isolation.py`: criterios 6, 7 y 9.
- `test_expenses.py`: sin cambios; debe seguir en verde tras mover la
  lectura del periodo a `requested_period`.

## Base de datos local

**No hace falta borrarla.** `create_all` crea `budgets` al arrancar y no
toca las tablas existentes (ADR 0004).

## Riesgos y temas abiertos

- **Fijar el presupuesto solo se puede con la API.** Ninguna spec planeada
  lo ofrece en el bot ni en la web. La spec lo anota para la 007.
- **Cambiar un mes pasado cambia su resumen**, y también los meses
  siguientes que lo heredan (decisiones 1 y 3). Es lo que se decidió, pero
  la 007 debería decir "desde este mes en adelante" al fijarlo.
- **El resumen no dice desde qué mes rige cada presupuesto.** Si la web
  necesita mostrarlo, se añade un campo en la 007.
- **`starts_on` siempre es día 1 solo porque lo escribe la API.** La base de
  datos no lo comprueba: una restricción así se escribe distinto en SQLite
  y en PostgreSQL. Basta mientras solo la API escriba en la base de datos
  (principio 9).
- **La comprobación de que la categoría es del espacio vive en la API**,
  igual que en los gastos (plan 003). La spec que añada el borrado de
  categorías tendrá que revisarla también aquí.

## Conceptos nuevos

- [`PUT` e idempotencia](https://developer.mozilla.org/es/docs/Web/HTTP/Methods/PUT) — repetir la misma petición deja el mismo resultado.
- [Agregaciones con `func.sum` y `group_by` en SQLAlchemy](https://docs.sqlalchemy.org/en/20/tutorial/data_select.html#aggregate-functions-with-group-by-having) — sumar por grupos en una sola consulta.
- [Tipo que devuelve `SUM` en PostgreSQL](https://www.postgresql.org/docs/current/functions-aggregate.html) — `sum(bigint)` devuelve `numeric`, que Python recibe como `Decimal`.
- [Dependencias con parámetros de consulta en FastAPI](https://fastapi.tiangolo.com/tutorial/dependencies/) — reutilizar la lectura y validación de `?period=` en varias rutas.
- [`UniqueConstraint` de SQLAlchemy](https://docs.sqlalchemy.org/en/20/core/constraints.html#unique-constraint) — la base de datos impide dos filas con los mismos valores aunque lleguen a la vez.
