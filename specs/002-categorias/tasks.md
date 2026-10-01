# Tareas 002 — Categorías

- Spec: `spec.md` (aprobada) · Plan: `plan.md` (aprobado)
- Regla: una tarea por vez, primero los tests y luego el código. Al
  terminarla, marcarla, ejecutar `make test` y `make lint`, y detenerse.

## [x] T1 — Modelo `Category` y clave normalizada
`app/models.py`: la tabla `categories` (`id`, `space_id` con
`ON DELETE CASCADE`, `name`, `name_key`, `created_at`), el índice único
sobre (`space_id`, `name_key`), la función pura `category_key()` y el
validador `@validates("name")` que rellena `name_key`.

- Test primero (`test_models.py`):
  - `category_key` da la misma clave a `" Comida "`, `"comida"` y
    `"Cómida"`, y a `"Educacion"` y `"Educación"`; da claves distintas a
    `"Año"` y `"Ano"`.
  - Crear una `Category` rellena `name_key` sin asignarla a mano.
  - El índice único rechaza dos categorías con la misma clave en el mismo
    espacio y acepta la misma clave en espacios distintos.
  - Borrar un espacio borra sus categorías.
- Hecho cuando: los tests pasan con la base de datos en memoria del
  `conftest.py`.
- RF: base de RF-2, RF-8, RF-9 y RF-11.

## [x] T2 — Categorías predefinidas al crear un espacio
`app/routers/categories.py` con `DEFAULT_CATEGORIES` y
`add_default_categories(db, space_id)`. El registro y `POST /spaces` la
llaman antes del `commit`, en la misma transacción que crea el espacio.
Todavía no hay rutas de categorías: los tests leen la base de datos con la
sesión del `conftest.py`.

- Test primero (`test_categories.py`):
  - Tras registrarse, el espacio personal tiene las siete predefinidas, en
    el orden de la decisión 1.
  - Tras `POST /spaces`, el espacio nuevo tiene las suyas, con
    identificadores distintos de las del espacio personal.
  - Canjear una invitación no cambia las categorías del espacio.
  - Un registro rechazado por correo repetido no deja categorías huérfanas.
- Hecho cuando: los tests pasan y el resto de la suite sigue en verde.
- RF: RF-1, RF-2, RF-3.

## [ ] T3 — Listar categorías
`GET /spaces/{space_id}/categories` con `member_space`, `CategoryOut`
(`id`, `name`) en `schemas.py`, orden por `id`, y el router montado en
`main.py`.

- Test primero:
  - Un miembro recibe las categorías de su espacio en orden de creación,
    con `id` y `name`, y sin `name_key` (criterio 1).
  - Dos miembros del mismo espacio reciben la misma lista (parte del
    criterio 4).
  - Sin sesión, `401`.
- Hecho cuando: los tests pasan y el test que recorre las rutas con
  `{space_id}` sigue en verde con la ruta nueva.
- RF: RF-4, RF-10.

## [ ] T4 — Crear categorías
`POST /spaces/{space_id}/categories` con `CategoryIn` (nombre sin espacios
alrededor, de 1 a 50 caracteres). Si el nombre ya existe según `name_key`,
responde `409` con "Ya existe la categoría «<nombre guardado>» en este
espacio.", tanto si lo detecta la consulta previa como si lo detecta el
índice único (`IntegrityError`).

- Test primero:
  - Crear "Mascotas" responde `201` con `id` y `name`, y la categoría
    aparece al final de la lista, también para el otro miembro (criterio
    4).
  - `"  Mascotas  "` se guarda como `"Mascotas"`.
  - Nombre vacío, solo con espacios o de 51 caracteres: `422` con el
    límite, sin crear nada.
  - `"comida"` y `"Cómida"` donde ya existe `"Comida"`: `409` con el
    nombre guardado; `"Año"` y `"Ano"` conviven; `"comida"` se acepta en
    otro espacio (criterio 5).
  - La rama de `IntegrityError` responde el mismo `409`: se prueba
    simulando que la consulta previa no encontró nada.
- Hecho cuando: los tests pasan.
- RF: RF-5, RF-6, RF-7, RF-8, RF-9.

## [ ] T5 — Aislamiento con categorías
`test_isolation.py`: amplía los criterios de aislamiento de la 001 con
categorías y actualiza su docstring, que dice que aún no hay datos del
presupuesto. Si T3 y T4 están bien hechas, no debería hacer falta código
nuevo; si algún test falla, se corrige en esta tarea.

- Test primero:
  - Listar y crear categorías en un espacio ajeno o inexistente responden
    `404`, sin distinguir los casos, y no se crea nada (criterio 6).
  - Borrar un espacio borra sus categorías y no toca las de otro espacio
    del mismo usuario (criterio 7).
- Hecho cuando: los tests pasan.
- RF: RF-10, RF-11.

## [ ] T6 — ADR 0006: clave normalizada para nombres de categoría
`docs/adr/0006-clave-normalizada-para-nombres-de-categoria.md` con la
plantilla `0000-plantilla.md`. Recoge por qué se guarda `name_key` con
índice único y por qué se descartaron comparar en SQL (`lower()` de SQLite
solo entiende ASCII) y comparar solo en Python (no frena dos peticiones
simultáneas).

- Test primero: no aplica, es documentación.
- Hecho cuando: el ADR existe y el plan lo cita.
- RF: ninguno; principio 4.

## [ ] T7 — Cierre: base de datos local, README y validación
- Borrar `services/api/budget.db` **con aprobación previa** y comprobar que
  `make run-api` la recrea con la tabla `categories` (decisión 3).
- `README.md`: sección de categorías con ejemplos `curl` de listar y crear.
- Repasar los ocho criterios de validación de la spec.
- `docs/roadmap.md`: marcar `002-categorias` como terminada y dejar
  `003-api-gastos` como spec activa.

- Test primero: no aplica, es documentación y validación.
- Hecho cuando: `make test` y `make lint` están en verde y los ejemplos
  `curl` del README funcionan contra `make run-api`.
- RF: ninguno nuevo; cierra la spec.
