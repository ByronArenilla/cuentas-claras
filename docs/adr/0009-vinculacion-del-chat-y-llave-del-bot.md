# ADR 0009 — Vinculación del chat con código y llave del bot

- Fecha: 2026-11-04
- Estado: aceptada
- Fase / spec: 1 / 005-bot-registro-guiado

## Contexto

El bot de Telegram registra gastos a nombre de quien le escribe, así que
tiene que saber qué usuario de gastito hay detrás de cada chat.

- El principio 13 exige que el bot solo atienda chats vinculados a un
  usuario registrado. El ADR 0001 retiró el `TELEGRAM_ALLOWED_CHAT_ID`
  fijo y propuso un código de vinculación de un solo uso.
- La vinculación estaba planeada para la 008, que va después del bot. Sin
  ella, la 005 no puede funcionar.
- El bot solo habla con la API por HTTP (principio 9) y no tiene base de
  datos propia.
- Toda ruta de datos de la API ya funciona con una sesión de la 001
  (`Authorization: Bearer`), y la tabla `sessions` ya está en `main`, así
  que cambiarla exigiría migraciones (ADR 0004).

## Decisión

1. **La vinculación entra en la 005.** El usuario pide con su sesión un
   código de un solo uso que caduca a los 10 minutos
   (`POST /telegram/link-codes`) y lo envía al bot con `/vincular`. La API
   guarda solo el hash del código y una fila `telegram_chats` que asocia
   el chat al usuario.
2. **El bot se identifica con una llave compartida**, `BOT_API_KEY`, en la
   cabecera `X-Bot-Key`. Solo con ella se vincula, se desvincula y se piden
   sesiones. La API la compara en tiempo constante y no arranca si mide
   menos de 32 caracteres.
3. **Para actuar en nombre del usuario, el bot pide una sesión normal que
   dura una hora** (`POST /telegram/sessions`) y la usa como la web, con
   `Authorization: Bearer`. Si caduca, pide otra.

## Alternativas descartadas

- **Un chat fijo en `.env` con las credenciales de un usuario**: era lo
  más rápido, pero revierte lo que retiró el ADR 0001 y deja el bot para
  una sola persona.
- **Que la API acepte la llave y un `chat_id` en cada petición de datos**:
  evita las sesiones del bot, pero cambia `current_user`, la pieza de la
  que depende toda la autenticación de la 001, y añade un segundo camino
  de entrada a cada ruta.
- **Una sesión de 15 días, como un inicio de sesión**: si el chat se
  desvincula, o la sesión se filtra, seguiría sirviendo dos semanas. La
  tabla `sessions` no sabe de qué chat viene una sesión, así que no se
  puede revocar por chat.
- **Un código corto de 6 dígitos**: un millón de combinaciones se puede
  recorrer a través de Telegram en sus 10 minutos de vida. Con 8
  caracteres de Crockford base32 (40 bits) no.
- **Enviar el correo y la contraseña al bot**: la contraseña quedaría en el
  historial del chat y en los servidores de Telegram.

## Consecuencias

- Las rutas existentes no cambian: el bot es un cliente más de la API.
- **La llave del bot es un secreto maestro**: con ella se obtiene una
  sesión de cualquier chat vinculado. Vive solo en `.env` (principio 12), y
  la 009 debe pasarla a los contenedores como secreto.
- Tras `/desvincular`, el bot cierra la sesión que tenía en memoria. Si
  hubiera otra copia, sirve como mucho una hora más.
- Las sesiones del bot se acumulan en `sessions` hasta caducar; limpiar
  las caducadas queda pendiente, igual que con las de la 001.
- La 008 se queda solo con la sesión de la web, y la web (007 u 008) debe
  mostrar el código de vinculación. Hasta entonces se pide con `curl`.
- Qué aprendí: cuando un servicio actúa en nombre de un usuario, pedir una
  credencial de corta duración y renovarla es más simple y más seguro que
  enseñar a cada ruta a reconocer al servicio.
