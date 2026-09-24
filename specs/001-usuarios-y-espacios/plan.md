# Plan 001 — Usuarios y espacios

- Spec: `spec.md` (estado: aprobada)
- Servicio afectado: `services/api`
- Estado: aprobado

Esta es la primera spec que produce código, así que el plan incluye también
el esqueleto del proyecto y el `Makefile` de la raíz, que todavía no existen.

## Decisiones técnicas

| Decisión | Elegido | Por qué |
|---|---|---|
| Hash de contraseñas | `argon2-cffi` (Argon2id) | Primera recomendación de OWASP; genera la sal sola y guarda los parámetros dentro del hash. |
| Credencial de sesión | Token opaco aleatorio | La fila de la sesión se consulta igual en cada petición, así que firmar no añade nada (ver nota del ADR 0001). |
| Esquema de base de datos | `create_all` de SQLAlchemy | No hay datos reales todavía y ninguna tabla cambia de forma. Alembic entrará cuando aparezca la primera migración que altere una tabla. |
| Validación del correo | Comprobación mínima propia | Evita añadir `email-validator` solo para esto. |

## Dependencias

De la API (`services/api/pyproject.toml`):

- `fastapi`, `uvicorn` — servicio HTTP.
- `sqlalchemy` — acceso a la base de datos.
- **`argon2-cffi`** — única dependencia realmente nueva respecto al stack
  que ya declara `AGENTS.md`.
- Desarrollo: `pytest`, `httpx` (lo necesita el cliente de pruebas de
  FastAPI), `ruff`.

No se añade nada más. Cualquier otra librería que aparezca durante la
implementación exige volver a este plan.

## Estructura de archivos

    Makefile                      install, run-api, test, lint
    services/api/
      pyproject.toml              dependencias y configuración de ruff
      app/
        main.py                   crea la app y monta los routers
        config.py                 lee el entorno y falla si falta algo  [RF-33]
        db.py                     motor, sesión de SQLAlchemy, create_all
        models.py                 user, space, membership, invitation, session
        schemas.py                entradas y salidas de la API
        security.py               hash de contraseñas y de tokens      [RF-6, RF-8]
        deps.py                   usuario autenticado y espacio del miembro
        routers/
          auth.py                 registro, login, logout, /me
          spaces.py               crear, listar, salir, borrar
          invitations.py          emitir y canjear
      tests/
        conftest.py               base de datos en memoria y cliente
        test_auth.py
        test_spaces.py
        test_invitations.py
        test_isolation.py         los tests que cuidan el principio 5

## Modelo de datos

Todas las fechas se guardan en UTC (principio 7).

**`users`** — `id`, `email` (único, normalizado a minúsculas), `password_hash`,
`created_at`.

**`spaces`** — `id`, `name`, `created_at`.

**`memberships`** — `id`, `user_id`, `space_id`, `created_at`, con índice
único sobre (`user_id`, `space_id`) para que RF-20 no dependa solo del
código: aunque dos peticiones lleguen a la vez, la base de datos impide la
membresía duplicada.

**`invitations`** — `id`, `code_hash`, `kind` (`instance` | `space`),
`space_id` (nulo cuando `kind` es `instance`), `created_by`, `expires_at`,
`used_at`, `used_by`. Guardar el hash y no el código evita que una copia de
la base de datos entregue invitaciones utilizables. [RF-15, RF-16, RF-19]

**`sessions`** — `id`, `token_hash`, `user_id`, `expires_at`, `created_at`.
[RF-8, RF-10, RF-12]

Notas de implementación:

- El borrado de un espacio arrastra sus membresías y, más adelante, sus
  gastos, mediante `ON DELETE CASCADE`. **SQLite no aplica las claves
  foráneas si no se activan explícitamente** (`PRAGMA foreign_keys=ON` en
  cada conexión); sin eso las reglas quedan decorativas. [RF-23, RF-27]
- Crear usuario + espacio personal + membresía ocurre en una sola
  transacción: o se crea todo, o no se crea nada. [RF-3, RF-18]

## Seguridad

**Contraseñas** (`security.py`): `PasswordHasher` de argon2-cffi, con los
parámetros por defecto de la librería. Longitud mínima: 12 caracteres, sin
exigir mayúsculas ni símbolos, siguiendo la recomendación actual de NIST de
premiar la longitud sobre la complejidad. [RF-5, RF-6]

**Tokens de sesión e invitación**: `secrets.token_urlsafe(32)` para la
sesión y `secrets.token_urlsafe(16)` para la invitación; en la base de datos
se guarda `sha256` del valor. Aquí SHA-256 es suficiente y Argon2 sería un
error de diseño: un hash lento protege secretos *adivinables* como una
contraseña, y estos tokens son aleatorios de 128 bits o más, imposibles de
adivinar por fuerza bruta. [RF-8, RF-15, RF-16]

**Aislamiento**: dos dependencias de FastAPI, y toda ruta protegida usa una
de las dos.

- `current_user`: lee la cabecera `Authorization: Bearer <token>`, busca la
  sesión por el hash, comprueba la caducidad y devuelve el usuario. Si algo
  falla, `401`. [RF-10, RF-11]
- `member_space(space_id)`: usa `current_user` y devuelve el espacio **solo
  si existe una membresía**. Si no, `404`, no `403`. [RF-29, RF-30]

Ninguna consulta de las specs 002 a 004 debe partir de `space_id` sin pasar
por `member_space`. Es la pieza que sostiene el principio 5 entero: si
alguien la salta una sola vez, el aislamiento se rompe ahí. [RF-32]

## Rutas

| Método y ruta | Qué hace | RF |
|---|---|---|
| `POST /auth/register` | Crea usuario, espacio personal y, si vino con invitación de espacio, la membresía | RF-1 a RF-5, RF-18, RF-19 |
| `POST /auth/login` | Crea la sesión y devuelve el token | RF-8, RF-9 |
| `POST /auth/logout` | Borra la sesión actual | RF-12 |
| `GET /me` | Quién soy (lo usará la web) | RF-10 |
| `GET /spaces` | Espacios de los que soy miembro | RF-14 |
| `POST /spaces` | Crea un espacio y me deja como miembro | RF-13 |
| `DELETE /spaces/{id}?confirm=<nombre>` | Borra el espacio | RF-23 a RF-27 |
| `DELETE /spaces/{id}/members/me` | Salir del espacio | RF-21, RF-22 |
| `POST /spaces/{id}/invitations` | Invitación a ese espacio | RF-15 |
| `POST /invitations/instance` | Invitación solo para crear cuenta | RF-16 |
| `POST /invitations/{code}/redeem` | Canjear estando ya registrado | RF-17, RF-19, RF-20 |
| `GET /health` | Sin autenticación, sin datos | RF-34 |

El nombre de confirmación del borrado viaja como parámetro de consulta
porque un `DELETE` con cuerpo es ambiguo y varios clientes HTTP lo
descartan.

Las specs 002 a 004 colgarán sus rutas de `/spaces/{space_id}/...`, que es
la forma de cumplir RF-28 sin que la API recuerde nada entre peticiones.

## Configuración y arranque

`config.py` lee el entorno una sola vez al importar. `DATABASE_URL` y `TZ`
son obligatorias: si falta alguna, el proceso termina con un error que la
nombra, en lugar de arrancar con un valor por defecto y fallar más tarde de
forma confusa. [RF-33]

## Tests

`pytest` con una base de datos SQLite en memoria por test, creada con
`create_all`, y el cliente de pruebas de FastAPI. `conftest.py` ofrece dos
ayudas: crear un usuario con sesión iniciada, y crear un espacio con dos
miembros.

Los tests de `test_isolation.py` son los que cierran la spec (criterios 1, 2
y 6): dos usuarios que no se ven, dos miembros que ven lo mismo, y el
borrado de un espacio que no toca al otro. Conviene escribirlos aunque
todavía no existan los gastos, usando los propios espacios y membresías como
dato observable; las specs 002 a 004 los ampliarán con gastos reales.

## Riesgos y temas abiertos

- **`create_all` no altera tablas existentes.** En cuanto una spec cambie la
  forma de una tabla ya creada, hace falta Alembic y un ADR. Mientras solo
  se añadan tablas nuevas, sirve.
- **Dónde guarda el token la web** (cookie `HttpOnly` o `localStorage`) se
  decide en `007-dashboard-web` y `008-control-acceso`. Este plan solo fija
  que la API lo acepta por la cabecera `Authorization`.
- **No hay límite de intentos de inicio de sesión.** Con registro cerrado el
  riesgo es menor, pero conviene anotarlo para `008-control-acceso`.
- **El código de invitación viaja en la URL** de
  `POST /invitations/{code}/redeem`, así que queda escrito en el log de
  accesos de uvicorn y, desde la fase 3, en el de Nginx. Se acepta por ahora:
  el código es de un solo uso y caduca en 24 horas, pero quien lea los logs
  podría canjear uno todavía sin usar. `010-reverse-proxy` debe decidir si
  Nginx enmascara esa ruta en sus logs o si el código pasa al cuerpo de la
  petición.
- **RF-4 permite saber si un correo ya está registrado** a quien tenga una
  invitación válida. Se acepta: el registro es cerrado y el mensaje claro
  vale más que ocultar ese detalle a alguien ya invitado.

## Conceptos nuevos

- [Argon2 y almacenamiento de contraseñas](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html) — OWASP.
- [Dependencias en FastAPI](https://fastapi.tiangolo.com/tutorial/dependencies/) — el mecanismo con el que `current_user` y `member_space` se aplican a cada ruta.
- [Claves foráneas en SQLite](https://www.sqlite.org/foreignkeys.html#fk_enable) — por qué hay que activarlas en cada conexión.
- [`secrets`](https://docs.python.org/3/library/secrets.html) — generación de tokens en Python.
