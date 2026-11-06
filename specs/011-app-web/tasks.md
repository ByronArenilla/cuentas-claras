# Tareas 011 — App web

- Spec: `spec.md` (aprobada) · Plan: `plan.md` (aprobado)
- Regla: una tarea por vez, primero los tests y luego el código. Al
  terminarla, marcarla, ejecutar `make test` y `make lint`, y detenerse.
- Orden: primero la API (T1, T2) y el servidor de la web (T3), luego la
  base visual (T4) y la lógica sin DOM (T5), después las pantallas (T6 a
  T11), y al final la revisión de diseño y accesibilidad (T12), el ADR (T13)
  y el cierre (T14).
- Las tareas de pantallas tienen tests de su lógica con `node --test` y
  pasos de la lista de verificación a mano (`verificacion.md`, que crea T4).

## [x] T1 — Sesión renovable de 90 días (API)
`SESSION_LIFETIME` de 90 días en `auth.py` y renovación en
`current_session` (`deps.py`), como mucho una vez al día.

- Test primero (`test_session.py`, con el reloj fijado):
  - Entrar crea una sesión que caduca a los 90 días (cambia el test de los
    15 días).
  - Una petición autenticada 10 días después renueva la caducidad a 90 días
    desde ese momento.
  - Dos peticiones el mismo día escriben una sola vez (`expires_at` no
    cambia en la segunda).
  - Una sesión caducada responde `401` y no se renueva.
  - Cerrar sesión la invalida aunque se haya renovado.
- Hecho cuando: los tests pasan y los de la 001 siguen en verde.
- RF: RF-5.

## [ ] T2 — CORS para la web (API)
`CORSMiddleware` en `main.py` con el origen `WEB_BASE_URL`.

- Test primero (`test_cors.py`):
  - `OPTIONS /spaces` con `Origin: <WEB_BASE_URL>` y
    `Access-Control-Request-Method: POST` responde con
    `Access-Control-Allow-Origin` igual a ese origen y permite
    `Authorization` y `Content-Type`.
  - Un `GET` con ese origen trae la cabecera; con `Origin:
    http://otro.example`, no.
  - La respuesta no lleva `Access-Control-Allow-Credentials`.
- Hecho cuando: los tests pasan.
- RF: RF-38.

## [ ] T3 — Servidor de la web y comandos
`services/web/serve.py`, `services/web/ruff.toml`, `public/index.html`
mínimo, `make run-web` y `make test`/`make lint` con la web; `BIND_HOST` en
`run-api` y `run-web`; `.env.example` (`BIND_HOST`, y el comentario de
`WEB_BASE_URL` ya sin "provisional").

- Test primero (`services/web/tests/test_serve.py`, criterio 3):
  - `/`, `/registrar`, `/gastos/12` y `/unirse/abc` devuelven `index.html`.
  - `/manifest.webmanifest` sale como `application/manifest+json`; un
    `.js`, como `text/javascript`; un `.woff2`, como `font/woff2`.
  - `/css/no-existe.css` y `/../serve.py` responden `404`.
  - `/config.js` es un módulo con el `API_URL` del entorno.
  - Cada respuesta lleva la CSP del plan (con el origen de `API_URL` en
    `connect-src`), `nosniff`, `no-referrer` y `frame-ancestors 'none'`.
  - Sin `API_URL`, el servidor no arranca y lo dice.
  - Un primer `node --test` vacío (`smoke.test.js`) para que `make test`
    ya corra los dos.
- Hecho cuando: los tests pasan, `make run-web` sirve la página en
  `http://localhost:8080` y `make lint` revisa también `serve.py`.
- RF: RF-36, RF-37, RF-39.

## [ ] T4 — Base visual: tokens, fuentes, navegación, manifiesto e íconos
`tokens.css` (los dos temas), `app.css` (base, retícula, renglones,
botones, campos, navegación inferior y lateral, avisos, diálogo, estados),
fuentes IBM Plex con su OFL, `index.html` con la navegación y los
contenedores de avisos, `manifest.webmanifest`, `icon.svg` y sus PNG, y
`specs/011-app-web/verificacion.md` con la lista del criterio 5.

- Test primero:
  - `contrast.test.js` (criterio 2): lee `tokens.css` y comprueba en los dos
    temas que tinta, secundario y rojo sobre papel y sobre campo pasan
    4,5:1, y que el borde de control y el foco pasan 3:1.
  - `test_serve.py`: el manifiesto tiene `name`, `display: standalone`,
    `start_url: /registrar`, colores e íconos 192, 512 y 512 *maskable*, y
    cada ícono existe.
- Verificación a mano: la página vacía se ve en claro y oscuro; la
  navegación queda abajo en 375 px y al lado en 1280 px; las fuentes cargan
  desde la propia web (pestaña Red, sin otros dominios).
- Hecho cuando: los tests pasan y la verificación a mano de esta tarea está
  marcada.
- RF: RF-28, RF-31, RF-32, RF-34, RF-39.

## [ ] T5 — Lógica base: formato, cliente de la API, sesión y rutas
`dom.js`, `format.js`, `api.js`, `session.js`, `routes.js`, `offline.js`,
`state.js` y `main.js` (arranque y navegación entre rutas).

- Test primero (`node --test`):
  - `format.js`: `1240000` → `$ 1.240.000`; `0` → `$ 0`; negativos
    (`−12.000`); la limpieza del monto escrito (`"1.240.000"`, `"$ 52 000"`
    → `1240000`, `52000`; letras fuera); fechas `jue 6 nov`; meses
    `noviembre 2026`; mes anterior y siguiente de `2026-01`.
  - `api.js` con `fetch` simulado: manda `Authorization: Bearer` si hay
    token; un `401` borra la sesión y avisa; un `TypeError` de red marca
    sin conexión; un `422` de Pydantic se convierte en mensajes por campo;
    un `409` o `404` devuelve el `detail` de la API.
  - `session.js` con `localStorage` simulado: guarda y lee el token y el
    espacio actual; si el espacio guardado ya no está en la lista, elige el
    primero; la ruta siguiente solo acepta rutas propias (`/gastos` sí,
    `//otro.example` y `https://otro.example` no).
  - `routes.js`: cada ruta encuentra su vista y si pide sesión;
    `/unirse/abc` extrae el token; una ruta desconocida va a `/registrar`.
  - `offline.js`: cambia de estado con los eventos y con un fallo de red.
- Hecho cuando: los tests pasan.
- RF: RF-3, RF-7, RF-15, RF-23, RF-30, RF-35.

## [ ] T6 — Entrar, crear cuenta y cerrar sesión
`views/auth.js`, la redirección de `/` y el bloque "Tu cuenta" con cerrar
sesión.

- Test primero (`node --test`): el flujo de `session.js`/`api.js` al
  entrar (guarda token y correo, elige espacio, va a la ruta siguiente o a
  `/registrar`) y al cerrar sesión (llama a la API, borra todo; sin
  conexión, borra igual y devuelve el aviso de los 90 días).
- Verificación a mano: crear cuenta, cerrar la app, abrirla de nuevo sin
  entrar; cerrar sesión; contraseña corta con el mensaje de la API junto al
  campo; todo con teclado.
- Hecho cuando: los tests pasan y la verificación está marcada.
- RF: RF-1 a RF-4.

## [ ] T7 — Registrar un gasto a débito
`expense-form.js` (débito) y `views/record.js`: monto, tipo de pago, "Qué
fue" con sugerencias de rubros, categoría, fecha, envío y "Deshacer".

- Test primero (`expense-form.test.js`):
  - `suggestItems`: "merc" encuentra "Mercado" y "Mercado mascotas";
    "accion" encuentra "Acción"; "ano" no encuentra "Año".
  - `buildExpense` a débito con rubro (sin categoría ni descripción), sin
    rubro (categoría y descripción) y con fecha "Hoy" (sin `spent_on`).
  - Cambiar la fecha a otro mes suelta el rubro elegido (RF-9).
  - Tras registrar, el estado limpia monto y qué fue y conserva tipo de
    pago y fecha (RF-14).
  - El formulario no se puede enviar dos veces mientras espera (RF-16).
- Verificación a mano: registrar con rubro y sin rubro en el celular; el
  teclado numérico se abre en el monto; "Deshacer" borra el gasto; un error
  de la API conserva lo escrito.
- Hecho cuando: los tests pasan y la verificación está marcada.
- RF: RF-6 a RF-9, RF-13 a RF-16.

## [ ] T8 — Registrar un gasto a crédito
Crédito en `expense-form.js` y `views/record.js`: tarjeta, cuotas,
categoría, descripción obligatoria y la simulación.

- Test primero (`expense-form.test.js`):
  - `buildExpense` a crédito con tarjeta, cuotas, categoría y descripción;
    sin descripción, el estado dice qué falta.
  - A 1 cuota aparece "¿Estaba en el plan de este mes?" con "Sí, es del
    mes" y "No, es una deuda" sin ninguna marcada: sin elegir, el estado no
    deja enviar y dice qué falta. Con "Sí" se comporta como un débito
    (sugiere rubros); con "No", o con 2 cuotas o más, es deuda (spec 010,
    decisión 26).
  - Cuotas de las opciones rápidas y escritas (1 a 48; `0` y `49` no).
  - Cuándo se pide la simulación: con monto, tarjeta y cuotas; de nuevo al
    cambiar cualquiera o la fecha; no sin monto.
  - El resumen de la simulación: mes de la primera cuota ("diciembre"),
    número de cuotas, primera cuota e intereses estimados.
  - Sin tarjetas activas, el estado de crédito dice que no hay y no deja
    enviar (RF-10).
- Verificación a mano: la "Compra TV" a 6 cuotas muestra "diciembre" y los
  intereses antes de guardar; cambiar a 12 cuotas lo actualiza.
- Hecho cuando: los tests pasan y la verificación está marcada.
- RF: RF-6, RF-10 a RF-12.

## [ ] T9 — Gastos del mes: ver, editar y borrar
`expenses-list.js`, `views/expenses.js`, la edición en `views/record.js`
(`/gastos/<id>`) y el diálogo de borrar.

- Test primero (`expenses-list.test.js` y `expense-form.test.js`):
  - Agrupar por día del más reciente al más antiguo y el total del mes.
  - "Solo los míos" deja los de `created_by` igual al usuario.
  - El texto de cada gasto: rubro o descripción, y "Débito", "Visa · del
    mes · se paga en dic" o "Visa · deuda · 6 cuotas desde dic".
  - `buildChanges` envía solo lo que cambió; quitar el rubro envía
    `budget_item_id: null` con la categoría.
  - Una compra con abonos marca como bloqueados todos los campos menos qué
    fue y categoría, con la razón (RF-20).
- Verificación a mano: cambiar de mes con las flechas; editar el monto de
  un gasto; borrar con el diálogo (Escape cancela); mes vacío con su
  enlace a Registrar.
- Hecho cuando: los tests pasan y la verificación está marcada.
- RF: RF-17 a RF-22.

## [ ] T10 — Espacio: cambiar, crear, compartir y salir
`views/space.js`: lista de espacios, crear, compartir, salir y el nombre
del espacio actual en todas las pantallas.

- Test primero (`session.test.js` y `api.test.js`):
  - Crear un espacio pasa a él; salir de uno pasa al primero que quede.
  - Compartir usa `navigator.share` si existe y, si no, copia; el texto
    dice "un solo uso" y "24 horas".
  - El `409` de salir del único espacio muestra el mensaje de la API.
- Verificación a mano: compartir desde el celular abre el menú del
  sistema; en el computador copia el enlace; salir pide confirmación.
- Hecho cuando: los tests pasan y la verificación está marcada.
- RF: RF-23 a RF-26.

## [ ] T11 — Unirse por enlace, fijar la app y aviso sin conexión
`views/join.js`, la guía de fijar en `views/space.js` con `platform.js`, y
el aviso sin conexión en `views/notices.js`.

- Test primero:
  - `routes.test.js` y `session.test.js`: `/unirse/<token>` sin sesión
    guarda la ruta para volver después de entrar.
  - `platform.test.js`: los *user agents* de Safari en iPhone, Chrome en
    Android, Chrome y Edge en el computador y Firefox dan sus pasos (o
    "tu navegador no permite fijarla"); con `display-mode: standalone` no
    hay guía.
  - `offline.test.js`: sin conexión, los botones que envían quedan
    deshabilitados y lo escrito no cambia.
- Verificación a mano: abrir un enlace de invitación con y sin sesión,
  unirse desde otra cuenta; un enlace usado muestra el mensaje de la API;
  fijar la app en Android, iPhone y el computador; modo avión muestra el
  aviso y al volver se quita.
- Hecho cuando: los tests pasan y la verificación está marcada.
- RF: RF-27, RF-29, RF-30.

## [ ] T12 — Revisión de diseño y accesibilidad
Pasada completa con la sección "Diseño" de la spec.

- Test primero: `contrast.test.js` sigue en verde con los valores finales.
- Verificación a mano, en los dos temas: todo con teclado y foco visible;
  lector de pantalla (VoiceOver o TalkBack) en Registrar; zoom al 200 % sin
  perder contenido; objetivos de 44 px; `prefers-reduced-motion` sin
  transiciones; estados de carga, vacío, error y bloqueado en cada pantalla;
  ningún emoji, sombra ni degradado; cifras monoespaciadas y alineadas a la
  derecha.
- Hecho cuando: toda la lista de `verificacion.md` está marcada en Chrome
  de Android, Safari de iPhone y Chrome del computador.
- RF: RF-31 a RF-35.

## [ ] T13 — ADR 0015
`docs/adr/0015-web-sin-framework-sesion-y-pruebas.md`: token en
`localStorage` con CSP (y la cookie `HttpOnly` descartada), servidor de
desarrollo propio hasta la fase 2, CORS por `WEB_BASE_URL`, sesión de 90
días renovable con el uso (cambia RF-8 de la 001), pruebas con `node
--test` sin `npm`. Alternativas descartadas de la spec y del plan.

- Test primero: no aplica, es documentación.
- Hecho cuando: el ADR existe con la plantilla y el plan lo cita.
- RF: ninguno; principio 4.

## [ ] T14 — Cierre: README y validación
- `README.md`:
  - "Puesta en marcha" con Node ≥ 22, `make run-web` y la web en
    `http://localhost:8080`;
  - probar en el celular con `BIND_HOST=0.0.0.0` y la IP del computador;
  - fijar la app y el límite sin HTTPS;
  - la sesión de 90 días;
  - regenerar los íconos con `rsvg-convert`;
  - "Registrar gastos mientras llega la web" pasa a explicar la web.
- Repasar los seis criterios de validación de la spec.
- `docs/roadmap.md`: marcar `011-app-web` como terminada y dejar
  `012-tablero-y-planear` como spec activa.

- Test primero: no aplica, es documentación y validación.
- Hecho cuando: `make test` y `make lint` están en verde y la verificación
  a mano está completa.
- RF: cierra la spec.
