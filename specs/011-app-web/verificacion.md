# Verificación a mano — 011 App web

Lista del criterio 5 de la spec. Se marca cada paso en cada navegador:
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
| La página carga sin errores en la consola ni peticiones a otros dominios (pestaña Red). | [ ] | [ ] | [ ] |
| Las fuentes IBM Plex cargan desde la propia web. | [ ] | [ ] | [ ] |
| Tema claro y tema oscuro siguen al sistema. | [ ] | [ ] | [ ] |
| Navegación abajo en 375 px y menú lateral en 1280 px. | — | — | [ ] |
| La barra inferior respeta el área segura del iPhone. | — | [ ] | — |

## Sesión (T6)

| Paso | A | I | C |
|---|---|---|---|
| Crear cuenta abre Registrar. | [ ] | [ ] | [ ] |
| Cerrar la app y volver a abrirla no pide entrar. | [ ] | [ ] | [ ] |
| Una contraseña corta muestra el mensaje de la API junto al campo. | [ ] | [ ] | [ ] |
| Cerrar sesión lleva a Entrar y borra la sesión. | [ ] | [ ] | [ ] |

## Registrar (T7 y T8)

| Paso | A | I | C |
|---|---|---|---|
| El monto abre el teclado numérico y muestra el punto de miles. | [ ] | [ ] | — |
| Débito con rubro: "Merc" sugiere "Mercado" con lo que queda. | [ ] | [ ] | [ ] |
| Débito sin rubro: pide la categoría. | [ ] | [ ] | [ ] |
| "Deshacer" borra el gasto recién registrado. | [ ] | [ ] | [ ] |
| Un error de la API conserva lo escrito. | [ ] | [ ] | [ ] |
| Crédito a 1 cuota: "¿Estaba en el plan?" sin respuesta marcada; sin elegir no deja registrar. | [ ] | [ ] | [ ] |
| Crédito "Sí, es del mes": sugiere rubros. | [ ] | [ ] | [ ] |
| Crédito a 6 cuotas: muestra "diciembre" y los intereses antes de guardar; a 12 se actualiza. | [ ] | [ ] | [ ] |

## Gastos (T9)

| Paso | A | I | C |
|---|---|---|---|
| Cambiar de mes con las flechas. | [ ] | [ ] | [ ] |
| "Solo los míos" filtra. | [ ] | [ ] | [ ] |
| Editar el monto de un gasto. | [ ] | [ ] | [ ] |
| Borrar con el diálogo; Escape cancela. | [ ] | [ ] | [ ] |
| Un mes vacío ofrece ir a Registrar. | [ ] | [ ] | [ ] |

## Espacio (T10 y T11)

| Paso | A | I | C |
|---|---|---|---|
| Compartir abre el menú del sistema (celular) o copia el enlace (computador). | [ ] | [ ] | [ ] |
| Abrir el enlace sin sesión, crear cuenta y unirse. | [ ] | [ ] | [ ] |
| Un enlace ya usado muestra el mensaje de la API. | [ ] | [ ] | [ ] |
| Salir de un espacio pide confirmación. | [ ] | [ ] | [ ] |
| La guía de fijar muestra los pasos de este navegador y la app queda fijada. | [ ] | [ ] | [ ] |
| Modo avión: aparece el aviso, no deja guardar y al volver se quita. | [ ] | [ ] | [ ] |

## Diseño y accesibilidad (T12)

| Paso | A | I | C |
|---|---|---|---|
| Todo se usa con teclado y el foco siempre se ve. | — | — | [ ] |
| Lector de pantalla (TalkBack o VoiceOver) lee cada campo de Registrar. | [ ] | [ ] | — |
| Zoom al 200 % sin perder contenido. | — | — | [ ] |
| Con "reducir movimiento", sin transiciones. | [ ] | [ ] | [ ] |
| Estados de carga, vacío, error y bloqueado en cada pantalla. | [ ] | [ ] | [ ] |
| Ningún emoji, sombra ni degradado; cifras alineadas a la derecha. | [ ] | [ ] | [ ] |
