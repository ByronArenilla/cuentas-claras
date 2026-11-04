# Plan 003 — API de gastos

- Spec: `spec.md` (estado: aprobada)
- Servicio afectado: `services/api`
- Estado: aprobado

La spec añade una tabla nueva, `expenses`, y no cambia ninguna tabla que
ya esté en `main`, así que `create_all` sigue bastando (ADR 0004). Es la
primera spec que trabaja con días y meses, así que también deja el reloj y
el cálculo de periodos que usará la spec 004.

## Decisiones técnicas

| Decisión | Elegido | Por qué |
|---|---|---|
| Tipo del monto | `BigInteger` | El tope es un billón (decisión 7). Un `Integer` de 32 bits llega a unos 2.100 millones, que en PostgreSQL no alcanzaría. En SQLite son iguales. |
| Validar el monto | Validador `mode="before"` que exige `type(value) is int` | Pydantic convierte por defecto `20000.0` y `"20000"` en `20000`, y RF-3 prohíbe aceptar o redondear. Comprobar el tipo exacto también rechaza `true`, que en Python es un `int`. El mensaje queda en español, como en el resto de la API. |
| Fecha del gasto | Columna `Date` llamada `spent_on` | Es un día calendario (decisión 2). El nombre evita `date`, que tapa el tipo de Python. Deja el ADR 0007 (ver "Fechas y periodos"). |
| "Hoy" y el periodo | Módulo `app/dates.py` con `now()`, `today()` y las funciones de periodo, usando `zoneinfo` con `settings.tz` | Una sola fuente de "hoy" en `TZ` (principio 7) que la spec 004 reutiliza. Los tests fijan el reloj sustituyendo `dates.now` con `monkeypatch`, sin dependencias nuevas. |
| Categoría del gasto | La ruta comprueba que la categoría sea del espacio | Para que lo garantizara la base de datos haría falta una clave foránea compuesta, y eso cambia la tabla `categories`, que ya está en `main` (ADR 0004). Como las categorías no se borran ni cambian de espacio, la comprobación previa no tiene condición de carrera. |
| Editar | `PATCH` con los campos enviados (`model_fields_set`) | RF-13: solo cambia lo que se envía. Pydantic distingue entre un campo no enviado y uno enviado como `null`, que es justo lo que pide la decisión 8. |
| Confirmar el borrado | Parámetro `confirm=true` en el `DELETE` | Es el mismo patrón de parámetro de consulta que el borrado de espacios (plan 001). A diferencia de un espacio, un gasto no tiene un nombre que repetir, así que basta con un `true` explícito (decisión 3). |
| Quién lo registró | `created_by` con el `id` del usuario | La spec no dice si un miembro puede ver el correo de los demás, y la 001 nunca lo muestra. El `id` cumple RF-8 sin revelar nada. Cómo se muestra el autor queda para `007-dashboard-web`. |

## Dependencias

Ninguna nueva. `zoneinfo` es de la biblioteca estándar de Python y usa la
base de datos de zonas horarias del sistema.

## Estructura de archivos

    services/api/
      app/
        config.py                 valida que TZ sea una zona horaria real
        dates.py                  nuevo: now(), today(), periodos      [RF-2, RF-6, RF-9 a RF-11]
        models.py                 + Expense                            [RF-1, RF-20, RF-21]
        schemas.py                + ExpenseIn, ExpensePatch, ExpenseOut [RF-3, RF-4, RF-6, RF-7, RF-13]
        routers/
          expenses.py             nuevo: registrar, consultar, listar, editar y borrar
        main.py                   monta el router de gastos
      tests/
        test_config.py            + TZ inválida
        test_dates.py             nuevo: periodos y "hoy" en TZ
        test_models.py            + restricciones y cascada de expenses
        test_expenses.py          nuevo
        test_isolation.py         + gastos en los criterios de aislamiento
    docs/adr/0007-fecha-del-gasto-como-dia-calendario.md
    README.md                     + sección de gastos (al cerrar la spec)

## Modelo de datos

**`expenses`** — `id`, `space_id`, `category_id`, `created_by`, `amount`,
`payment_type`, `spent_on`, `description`, `created_at`.

- `space_id`: clave foránea a `spaces.id` con `ON DELETE CASCADE`. Borrar
  un espacio borra sus gastos y nunca los de otro espacio. [RF-21]
- `category_id`: clave foránea a `categories.id`, **sin** `ON DELETE`. La
  acción por defecto (`NO ACTION`) comprueba la referencia al final de la
  sentencia: al borrar un espacio, la misma sentencia borra en cascada sus
  categorías y sus gastos, así que no queda ninguna referencia rota. Se
  descartó `CASCADE`, porque cuando exista el borrado de categorías se
  llevaría gastos por delante (principio 8). Se descartó `RESTRICT`,
  porque comprueba fila a fila y podría frenar el borrado del espacio
  según el orden en que la base de datos borre las filas. [RF-5, RF-21]
- `created_by`: clave foránea a `users.id`, como en `invitations`. Salir de
  un espacio solo borra la membresía, así que el gasto conserva su autor.
  [RF-1, RF-14, RF-20]
- `amount`: `BigInteger`, con `CheckConstraint("amount > 0")` como última
  defensa si algo salta la validación de la API. [RF-3]
- `payment_type`: `String(6)` con
  `CheckConstraint("payment_type IN ('credit', 'debit')")`. [RF-4]
- `spent_on`: `Date`. [RF-2, RF-6, RF-9]
- `description`: `String(200)`, nula si no hay. [RF-7]
- `created_at`: `UTCDateTime`, como el resto de tablas. [principio 7]
- Índice sobre (`space_id`, `spent_on`): es el filtro del listado por
  periodo y el que usará el resumen de la 004. [RF-9]

Ninguna tabla existente cambia.

## Fechas y periodos (`app/dates.py`)

Funciones puras o casi puras, probadas sin HTTP (principio 10):

- `now() -> datetime`: el instante actual en UTC. Es el único punto que
  los tests sustituyen.
- `today() -> date`: `now()` convertido a `ZoneInfo(settings.tz)`, y su
  día. Se descartó `date.today()`, que usa la zona del proceso y no la
  configurada, aunque en local coincidan. [RF-2, RF-6]
- `period_of(day: date) -> str`: el periodo `YYYY-MM` de un día. [RF-10]
- `period_bounds(period: str) -> tuple[date, date]`: primer día del mes y
  primer día del mes siguiente, o `ValueError` si el texto no es un mes
  válido con formato `YYYY-MM`. El listado filtra
  `start <= spent_on < next`, así que no depende de cuántos días tenga el
  mes. [RF-9, RF-11]

**`TZ` inválida.** Hoy `config.py` solo comprueba que `TZ` exista. Con
este plan también comprueba que `ZoneInfo(TZ)` funcione, y si no, la API no
arranca y lo dice. Sin esta comprobación, una `TZ` mal escrita dejaría
arrancar la API y cada petición de gastos fallaría con `500`. Es el mismo
criterio de RF-33 de la 001: mejor un error claro al inicio.

**ADR 0007.** El principio 7 dice que las fechas se guardan en UTC. Un día
calendario no tiene hora ni zona, así que hay que dejar escrito cómo se
cumple el principio: los instantes (`created_at`) van en UTC, y "hoy", que
es el valor por defecto de `spent_on`, se calcula en `TZ`. El ADR recoge
también la alternativa descartada (un instante en UTC) y la consecuencia:
cambiar `TZ` no mueve gastos de mes.

## Validación de entradas (`schemas.py`)

`ExpenseIn` (registrar) y `ExpensePatch` (editar) comparten las funciones
de validación. Los mensajes van en español con `PydanticCustomError`, como
el nombre de un espacio o de una categoría:

| Campo | Regla | RF |
|---|---|---|
| `amount` | `type(value) is int` y `1 <= amount <= 1_000_000_000_000`. El mensaje indica el máximo. | RF-3 |
| `payment_type` | `credit` o `debit`. El mensaje nombra los dos valores admitidos. | RF-4 |
| `category_id` | Entero. Que exista en el espacio lo comprueba la ruta. | RF-5 |
| `spent_on` | Texto `YYYY-MM-DD` y no posterior a `dates.today()`. Si no se envía al registrar, `dates.today()`. | RF-2, RF-6 |
| `description` | Sin espacios alrededor, y vacía pasa a `None`. Como máximo 200 caracteres. | RF-7 |

En `ExpensePatch` todos los campos son opcionales. Un validador solo se
ejecuta para los campos enviados, así que:

- Un campo que no se envía no cambia (RF-13).
- `"description": null`, `""` o solo espacios quitan la descripción
  (decisión 8).
- `null` en cualquier otro campo se rechaza con `422`: un gasto no puede
  quedarse sin monto, tipo de pago, categoría ni fecha.

Ninguno de los dos esquemas admite `space_id` ni `created_by`. Si llegan en
el cuerpo, se ignoran. [RF-14]

## Rutas

Todas cuelgan de `/spaces/{space_id}/expenses` y usan `member_space`:
espacio ajeno o inexistente, `404` "Espacio no encontrado."; sin sesión,
`401`. El test que recorre las rutas con `{space_id}` las vigila sin
cambios. [RF-19]

| Método y ruta | Qué hace | RF |
|---|---|---|
| `POST /spaces/{space_id}/expenses` | Registra un gasto: `201` con el gasto | RF-1 a RF-7 |
| `GET /spaces/{space_id}/expenses?period=YYYY-MM` | Gastos del periodo, por `spent_on` descendente y, a igual día, por `id` descendente. Sin `period`, el actual | RF-9 a RF-11 |
| `GET /spaces/{space_id}/expenses/{expense_id}` | Un gasto | RF-8, RF-12 |
| `PATCH /spaces/{space_id}/expenses/{expense_id}` | Cambia los campos enviados: `200` con el gasto | RF-13 a RF-15 |
| `DELETE /spaces/{space_id}/expenses/{expense_id}?confirm=true` | Borra el gasto: `204` | RF-16 a RF-18 |

- **Respuesta** (`ExpenseOut`): `id`, `amount`, `payment_type`,
  `category_id`, `spent_on`, `description`, `created_by`, `created_at`. El
  nombre de la categoría no se repite en cada gasto: el cliente lo tiene en
  la lista de RF-4 de la 002. [RF-8]
- **Gasto de la ruta**: una dependencia `space_expense` busca el gasto por
  `id` **y** por el `space_id` que ya validó `member_space`. Un gasto
  inexistente y uno de otro espacio, aunque quien llama sea miembro de
  los dos, responden igual: `404` "Gasto no encontrado.". [RF-12]
- **Categoría de otro espacio**: se busca por `id` y `space_id`, y si no
  está responde `422` "La categoría no existe en este espacio.". Una
  categoría de otro espacio y una inexistente reciben el mismo mensaje.
  [RF-5]
- **Periodo mal escrito**: `422` "El periodo debe tener el formato AAAA-MM,
  por ejemplo 2026-10.". [RF-11]
- **Borrar sin `confirm=true`**: `400` "Para borrar el gasto, confirma con
  confirm=true.", sin borrar nada. El `DELETE` filtra por `id` y por
  `space_id`, así que nunca toca otra fila. [RF-17, RF-18]

## Tests

- `test_dates.py`: `period_bounds` con meses de 28, 29, 30 y 31 días, con
  diciembre (el mes siguiente es enero de otro año) y con textos inválidos
  (`2026-13`, `2026-1`, `26-10`, `octubre`). `today()` con el reloj fijado
  en el 1 de noviembre a la 01:00 UTC devuelve el 31 de octubre en Bogotá.
- `test_config.py`: una `TZ` que no existe impide arrancar y el error la
  nombra.
- `test_models.py`: las dos `CheckConstraint`, la cascada al borrar el
  espacio y que borrar un espacio con gastos no choca con la clave foránea
  de `category_id`.
- `test_expenses.py`: un test por RF. Entre ellos, el criterio 4 (reloj
  fijado el 31 de octubre a las 20:00 en Bogotá, que ya es 1 de noviembre
  en UTC: un gasto sin fecha cae en `2026-10`), el criterio 5 (montos con
  decimales, negativos, cero, mayores que el máximo, como texto o
  booleanos), el criterio 3 (un miembro edita el gasto de otro) y el
  criterio 7 (tras salir del espacio, sus gastos siguen ahí con su autor).
- `test_isolation.py`: criterios 1, 2 y 6, con gastos reales.

## Base de datos local

**Esta vez no hace falta borrarla.** `create_all` crea las tablas que
faltan y no toca las existentes (ADR 0004). Al arrancar, `make run-api`
crea `expenses` y conserva los usuarios, espacios y categorías que ya hay.

## Riesgos y temas abiertos

- **La comprobación de que la categoría es del espacio vive en la API, no
  en la base de datos.** Basta mientras las categorías no se borren ni
  cambien de espacio. La spec que añada el borrado de categorías tendrá
  que revisarlo.
- **Las imágenes de Docker *slim* no siempre traen la base de datos de
  zonas horarias.** Si `ZoneInfo("America/Bogota")` falla dentro del
  contenedor, la comprobación de `config.py` lo dirá al arrancar, y
  `009-contenedores` tendrá que instalar `tzdata`.
- **Cambiar `TZ` no recalcula nada.** Los gastos guardan un día, no un
  instante, así que siguen en su mes. Solo cambia qué día es "hoy" (ADR
  0007).
- **Quién lo registró se muestra como un `id`.** Mostrar el correo o un
  nombre a los demás miembros es una decisión de privacidad que ninguna
  spec ha tomado.
- **El orden de `/ultimos` (006)** puede necesitar ordenar por
  `created_at` en lugar de por `spent_on`. Ya lo anota la spec.

## Conceptos nuevos

- [`zoneinfo`](https://docs.python.org/3/library/zoneinfo.html) — zonas horarias de la base de datos IANA en la biblioteca estándar.
- [Validadores de Pydantic en modo `before`](https://docs.pydantic.dev/latest/concepts/validators/#field-before-validator) — se ejecutan antes de la conversión de tipos, así que ven el valor tal como llegó en el JSON.
- [Campos enviados en Pydantic (`model_fields_set`)](https://docs.pydantic.dev/latest/api/base_model/#pydantic.BaseModel.model_fields_set) — cómo distinguir "no enviado" de "enviado como `null`".
- [`PATCH` frente a `PUT`](https://developer.mozilla.org/es/docs/Web/HTTP/Methods/PATCH) — actualizar solo una parte de un recurso.
- [Acciones de claves foráneas en SQLite](https://www.sqlite.org/foreignkeys.html#fk_actions) — en qué se diferencian `NO ACTION`, `RESTRICT` y `CASCADE`.
- [`CheckConstraint` de SQLAlchemy](https://docs.sqlalchemy.org/en/20/core/constraints.html#check-constraint) — reglas que la propia base de datos hace cumplir.
- [`monkeypatch` de pytest](https://docs.pytest.org/en/stable/how-to/monkeypatch.html) — sustituir una función durante un test, aquí para fijar el reloj.
