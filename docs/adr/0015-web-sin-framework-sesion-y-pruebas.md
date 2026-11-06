# ADR 0015 — Web sin framework: sesión, servidor de desarrollo y pruebas

- Fecha: 2026-11-06
- Estado: aceptada
- Fase / spec: 1 / 011-app-web
- Cambia: RF-8 de la spec 001 (duración de la sesión)

## Contexto

La spec 011 trae la primera web: HTML, CSS y módulos de JavaScript nativos,
sin framework ni paso de compilación (roadmap, evaluación del 2026-11-04).
Quedaban abiertas varias decisiones técnicas:

- **Dónde guardar el token.** El ADR 0003 fijó qué es (opaco, en la tabla
  `sessions`) y dejó para la web dónde vive en el navegador.
- **Cuánto dura la sesión.** RF-8 de la 001 la fijaba en 15 días desde que
  se entra. La persona pidió entrar una sola vez.
- **Cómo servir la web en la fase 1.** El enlace de invitación es una ruta,
  `/unirse/<token>` (ADR 0005), y la web necesita cabeceras de seguridad.
- **Cómo hablar con la API desde otro origen**: otro puerto en local.
- **Cómo probar JavaScript** sin `npm` ni dependencias (principios 2 y 3).

## Decisión

1. **El token se guarda en `localStorage`**, protegido por una
   Content-Security-Policy estricta. Solo se cargan scripts, estilos y
   fuentes propios, no hay código en línea, y la conexión solo va a la API.
   La web inserta el texto siempre con `textContent`, nunca con `innerHTML`.
2. **La sesión dura 90 días sin uso** y cada petición la renueva, como
   mucho una vez al día. Cerrar sesión la corta al momento. La renovación
   está en `current_session`.
3. **En la fase 1, la web la sirve `services/web/serve.py`**, hecho solo
   con la biblioteca estándar de Python:
   - responde `index.html` a las rutas de la app;
   - genera `/config.js` con `API_URL`;
   - pone la CSP, `nosniff`, `no-referrer` y `frame-ancestors 'none'`.
4. **La API acepta el origen `WEB_BASE_URL` con CORS**, sin credenciales.
5. **La lógica de la web se prueba con `node --test`**: módulos sin DOM que
   reciben sus dependencias (`fetch`, el almacenamiento). No hay
   `package.json`, ni `npm`, ni `node_modules`. Las pantallas se verifican a
   mano con una lista, y un test lee los colores de `tokens.css` y comprueba
   el contraste de WCAG 2.2 AA.
6. **Las fuentes (IBM Plex, licencia OFL) y los íconos se sirven desde la
   propia web.** Los PNG se generan una vez con `rsvg-convert`, que no es
   dependencia del proyecto.

## Alternativas descartadas

- **Cookie `HttpOnly`**: JavaScript no podría leer el token. Pero obliga a
  cambiar la API (poner y leer la cookie), configurar CORS con credenciales
  y protegerse de CSRF. Como la web no carga código de terceros, la CSP
  cubre el riesgo principal con menos piezas.
- **Sesión de 30 días sin uso**: más prudente, pero pide entrar tras unas
  vacaciones.
- **Sesión que nunca caduca**: un celular perdido seguiría con acceso, y no
  hay forma de cerrar sesión en otro dispositivo.
- **`python -m http.server`**: no responde `index.html` a
  `/unirse/<token>` ni pone cabeceras.
- **Que la API sirva la web**: acopla los dos servicios (principio 9).
- **Rutas con `#`**: el enlace de invitación ya es una ruta real.
- **Solo pytest**: la lógica de la web quedaría sin tests.
- **Playwright**: es una dependencia pesada, con navegadores descargados;
  encaja mejor en la fase de CI.
- **Service worker para el aviso sin conexión**: Chrome y Safari ya no lo
  exigen para fijar la web, y `navigator.onLine` más el fallo de `fetch`
  bastan para avisar.

## Consecuencias

- Se entra una sola vez. En el iPhone, la app fijada conserva su
  almacenamiento; abierta en Safari sin fijar, puede perderlo tras 7 días
  sin uso.
- Una petición `GET` puede escribir en `sessions` una vez al día para
  renovarla.
- **Un XSS podría leer el token.** Mitigarlo depende de mantener la CSP y
  no usar `innerHTML` con datos.
- En la fase 2, un contenedor reemplaza a `serve.py`, con la misma regla de
  rutas y las mismas cabeceras. En la fase 3, Nginx puede dejar web y API en
  el mismo origen y retirar CORS.
- `make test` exige Node ≥ 22.
- **Qué aprendí:** un framework no hace falta para tener tests ni una
  arquitectura clara. Basta separar la lógica (módulos puros con sus
  dependencias inyectadas) de la vista (funciones que arman el DOM).
