# ADR 0006 — Clave normalizada para nombres de categoría

- Fecha: 2026-10-29
- Estado: aceptada
- Fase / spec: 1 / 002-categorias

## Contexto

La decisión 4 de la spec 002 fija cuándo dos nombres de categoría son el
mismo: si solo se diferencian en mayúsculas, tildes, diéresis o espacios
alrededor ("comida" y " Comida ", "Educacion" y "Educación"). La ñ es una
letra propia: "Año" y "Ano" son distintos. El nombre se guarda tal como se
escribió, solo sin los espacios alrededor.

RF-8 exige rechazar el duplicado sin crear nada, **aunque lleguen dos
peticiones iguales a la vez**. Una comprobación que solo consulta antes de
insertar no basta: las dos peticiones pueden consultar, no encontrar nada e
insertar las dos.

Restricciones que aplican:

- La base de datos de la fase 1 es SQLite, y su función
  [`lower()`](https://www.sqlite.org/lang_corefunc.html#lower) solo
  convierte caracteres ASCII: `lower('É')` sigue siendo `'É'`. Tampoco
  tiene ninguna función que quite tildes.
- No se añaden dependencias que el plan no recoja.
- La regla de comparación es lógica de negocio y debe probarse sin HTTP
  (principio 10).

## Decisión

Cada categoría guarda, además de `name`, una columna `name_key` con el
nombre normalizado, y la tabla tiene un índice único sobre
(`space_id`, `name_key`).

- `category_key()` en `app/models.py` calcula la clave con la biblioteca
  estándar: quita los espacios alrededor, aplica `casefold()`, descompone
  con NFD, descarta las marcas combinantes salvo la virgulilla detrás de
  una `n` y recompone con NFC.
- Un validador `@validates("name")` del modelo rellena `name_key` cada vez
  que se asigna el nombre, así que ninguna ruta tiene que acordarse de
  hacerlo.
- La ruta de creación consulta primero por `name_key` para responder `409`
  con el nombre guardado. Si dos peticiones pasan esa consulta a la vez,
  el índice único frena la segunda y su `IntegrityError` se convierte en el
  mismo `409`.

## Alternativas descartadas

- **Comparar en SQL** (`WHERE lower(name) = lower(:name)` o un índice único
  sobre `lower(name)`): con SQLite no cumple la decisión 4, porque
  `lower()` no convierte letras con tilde y nada quita los acentos. "Cómida"
  y "cómida" serían distintos.
- **Comparar solo en Python**, cargando los nombres del espacio y
  normalizándolos antes de insertar: aplica bien la regla, pero no frena
  dos peticiones simultáneas, y RF-8 lo pide de forma explícita.
- **Guardar solo el nombre normalizado**: no hace falta una segunda
  columna, pero se pierde cómo lo escribió la persona ("Educación" se
  mostraría como "educacion"), y la decisión 4 pide conservarlo.
- **Una colación o extensión de la base de datos** que ignore tildes (ICU
  en SQLite, `unaccent` en PostgreSQL): mueve la regla fuera de Python, la
  ata a un motor concreto y añade una dependencia que el plan no recoge.
  Además, la excepción de la ñ habría que reproducirla en cada motor.

## Consecuencias

Lo que gana el proyecto:

- La base de datos garantiza RF-8 incluso con peticiones simultáneas, y el
  mismo nombre puede repetirse en espacios distintos (RF-9).
- La regla vive en una función pura, `category_key()`, que se prueba con
  ejemplos sin levantar la API, y funciona igual con cualquier motor de
  base de datos.
- Una futura spec que renombre categorías recibe la clave nueva sin código
  extra, porque el validador la recalcula al asignar `name`.

Lo que cuesta:

- **`name` y `name_key` deben ir siempre juntos.** El validador solo actúa
  al asignar el atributo desde Python: un `UPDATE` escrito a mano, o una
  migración de datos futura, tiene que recalcular la clave.
- **Cambiar la regla de normalización obliga a recalcular las claves
  guardadas**, y puede descubrir duplicados entre categorías que antes
  convivían. Habrá que hacerlo con una migración (ADR 0004).
- Una columna más por categoría. `name_key` no tiene límite de longitud,
  porque `casefold()` puede alargar el texto (`ß` → `ss`).
- Qué aprendí: una regla de unicidad que deba resistir peticiones
  simultáneas tiene que acabar en una restricción de la base de datos. La
  consulta previa solo sirve para dar un mensaje claro.
