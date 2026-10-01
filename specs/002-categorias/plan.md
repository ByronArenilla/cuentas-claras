# Plan 002 — Categorías

- Spec: `spec.md` (estado: aprobada)
- Servicio afectado: `services/api`
- Estado: aprobado

La spec añade una tabla nueva y cambia lo que ocurre al crear un espacio.
No toca ninguna tabla que ya esté en `main`, así que `create_all` sigue
bastando (ADR 0004).

## Decisiones técnicas

| Decisión | Elegido | Por qué |
|---|---|---|
| Comparar nombres (decisión 4) | Columna `name_key` con el nombre normalizado e índice único sobre (`space_id`, `name_key`) | La base de datos impide el duplicado aunque lleguen dos peticiones a la vez (RF-8). Se descartó comparar en SQL: `lower()` de SQLite solo entiende ASCII y no quita tildes. Deja ADR 0006. |
| Dónde se calcula `name_key` | Validador de SQLAlchemy en el modelo (`@validates("name")`) | Toda categoría, predefinida o nueva, recibe su clave al asignar el nombre. Nadie puede olvidarse de calcularla, tampoco una futura spec que renombre categorías. |
| Normalización | Biblioteca estándar: `str.casefold` y `unicodedata` | Sin dependencias nuevas. Ver "Normalización del nombre". |
| Crear las predefinidas | Función `add_default_categories(db, space_id)`, llamada desde el registro y desde la creación de espacios antes del `commit` | Cada creación de espacio ocurre ya en una transacción: las categorías entran en la misma y o se guarda todo o nada (RF-1). Sigue el patrón de `issue_invitation`, que un router expone y otro reutiliza. |
| Orden de la lista | `ORDER BY id` | El `id` crece con cada inserción, así que es el orden de creación (decisión 5) sin columnas extra. |

## Dependencias

Ninguna nueva. `unicodedata` es de la biblioteca estándar de Python.

## Estructura de archivos

    services/api/
      app/
        models.py                 + Category y category_key()          [RF-2, RF-8]
        schemas.py                + CategoryIn, CategoryOut             [RF-6, RF-7]
        routers/
          categories.py           nuevo: listar, crear, predefinidas    [RF-1, RF-4, RF-5, RF-8]
          auth.py                 el registro llama a add_default_categories    [RF-1]
          spaces.py               crear espacio llama a add_default_categories  [RF-1]
        main.py                   monta el router de categorías
      tests/
        test_models.py            + clave normalizada e índice único
        test_categories.py        nuevo
        test_isolation.py         + categorías en los criterios de aislamiento
    docs/adr/0006-clave-normalizada-para-nombres-de-categoria.md
    README.md                     + sección de categorías (al cerrar la spec)

## Modelo de datos

**`categories`** — `id`, `space_id`, `name`, `name_key`, `created_at`.

- `space_id`: clave foránea a `spaces.id` con `ON DELETE CASCADE`. Borrar
  un espacio borra sus categorías y la base de datos no deja tocar las de
  otro espacio. [RF-2, RF-11]
- `name`: `String(50)`, tal como se escribió y sin espacios alrededor.
  [RF-6, RF-7]
- `name_key`: `String`, sin límite de longitud, porque `casefold` puede
  alargar el texto (`ß` → `ss`). Nunca sale en una respuesta: solo sirve
  para comparar. [RF-8]
- `UniqueConstraint("space_id", "name_key")`: el mismo nombre puede
  repetirse en espacios distintos (RF-9), pero no dentro de uno (RF-8).

Ninguna tabla existente cambia. Los espacios de la base de datos local
quedan sin categorías, y por eso se recrea (decisión 3, última tarea).

## Normalización del nombre

`category_key(name: str) -> str`, en `models.py`, es una función pura y se
prueba sin HTTP (principio 10):

1. Quita los espacios alrededor y aplica `casefold()`, que es como
   `lower()` pero pensado para comparar textos en cualquier idioma.
2. Descompone el texto con `unicodedata.normalize("NFD", ...)`: `é` pasa a
   ser `e` seguida de un acento suelto (una "marca combinante").
3. Descarta las marcas combinantes, salvo la virgulilla (`U+0303`) cuando
   va detrás de una `n`. Así `é`, `ü` y `á` pierden su marca, pero `ñ`
   sigue siendo `ñ` (decisión 4).
4. Recompone con `unicodedata.normalize("NFC", ...)`.

Ejemplos que se prueban: `" Comida "`, `"comida"` y `"Cómida"` dan la misma
clave; `"Educacion"` y `"Educación"` también; `"Año"` y `"Ano"` no.

## Categorías predefinidas

En `routers/categories.py`:

    DEFAULT_CATEGORIES = ("Hogar", "Comida", "Transporte", "Salud",
                          "Servicios", "Ocio", "Otros")

`add_default_categories(db, space_id)` las añade en ese orden a la sesión
de SQLAlchemy, sin hacer `commit`: el `commit` lo hace quien creó el
espacio. [RF-1, decisión 1]

- `POST /auth/register` la llama después del `flush` que da `id` al
  espacio personal. Si falla, el `rollback` que ya existe deshace usuario,
  espacio, membresía y categorías. [RF-1]
- `POST /spaces` la llama después de crear el espacio y la membresía.
  [RF-1]
- `POST /invitations/{token}/redeem` no cambia: unirse no crea categorías.
  [RF-3]

Cambiar más adelante `DEFAULT_CATEGORIES` solo afecta a los espacios
nuevos. Es la consecuencia buscada de copiarlas (decisión 2).

## Rutas

| Método y ruta | Qué hace | RF |
|---|---|---|
| `GET /spaces/{space_id}/categories` | Categorías del espacio en orden de creación: `[{id, name}]` | RF-4, RF-10 |
| `POST /spaces/{space_id}/categories` | Crea una categoría: `201` con `{id, name}` | RF-5 a RF-8, RF-10 |

- Las dos rutas usan `member_space`: espacio ajeno o inexistente, `404`;
  sin sesión, `401`. El test que recorre todas las rutas con `{space_id}`
  las vigila sin cambios. [RF-10]
- Nombre vacío o de más de 50 caracteres tras quitar los espacios: `422`
  con el límite, igual que el nombre de un espacio. [RF-7]
- Nombre repetido según `name_key`: `409` con el mensaje "Ya existe la
  categoría «Comida» en este espacio.", que muestra el nombre guardado
  para que se entienda por qué "comida" choca. Primero se comprueba con una
  consulta. Si dos peticiones pasan la comprobación a la vez, el índice
  único frena la segunda y la `IntegrityError` se convierte en el mismo
  `409`, como en el registro. [RF-8]

## Tests

- `test_models.py`: `category_key` con los ejemplos de la normalización, y
  el índice único que rechaza dos claves iguales en el mismo espacio pero
  no en espacios distintos. [RF-8, RF-9]
- `test_categories.py`: predefinidas tras registrarse y tras crear un
  espacio, en su orden (criterios 1 y 2); unirse no las cambia (criterio
  3); dos miembros ven lo mismo (criterio 4); validación del nombre y
  duplicados (criterio 5); registro fallido sin categorías huérfanas.
- `test_isolation.py`: listar y crear en un espacio ajeno responde `404` y
  no crea nada (criterio 6), y borrar un espacio borra sus categorías sin
  tocar las de otro espacio del mismo usuario (criterio 7). Se actualiza el
  docstring que dice que todavía no hay datos del presupuesto.

## Base de datos local (decisión 3)

Cuando el código esté listo, se borra `services/api/budget.db` y
`make run-api` la recrea con la tabla nueva. Antes se pide aprobación,
porque es borrar datos (AGENTS.md). No hay datos reales ni entornos
desplegados que proteger (principio 8, nota del ADR 0004).

## Riesgos y temas abiertos

- **`name_key` y `name` deben ir siempre juntos.** El validador lo
  garantiza al asignar `name` desde Python. Una sentencia `UPDATE` escrita
  a mano saltaría el validador. Hoy no existe ninguna, y renombrar
  categorías no tiene spec.
- **La normalización no unifica espacios internos ni guiones**: "Comida
  rápida" y "Comida  rápida" son distintas. La decisión 4 no lo pide.
- **Renombrar y borrar categorías** sigue sin spec asignada. Antes de
  añadirlo hay que decidir qué pasa con sus gastos y presupuestos
  (principio 8).

## Conceptos nuevos

- [Normalización Unicode (`unicodedata.normalize`)](https://docs.python.org/3/library/unicodedata.html#unicodedata.normalize) — formas NFD y NFC, y por qué una letra con tilde puede ser uno o dos caracteres.
- [`str.casefold`](https://docs.python.org/3/library/stdtypes.html#str.casefold) — en qué se diferencia de `lower()` al comparar textos.
- [Validadores de SQLAlchemy (`@validates`)](https://docs.sqlalchemy.org/en/20/orm/mapped_attributes.html#simple-validators) — código que se ejecuta al asignar un atributo del modelo.
- [`lower()` en SQLite](https://www.sqlite.org/lang_corefunc.html#lower) — por qué solo convierte caracteres ASCII.
