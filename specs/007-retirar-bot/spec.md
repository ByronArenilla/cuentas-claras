# Spec 007 — Retirar el bot de Telegram

- Fase: 1 — Aplicación y SDD
- Estado: aprobada (2026-11-04)
- Base: ADR 0010, que reemplaza al ADR 0009; specs 005 y 006

## Por qué

Los gastos se van a registrar solo desde la app web, que en el celular se
fija en la pantalla de inicio desde el navegador (ADR 0010). Con las
partidas y las cuotas que vienen en la 008 y la 009, registrar un gasto
conversando exige muchas preguntas seguidas. Adaptar el bot a cada cambio
del modelo sería mantener un segundo cliente al día.

Esta spec quita el bot antes de cambiar el modelo, para que la 008 y la 009
no tengan que adaptarlo. Después de ella, la API queda como estaba al
cerrar la 006, menos lo que solo usaba el bot.

## Qué entra

- Quitar el servicio `services/bot/`.
- Quitar de la API la vinculación de chats y las sesiones del bot:
  - las rutas `/telegram/*`;
  - la llave `BOT_API_KEY` y su cabecera `X-Bot-Key`;
  - las tablas, los esquemas y las funciones que solo servían para eso.
- Que `make`, `.env.example` y el README dejen de mencionar el bot.

## Qué NO entra

- Borrar las tablas de Telegram de las bases que ya existen: lo hace la
  primera migración de la 008 (decisión 1).
- Cambiar cualquier otra ruta de la API. `GET
  /spaces/{space_id}/expenses/recent` se queda, porque la web también lo
  usa (ADR 0010).
- Reescribir las specs 005 y 006 o el ADR 0009: quedan como historia.
- La web: es la 010.

## Decisiones de clarificación (2026-11-04)

1. **Las tablas `telegram_link_codes` y `telegram_chats` de las bases ya
   creadas se borran en la 008**, con la primera migración de Alembic y su
   ADR. Esta spec no toca la base: `create_all` no borra tablas, así que
   esas tablas siguen ahí sin que nada las use. Se descartaron:
   - **Borrarlas ahora con una instrucción manual:** sería un paso a mano
     sin migraciones, y el principio 14 lo considera un defecto.
   - **Dejarlas para siempre:** el esquema quedaría con tablas huérfanas.

Decididas al redactar la spec, dentro de la aprobación del ADR 0010:

2. **Si un `.env` viejo todavía define `BOT_API_KEY` o
   `TELEGRAM_BOT_TOKEN`, la API arranca igual y las ignora.** Fallar por
   una variable que sobra no protege nada y obligaría a editar el `.env`
   antes de poder trabajar. El README dice que se pueden borrar.
3. **Las sesiones que el bot ya tenga caducan solas en una hora** (ADR
   0009) y no se revocan. Son sesiones normales de su usuario: revocarlas
   exigiría saber cuáles vinieron del bot, y la tabla `sessions` no lo
   guarda.
4. **Lo que no es exclusivo del bot no se toca**, aunque lo haya creado la
   005 o la 006. Por ejemplo, `create_session(db, user_id, lifetime)` sigue
   recibiendo la duración: cambiarlo ahora no aporta nada y movería código
   que funciona.

## Requisitos funcionales

### API

- **RF-1** La API NO DEBE exponer rutas bajo `/telegram`. Una petición a
  cualquiera de ellas DEBE responder `404`.
- **RF-2** La API DEBE arrancar sin `BOT_API_KEY`. SI el entorno todavía la
  define, o define `TELEGRAM_BOT_TOKEN`, ENTONCES la API DEBE arrancar igual
  y no usarlas (decisión 2).
- **RF-3** La cabecera `X-Bot-Key` NO DEBE dar acceso a nada. Una petición
  que la trae sin sesión DEBE responder igual que cualquier petición sin
  sesión.
- **RF-4** Las demás rutas NO DEBEN cambiar de comportamiento, incluida la
  de últimos gastos de la 006. Sus tests DEBEN pasar con las mismas
  aserciones. Solo cambian los tests que arman la configuración con
  `BOT_API_KEY`.
- **RF-5** Una base de datos creada antes de esta spec, que todavía tiene
  las tablas de Telegram con filas, DEBE seguir funcionando. La API NUNCA
  DEBE borrar ni modificar esas tablas (decisión 1, principio 8).
- **RF-6** Una base de datos nueva NO DEBE tener las tablas de Telegram.

### Repositorio

- **RF-7** El repositorio NO DEBE contener `services/bot/`. `make install`,
  `make test` y `make lint` DEBEN cubrir solo la API, y el target
  `run-bot` NO DEBE existir.
- **RF-8** `.env.example` NO DEBE tener `TELEGRAM_BOT_TOKEN` ni
  `BOT_API_KEY`, y NO DEBE decir que el bot usa la API.
- **RF-9** El README NO DEBE describir el bot. DEBE explicar que, hasta la
  010, los gastos se registran con la API (`curl` o `/docs`), y que las
  variables del bot de un `.env` viejo se pueden borrar.

## Criterios de validación

La spec se da por cumplida cuando, además de los tests por requisito:

1. Un test pide cada una de las rutas que tenía `/telegram`, con y sin
   `X-Bot-Key`, y recibe `404` (RF-1, RF-3).
2. Un test pide una ruta de datos con `X-Bot-Key` y sin sesión, y recibe
   `401` (RF-3).
3. Tests de configuración: la API carga sin `BOT_API_KEY`, y también con
   `BOT_API_KEY` y `TELEGRAM_BOT_TOKEN` definidas (RF-2).
4. Un test arma una base con las tablas de Telegram y una fila en cada una
   antes de `create_all`, usa la API (registro, gasto y resumen) y
   comprueba que las tablas y sus filas siguen intactas (RF-5).
5. Un test comprueba que `create_all` sobre una base vacía no crea tablas
   de Telegram (RF-6).
6. `services/bot/` no existe, y `make install`, `make test` y `make lint`
   pasan en verde (RF-7).
7. `grep -ri "telegram\|bot_api_key"` sobre `Makefile`, `.env.example`,
   `services/` y el README solo encuentra menciones de historia
   justificadas: por ejemplo, las vistas previas de enlaces en Telegram o
   WhatsApp de la 001 (RF-8, RF-9).

## Requisitos para otras specs

- **008:** su primera migración de Alembic DEBE borrar
  `telegram_link_codes` y `telegram_chats` si existen, y su ADR DEBE
  justificarlo frente al principio 8 (decisión 1).
- **010:** la web es la única forma de registrar gastos además de la API.
  Puede usar `GET /spaces/{space_id}/expenses/recent` para "registrados
  recientemente".
