# Spec 001 — Usuarios y espacios

- Fase: 1 — Aplicación y SDD
- Estado: aprobada
- Base: ADR 0001 — Multiusuario mediante espacios compartidos

## Por qué

La constitución (principio 5) dice que los datos pertenecen a un *espacio*,
no a una persona. Ninguna otra spec de la fase 1 puede escribirse hasta que
existan el usuario, el espacio y la membresía: un gasto no se puede guardar
si no hay espacio al que pertenezca, y el resumen mensual no se puede
calcular si no se sabe qué gastos puede ver quien pregunta.

Esta spec cubre dos necesidades reales:

- Una pareja o un hogar registra gastos contra el mismo presupuesto y ve el
  mismo resumen.
- Dos personas usan la misma instancia sin verse los datos entre sí.

## Qué entra

La API gana usuarios, espacios, membresías, invitaciones, borrado de
espacios y la sesión con la que se identifica a quien llama. Con eso, las
specs siguientes pueden colgar sus datos de un espacio.

## Qué NO entra

- La pantalla de inicio de sesión de la web y la vinculación del `chat_id`
  de Telegram a un usuario: son de `008-control-acceso`.
- Gastos, categorías y presupuestos: specs 002, 003 y 004. Esta spec solo
  fija la regla de aislamiento que aquellas deberán cumplir.
- Recuperación de contraseña, verificación de correo y cambio de correo.
- Roles y permisos distintos dentro de un espacio, y expulsar a un miembro:
  por el ADR 0001, hoy todos los miembros de un espacio son iguales.

## Conceptos

- **Usuario** (`user`): persona que se autentica. Se identifica por su
  correo.
- **Espacio** (`space`): ámbito que contiene los datos del presupuesto.
- **Membresía** (`membership`): vincula un usuario con un espacio.
- **Espacio personal**: el espacio que se crea junto con el usuario, para
  que pueda registrar gastos sin configurar nada.
- **Invitación de instancia**: código de un solo uso que permite crear una
  cuenta sin unirse a ningún espacio ajeno. Es la vía del usuario que quiere
  su presupuesto independiente.
- **Invitación de espacio**: código de un solo uso que convierte a quien lo
  canjea en miembro de un espacio concreto.
- **Sesión**: fila en la base de datos, con caducidad, que respalda el
  token que la API entrega al iniciar sesión. El token es aleatorio y la
  base de datos guarda solo su hash.

## Decisiones de clarificación (2026-09-22)

1. **El registro exige código de invitación**, salvo el primer usuario de la
   instancia, que no tiene quién se lo dé. Evita que una instancia expuesta
   en internet acepte cuentas de desconocidos.
2. **El usuario se identifica por su correo**, no por un nombre de usuario.
3. **La sesión dura 15 días y la invitación 24 horas.** La invitación viaja
   por mensajería y queda ahí guardada, así que caduca pronto.
4. **Las sesiones se guardan en la base de datos.** Sin esa fila no se
   puede revocar una sesión antes de su caducidad y "cerrar sesión" no
   cerraría nada de verdad. Como la fila se consulta en cada petición, el
   token no necesita ir firmado: basta con que sea aleatorio e
   impredecible, y en la base de datos se guarda solo su hash, para que
   una copia de la base de datos no permita suplantar a nadie.
5. **El espacio se indica en cada petición.** La API no guarda un "espacio
   activo": recordar el último usado es trabajo de la web y del bot. Evita
   que un gasto caiga en un espacio distinto del que el usuario cree.
6. **Un espacio solo lo borra su único miembro**, confirmando con el nombre
   exacto. Así quien confirma es siempre quien pierde los datos.
7. **El espacio personal se llama siempre "Personal"** (2026-09-24). El
   registro no pide nombre de espacio: cada usuario solo ve los suyos, así
   que no hay confusión, y el nombre a confirmar al borrarlo (RF-25) es
   predecible.
8. **Nadie sale de su único espacio** (2026-09-24). Igual que RF-26 impide
   borrarlo, salir del último espacio que le queda a un usuario se rechaza:
   así nadie se queda sin sitio donde registrar gastos (RF-35).

## Requisitos funcionales

### Registro

- **RF-1** CUANDO no existe todavía ningún usuario y alguien se registra con
  un correo y una contraseña válidos, el sistema DEBE crear el usuario sin
  exigir código de invitación.
- **RF-2** MIENTRAS exista al menos un usuario, el sistema DEBE exigir un
  código de invitación vigente para registrar a alguien nuevo.
- **RF-3** CUANDO se crea un usuario, el sistema DEBE crear en la misma
  operación su espacio personal, con esa persona como único miembro.
- **RF-4** SI el correo ya pertenece a un usuario, ENTONCES el sistema DEBE
  rechazar el registro, sin crear nada y sin consumir el código.
- **RF-5** SI la contraseña no alcanza la longitud mínima, ENTONCES el
  sistema DEBE rechazar el registro e indicar el requisito incumplido.
- **RF-6** El sistema DEBE guardar las contraseñas con un algoritmo de hash
  de contraseñas con sal, y nunca en claro ni de forma reversible.
- **RF-7** El sistema NUNCA DEBE devolver el hash de la contraseña en
  ninguna respuesta.

### Sesión

- **RF-8** CUANDO un usuario envía credenciales correctas, el sistema DEBE
  crear una sesión en la base de datos con caducidad de 15 días y entregar
  un token aleatorio que la represente. El sistema DEBE guardar solo el
  hash del token, nunca el token en claro.
- **RF-9** SI las credenciales son incorrectas, ENTONCES el sistema DEBE
  rechazar la petición con un mensaje que no revele si falló el correo o la
  contraseña.
- **RF-10** MIENTRAS la sesión exista en la base de datos y no haya
  caducado, el sistema DEBE identificar en cada petición al usuario al que
  pertenece.
- **RF-11** SI una petición a un recurso protegido llega sin token, con un
  token desconocido, con la sesión caducada o con una sesión que ya no está
  en la base de datos, ENTONCES el sistema DEBE rechazarla con `401` y sin
  ejecutar la operación.
- **RF-12** CUANDO un usuario cierra sesión, el sistema DEBE eliminar esa
  sesión de la base de datos, de modo que el token deje de servir aunque no
  haya llegado su caducidad.

### Espacios y membresías

- **RF-13** CUANDO un usuario crea un espacio con nombre, el sistema DEBE
  crearlo y dejarlo como miembro.
- **RF-14** El sistema DEBE permitir a un usuario listar los espacios de los
  que es miembro.
- **RF-15** CUANDO un miembro pide una invitación para su espacio, el
  sistema DEBE emitir un código de un solo uso con caducidad de 24 horas.
- **RF-16** CUANDO un usuario pide una invitación de instancia, el sistema
  DEBE emitir un código de un solo uso con caducidad de 24 horas que permita
  crear una cuenta sin unirse a ningún espacio ajeno.
- **RF-17** CUANDO un usuario autenticado canjea una invitación de espacio
  vigente, el sistema DEBE crear su membresía en ese espacio y marcar la
  invitación como usada.
- **RF-18** CUANDO alguien sin cuenta se registra con una invitación de
  espacio vigente, el sistema DEBE crear en la misma operación el usuario,
  su espacio personal y su membresía en el espacio invitado.
- **RF-19** SI una invitación no existe, ya se usó o caducó, ENTONCES el
  sistema DEBE rechazar la operación sin crear usuario ni membresía.
- **RF-20** SI quien canjea una invitación de espacio ya es miembro de ese
  espacio, ENTONCES el sistema DEBE rechazar el canje sin duplicar la
  membresía y sin consumir el código.
- **RF-21** CUANDO un miembro sale de un espacio, el sistema DEBE eliminar
  su membresía y conservar los gastos que registró, que siguen
  perteneciendo al espacio (principio 8).
- **RF-22** SI un usuario intenta salir de un espacio siendo su último
  miembro, ENTONCES el sistema DEBE rechazarlo e indicar que la vía para
  deshacerse de ese espacio es borrarlo.
- **RF-35** SI un usuario intenta salir del único espacio del que es
  miembro, ENTONCES el sistema DEBE rechazarlo, para que nadie quede sin
  ningún sitio donde registrar gastos.

### Borrado de espacios

- **RF-23** CUANDO el único miembro de un espacio pide borrarlo y confirma
  escribiendo su nombre exacto, el sistema DEBE borrar el espacio junto con
  sus datos del presupuesto.
- **RF-24** SI el espacio tiene más de un miembro, ENTONCES el sistema DEBE
  rechazar el borrado, para que nadie destruya datos que otra persona no
  aceptó perder.
- **RF-25** SI el nombre de confirmación no coincide exactamente con el del
  espacio, ENTONCES el sistema DEBE rechazar el borrado sin borrar nada.
- **RF-26** SI ese espacio es el único del que el usuario es miembro,
  ENTONCES el sistema DEBE rechazar el borrado, para que nadie quede sin
  ningún sitio donde registrar gastos.
- **RF-27** CUANDO se borra un espacio, el sistema NUNCA DEBE borrar el
  usuario ni tocar los datos de otros espacios.

### Aislamiento entre espacios

- **RF-28** Toda operación sobre datos del presupuesto DEBE indicar de forma
  explícita el espacio sobre el que actúa; el sistema NUNCA DEBE guardar un
  espacio activo por usuario ni deducirlo de peticiones anteriores.
- **RF-29** MIENTRAS un usuario esté autenticado, el sistema DEBE resolver
  la operación solo si es miembro del espacio indicado.
- **RF-30** SI un usuario indica un espacio del que no es miembro, o pide un
  recurso que pertenece a otro espacio, ENTONCES el sistema DEBE responder
  `404`, sin distinguir "no existe" de "existe pero no es tuyo".
- **RF-31** CUANDO se crea un gasto, el sistema DEBE guardar el espacio al
  que pertenece y el usuario que lo registró.
- **RF-32** El sistema NUNCA DEBE devolver datos del presupuesto en una
  respuesta sin haber filtrado por espacio.

### Arranque y salud

- **RF-33** SI falta al arrancar alguna variable de entorno obligatoria,
  ENTONCES el servicio DEBE negarse a arrancar con un error que la nombre,
  en lugar de continuar con un valor por defecto silencioso.
- **RF-34** El sistema DEBE seguir exponiendo `/health` sin autenticación y
  sin datos de usuarios ni de espacios (principio 15).

## Criterios de validación

La spec se da por cumplida cuando, además de los tests por requisito:

1. Un test crea dos usuarios en espacios distintos, registra un dato en cada
   uno y comprueba que ninguno aparece en las respuestas del otro
   (RF-29, RF-30, RF-32).
2. Un test comprueba que dos miembros del mismo espacio ven exactamente los
   mismos datos (RF-17, RF-29).
3. Un test comprueba que, tras cerrar sesión, el mismo token recibe `401`
   aunque no haya caducado (RF-12).
4. Un test comprueba que una petición sin sesión no modifica nada (RF-11).
5. Un test comprueba que un código de invitación no se puede canjear dos
   veces (RF-19).
6. Un test comprueba que borrar un espacio no toca los datos de otro
   espacio del mismo usuario (RF-27).
7. `make test` y `make lint` pasan en verde.

## Requisitos cubiertos por otras specs

`008-control-acceso` deberá cubrir la vinculación del `chat_id` a un usuario
y la sesión en la web, apoyándose en RF-8 a RF-12. La interfaz que recuerda
el último espacio usado (RF-28) es responsabilidad de la web y del bot, en
`007-dashboard-web` y `008-control-acceso`.
