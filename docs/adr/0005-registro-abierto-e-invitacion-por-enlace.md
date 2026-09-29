# ADR 0005 — Registro abierto e invitación a espacios por enlace

- Fecha: 2026-09-29
- Estado: aceptada
- Fase / spec: 1 / 001-usuarios-y-espacios

## Contexto

La spec 001 cerró el registro (clarificación 1, RF-1 y RF-2): salvo el
primer usuario, nadie crea una cuenta sin un código de invitación. Para
quien quiere un presupuesto independiente existe una invitación de
instancia (RF-16), y para unirse a un espacio, una invitación de espacio
(RF-15, RF-17 y RF-18). Las dos se entregan como un código que hay que
copiar y pegar.

En la práctica eso tiene dos problemas:

- Para que alguien use la app por su cuenta, otro usuario tiene que
  generarle un código. El registro depende de conocer a alguien que ya
  esté dentro.
- Compartir un espacio consiste en pasar un código que la otra persona
  debe pegar en el sitio correcto. Lo natural es pulsar "compartir" y
  mandar un enlace.

Restricciones que aplican:

- El principio 13 exige que cada persona se autentique y solo alcance los
  espacios de los que es miembro. No exige que el registro sea cerrado.
- El principio 11 obliga a que la URL pública de la web entre por variable
  de entorno, porque cambia entre local, Docker y la nube.
- La rama de la spec 001 todavía no está integrada en `main` y no hay datos
  reales, así que cambiar la tabla `invitations` no obliga a migrar nada
  (ADR 0004).

## Decisión

1. **El registro es abierto**: cualquiera crea una cuenta con correo y
   contraseña. El primer usuario deja de ser un caso especial. La
   invitación de instancia desaparece.
2. **Compartir un espacio genera un enlace** con la forma
   `<WEB_BASE_URL>/unirse/<token>`. Es un
   [*capability URL*](https://www.w3.org/TR/capability-urls/): tener el
   enlace da el permiso de unirse. Por dentro es el mismo token aleatorio
   de 128 bits de hoy, del que la base de datos guarda solo el hash. La API
   devuelve el enlace completo, para que la web y el bot compartan
   exactamente lo mismo.
3. **El enlace es de un solo uso y caduca a las 24 horas**, igual que la
   invitación actual.
4. **Quien abre el enlace ve a qué espacio lo invitan** antes de decidir:
   una consulta sin sesión devuelve el nombre del espacio y la caducidad,
   sin consumir el enlace.
5. **Unirse exige sesión iniciada y una petición explícita** (`POST`).
   Abrir o consultar el enlace nunca une a nadie. Telegram y WhatsApp abren
   los enlaces para generar la vista previa; si abrir bastara para unirse,
   esa visita automática gastaría la invitación.
6. **El registro deja de aceptar invitaciones.** Quien abre el enlace sin
   cuenta se registra, inicia sesión y después se une: dos pasos que
   encadena la web. `/auth/register` ya no necesita saber nada de
   invitaciones.

## Alternativas descartadas

- **Mantener el registro cerrado**: protege una instancia expuesta en
  internet, pero obliga a pedirle un código a alguien para usar la app. El
  aislamiento por espacio ya impide que un desconocido vea datos ajenos, y
  el riesgo que queda (cuentas basura) se ataca mejor limitando peticiones.
- **Interruptor `REGISTRATION_OPEN` por entorno**: una variable y una rama
  de código más para un riesgo que hoy no existe, porque la instancia
  todavía no está expuesta. Se puede añadir si aparece el abuso.
- **Enlace reutilizable hasta que se revoque** (como un grupo de WhatsApp):
  cómodo para invitar a varias personas, pero obliga a decidir su
  caducidad y cómo revocarlo. Un enlace de un solo uso reutiliza la lógica
  que ya existe y está probada.
- **La API devuelve solo el token y cada cliente arma el enlace**: evita la
  variable `WEB_BASE_URL` en la API, pero duplica en la web y en el bot el
  conocimiento de la ruta `/unirse/...`, y los dos pueden acabar generando
  enlaces distintos.
- **Registrarse y unirse en una sola petición** (el RF-18 actual): es
  atómico, pero mezcla dos responsabilidades en `/auth/register`. Si el
  enlace caduca entre abrirlo y registrarse, la persona igualmente tiene
  cuenta y su espacio personal, que es un resultado aceptable.

## Consecuencias

Lo que gana el proyecto:

- Registrarse no depende de nadie, y compartir un espacio es pulsar un
  botón y mandar un enlace.
- Menos código: desaparecen la invitación de instancia, la columna `kind`
  con su restricción y la rama de invitaciones de `/auth/register`.

Lo que cuesta:

- **Cualquiera que alcance la instancia puede crear cuentas.** No ve datos
  ajenos, pero ocupa espacio en la base de datos. La mitigación es limitar
  peticiones (*rate limiting*) en Nginx, en `010-reverse-proxy`.
- **RF-4 deja saber a cualquiera si un correo está registrado.** Antes solo
  lo averiguaba quien tenía una invitación válida. También se mitiga con el
  límite de peticiones de `010-reverse-proxy`, junto con el de inicio de
  sesión que el plan 001 ya dejaba pendiente.
- **La API necesita una variable obligatoria nueva, `WEB_BASE_URL`**
  (RF-33), aunque la web todavía no exista.
- **El enlace no será utilizable desde un navegador hasta
  `007-dashboard-web`**, que es la spec que crea la página `/unirse/...`.
  Hasta entonces se canjea llamando a la API.
- **El token viaja en la URL** y quedará en los logs del servidor web. El
  riesgo es el mismo que el plan 001 ya anotaba para
  `POST /invitations/{code}/redeem`, y lo resuelve `010-reverse-proxy`.
- Qué aprendí: cerrar el registro protegía la instancia, pero no protegía
  los datos: eso ya lo hacía el aislamiento por espacio. Conviene separar
  qué control protege qué antes de mantenerlo.

## Cambios que se aplican si se acepta este ADR

1. `specs/001-usuarios-y-espacios/spec.md`:
   - Añadir la clarificación 9 (2026-09-29), que reemplaza a la 1, y
     marcar la 1 como reemplazada.
   - Conceptos: quitar "Invitación de instancia" y redefinir la invitación
     de espacio como enlace de un solo uso.
   - RF-1: el registro con correo y contraseña válidos crea el usuario,
     sin código.
   - RF-2, RF-16 y RF-18: retirados. Se conservan los números, que ya citan
     el código y los tests.
   - RF-4: quitar "sin consumir el código".
   - RF-15: compartir emite un enlace `<WEB_BASE_URL>/unirse/<token>` de un
     solo uso y 24 horas.
   - RF-36 (nuevo): consultar un enlace vigente devuelve el nombre del
     espacio y la caducidad, sin sesión y sin consumirlo.
   - RF-37 (nuevo): consultar el enlace nunca une a nadie; unirse exige
     sesión y una petición explícita.
   - Criterio de validación 5: añadir que consultar el enlace no lo
     consume.
2. `specs/001-usuarios-y-espacios/plan.md` y `tasks.md`: modelo sin `kind`,
   `WEB_BASE_URL` en `config.py` y `.env.example`, rutas nuevas y tareas
   para aplicarlo.
3. `README.md`: sustituir la tabla de invitaciones por el flujo del enlace.
4. `docs/roadmap.md`: anotar en `010-reverse-proxy` el límite de peticiones
   para el registro y el inicio de sesión.
