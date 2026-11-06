# Verificación a mano — 011 App web

Lista del criterio 5 de la spec. Se marca cada paso en cada navegador.
Las marcas de **C** se comprobaron con Chromium sin interfaz, conducido por
su protocolo de depuración, el 2026-11-06: a 390 y 1280 px, en los dos
temas, con Tab de teclado y sin conexión emulada. "Zoom al 200 %" se
comprobó como *reflow* a 320 px sin desbordar. Faltan A, I y los pasos
que piden un lector de pantalla, el menú de compartir del sistema,
"reducir movimiento" o fijar la app de verdad.

Columnas:
**A** = Chrome en Android, **I** = Safari en iPhone, **C** = Chrome en el
computador. Antes de empezar:

- `make run-api` y `make run-web` corriendo.
- Para el celular: `BIND_HOST=0.0.0.0`, y `API_URL` y `WEB_BASE_URL` con la
  IP del computador en la red de la casa (README, "Probar en el celular").
- El espacio tiene al menos un rubro del mes y una tarjeta activa (se crean
  con la API: README, "Plan del mes" y "Tarjetas").

## Base (T4)

| Paso | A | I | C |
|---|---|---|---|
| La página carga sin errores en la consola ni peticiones a otros dominios (pestaña Red). | [ ] | [ ] | [x] |
| Las fuentes IBM Plex cargan desde la propia web. | [ ] | [ ] | [x] |
| Tema claro y tema oscuro siguen al sistema. | [ ] | [ ] | [x] |
| Navegación abajo en 375 px y menú lateral en 1280 px. | — | — | [x] |
| La barra inferior respeta el área segura del iPhone. | — | [ ] | — |

## Sesión (T6)

| Paso | A | I | C |
|---|---|---|---|
| Crear cuenta abre Registrar. | [ ] | [ ] | [x] |
| Cerrar la app y volver a abrirla no pide entrar. | [ ] | [ ] | [x] |
| Una contraseña corta muestra el mensaje de la API junto al campo. | [ ] | [ ] | [x] |
| Cerrar sesión lleva a Entrar y borra la sesión. | [ ] | [ ] | [x] |

## Registrar (T7 y T8)

| Paso | A | I | C |
|---|---|---|---|
| El monto abre el teclado numérico y muestra el punto de miles. | [ ] | [ ] | — |
| Débito con rubro: "Merc" sugiere "Mercado" con lo que queda. | [ ] | [ ] | [x] |
| Débito sin rubro: pide la categoría. | [ ] | [ ] | [x] |
| "Deshacer" borra el gasto recién registrado. | [ ] | [ ] | [x] |
| Un error de la API conserva lo escrito. | [ ] | [ ] | [x] |
| Crédito a 1 cuota: "¿Estaba en el plan?" sin respuesta marcada; sin elegir no deja registrar. | [ ] | [ ] | [x] |
| Crédito "Sí, es del mes": sugiere rubros. | [ ] | [ ] | [x] |
| Crédito a 6 cuotas: muestra "diciembre" y los intereses antes de guardar; a 12 se actualiza. | [ ] | [ ] | [x] |

## Gastos (T9)

| Paso | A | I | C |
|---|---|---|---|
| Cambiar de mes con las flechas. | [ ] | [ ] | [x] |
| "Solo los míos" filtra. | [ ] | [ ] | [x] |
| Editar el monto de un gasto. | [ ] | [ ] | [x] |
| Borrar con el diálogo; Escape cancela. | [ ] | [ ] | [ ] |
| Un mes vacío ofrece ir a Registrar. | [ ] | [ ] | [x] |

## Espacio (T10 y T11)

| Paso | A | I | C |
|---|---|---|---|
| Compartir abre el menú del sistema (celular) o copia el enlace (computador). | [ ] | [ ] | [ ] |
| Abrir el enlace sin sesión, crear cuenta y unirse. | [ ] | [ ] | [x] |
| Un enlace ya usado muestra el mensaje de la API. | [ ] | [ ] | [x] |
| Salir de un espacio pide confirmación. | [ ] | [ ] | [x] |
| La guía de fijar muestra los pasos de este navegador y la app queda fijada. | [ ] | [ ] | [ ] |
| Modo avión: aparece el aviso, no deja guardar y al volver se quita. | [ ] | [ ] | [x] |

## Diseño y accesibilidad (T12)

| Paso | A | I | C |
|---|---|---|---|
| Todo se usa con teclado y el foco siempre se ve. | — | — | [x] |
| Lector de pantalla (TalkBack o VoiceOver) lee cada campo de Registrar. | [ ] | [ ] | — |
| Zoom al 200 % sin perder contenido. | — | — | [x] |
| Con "reducir movimiento", sin transiciones. | [ ] | [ ] | [ ] |
| Estados de carga, vacío, error y bloqueado en cada pantalla. | [ ] | [ ] | [ ] |
| Ningún emoji, sombra ni degradado; cifras alineadas a la derecha. | [ ] | [ ] | [x] |
