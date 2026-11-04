# Spec 005 — Bot: vinculación y registro guiado

- Fase: 1 — Aplicación y SDD
- Estado: aprobada (aprobación previa del 2026-11-04)
- Base: spec 001 (sesiones, RF-8 a RF-12; aislamiento, RF-28 a RF-32),
  spec 002 (categorías), spec 003 (gastos), spec 004 (resumen), ADR 0001

## Por qué

La forma principal de registrar un gasto en gastito es escribirle al bot
de Telegram en el momento en que sale el dinero. Si registrar cuesta más
que unos pocos toques, la gente deja de hacerlo y el presupuesto pierde su
sentido. Por eso el bot guía paso a paso con botones y pide confirmación
antes de guardar nada.

Para registrar a nombre de alguien, el bot tiene que saber quién le
escribe. El principio 13 exige que solo atienda chats vinculados a un
usuario registrado, y esa vinculación estaba planeada para la 008, que va
después. Sin ella este bot no podría funcionar, así que la vinculación del
chat se adelanta a esta spec (decisión 1). La 008 se queda con la sesión de
la web.

Por el principio 10, las reglas de un gasto siguen en la API: el bot solo
conversa, traduce lo que escribe el usuario y llama a la API.

## Qué entra

- Vincular un chat privado de Telegram a un usuario con un código de un
  solo uso, y desvincularlo.
- Que el bot obtenga una sesión de la API para el usuario de un chat
  vinculado.
- Registrar un gasto conversando: monto, espacio, categoría, tipo de pago,
  fecha y descripción, con confirmación.
- Tras registrar, una línea con cómo va el presupuesto de esa categoría.
- `/start`, `/ayuda` y `/cancelar`.

## Qué NO entra

- `/resumen`, `/ultimos` y `/deshacer`: spec 006.
- Editar o borrar gastos desde el bot, y corregir un paso del borrador
  antes de confirmar (se cancela y se empieza de nuevo).
- Entender frases libres como "gasté 20 mil en el mercado": spec 026.
- Mostrar el código de vinculación en la web: spec 007 o 008. Mientras
  tanto se pide a la API.
- Conversaciones que sobrevivan a un reinicio del bot (decisión 8).
- Grupos y canales de Telegram (decisión 6).
- *Webhooks*: el bot pregunta a Telegram por mensajes nuevos (*polling*),
  así no necesita una URL pública hasta la fase de despliegue.
- La sesión de la web: sigue en la 008.

## Conceptos

- **Chat vinculado**: chat privado de Telegram asociado a un usuario de
  gastito. Un chat pertenece a un solo usuario; un usuario puede tener
  varios chats (por ejemplo, dos cuentas de Telegram).
- **Código de vinculación**: código de un solo uso que el usuario pide a la
  API con su sesión y envía al bot con `/vincular`. Caduca a los 10
  minutos (decisión 1).
- **Llave del bot**: secreto compartido entre la API y el bot. Con ella el
  bot vincula chats y pide sesiones; nadie más puede hacerlo.
- **Borrador**: el gasto que el bot va armando durante la conversación.
  Vive en la memoria del bot y no existe en la API hasta que se confirma.

## Decisiones de clarificación (2026-11-04)

1. **La vinculación del chat entra en esta spec.** El usuario pide a la API
   un código de un solo uso, que caduca a los 10 minutos, y lo envía al bot
   con `/vincular CÓDIGO`. La API guarda qué chat pertenece a qué usuario y
   el bot se identifica ante ella con la llave del bot. La 008 se queda con
   la sesión de la web. Se descartaron un chat fijo en `.env`, que revierte
   lo que retiró el ADR 0001, y adelantar la 008 entera, que es el mismo
   trabajo en otra spec.
2. **Si el usuario tiene varios espacios, el bot pregunta en cuál con
   botones en cada gasto**; con uno solo, no pregunta. La confirmación
   muestra siempre el espacio. Evita que un gasto caiga en un espacio
   distinto del que el usuario cree (decisión 5 de la 001). Se descartó un
   espacio fijo elegido con un comando, porque es fácil olvidar en cuál
   está.
3. **El registro empieza con `/gasto`, con `/gasto MONTO` o escribiendo
   solo un monto.** El monto se escribe en pesos enteros, con o sin `$` y
   con o sin puntos de miles: `20000`, `20.000` o `$20.000`. Nunca se
   aceptan decimales ni la coma: en Colombia la coma es el separador
   decimal y `20,000` es ambiguo.
4. **Al registrar, el bot añade una línea con el presupuesto de esa
   categoría en el mes del gasto**: cuánto lleva, de cuánto, y lo que queda
   o cuánto se pasó. Si la categoría no tiene presupuesto, lo dice.

Decididas al redactar la spec, dentro de la aprobación previa:

5. **La fecha se elige con los botones Hoy, Ayer u Otra fecha.** Otra fecha
   se escribe `DD/MM` (año actual) o `DD/MM/AAAA`. Hoy y ayer se calculan
   en `TZ` (principio 7).
6. **El bot solo atiende chats privados.** En un grupo, cualquiera de sus
   miembros podría registrar a nombre del usuario vinculado.
7. **La sesión que el bot obtiene para un chat dura una hora**, no los 15
   días de un inicio de sesión. Si el chat se desvincula, el bot pierde el
   acceso a los datos de ese usuario como mucho una hora después, aunque la
   sesión se hubiera filtrado.
8. **El borrador vive en la memoria del bot y caduca tras 10 minutos sin
   respuesta.** Si el bot se reinicia, los borradores se pierden y el
   usuario empieza de nuevo. Nada se registra sin confirmación, así que no
   se pierde ningún gasto guardado.

## Requisitos funcionales

### Vincular el chat

- **RF-1** CUANDO un usuario autenticado pide un código de vinculación, el
  sistema DEBE generar un código de un solo uso que caduca a los 10 minutos
  y devolverlo con su caducidad (decisión 1).
- **RF-2** El sistema DEBE guardar solo el hash del código, nunca el código
  en claro, como con las invitaciones (RF-15 de la 001).
- **RF-3** CUANDO alguien envía `/vincular` con un código vigente en un
  chat privado, el sistema DEBE vincular ese chat al usuario del código,
  marcar el código como usado y confirmarlo en el chat con el correo del
  usuario.
- **RF-4** SI el código no existe, ya se usó o caducó, ENTONCES el sistema
  DEBE rechazar la vinculación con el mismo mensaje en los tres casos y sin
  vincular nada, aunque lleguen dos peticiones a la vez con el mismo código.
- **RF-5** CUANDO se vincula un chat que ya estaba vinculado a otro
  usuario, el sistema DEBE pasarlo al usuario del código nuevo. Un chat
  nunca pertenece a dos usuarios a la vez; un usuario puede tener varios
  chats.
- **RF-6** CUANDO alguien envía `/desvincular` en un chat vinculado, el
  sistema DEBE quitar la vinculación, y el bot NUNCA DEBE volver a actuar
  en nombre de ese usuario en ese chat sin una vinculación nueva.
- **RF-7** MIENTRAS un chat no esté vinculado, el bot NUNCA DEBE consultar
  ni registrar datos en su nombre, y DEBE responder a `/gasto`, o a un
  monto, con las instrucciones para vincularlo (principio 13).
- **RF-8** El bot DEBE ignorar los mensajes de grupos y canales
  (decisión 6).
- **RF-9** El sistema DEBE exigir la llave del bot para vincular,
  desvincular y obtener la sesión de un chat. SI falta o no coincide,
  ENTONCES DEBE responder `401` sin vincular nada y sin revelar si el chat
  está vinculado.
- **RF-10** CUANDO el bot pide la sesión de un chat vinculado, el sistema
  DEBE crear una sesión del usuario de ese chat que caduca a la hora
  (decisión 7). SI el chat no está vinculado, ENTONCES DEBE responder `404`.
- **RF-11** SI la API rechaza una sesión del bot porque caducó, ENTONCES el
  bot DEBE pedir una nueva y repetir la petición una sola vez.

### Registrar un gasto

- **RF-12** CUANDO el usuario de un chat vinculado envía `/gasto`, el bot
  DEBE pedir el monto. CUANDO envía `/gasto MONTO` o solo un monto, el bot
  DEBE empezar con ese monto (decisión 3).
- **RF-13** SI el monto no tiene uno de los formatos de la decisión 3, no
  es mayor que cero o supera el máximo de la API (un billón), ENTONCES el
  bot DEBE pedirlo de nuevo explicando el formato, sin avanzar. El bot
  NUNCA DEBE aceptar ni redondear decimales (principio 6).
- **RF-14** SI el usuario pertenece a un solo espacio, ENTONCES el bot DEBE
  usarlo sin preguntar. SI pertenece a varios, ENTONCES DEBE preguntar en
  cuál con un botón por espacio (decisión 2).
- **RF-15** El bot DEBE ofrecer como botones las categorías del espacio
  elegido, en el orden de la API (RF-4 de la 002).
- **RF-16** El bot DEBE preguntar el tipo de pago con los botones Débito y
  Crédito.
- **RF-17** El bot DEBE preguntar la fecha con los botones Hoy, Ayer y Otra
  fecha. SI la otra fecha no es un día real con formato `DD/MM` o
  `DD/MM/AAAA`, o es posterior a hoy en `TZ`, ENTONCES el bot DEBE pedirla
  de nuevo explicando el motivo (decisión 5; RF-6 de la 003).
- **RF-18** El bot DEBE ofrecer añadir una descripción, con un botón
  Omitir. SI supera 200 caracteres, ENTONCES DEBE pedirla de nuevo
  indicando el límite (RF-7 de la 003).
- **RF-19** ANTES de registrar, el bot DEBE mostrar el borrador completo
  (monto, tipo de pago, categoría, espacio, fecha y descripción) con los
  botones Confirmar y Cancelar. El bot NUNCA DEBE registrar un gasto sin
  que el usuario toque Confirmar.
- **RF-20** CUANDO el usuario confirma, el bot DEBE registrar el gasto en
  la API una sola vez, aunque toque Confirmar más de una vez, y responder
  que quedó registrado.
- **RF-21** CUANDO el gasto queda registrado, el bot DEBE añadir una línea
  con lo gastado en la categoría en el mes del gasto y su presupuesto
  vigente, y lo que queda o cuánto se pasó. Si no tiene presupuesto, DEBE
  decirlo (decisión 4; RF-11 a RF-13 de la 004). SI esa consulta falla,
  ENTONCES el bot DEBE confirmar el registro igualmente, sin la línea.
- **RF-22** CUANDO el usuario cancela, con el botón o con `/cancelar`, en
  cualquier paso, el bot DEBE descartar el borrador sin registrar nada y
  decirlo.
- **RF-23** SI pasan 10 minutos sin respuesta, ENTONCES el bot DEBE
  descartar el borrador; un mensaje o botón posterior de esa conversación
  NUNCA DEBE registrar nada (decisión 8).
- **RF-24** SI el usuario toca un botón de una conversación que ya terminó
  o de un paso anterior, ENTONCES el bot NUNCA DEBE cambiar el borrador ni
  registrar nada, y DEBE decir que esa conversación ya terminó.
- **RF-25** SI la API rechaza el gasto, ENTONCES el bot DEBE mostrar el
  motivo y no darlo por registrado. SI la API no responde, ENTONCES el bot
  DEBE avisarlo y conservar el borrador en la confirmación para que el
  usuario lo reintente o lo cancele.
- **RF-26** Mientras haya un borrador, `/gasto` DEBE descartarlo y empezar
  uno nuevo, y un texto que no corresponde al paso actual DEBE recibir una
  indicación de qué se espera, sin cambiar el borrador.

### Ayuda y formato

- **RF-27** CUANDO el usuario envía `/start` o `/ayuda`, o un texto que el
  bot no entiende y que no forma parte de un borrador, el bot DEBE explicar
  los comandos y, si el chat no está vinculado, cómo vincularlo.
- **RF-28** Todos los mensajes del bot DEBEN estar en español y mostrar los
  montos en pesos colombianos con puntos de miles (`$ 20.000`).

## Criterios de validación

La spec se da por cumplida cuando, además de los tests por requisito:

1. Un test pide un código con la sesión de Ana, lo usa desde un chat y
   comprueba que el chat queda vinculado a Ana, que el mismo código ya no
   sirve una segunda vez y que un código caducado se rechaza con el mismo
   mensaje (RF-1 a RF-4).
2. Un test comprueba que sin la llave del bot, o con una equivocada, las
   rutas de vinculación y de sesión responden `401` y no cambian nada
   (RF-9).
3. Un test comprueba que la sesión que obtiene el bot sirve para listar los
   espacios de Ana, que caduca a la hora y que, tras `/desvincular`, el bot
   ya no consigue sesión para ese chat (RF-6, RF-10).
4. Un test de la conversación recorre un gasto completo en un usuario con
   dos espacios: monto escrito como `$20.000`, espacio, categoría, tipo de
   pago, Ayer, descripción y Confirmar. Comprueba que la API recibe
   exactamente un gasto con esos datos y que la respuesta incluye la línea
   del presupuesto (RF-12 a RF-21).
5. Un test comprueba que `20,5`, `20.000,50`, `0`, `-5`, `abc` y un monto
   mayor que un billón se piden de nuevo sin avanzar (RF-13).
6. Un test comprueba que, con un solo espacio, el bot no pregunta el
   espacio (RF-14).
7. Un test fija el reloj el 31 de octubre a las 20:00 en Bogotá (ya 1 de
   noviembre en UTC) y comprueba que Ayer es el 30 de octubre y que una
   fecha del 1 de noviembre se rechaza por futura (RF-17, principio 7).
8. Un test comprueba que tocar Confirmar dos veces registra un solo gasto,
   y que un botón de una conversación cancelada o caducada no registra
   nada (RF-20, RF-23, RF-24).
9. Un test comprueba que un chat no vinculado recibe las instrucciones para
   vincularse y que el bot no llama a ninguna ruta de datos (RF-7).
10. `make test` y `make lint` pasan en verde para la API y el bot.

## Requisitos para otras specs

- `006-bot-consultas` reutiliza la vinculación, la sesión del bot y la
  conversación de esta spec. `/deshacer` ayuda en el caso de RF-25 en que
  la API registró el gasto pero la respuesta no llegó al bot.
- `007-dashboard-web` o `008-control-acceso` deben mostrar en la web el
  código de vinculación de RF-1 y, si hace falta, la lista de chats
  vinculados para quitarlos.
- `008-control-acceso` deja de cubrir la vinculación del chat, que pasa a
  esta spec, y se queda con la sesión de la web.
- `009-contenedores` debe pasar la llave del bot a la API y al bot como
  secreto, nunca dentro de la imagen (principio 12).
