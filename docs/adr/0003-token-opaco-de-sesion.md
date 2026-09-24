# ADR 0003 — Token de sesión opaco guardado en la base de datos

- Fecha: 2026-09-24
- Estado: aceptada
- Fase / spec: 1 / 001-usuarios-y-espacios

## Contexto

Después de iniciar sesión, la web y más adelante el bot necesitan una
credencial que presentar en cada petición a la API. La spec 001 fija tres
condiciones:

- La sesión dura 15 días (RF-8).
- Cerrar sesión invalida el token en el momento, aunque no haya caducado
  (RF-12, criterio de validación 3).
- Una copia de la base de datos no debe permitir suplantar a nadie
  (clarificación 4).

La segunda condición obliga a que exista estado en el servidor: sin una fila
que se pueda borrar, "cerrar sesión" no cierra nada.

## Decisión

Al iniciar sesión, la API genera un **token opaco aleatorio** con
[`secrets.token_urlsafe(32)`](https://docs.python.org/3/library/secrets.html)
(256 bits) y guarda en la tabla `sessions` solo su **hash SHA-256**, junto al
usuario y la fecha de caducidad. El cliente lo envía en la cabecera
`Authorization: Bearer <token>`. Cada petición busca la sesión por ese hash y
comprueba la caducidad. Cerrar sesión borra la fila.

SHA-256 basta, aunque para contraseñas sería un error (ADR 0002). Un token
de 256 bits es imposible de adivinar por fuerza bruta, así que un hash lento
no añade protección. Además, el hash tiene que ser determinista para poder
buscar la sesión por él, y Argon2 con sal no lo es.

## Alternativas descartadas

- **JWT firmado sin estado**: su ventaja es no consultar la base de datos en
  cada petición, pero entonces un token no se puede revocar antes de que
  caduque. Revocarlo exige una lista de tokens anulados en la base de datos,
  y eso devuelve la consulta en cada petición. Además añade una clave de
  firma que custodiar y rotar, y los
  [errores de configuración conocidos](https://cheatsheetseries.owasp.org/cheatsheets/JSON_Web_Token_for_Java_Cheat_Sheet.html)
  (`alg: none`, confusión de algoritmos). Complejidad sin beneficio aquí.
- **JWT más fila en la base de datos**: la firma no aporta nada si igualmente
  se consulta la fila.
- **Guardar el token en claro**: una copia de la base de datos permitiría
  usar cualquier sesión vigente. Se descarta por la clarificación 4.
- **Cookie de sesión del framework**: sirve para un navegador, pero el bot de
  Telegram no es un navegador. Dónde guarda la web el token (cookie `HttpOnly`
  o `localStorage`) se decide en `007-dashboard-web` y `008-control-acceso`;
  este ADR solo fija qué es el token y cómo lo valida la API.

## Consecuencias

- Cada petición autenticada hace una consulta indexada por `token_hash`.
  Con SQLite y un solo usuario o un hogar, el costo es despreciable.
- Cerrar sesión y revocar funcionan de verdad: basta borrar la fila.
- Las sesiones caducadas no se borran solas: la tabla crece poco a poco.
  Hace falta una limpieza periódica antes de que importe; buen candidato
  para cuando llegue la observabilidad (fase 7).
- Al no depender de una clave de firma, no hay secreto nuevo que gestionar
  en `.env` (principio 12).
- Qué aprendí: "sin estado" no es gratis. Si la revocación es un requisito,
  el estado vuelve por otro lado.
