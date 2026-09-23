# Tareas 001 — Usuarios y espacios

- Spec: `spec.md` (aprobada) · Plan: `plan.md` (aprobado)
- Regla: una tarea por vez, primero los tests y luego el código. Al
  terminarla, marcarla, ejecutar `make test` y `make lint`, y detenerse.

## [x] T1 — Esqueleto de la API y `Makefile`
Crear `services/api/pyproject.toml` con las dependencias del plan y la
configuración de `ruff`, la app de FastAPI con `GET /health`, y el
`Makefile` de la raíz con `install`, `run-api`, `test` y `lint`.

- Test primero: `/health` responde `200` sin cabecera de autenticación y su
  cuerpo no contiene datos de usuarios ni de espacios.
- Hecho cuando: `make install`, `make test` y `make lint` funcionan desde la
  raíz y `make run-api` levanta el servicio.
- RF: RF-34.

## T2 — Configuración que falla al arrancar
`app/config.py` lee `DATABASE_URL` y `TZ` una sola vez y termina con un
error que nombra la variable que falta.

- Test primero: sin `DATABASE_URL` en el entorno, importar la configuración
  falla y el mensaje nombra la variable.
- Hecho cuando: el test pasa y `make run-api` sin `.env` explica qué falta
  en lugar de arrancar a medias.
- RF: RF-33.

## T3 — Base de datos y modelos
`app/db.py` (motor, sesión, `create_all`, `PRAGMA foreign_keys=ON` en cada
conexión) y `app/models.py` con `users`, `spaces`, `memberships`,
`invitations` y `sessions`.

- Test primero: las claves foráneas están activas en una conexión nueva;
  borrar un espacio arrastra sus membresías; el índice único impide dos
  membresías del mismo usuario en el mismo espacio.
- Hecho cuando: los tests pasan con la base de datos en memoria del
  `conftest.py`.
- RF: base de RF-3, RF-20, RF-23, RF-27.

## T4 — Contraseñas y tokens
`app/security.py`: hash y verificación con Argon2id, generación de tokens
con `secrets` y su hash SHA-256.

- Test primero: dos hashes de la misma contraseña son distintos (la sal);
  la verificación acepta la correcta y rechaza la equivocada; el hash del
  token es estable y el token generado no se repite.
- Hecho cuando: los tests pasan y ninguna función devuelve la contraseña.
- RF: RF-6.

## T5 — Registro del primer usuario
`POST /auth/register`: crea usuario, espacio personal y membresía en una
transacción. Sin usuarios en la base de datos, no exige invitación.

- Test primero: el primer registro crea las tres filas; un correo repetido
  se rechaza y no deja nada a medias; una contraseña corta se rechaza
  nombrando el requisito; la respuesta nunca incluye el hash.
- Hecho cuando: los tests pasan y un registro fallido deja la base de datos
  igual que estaba.
- RF: RF-1, RF-3, RF-4, RF-5, RF-7.

## T6 — Sesión: entrar, identificarse y salir
`POST /auth/login`, `POST /auth/logout`, `GET /me` y la dependencia
`current_user`.

- Test primero: credenciales correctas devuelven token y crean la fila;
  credenciales incorrectas se rechazan con el mismo mensaje tanto si falla
  el correo como la contraseña; una ruta protegida sin token, con token
  desconocido o con sesión caducada responde `401` y no modifica nada;
  tras `logout` el mismo token recibe `401` aunque no haya caducado.
- Hecho cuando: los tests pasan, incluidos los criterios de validación 3 y 4
  de la spec.
- RF: RF-8 a RF-12.

## T7 — Registro cerrado e invitación de instancia
`POST /invitations/instance` y la regla de que, existiendo ya algún usuario,
el registro exige un código vigente.

- Test primero: con un usuario en la base de datos, registrarse sin código
  se rechaza; con un código vigente funciona y el código queda usado; el
  mismo código no sirve dos veces; un código caducado se rechaza.
- Hecho cuando: los tests pasan y el registro de T5 sigue funcionando solo
  cuando la base de datos está vacía.
- RF: RF-2, RF-16, RF-19.

## T8 — Espacios y la dependencia `member_space`
`GET /spaces`, `POST /spaces` y la dependencia que resuelve el espacio solo
para sus miembros.

- Test primero: crear un espacio deja al creador como miembro; el listado
  devuelve solo los espacios propios; pedir un espacio ajeno responde `404`
  y no `403`; pedir un espacio inexistente responde igual que el ajeno.
- Hecho cuando: los tests pasan y ninguna ruta de espacios consulta por
  `space_id` sin pasar por la dependencia.
- RF: RF-13, RF-14, RF-29, RF-30.

## T9 — Invitación de espacio
`POST /spaces/{id}/invitations`, `POST /invitations/{code}/redeem` y el
registro con invitación de espacio.

- Test primero: un miembro emite el código y otro usuario lo canjea y queda
  como miembro; quien ya es miembro recibe un rechazo y el código sigue sin
  usarse; alguien sin cuenta se registra con el código y acaba con usuario,
  espacio personal y membresía; un no miembro no puede emitir códigos de ese
  espacio.
- Hecho cuando: los tests pasan, incluido el criterio 5 de la spec.
- RF: RF-15, RF-17, RF-18, RF-19, RF-20.

## T10 — Salir de un espacio
`DELETE /spaces/{id}/members/me`.

- Test primero: un miembro sale y deja de verlo en su listado; los datos del
  espacio siguen ahí para el resto; el último miembro no puede salir y el
  mensaje explica que la vía es borrarlo.
- Hecho cuando: los tests pasan.
- RF: RF-21, RF-22.

## T11 — Borrar un espacio
`DELETE /spaces/{id}?confirm=<nombre>`.

- Test primero: el único miembro lo borra confirmando el nombre exacto; con
  el nombre equivocado no se borra nada; con más de un miembro se rechaza;
  si es el único espacio del usuario se rechaza; tras borrarlo el usuario
  sigue existiendo y sus otros espacios están intactos.
- Hecho cuando: los tests pasan, incluido el criterio 6 de la spec.
- RF: RF-23 a RF-27.

## T12 — Cierre: aislamiento y documentación
`tests/test_isolation.py` reuniendo los criterios 1 y 2 de la spec, y
actualización del `README.md` y del `docs/roadmap.md`.

- Test primero: dos usuarios en espacios distintos no ven nada del otro; dos
  miembros del mismo espacio ven exactamente lo mismo.
- Hecho cuando: los siete criterios de validación de la spec se cumplen,
  `make test` y `make lint` están en verde, el README describe cómo
  registrarse e invitar, y la spec queda marcada en el roadmap.
- RF: RF-28, RF-32.

## Requisito que no se cierra en esta spec

**RF-31** (un gasto guarda su espacio y quién lo registró) no se puede
verificar aquí porque los gastos no existen todavía. Queda como requisito
heredado: la spec `002-api-gastos` debe cubrirlo y citarlo.
