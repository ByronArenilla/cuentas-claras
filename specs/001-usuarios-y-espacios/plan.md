# Plan 001 — Usuarios y espacios

- Spec: `spec.md` (estado: aprobada)
- Servicio afectado: `services/api`
- Estado: aprobado
- Cambios: ADR 0005 — registro abierto e invitación por enlace (2026-09-29).
  Las secciones afectadas lo citan.

Esta es la primera spec que produce código, así que el plan incluye también
el esqueleto del proyecto y el `Makefile` de la raíz, que todavía no existen.

## Decisiones técnicas

| Decisión | Elegido | Por qué |
|---|---|---|
| Hash de contraseñas | `argon2-cffi` (Argon2id) | Primera recomendación de OWASP; genera la sal sola y guarda los parámetros dentro del hash. |
| Credencial de sesión | Token opaco aleatorio | La fila de la sesión se consulta igual en cada petición, así que firmar no añade nada (ver nota del ADR 0001). |
| Esquema de base de datos | `create_all` de SQLAlchemy | No hay datos reales todavía y ninguna tabla de `main` cambia de forma. Alembic entrará cuando aparezca la primera migración que altere una tabla (ADR 0004 y su nota del 2026-09-29). |
| Validación del correo | Comprobación mínima propia | Evita añadir `email-validator` solo para esto. |
| Enlace de invitación | La API lo arma con `WEB_BASE_URL` + `/unirse/` + token | La web y el bot comparten el mismo enlace sin duplicar la ruta (ADR 0005). |

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
          invitations.py          emitir, consultar y canjear
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

**`invitations`** — `id`, `code_hash`, `space_id` (obligatorio), `created_by`,
`expires_at`, `used_at`, `used_by`. Guardar el hash y no el token evita que
una copia de la base de datos entregue invitaciones utilizables. Desde el
ADR 0005 ya no hay columna `kind` ni la restricción que la acompañaba: toda
invitación es de espacio. [RF-15, RF-19]

**`sessions`** — `id`, `token_hash`, `user_id`, `expires_at`, `created_at`.
[RF-8, RF-10, RF-12]

Notas de implementación:

- El borrado de un espacio arrastra sus membresías y, más adelante, sus
  gastos, mediante `ON DELETE CASCADE`. **SQLite no aplica las claves
  foráneas si no se activan explícitamente** (`PRAGMA foreign_keys=ON` en
  cada conexión); sin eso las reglas quedan decorativas. [RF-23, RF-27]
- Crear usuario + espacio personal + membresía ocurre en una sola
  transacción: o se crea todo, o no se crea nada. [RF-3]
- La base de datos de desarrollo (`services/api/budget.db`) se creó con la
  columna `kind`, y `create_all` no la quita. Al aplicar el ADR 0005 se
  borra y se recrea al arrancar; como es borrar datos, se pide aprobación
  antes (nota del 2026-09-29 en el ADR 0004).

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
adivinar por fuerza bruta. [RF-8, RF-15]

**Enlace de invitación** (ADR 0005): la respuesta de
`POST /spaces/{id}/invitations` trae `url` (`<WEB_BASE_URL>/unirse/<token>`)
y `expires_at`. El token en claro solo existe dentro de esa URL. La consulta
pública `GET /invitations/{token}` devuelve únicamente el nombre del espacio
y la caducidad: ni el `id` del espacio, ni sus miembros, ni quién invitó.
Consultar nunca escribe en la base de datos; unirse sigue siendo
`POST /invitations/{token}/redeem` con sesión. [RF-36, RF-37]

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
| `POST /auth/register` | Crea usuario y espacio personal, sin código | RF-1, RF-3 a RF-5 |
| `POST /auth/login` | Crea la sesión y devuelve el token | RF-8, RF-9 |
| `POST /auth/logout` | Borra la sesión actual | RF-12 |
| `GET /me` | Quién soy (lo usará la web) | RF-10 |
| `GET /spaces` | Espacios de los que soy miembro | RF-14 |
| `POST /spaces` | Crea un espacio y me deja como miembro | RF-13 |
| `DELETE /spaces/{id}?confirm=<nombre>` | Borra el espacio | RF-23 a RF-27 |
| `DELETE /spaces/{id}/members/me` | Salir del espacio | RF-21, RF-22 |
| `POST /spaces/{id}/invitations` | Compartir: devuelve el enlace de invitación | RF-15 |
| `GET /invitations/{token}` | Sin sesión: nombre del espacio y caducidad; `404` si no es válida | RF-19, RF-36, RF-37 |
| `POST /invitations/{token}/redeem` | Unirse al espacio, con sesión | RF-17, RF-19, RF-20 |
| `GET /health` | Sin autenticación, sin datos | RF-34 |

El nombre de confirmación del borrado viaja como parámetro de consulta
porque un `DELETE` con cuerpo es ambiguo y varios clientes HTTP lo
descartan.

Las specs 002 a 004 colgarán sus rutas de `/spaces/{space_id}/...`, que es
la forma de cumplir RF-28 sin que la API recuerde nada entre peticiones.

## Configuración y arranque

`config.py` lee el entorno una sola vez al importar. `DATABASE_URL`, `TZ` y
`WEB_BASE_URL` son obligatorias: si falta alguna, el proceso termina con un
error que la nombra, en lugar de arrancar con un valor por defecto y fallar
más tarde de forma confusa. [RF-33]

`WEB_BASE_URL` es la URL pública de la web y cambia entre entornos
(principio 11). En local vale `http://localhost:8080` de forma provisional:
el puerto real lo fija `007-dashboard-web`, que crea la web. Se le quita
la `/` final al leerla, para que el enlace no salga con `//unirse`. Entra en
`.env.example` y en `tests/conftest.py`. [RF-15]

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
- **No hay límite de peticiones al registro ni al inicio de sesión.** Con el
  registro abierto (ADR 0005), cualquiera puede crear cuentas o probar
  contraseñas. Lo resuelve el *rate limiting* de Nginx en
  `010-reverse-proxy`.
- **El token de invitación viaja en la URL**: en el enlace
  `/unirse/<token>` de la web y en `GET /invitations/{token}` y
  `POST /invitations/{token}/redeem` de la API. Queda escrito en el log de
  accesos de uvicorn y, desde la fase 3, en el de Nginx. Se acepta por ahora:
  el token es de un solo uso y caduca en 24 horas, pero quien lea los logs
  podría canjear uno todavía sin usar. `010-reverse-proxy` debe decidir si
  Nginx enmascara esas rutas en sus logs.
- **RF-4 permite a cualquiera saber si un correo ya está registrado.** Antes
  solo lo averiguaba quien tenía una invitación; con el registro abierto es
  público. Se acepta, porque un mensaje claro vale más, y el límite de
  peticiones de `010-reverse-proxy` impide recorrer listas de correos.
- **`GET /invitations/{token}` responde `404` y el canje, `403`**, para el
  mismo token no válido y con el mismo mensaje (RF-19). La consulta busca un
  recurso que no existe; el canje es una acción que se rechaza. Se deja así
  para no cambiar el contrato del canje que ya está probado.

## Conceptos nuevos

- [Argon2 y almacenamiento de contraseñas](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html) — OWASP.
- [Dependencias en FastAPI](https://fastapi.tiangolo.com/tutorial/dependencies/) — el mecanismo con el que `current_user` y `member_space` se aplican a cada ruta.
- [Claves foráneas en SQLite](https://www.sqlite.org/foreignkeys.html#fk_enable) — por qué hay que activarlas en cada conexión.
- [`secrets`](https://docs.python.org/3/library/secrets.html) — generación de tokens en Python.
- [Capability URLs](https://www.w3.org/TR/capability-urls/) — W3C. Por qué un enlace puede ser el permiso, y cómo cuidarlo (ADR 0005).
