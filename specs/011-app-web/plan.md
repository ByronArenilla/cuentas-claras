# Plan 011 — App web

- Spec: `spec.md` (estado: aprobada)
- Servicios afectados: `services/web` (nuevo) y `services/api` (CORS y
  sesión renovable)
- Estado: aprobado (2026-11-06)

La web es HTML, CSS y módulos de JavaScript nativos, sin framework, sin
`npm` y sin paso de compilación (roadmap, evaluación del 2026-11-04). El
plan tiene cinco partes:

1. **Servir la web**: un servidor de desarrollo pequeño con la biblioteca
   estándar de Python, con las cabeceras de seguridad y la regla de rutas
   de una app de una página.
2. **API**: CORS para el origen de la web y la sesión renovable de 90 días.
3. **Base visual**: tokens, fuentes, retícula, navegación, manifiesto e
   íconos.
4. **Lógica de la web**: módulos puros que se prueban con `node --test`, y
   vistas que los usan y tocan el DOM.
5. **Pantallas**: entrar, Registrar, Gastos, Espacio y unirse.

Las decisiones técnicas quedan en el ADR **0015**: sesión en `localStorage`
con CSP, servidor de desarrollo propio, CORS, sesión renovable y pruebas
con `node --test`.

## Decisiones técnicas

| Decisión | Elegido | Por qué |
|---|---|---|
| Servidor de la web en la fase 1 | `services/web/serve.py` con [`http.server`](https://docs.python.org/3/library/http.server.html) de la biblioteca estándar: sirve `public/`, responde `index.html` a las rutas de la app y añade las cabeceras de RF-37 | `python -m http.server` no sabe responder `index.html` a `/unirse/<token>` (el enlace que arma la API) ni poner cabeceras. Se descartó que la API sirva la web: acoplaría los dos servicios (principio 9). En la fase 2 lo reemplaza un contenedor con la misma regla (spec, requisitos para la 013). |
| Rutas de la app | [History API](https://developer.mozilla.org/es/docs/Web/API/History_API): `/registrar`, `/gastos`, `/gastos/<id>`, `/espacio`, `/entrar`, `/crear-cuenta`, `/unirse/<token>` | El enlace de invitación ya es una ruta (`/unirse/<token>`, ADR 0005), así que hace falta la regla de rutas de todos modos. Con rutas reales, el botón atrás y los enlaces se comportan como se espera. Se descartaron las rutas con `#`. |
| Configuración de la web | `serve.py` genera `/config.js` con `export const API_URL = "…"` desde la variable `API_URL` | Principio 11: la URL de la API cambia entre entornos y no puede quedar escrita en el código. Un módulo propio cumple la CSP; un `<script>` en línea no. |
| Cabeceras de seguridad | CSP `default-src 'none'; script-src 'self'; style-src 'self'; font-src 'self'; img-src 'self' data:; manifest-src 'self'; connect-src <origen de API_URL>; base-uri 'none'; form-action 'self'; frame-ancestors 'none'`, más `X-Content-Type-Options: nosniff` y `Referrer-Policy: no-referrer` | Decisión 2 y RF-37. Con el token en `localStorage`, la CSP es la defensa principal contra XSS: ningún script ajeno ni en línea se ejecuta. `no-referrer` evita que el token de `/unirse/<token>` viaje a otra página. |
| Insertar datos en la página | Siempre con `textContent` y un ayudante `h(tag, attrs, ...children)` en `dom.js`; nunca `innerHTML` con datos | Una descripción como `<img onerror=…>` se muestra como texto. Complementa la CSP. |
| CORS | [`CORSMiddleware`](https://fastapi.tiangolo.com/tutorial/cors/) de FastAPI con `allow_origins=[settings.web_base_url]`, los métodos que usa la web y las cabeceras `Authorization` y `Content-Type`; sin credenciales | RF-38. Viene con FastAPI: no es una dependencia nueva. `WEB_BASE_URL` ya existe (es la URL de los enlaces de invitación). Sin cookies, no hace falta `allow_credentials`. |
| Sesión renovable | `SESSION_LIFETIME = 90 días`. `current_session` renueva `expires_at` a ahora + 90 días si quedan menos de 89, es decir, como mucho una escritura al día por sesión | RF-5 y decisión 9. Escribir en cada petición haría una escritura por clic; una al día basta para que la sesión no caduque mientras se use. |
| Dónde se guarda el token | `localStorage` con la clave `gastito.session` (token y correo), y `gastito.space` con el espacio actual | Decisión 2 y RF-23. Sobrevive a cerrar la app. En Safari del iPhone, la web fijada en la pantalla de inicio no pierde su almacenamiento por los 7 días sin uso que aplica Safari a las páginas normales ([WebKit](https://webkit.org/blog/10218/full-third-party-cookie-blocking-and-more/)). |
| Volver a la pantalla tras entrar | La ruta a la que se iba se guarda en `sessionStorage` (`gastito.next`) y solo se acepta si empieza por `/` y no por `//` | Decisión 16. Validarla evita una redirección abierta a otro sitio. |
| Lo escrito si la sesión caduca | El estado del formulario vive en memoria (módulo `state.js`) y no se pierde al pasar por Entrar, que no recarga la página | Decisión 16. Sin guardar datos de gastos en el dispositivo. |
| Sin conexión | `offline.js`: `navigator.onLine`, eventos `online`/`offline` y el `TypeError` de `fetch` cuando falla la red | Decisión 15 y RF-30. Sin *service worker*: Chrome dejó de exigirlo para instalar ([Chrome](https://developer.chrome.com/blog/update-install-criteria)) y Safari nunca lo pidió. |
| Pruebas de la web | `node --test services/web/tests/` (Node ≥ 22, que reconoce solo los módulos ES), con `fetch` y `localStorage` simulados que se pasan a cada módulo | Decisión 7. Node es una herramienta de desarrollo, como `make`: no hay `package.json`, ni `npm`, ni `node_modules`. Para que se pueda probar, la lógica vive en módulos sin DOM que reciben sus dependencias. |
| Servidor de la web en las pruebas | pytest de la API (`../api/.venv/bin/pytest`) corre `services/web/tests/test_serve.py` | El servidor es Python. No se crea otro entorno virtual: `serve.py` solo usa la biblioteca estándar y pytest ya está en el de la API. |
| Lint de `serve.py` | `ruff` de la API con `services/web/ruff.toml`, que extiende la configuración de la API | Mismas reglas en todo el Python del repositorio. |
| Fuentes | IBM Plex Sans (400 y 600) e IBM Plex Mono (400 y 500) en `woff2`, solo el subconjunto latino, descargadas del [repositorio oficial](https://github.com/IBM/plex) y guardadas en `public/fonts/` con su licencia OFL | RF-39: la CSP solo permite fuentes propias. Cuatro archivos de unos 20 KB. `font-display: swap` para que el texto se vea antes de que cargue la fuente. |
| Íconos de la app | `public/icons/icon.svg` como fuente; los PNG (192, 512, 512 *maskable* y 180 para iPhone) se generan una vez con `rsvg-convert` y se guardan en el repositorio | El iPhone no acepta SVG como ícono de inicio. `rsvg-convert` no es dependencia del proyecto: el comando queda en el README para regenerarlos. |
| Escuchar al sistema para el tema | Solo CSS: `@media (prefers-color-scheme: dark)`; `<meta name="theme-color">` con `media` para cada tema | Decisión 4. Sin JavaScript ni selector propio. |
| Formulario de Registrar | Un `<form>` real con `<label>` por campo y `inputmode="numeric"` en el monto; el envío se hace con `fetch` | Teclado, lector de pantalla y "Enter para enviar" funcionan sin trabajo extra (RF-33). |
| Diálogos | Elemento [`<dialog>`](https://developer.mozilla.org/es/docs/Web/HTML/Element/dialog) con `showModal()` | Decisión 23. Atrapa el foco y se cierra con Escape sin código propio. |
| Fecha máxima | `max` del campo de fecha con la fecha del dispositivo, solo como ayuda | La regla la pone la API (RF-6 de la 003): una fecha futura se rechaza con su mensaje. La web no calcula "hoy" para nada más (decisión 12). |
| Probar en el celular | `make run-api` y `make run-web` escuchan en `BIND_HOST`, por defecto `127.0.0.1` | Para abrir la web desde el celular en la red de la casa se pone `BIND_HOST=0.0.0.0` y `API_URL`/`WEB_BASE_URL` con la IP del computador. Por defecto no se expone a la red. El README lo explica. |

## Dependencias

- **Ninguna dependencia nueva de Python ni de JavaScript.**
- **Node ≥ 22** como herramienta de desarrollo, solo para `node --test`.
- **Fuentes IBM Plex** como archivos de la web (licencia OFL).
- **`rsvg-convert`** solo para regenerar los íconos; no lo necesita `make`.

## Estructura de archivos

    services/web/
      serve.py                       servidor de desarrollo           [RF-36, RF-37]
      ruff.toml                      extiende la configuración de la API
      public/
        index.html                   esqueleto: navegación, <main>, avisos
        manifest.webmanifest                                            [RF-28]
        css/
          tokens.css                 colores, tipografía, espacios, temas [RF-31, RF-32]
          app.css                    base, retícula, navegación, componentes, estados
        fonts/                       IBM Plex Sans y Mono (woff2) + OFL.txt
        icons/                       icon.svg y PNG 180, 192, 512, 512-maskable
        js/
          main.js                    arranque: sesión, rutas, navegación
          dom.js                     h(), sin innerHTML
          format.js                  pesos, fechas, meses, limpieza del monto [RF-7, RF-35]
          api.js                     cliente de la API                   [RF-3, RF-15, RF-30]
          session.js                 token, espacio actual, ruta siguiente [RF-2 a RF-4, RF-23]
          routes.js                  ruta → vista y si pide sesión
          expense-form.js            estado del formulario → gasto que se envía,
                                     sugerencias de rubros, cambios al editar [RF-6 a RF-16, RF-20]
          expenses-list.js           agrupar por día, total, "solo los míos" [RF-17 a RF-19]
          platform.js                navegador → pasos para fijar         [RF-29]
          offline.js                 estado de conexión                   [RF-30]
          state.js                   estado en memoria y suscripciones
          views/
            auth.js                  Entrar y Crear cuenta
            record.js                Registrar y editar
            expenses.js              Gastos del mes
            space.js                 Espacio, cuenta y guía para fijar
            join.js                  /unirse/<token>
            notices.js               registrado, error, sin conexión, diálogo
      tests/
        test_serve.py                pytest                               (criterio 3)
        format.test.js, api.test.js, session.test.js, routes.test.js,
        expense-form.test.js, expenses-list.test.js, platform.test.js,
        offline.test.js, contrast.test.js                                  (criterios 1 y 2)
    services/api/app/main.py         + CORSMiddleware                    [RF-38]
    services/api/app/deps.py         renovación de la sesión             [RF-5]
    services/api/app/routers/auth.py SESSION_LIFETIME de 90 días         [RF-5]
    services/api/tests/test_cors.py, test_session.py                     (criterio 4)
    Makefile                         + run-web; test y lint con la web
    .env.example                     comentario de WEB_BASE_URL; + BIND_HOST
    docs/adr/0015-web-sin-framework-sesion-y-pruebas.md
    README.md                        la web, probar en el celular, fijar la app

Solo `expense-form.js`, `expenses-list.js`, `format.js`, `api.js`,
`session.js`, `routes.js`, `platform.js`, `offline.js` y `state.js` tienen
lógica que se prueba sin navegador. Las vistas solo arman el DOM y llaman a
esos módulos.

## API

**Sesión renovable** (`app/deps.py`):

    RENEW_AFTER = timedelta(days=1)

    def current_session(...):
        ...  # igual que hoy: busca por hash y rechaza la caducada
        now = datetime.now(UTC)
        if session.expires_at - now < SESSION_LIFETIME - RENEW_AFTER:
            session.expires_at = now + SESSION_LIFETIME
            db.commit()
        return session

El `commit` va en la dependencia, antes de la ruta: si la ruta falla
después, la sesión igual queda renovada, que es lo correcto (se usó).

**CORS** (`app/main.py`):

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.web_base_url],
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )

Ninguna ruta nueva: la web usa las que ya existen.

## Servidor de la web (`serve.py`)

- `python3 services/web/serve.py --host $BIND_HOST --port 8080`, con
  `API_URL` del entorno. Si falta `API_URL`, no arranca y lo dice (como la
  API con sus variables).
- Una petición `GET`:
  - `/config.js` → el módulo con `API_URL`;
  - un archivo que existe en `public/` → el archivo, con su tipo
    (`.webmanifest` como `application/manifest+json`, `.woff2` como
    `font/woff2`, `.js` como `text/javascript`);
  - una ruta sin extensión → `index.html` (rutas de la app);
  - cualquier otra (`/css/no-existe.css`) → `404`.
- Nunca sirve nada fuera de `public/` (`/../serve.py` → `404`).
- Cada respuesta lleva las cabeceras de seguridad; `index.html` y
  `config.js`, además, `Cache-Control: no-cache`.

## Pantallas y datos

| Ruta | Pantalla | Pide sesión | Llamadas a la API |
|---|---|---|---|
| `/entrar` | Entrar | No | `POST /auth/login`, `GET /me`, `GET /spaces` |
| `/crear-cuenta` | Crear cuenta | No | `POST /auth/register` y lo de Entrar |
| `/registrar` | Registrar | Sí | `GET categories`, `GET cards`, `GET summary?period=` (rubros del mes), `POST cards/{id}/simulate`, `POST expenses`, `DELETE expenses/{id}?confirm=true` (Deshacer) |
| `/gastos` | Gastos del mes | Sí | `GET expenses?period=`, `GET categories`, `GET cards`, `GET summary?period=` (nombres de rubros), `GET /me` |
| `/gastos/<id>` | Editar gasto | Sí | `GET expenses/{id}`, `GET expenses/{id}/installments` (abonos), `PATCH`, `DELETE ?confirm=true` |
| `/espacio` | Espacio y cuenta | Sí | `GET /spaces`, `POST /spaces`, `POST spaces/{id}/invitations`, `DELETE spaces/{id}/members/me`, `POST /auth/logout` |
| `/unirse/<token>` | Unirse | No | `GET /invitations/{token}`, `POST /invitations/{token}/redeem` |
| `/` | — | — | Redirige a `/registrar` con sesión o a `/entrar` sin ella |

**Armar el gasto** (`expense-form.js`, sin DOM):

    buildExpense(state) -> objeto para POST /expenses
    buildChanges(original, state) -> solo lo que cambió, para PATCH
    suggestItems(items, text) -> rubros cuyo nombre contiene `text`, comparado
                                 sin mayúsculas ni tildes (la ñ cuenta)
    periodOf(state) -> mes de la fecha elegida, o null si es "Hoy"

- Débito con rubro: `{amount, payment_type: "debit", budget_item_id,
  spent_on?}`. La descripción no se envía: el nombre es el del rubro
  (decisión 26 de la 009).
- Débito sin rubro: `{amount, payment_type: "debit", category_id,
  description, spent_on?}`.
- Crédito como deuda (varias cuotas, o 1 cuota que no estaba en el plan):
  `{amount, payment_type: "credit", card_id, installments, is_debt: true,
  category_id, description, spent_on?}`.
- Crédito del mes (1 cuota que estaba en el plan): como un débito, con
  rubro o con categoría, más `card_id` e `is_debt: false` (spec 010). Se
  envía `is_debt` siempre, aunque la API lo deduzca, para que el gasto diga
  lo que la persona eligió.
- Editar: `is_debt` se manda solo si cambió la respuesta o las cuotas.
- `spent_on` solo si la fecha no es "Hoy" (RF-13).
- La comparación de nombres replica `category_key` de la 002: minúsculas,
  sin tildes ni diéresis, la ñ aparte. Los mismos casos de su test.

## Tokens de diseño (`tokens.css`)

Valores de partida. El test de contraste (`contrast.test.js`) lee este
archivo y comprueba RF-32 en los dos temas; cualquier ajuste tiene que
seguir pasándolo.

| Token | Claro | Oscuro | Uso |
|---|---|---|---|
| `--paper` | `#e9eee6` | `#111823` | Fondo |
| `--field` | `#f4f7f1` | `#18212e` | Renglón destacado, campo enfocado |
| `--ink` | `#18233a` | `#e3e9df` | Texto, botón principal |
| `--rule` | `#a9bccf` | `#2b3a4e` | Renglones (decorativos) |
| `--rule-strong` | `#5f7590` | `#7489a3` | Bordes de controles |
| `--red` | `#a8241c` | `#ff8a7e` | Doble raya, excedido, errores |
| `--muted` | `#566273` | `#9aa8b9` | Rótulos y texto secundario |

Contrastes medidos: tinta sobre papel 13,3 (claro) y 14,4 (oscuro);
secundario 5,3 y 7,4; rojo 6,1 y 7,8; borde de control 4,0 y 5,0.

Tipografía y espacios:

    --font-text: "IBM Plex Sans", system-ui, sans-serif;
    --font-figures: "IBM Plex Mono", ui-monospace, monospace;
    --size-label: 0.75rem;  --size-text: 1rem;  --size-strong: 1.125rem;
    --size-title: 1.375rem; --size-amount: 2.5rem;
    --space-1: 4px … --space-8: 40px;   --touch: 44px;   --row: 52px;
    --radius: 2px;  --rule-width: 1px;  --double-rule: 3px double var(--red);

## Tests

**API (pytest)**

- `test_cors.py`: una petición `OPTIONS` con `Origin: WEB_BASE_URL` recibe
  `Access-Control-Allow-Origin`; con otro origen, no (RF-38).
- `test_session.py` (con el reloj fijado): login → caduca en 90 días; una
  petición al día siguiente la renueva a 90 días desde ese momento; dos
  peticiones el mismo día escriben una sola vez; una sesión caducada sigue
  respondiendo `401` y no se renueva; cerrar sesión la invalida (RF-5).
- Los tests de la 001 que fijan los 15 días cambian a 90.

**Servidor de la web (pytest)**: `test_serve.py` levanta `serve.py` en un
puerto libre con un `API_URL` de prueba y comprueba el criterio 3.

**Lógica de la web (`node --test`)**: un archivo por módulo, criterio 1.
`contrast.test.js`: criterio 2.

**Verificación a mano**: la lista del criterio 5, en
`specs/011-app-web/verificacion.md`, con una casilla por paso y por
navegador.

## Makefile

    run-web:   $(LOAD_ENV); python3 services/web/serve.py --host $${BIND_HOST:-127.0.0.1} --port 8080
    run-api:   igual que hoy, con --host $${BIND_HOST:-127.0.0.1}
    test:      pytest de la API; pytest de services/web/tests; node --test services/web/tests/
    lint:      ruff check y format --check en la API y en services/web

## Riesgos y temas abiertos

- **Sin HTTPS, la app fijada no se abre a pantalla completa en el
  celular** (ADR 0010). Se verifica en el computador, donde `localhost`
  cuenta como seguro, y en el celular a pantalla completa cuando llegue la
  019.
- **Un XSS podría leer el token** (decisión 2). Lo mitigan la CSP sin
  scripts en línea ni ajenos, `textContent` en lugar de `innerHTML`, y no
  cargar nada de terceros.
- **La renovación de la sesión escribe desde una dependencia de lectura.**
  Una petición `GET` puede hacer un `UPDATE` una vez al día. Es aceptable,
  y queda dicho en el ADR.
- **Safari borra el almacenamiento de una página normal tras 7 días sin
  abrirla.** Con la app fijada no pasa. Si se usa desde el navegador sin
  fijar, puede pedir entrar de nuevo: la guía de fijar lo menciona.
- **Las vistas no tienen tests automáticos.** La lógica sí; lo visual se
  cubre con la lista de verificación hasta que la fase 4 añada pruebas de
  punta a punta.
- **Node ≥ 22 es requisito para `make test`.** El README lo dice en
  "Puesta en marcha".

## Conceptos nuevos

- [Web App Manifest](https://developer.mozilla.org/es/docs/Web/Manifest) e
  [íconos *maskable*](https://web.dev/articles/maskable-icon).
- [Content Security Policy](https://developer.mozilla.org/es/docs/Web/HTTP/CSP).
- [CORS](https://developer.mozilla.org/es/docs/Web/HTTP/CORS): qué es una
  petición de otro origen y por qué el navegador pregunta antes (`OPTIONS`).
- [History API](https://developer.mozilla.org/es/docs/Web/API/History_API) y
  la regla "toda ruta devuelve `index.html`" de una app de una página.
- [Módulos ES en el navegador](https://developer.mozilla.org/es/docs/Web/JavaScript/Guide/Modules).
- [`node --test`](https://nodejs.org/api/test.html): el test runner que
  trae Node.
- [Expiración deslizante](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html#idle-timeout)
  (*idle timeout*) de una sesión.
- [`prefers-color-scheme`](https://developer.mozilla.org/es/docs/Web/CSS/@media/prefers-color-scheme)
  y [`env(safe-area-inset-*)`](https://developer.mozilla.org/es/docs/Web/CSS/env).
- [WCAG 2.2](https://www.w3.org/TR/WCAG22/): contraste mínimo y tamaño de
  los objetivos táctiles.
