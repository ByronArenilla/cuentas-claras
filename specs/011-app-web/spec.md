# Spec 011 — App web

- Fase: 1 — Aplicación y SDD
- Estado: borrador, pendiente de aprobación (2026-11-06)
- Base: spec 001 (usuarios, espacios, sesión e invitaciones; ADR 0003 y
  ADR 0005), spec 003 (gastos), spec 008 (rubros y resumen), spec 009
  (tarjetas, compras a cuotas y simulación), spec 010 (gasto del mes con
  tarjeta o deuda), ADR 0010

## Por qué

Desde la 007 los gastos solo se registran desde la web (ADR 0010), y la web
todavía no existe: hoy todo se hace con `curl` o desde `/docs`. Registrar un
gasto tiene que tomar unos segundos en el celular, en la fila del
supermercado, con una mano.

Esta spec trae la primera versión de la web: entrar una sola vez,
registrar gastos a débito y a crédito, ver y corregir los gastos del mes,
cambiar de espacio y compartirlo, y fijarla en la pantalla de inicio para
que se abra como una aplicación. También fija el diseño que heredará la
012: su dirección visual, sus colores, su tipografía y sus reglas de
accesibilidad.

## Qué entra

- Crear cuenta, entrar y cerrar sesión. **Se entra una sola vez**: la sesión
  se renueva con el uso y solo caduca tras 90 días sin abrir la app.
- Registrar un gasto a débito (con rubro o no planeado) y a crédito (con
  tarjeta y cuotas), con el mes de pago y las cuotas a la vista antes de
  guardar. A 1 cuota, preguntar si estaba en el plan del mes (spec 010).
- Los gastos del mes: verlos, cambiar de mes, filtrar los propios, editarlos
  y borrarlos con confirmación.
- Espacios: cambiar de espacio, crear uno, compartirlo con un enlace, unirse
  desde ese enlace y salir de uno compartido.
- Fijar la web en la pantalla de inicio, con su manifiesto, sus íconos y una
  guía de pasos según el navegador.
- Avisar cuando no hay conexión.
- Diseño responsive con una sola app: navegación abajo en el celular y menú
  lateral desde 1024 px.
- El diseño de la app (sección "Diseño"), que la 012 reutiliza.
- En la API: CORS para la web y la renovación de la sesión.

## Qué NO entra

- El tablero del mes, planear el mes (rubros, ingresos, copiar el plan) y
  la pantalla de tarjetas (estado, abonos, pagar todo, extractos): son de la
  012.
- Crear, editar o archivar tarjetas y categorías desde la web: hasta la 012
  se hacen con la API.
- Borrar un espacio.
- Registrar gastos sin conexión o guardarlos para enviarlos después.
- Publicar la app en Play Store o App Store (ADR 0010).
- Notificaciones, recordatorios y widgets.
- Recuperar la contraseña o cambiarla.
- Cerrar sesión en otros dispositivos.
- Ver quién registró cada gasto de otro miembro: la API no tiene una ruta de
  miembros. Solo se distingue "mío" de "de otro miembro".
- HTTPS: llega con la 019. Hasta entonces, en el celular la app fijada se
  abre en el navegador y no a pantalla completa (ADR 0010).
- Traducciones: la app está en español de Colombia.

## Conceptos

- **App fijada**: la web abierta desde su ícono en la pantalla de inicio. Se
  ve sin la barra del navegador (modo *standalone*) cuando hay HTTPS.
- **Manifiesto web**: archivo
  ([Web App Manifest](https://developer.mozilla.org/es/docs/Web/Manifest))
  que le dice al navegador el nombre, los íconos y los colores de la app, y
  que se abra sin la barra.
- **Espacio actual**: el espacio en el que la web registra y lista. Se
  recuerda en cada dispositivo.
- **Sesión renovable**: la sesión no caduca a una fecha fija desde que se
  entra, sino 90 días después del último uso.
- **Qué fue**: el único campo con el que se nombra un gasto al registrarlo
  (decisión 26 de la 009). A débito sugiere los rubros del mes; a crédito es
  la descripción obligatoria.

## Decisiones de clarificación (2026-11-06)

1. **Alcance**: entrar y registrarse, registrar gastos, los gastos del mes
   con editar y borrar, y espacios (cambiar, crear, compartir, unirse y
   salir). Las tarjetas y categorías se siguen creando con la API hasta la
   012. Se descartó adelantar un resumen del mes en la pantalla de registro:
   es del tablero de la 012.
2. **El token de sesión se guarda en `localStorage`**, y la web se protege
   con una
   [Content Security Policy](https://developer.mozilla.org/es/docs/Web/HTTP/CSP)
   estricta: solo carga scripts, estilos y fuentes propios. Es la decisión
   que el ADR 0003 dejó para la web. Se descartó una cookie `HttpOnly`:
   obliga a cambiar la API, configurar CORS con credenciales y protegerse de
   CSRF, y la web no carga código de terceros.
3. **La dirección visual es "Libro auxiliar"**, elegida en un prototipo de
   tres direcciones (2026-11-06). El prototipo es desechable y no entra al
   repositorio; lo que vale de él está en la sección "Diseño". Se
   descartaron "Instrumento" (retícula de alto contraste con amarillo de
   señal) y "Recibo" (un recibo sobre fondo de pizarra).
4. **La app tiene tema claro y oscuro**, según el sistema. Se descartó solo
   el claro: registrar de noche con la pantalla blanca molesta.
5. **La pestaña Gastos muestra los gastos del mes por fecha de compra**,
   con flechas para cambiar de mes y un filtro "Solo los míos". Se descartó
   la lista de los últimos 20 registrados: no deja revisar un mes completo.
6. **Después de entrar, la app abre en Registrar**, con el teclado numérico
   en el monto. Se descartó abrir en la lista: un toque más por cada gasto.
7. **La web se prueba con el test runner de Node (`node --test`)**, sin
   `npm`, sin `package.json` y sin dependencias. Las pantallas se verifican
   a mano con una lista. Se descartaron solo pytest (la lógica de la web
   quedaría sin tests) y Playwright (dependencia pesada, mejor en la fase de
   CI).
8. **Salir de un espacio compartido entra; borrar un espacio no.**
9. **Se entra una sola vez.** La sesión se renueva cada vez que se usa y
   caduca tras 90 días sin abrir la app. Cerrar sesión la corta al momento.
   Cambia RF-8 de la 001 (15 días desde que se entra). Se descartaron 30
   días (más prudente, pero pide entrar tras un mes de vacaciones) y una
   sesión que nunca caduca (un celular perdido seguiría con acceso, y no hay
   forma de cerrar sesión en otro dispositivo).

## Decisiones tomadas al redactar la spec

10. **Un solo campo "Qué fue"** (decisión 26 de la 009). En un gasto del
    mes, mientras se escribe, sugiere los rubros del mes de la fecha del
    gasto con lo planeado y lo que queda. Elegir uno lo liga al rubro y la
    categoría sale de él. Escribir otra cosa pide la categoría y el gasto
    queda no planeado; el texto queda como descripción. Un gasto del mes es
    uno a débito o uno con tarjeta a 1 cuota que estaba en el plan (spec
    010). En una deuda (con tarjeta a varias cuotas, o a 1 cuota que no
    estaba en el plan) no sugiere rubros: pide categoría, y el texto es la
    descripción obligatoria.
11. **A crédito, la web muestra el mes de pago y las cuotas antes de
    guardar**, con la simulación de la API (RF-41 de la 009), y la actualiza
    al cambiar el monto, la tarjeta, las cuotas o la fecha.
12. **La web no calcula "hoy".** Si la fecha queda en "Hoy", no se envía y la
    API usa el día de hoy en `TZ`. Los rubros sugeridos para hoy salen del
    resumen sin periodo, que también es el mes actual en `TZ`. Así el
    celular con otra zona horaria no cambia de mes un gasto (principio 7).
13. **Tras registrar, el formulario queda listo para el siguiente gasto** y
    un aviso dice qué se registró, con un botón "Deshacer" durante 10
    segundos. Pulsar "Deshacer" es la confirmación explícita del borrado
    (principio 8). Se conservan el tipo de pago, la tarjeta y la fecha.
14. **Los mensajes de error de la API se muestran tal cual**: ya están en
    español y dicen qué hacer. Un error de un campo se muestra junto al
    campo.
15. **Sin conexión, la web lo avisa y no deja guardar**, pero conserva lo
    escrito. No hay *service worker*: el aviso sale de `navigator.onLine`,
    sus eventos y de una petición que falla por red. Chrome y Safari ya no
    exigen un *service worker* para fijar la web.
16. **Si la sesión caducó o se cerró en otro lado**, la web pide entrar de
    nuevo con un aviso y, después de entrar, vuelve a la pantalla en la que
    estaba, con lo que se había escrito.
17. **El espacio actual se recuerda en el dispositivo.** Si ya no se es
    miembro de él, la web pasa al primero de la lista.
18. **Compartir un espacio** usa el menú de compartir del sistema
    ([Web Share API](https://developer.mozilla.org/es/docs/Web/API/Navigator/share))
    si existe y, si no, un botón "Copiar enlace". Dice que el enlace es de
    un solo uso y caduca en 24 horas.
19. **Abrir un enlace `/unirse/<token>` nunca une a nadie** (ADR 0005).
    Muestra el nombre del espacio; con sesión, un botón "Unirme a «Casa»";
    sin sesión, entrar o crear cuenta, y después vuelve al enlace.
20. **La guía para fijar la app** detecta el navegador y muestra solo sus
    pasos: Safari en iPhone, Chrome en Android, o Chrome y Edge en el
    computador. No se muestra si la app ya se abrió fijada.
21. **Si el espacio no tiene tarjetas**, el crédito lo dice y explica que por
    ahora se crean con la API. No deja registrar un gasto a crédito sin
    tarjeta (decisión 8 de la 009).
22. **Cerrar sesión está en la pestaña Espacio**, en un bloque "Tu cuenta"
    con el correo, junto a la guía para fijar la app.
23. **Borrar un gasto pide confirmación en un diálogo propio** que muestra el
    monto y qué fue, no la ventana `confirm()` del navegador, que no se
    puede diseñar ni probar.
24. **Una compra con abonos** se edita solo en descripción y categoría (RF-16
    de la 009): los demás campos aparecen bloqueados con la razón.
25. **La navegación tiene tres secciones con nombre y sin íconos**:
    Registrar, Gastos y Espacio. Tres palabras se entienden sin aprender
    íconos, y en el celular caben con su texto completo.
26. **A crédito y a 1 cuota, la web pregunta "¿Estaba en el plan de este
    mes?"** con dos respuestas: "Sí, es del mes" (por defecto) y "No, es una
    deuda". La pregunta desaparece al elegir 2 cuotas o más. Lo pide la
    spec 010, que define cómo lo recibe la API; esta spec solo pone la
    pregunta en el formulario. Añadida al cambiar el orden de las specs
    (2026-11-06).

## Requisitos funcionales

### Sesión

- **RF-1** CUANDO una persona crea una cuenta con correo y contraseña
  válidos, la web DEBE crearla, entrar con ella y abrir Registrar. SI la API
  rechaza los datos, ENTONCES la web DEBE mostrar su mensaje junto al campo.
- **RF-2** CUANDO una persona entra con credenciales correctas, la web DEBE
  guardar el token en el dispositivo y abrir Registrar, o la pantalla a la
  que iba antes de entrar (decisiones 6 y 16).
- **RF-3** CUANDO la web se abre con un token guardado, DEBE usarlo sin
  pedir credenciales. SOLO SI la API responde `401`, ENTONCES la web DEBE
  borrar el token y pedir entrar de nuevo con el aviso de la API.
- **RF-4** CUANDO una persona cierra sesión, la web DEBE cerrar la sesión en
  la API, borrar el token y el espacio recordado del dispositivo y abrir
  Entrar. Sin conexión, DEBE borrar igual lo del dispositivo y avisar que la
  sesión en la API se cerrará sola a los 90 días.
- **RF-5** La API DEBE crear cada sesión con caducidad de 90 días y, CUANDO
  una petición autenticada usa una sesión vigente, DEBE renovar su
  caducidad a 90 días desde ese momento, como mucho una vez al día por
  sesión (decisión 9). Una sesión caducada NO DEBE renovarse. Cambia RF-8
  de la 001.

### Registrar un gasto

- **RF-6** La pantalla Registrar DEBE pedir, en este orden: monto, tipo de
  pago (débito por defecto), qué fue y fecha (por defecto "Hoy"). A crédito,
  además la tarjeta y las cuotas (1 por defecto) y, a 1 cuota, si estaba en
  el plan del mes (decisión 26). Un gasto del mes sin rubro elegido y una
  deuda piden además la categoría.
- **RF-7** El monto DEBE aceptar solo dígitos, mostrarse con punto de miles
  mientras se escribe (`1.240.000`) y abrir el teclado numérico en el
  celular. La web DEBE enviarlo como entero de pesos (principio 6).
- **RF-8** En un gasto del mes (decisión 10), CUANDO se escribe en "Qué
  fue", la web DEBE sugerir los
  rubros del mes de la fecha cuyo nombre contenga lo escrito, sin importar
  mayúsculas ni tildes, cada uno con su categoría, lo planeado y lo que
  queda. CUANDO se elige uno, el gasto DEBE enviarse con su rubro y sin
  categoría. CUANDO no se elige ninguno, DEBE pedirse la categoría y
  enviarse sin rubro (decisión 10).
- **RF-9** CUANDO cambia la fecha a otro mes, la web DEBE soltar el rubro
  elegido si no es de ese mes y sugerir los del mes nuevo.
- **RF-10** A crédito, la web DEBE ofrecer solo las tarjetas activas del
  espacio. En una deuda, DEBE exigir qué fue y categoría. SI el espacio no tiene tarjetas,
  ENTONCES DEBE decirlo y no dejar registrar a crédito (decisión 21).
- **RF-11** A crédito, CUANDO hay monto, tarjeta y cuotas, la web DEBE
  mostrar el mes de la primera cuota, el número de cuotas, el valor de la
  primera y los intereses estimados, con la simulación de la API, y
  actualizarlos al cambiar cualquiera de esos datos o la fecha (decisión
  11).
- **RF-12** Las cuotas DEBEN elegirse entre 1, 2, 3, 6, 12, 24 y 36 con un
  toque, o escribirse de 1 a 48.
- **RF-13** CUANDO la fecha queda en "Hoy", la web NO DEBE enviar `spent_on`
  (decisión 12). Una fecha futura NO DEBE poder elegirse.
- **RF-14** CUANDO el gasto se registra, la web DEBE limpiar monto y qué
  fue, conservar el tipo de pago, la tarjeta y la fecha, devolver el foco
  al monto y mostrar qué se registró con "Deshacer" durante 10 segundos
  (decisión 13). CUANDO se pulsa "Deshacer", DEBE borrar ese gasto y
  confirmarlo.
- **RF-15** SI la API rechaza el gasto, ENTONCES la web NO DEBE perder lo
  escrito y DEBE mostrar el mensaje de la API (decisión 14).
- **RF-16** El botón de registrar DEBE quedar deshabilitado mientras se
  envía, para que dos toques no registren dos gastos.

### Gastos del mes

- **RF-17** La pestaña Gastos DEBE listar los gastos del espacio actual en
  el mes elegido (por defecto el actual), agrupados por día del más
  reciente al más antiguo, y cambiar de mes con flechas (decisión 5).
- **RF-18** Cada gasto DEBE mostrar qué fue (rubro o descripción), su
  categoría, su monto y cómo se pagó: débito, o la tarjeta con sus cuotas
  ("Visa · 6 cuotas · desde dic"). La lista DEBE mostrar el total del mes
  listado.
- **RF-19** El filtro "Solo los míos" DEBE dejar solo los gastos que
  registró quien usa la app.
- **RF-20** CUANDO se abre un gasto, la web DEBE mostrar el formulario de
  Registrar con sus datos para editarlo, con las mismas reglas, y enviar
  solo lo que cambió. Una compra con abonos DEBE bloquear lo que no sea qué
  fue y categoría, diciendo por qué (decisión 24).
- **RF-21** CUANDO se pide borrar un gasto, la web DEBE pedir confirmación
  en un diálogo que muestre el monto y qué fue, y borrarlo solo al
  confirmar (decisión 23, principio 8).
- **RF-22** SI el mes no tiene gastos, ENTONCES la lista DEBE decirlo y
  ofrecer ir a Registrar.

### Espacios

- **RF-23** La web DEBE mostrar el nombre del espacio actual en todas las
  pantallas con sesión y, si hay más de uno, dejar cambiarlo desde la
  pestaña Espacio. El espacio elegido DEBE recordarse en el dispositivo
  (decisión 17).
- **RF-24** CUANDO se crea un espacio, la web DEBE crearlo y pasar a él.
- **RF-25** CUANDO se comparte el espacio, la web DEBE pedir un enlace a la
  API y ofrecerlo con el menú de compartir del sistema o copiarlo, diciendo
  que es de un solo uso y caduca en 24 horas (decisión 18).
- **RF-26** CUANDO se sale de un espacio compartido, la web DEBE pedir
  confirmación, salir y pasar a otro espacio. SI la API lo rechaza (único
  espacio o último miembro), ENTONCES DEBE mostrar su mensaje.
- **RF-27** CUANDO se abre `/unirse/<token>`, la web DEBE mostrar el nombre
  del espacio y la caducidad sin unir a nadie. Con sesión, DEBE ofrecer
  unirse y, al confirmar, pasar a ese espacio. Sin sesión, DEBE ofrecer
  entrar o crear cuenta y volver al enlace después. SI el enlace no es
  válido, ENTONCES DEBE decirlo con el mensaje de la API (decisión 19).

### Fijar en la pantalla de inicio

- **RF-28** La web DEBE servir un manifiesto con nombre "gastito",
  `display: standalone`, inicio en Registrar, colores del tema e íconos de
  192 y 512 px (también *maskable*), y un ícono de 180 px para iPhone.
- **RF-29** La pestaña Espacio DEBE mostrar los pasos para fijar la app del
  navegador que se está usando, y NO DEBE mostrarlos si la app ya está
  fijada (decisión 20).

### Aviso sin conexión

- **RF-30** CUANDO el dispositivo pierde la conexión o una petición falla
  por red, la web DEBE mostrar un aviso persistente, deshabilitar lo que
  envía datos y conservar lo escrito. CUANDO vuelve la conexión, DEBE quitar
  el aviso y habilitar de nuevo (decisión 15).

### Diseño y accesibilidad

- **RF-31** La web DEBE seguir la sección "Diseño" de esta spec: tokens,
  tipografía, temas claro y oscuro, navegación responsive y estados.
- **RF-32** Todo texto DEBE tener contraste de al menos 4,5:1 con su fondo,
  y los bordes de los controles y el foco, de al menos 3:1, en los dos
  temas ([WCAG 2.2 AA](https://www.w3.org/TR/WCAG22/)).
- **RF-33** Todo DEBE poder usarse solo con teclado, con el foco siempre
  visible, y cada control DEBE tener una etiqueta que lea un lector de
  pantalla. Los avisos (registrado, error, sin conexión) DEBEN anunciarse
  con `aria-live`.
- **RF-34** Todo lo que se toca DEBE medir al menos 44 × 44 px.
- **RF-35** Los montos DEBEN mostrarse en pesos colombianos con
  `Intl.NumberFormat("es-CO")` (`$ 1.240.000`), y las fechas y meses en
  español ("jue 6 nov", "noviembre 2026").

### Servicio web y API

- **RF-36** `make run-web` DEBE servir la web en el puerto 8080, con
  cualquier ruta de la app (`/registrar`, `/unirse/<token>`…) devolviendo
  la página de la app, y con la URL de la API tomada de `API_URL`
  (principio 11).
- **RF-37** Cada respuesta de la web DEBE llevar una Content-Security-Policy
  que solo permita scripts, estilos, fuentes e imágenes propios y
  conexiones a la API, además de `X-Content-Type-Options: nosniff`,
  `Referrer-Policy: no-referrer` y `frame-ancestors 'none'` (decisión 2).
- **RF-38** La API DEBE aceptar peticiones del origen `WEB_BASE_URL` (CORS)
  y de ningún otro.
- **RF-39** La web NUNCA DEBE cargar scripts, estilos ni fuentes de otros
  dominios.

## Diseño

Dirección: **Libro auxiliar**. Registrar un gasto es llenar un renglón de
un libro de cuentas: papel verdoso, renglones azules, tinta casi negra y
la doble raya roja bajo las cifras que cuentan. Es sereno y legible, y
encaja con lo que viene en la 012: columnas de cifras para planear.

### Principios

1. **Renglones, no tarjetas.** La información se ordena en líneas a lo ancho
   separadas por filetes finos, como un libro contable. Sin tarjetas
   flotantes, sin sombras, sin degradados, sin esquinas muy redondeadas
   (radio de 2 px como mucho).
2. **Las cifras son monoespaciadas y alineadas a la derecha**, con números
   tabulares, para que las columnas de montos se lean de un vistazo.
3. **Un solo color de acción: la tinta.** El botón principal es un bloque
   de tinta con texto en color papel. Los demás controles son texto o
   contorno.
4. **El rojo significa algo**: la doble raya bajo el monto que se está
   escribiendo y bajo los totales, lo excedido y los errores. Nunca decora.
   Lo excedido o el error nunca se marcan solo con color: llevan palabra o
   signo ("excedido", "−12.000").
5. **Sin emojis ni íconos decorativos.** Las secciones se nombran con
   palabras; los únicos glifos son flechas de mes y la marca de cerrar.
6. **El primer toque es el monto.** Registrar abre con el foco en el monto
   y el teclado numérico; el botón principal queda al alcance del pulgar.
7. **Pensado primero para el celular** (360 px de ancho) y extendido hacia
   el computador.

### Color

Seis tokens por tema, como variables CSS. Los valores exactos están en el
plan y los comprueba un test de contraste (RF-32).

| Token | Claro: libro de día | Oscuro: libro de noche |
|---|---|---|
| `--paper` | Papel verde grisáceo | Azul tinta muy oscuro |
| `--ink` | Tinta azul-negra | Papel claro |
| `--rule` | Renglón azul claro (decorativo) | Renglón azul apagado |
| `--rule-strong` | Borde de controles (≥ 3:1) | Borde de controles (≥ 3:1) |
| `--red` | Rojo de libro contable | Rojo claro legible sobre oscuro |
| `--muted` | Texto secundario (≥ 4,5:1) | Texto secundario (≥ 4,5:1) |

El tema oscuro no se invierte sin más: el papel pasa a azul tinta, los
renglones se apagan y el rojo se aclara para mantener el contraste.
`theme-color` del manifiesto y de la página sigue al tema.

### Tipografía

- **IBM Plex Sans** para el texto e **IBM Plex Mono** para cifras, fechas
  cortas y rótulos. Las dos con licencia
  [SIL Open Font License](https://openfontlicense.org/), servidas desde la
  propia web en `woff2` (RF-39), con una pila de respaldo del sistema.
- Escala de 5 tamaños: rótulo (12 px, mayúsculas espaciadas), texto
  (16 px), destacado (18 px), título (22 px) y monto (40 px en el celular).
  El texto de los campos nunca baja de 16 px: así el iPhone no hace zoom al
  enfocarlos.

### Espacio y retícula

- Base de 4 px: 4, 8, 12, 16, 20, 24, 32, 40.
- Margen lateral de 20 px en el celular. Renglones de al menos 52 px.
- Formulario de Registrar: columna de rótulo de 96 px y campo al lado.
- Desde 1024 px: menú lateral de 240 px y contenido de hasta 640 px (720 px
  en Gastos).

### Navegación

- **Celular (< 1024 px)**: barra inferior fija con Registrar, Gastos y
  Espacio, solo texto, con la sección actual en tinta y una raya roja
  arriba. Respeta el área segura del iPhone (`env(safe-area-inset-bottom)`).
- **Computador (≥ 1024 px)**: menú lateral con el nombre del espacio
  arriba y las tres secciones.
- La parte de arriba de cada pantalla muestra el espacio actual y el mes.

### Estados

- **Cargando**: renglones vacíos con el filete punteado, sin animaciones
  giratorias. Si tarda más de un segundo, el texto "Cargando…".
- **Vacío**: una línea que dice qué falta y la acción para resolverlo ("No
  hay gastos en octubre. Registrar uno").
- **Error**: un renglón con borde rojo a la izquierda, el mensaje de la API
  y cómo seguir.
- **Registrado**: una franja bajo el encabezado con lo registrado y
  "Deshacer"; se va sola a los 10 segundos.
- **Sin conexión**: una franja fija bajo el encabezado, en tinta sobre
  papel con raya roja: "Sin conexión. Lo que escribiste se queda aquí;
  podrás guardarlo cuando vuelva la conexión."
- **Bloqueado**: un campo que no se puede editar se ve como texto con la
  razón debajo, no como un campo gris.

### Movimiento

Solo transiciones cortas (150 ms) de color y de aparición de las
sugerencias y los avisos. Con `prefers-reduced-motion`, ninguna.

### Palabras

- Se habla de tú, en frases cortas.
- Cada botón dice lo que hace: "Registrar gasto", "Unirme a «Casa»",
  "Copiar enlace", "Salir de «Casa»".
- Los errores dicen qué pasó y cómo arreglarlo; los de la API se muestran
  tal cual.

## Criterios de validación

La spec se da por cumplida cuando, además de los tests por requisito:

1. `node --test` prueba sin navegador: el formato de pesos y fechas
   (`1240000` → `$ 1.240.000`), la limpieza del monto escrito, el filtro de
   rubros sin mayúsculas ni tildes ("merc" encuentra "Mercado" y "Mercado
   mascotas"; "accion" encuentra "Acción"), el armado del gasto que se
   envía en cada caso (débito con rubro, débito sin rubro, crédito del mes,
   crédito como deuda, fecha
   "Hoy" sin `spent_on`, edición con solo lo cambiado), el cliente de la API
   (token en la cabecera, `401` borra la sesión, error de red marca sin
   conexión, mensajes de error por campo) y la detección del navegador para
   la guía de fijar (RF-1 a RF-29).
2. Un test de contraste lee los tokens de los dos temas y comprueba RF-32.
3. pytest prueba el servidor de la web: cualquier ruta de la app devuelve
   la página, los archivos existentes se sirven con su tipo, un archivo que
   no existe responde `404`, la configuración sale de `API_URL` y cada
   respuesta lleva las cabeceras de RF-37.
4. pytest prueba en la API que el origen `WEB_BASE_URL` pasa CORS y otro no
   (RF-38); que la sesión nueva caduca a los 90 días; que usarla al día
   siguiente la renueva y usarla dos veces el mismo día escribe una sola
   vez; y que una caducada no se renueva (RF-5).
5. Verificación a mano en Chrome de Android, Safari de iPhone y Chrome del
   computador, con la lista del plan: crear cuenta, cerrar la app y volver
   a abrirla sin entrar, registrar un débito con rubro y otro sin rubro, un
   crédito a 6 cuotas viendo el mes de pago, deshacer, editar y borrar
   desde Gastos, cambiar de mes, compartir el espacio y unirse desde otra
   cuenta, salir del espacio, fijar la app, apagar la red y ver el aviso,
   tema oscuro, todo con teclado en el computador, y la navegación abajo y
   lateral (RF-1 a RF-35).
6. `make test` y `make lint` pasan en verde.

## Requisitos para otras specs y documentos

- **012-tablero-y-planear:** reutiliza el diseño de esta spec (tokens,
  tipografía, renglones, estados) y añade sus pantallas a la misma
  navegación; puede cambiar la pantalla de inicio al tablero (decisión 6).
  Trae la gestión de tarjetas y categorías desde la web (decisión 1).
- **013-contenedores:** la web se sirve con su propio contenedor; el
  servidor de desarrollo de esta spec (`serve.py`) se reemplaza por uno que
  aplique la misma regla de rutas y las mismas cabeceras (RF-36, RF-37).
- **014-reverse-proxy:** Nginx pone las cabeceras de seguridad de RF-37 y,
  si la web y la API quedan en el mismo origen, CORS puede retirarse.
- **015-integracion-continua:** el pipeline corre `node --test` además de
  pytest, y puede añadir pruebas de punta a punta (decisión 7).
- **019-https-dominio:** con HTTPS la app fijada se abre a pantalla
  completa en el celular.
- **Spec 001:** RF-8 pasa a sesiones de 90 días renovables con el uso
  (decisión 9). El ADR 0003 sigue valiendo: el token es el mismo.
- **AGENTS.md:** el glosario no cambia; el comando `make run-web` ya está
  nombrado y lo crea esta spec.
