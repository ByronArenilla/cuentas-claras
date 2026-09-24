# ADR 0002 — Argon2id para guardar contraseñas

- Fecha: 2026-09-24
- Estado: aceptada
- Fase / spec: 1 / 001-usuarios-y-espacios

## Contexto

Desde el ADR 0001 cada persona se autentica con correo y contraseña, así que
la API guarda contraseñas por primera vez. RF-6 exige un algoritmo de hash
de contraseñas con sal, nunca en claro ni reversible.

El riesgo que se quiere cubrir es el robo de una copia de la base de datos.
Si eso pasa, quien la tenga intentará adivinar contraseñas probando millones
de candidatas por segundo con GPU. Una contraseña la elige una persona y se
puede adivinar, así que el hash tiene que ser **lento y caro en memoria**
para que cada intento cueste.

Restricciones: el servidor será pequeño por el límite de 15 USD/mes
(principio 16), y la dependencia debe ser fácil de explicar y de mantener.

## Decisión

Usar **Argon2id** mediante `PasswordHasher` de
[`argon2-cffi`](https://argon2-cffi.readthedocs.io/), con sus parámetros por
defecto. En la versión 25.1.0 son t=3 iteraciones, 64 MiB de memoria y 4
hilos, el perfil de "poca memoria" recomendado por la
[RFC 9106](https://www.rfc-editor.org/rfc/rfc9106.html#section-4). La sal se
genera sola y los parámetros quedan guardados dentro del propio hash.

La contraseña mínima tiene 12 caracteres, sin exigir mayúsculas ni símbolos,
siguiendo a [NIST SP 800-63B](https://pages.nist.gov/800-63-4/sp800-63b.html),
que premia la longitud sobre la complejidad.

## Alternativas descartadas

- **bcrypt**: sigue siendo aceptable, pero apenas usa memoria, así que una GPU
  lo ataca mejor que a Argon2id. Además ignora todo lo que pase de 72 bytes
  sin avisar. OWASP lo propone solo cuando Argon2id no está disponible.
- **scrypt**: también es caro en memoria, pero tiene menos soporte en Python
  y OWASP lo coloca por detrás de Argon2id.
- **PBKDF2**: no es caro en memoria y necesita cientos de miles de
  iteraciones para ser razonable. Solo tiene sentido cuando se exige
  certificación FIPS, que no es el caso.
- **SHA-256 con sal**: es un hash rápido, diseñado para no costar. Justo lo
  contrario de lo que se necesita con una contraseña.

## Consecuencias

- Cada inicio de sesión reserva 64 MiB durante un momento. Para una app
  personal es asumible, pero muchos inicios de sesión simultáneos en un
  servidor pequeño podrían agotar la memoria. Es otra razón para limitar los
  intentos de inicio de sesión en `008-control-acceso`.
- Como los parámetros viajan dentro del hash, se pueden endurecer en el
  futuro sin romper las contraseñas existentes: `check_needs_rehash` indica
  cuándo volver a calcular el hash al iniciar sesión.
- El inicio de sesión verifica contra un hash de relleno cuando el correo no
  existe, para que el tiempo de respuesta no delate qué correos están
  registrados.
- Qué aprendí: una contraseña y un token aleatorio no se protegen igual. La
  contraseña necesita un hash lento; el token, no (ver ADR 0003).
