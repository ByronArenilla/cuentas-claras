# Spec 006 — Bot: consultas y deshacer

- Fase: 1 — Aplicación y SDD
- Estado: aprobada (aprobación previa del 2026-11-04)
- Base: spec 003 (gastos), spec 004 (resumen), spec 005 (vinculación y
  conversación del bot), ADR 0009

## Por qué

Con la 005 el bot ya registra gastos, pero no responde a las dos preguntas
que vienen justo después: "¿cómo voy este mes?" y "¿qué acabo de anotar?".
Y si un gasto quedó mal, hoy solo se arregla con la API. Esta spec añade
tres comandos al bot:

- `/resumen`: cómo va el mes frente al presupuesto.
- `/ultimos`: lo último que se registró en un espacio.
- `/deshacer`: borrar el último gasto que registró el usuario, con
  confirmación. También resuelve el caso de la 005 en que un reintento
  pudo duplicar un gasto (RF-25 de la 005).

Como en la 005, las reglas siguen en la API (principio 10): el bot pide los
datos, los resume en un mensaje y, para borrar, pregunta antes de llamar a
la API.

## Qué entra

- `/resumen` con navegación al mes anterior y al siguiente.
- `/ultimos` con los cinco últimos gastos registrados en un espacio.
- `/deshacer` del último gasto propio, con confirmación.
- Una ruta de la API para los últimos gastos registrados de un espacio.
- Que el menú de comandos de Telegram muestre los comandos del bot.

## Qué NO entra

- Editar un gasto desde el bot.
- Borrar desde el bot un gasto que no sea el último propio.
- Gráficos o imágenes en el chat: el dashboard es de la 007.
- Fijar el presupuesto desde el bot: la 007 lo cubre en la web.
- Avisos que el bot envíe por su cuenta (por ejemplo, al acercarse al
  presupuesto).

## Conceptos

- **Últimos gastos registrados**: los gastos de un espacio ordenados por el
  momento en que se registraron (`created_at`), no por su fecha. Un gasto
  de la semana pasada registrado hoy aparece primero.
- **Mi último gasto**: el gasto registrado más recientemente por el
  usuario del chat, entre todos sus espacios.

## Decisiones de clarificación (2026-11-04)

1. **`/ultimos` muestra los cinco últimos gastos registrados en el
   espacio**, de cualquier mes y de cualquier miembro, del más reciente al
   más antiguo por momento de registro. Sirve para revisar lo que se acaba
   de anotar. Se descartó listar el mes por fecha del gasto, porque un
   gasto de otro mes registrado hoy no aparecería.
2. **`/deshacer` borra el último gasto que registró el usuario**, en
   cualquiera de sus espacios y sin límite de tiempo. Antes muestra el
   gasto y pide Borrar o Cancelar (principio 8). Nunca toca gastos de otros
   miembros. Se descartaron limitarlo a las últimas 24 horas (la
   confirmación ya muestra qué se va a borrar) y elegir de una lista (eso es
   borrar, no deshacer).
3. **`/resumen` muestra los totales y solo las categorías con presupuesto o
   con gastos en el mes.** En un chat, las líneas con todo en cero son
   ruido. La API sigue devolviendo todas (decisión 2 de la 004).
4. **`/resumen` empieza en el mes actual en `TZ` y trae los botones
   ‹ mes anterior y mes siguiente ›**, así se navega sin escribir fechas.

Decididas al redactar la spec, dentro de la aprobación previa:

5. **Si el usuario tiene varios espacios, `/resumen` y `/ultimos` preguntan
   en cuál con botones**, igual que al registrar (decisión 2 de la 005).
   `/deshacer` no pregunta: busca en todos.
6. **Los botones de estos comandos no dependen del estado del bot.** Cada
   botón lleva el espacio, el mes o el gasto al que se refiere, así que
   sigue sirviendo después de reiniciar el bot y no interrumpe un gasto
   que se está registrando.
7. **En `/ultimos` se marca el gasto que registró otro miembro**, sin decir
   quién: la API solo da su identificador, y mostrar el correo de otro
   miembro es una decisión de privacidad que ninguna spec ha tomado (plan
   003).
8. **El bot registra sus comandos en el menú de Telegram al arrancar**,
   para que aparezcan al escribir `/` sin configurarlos a mano en
   @BotFather (principio 14).

## Requisitos funcionales

### API: últimos gastos registrados

- **RF-1** CUANDO un miembro pide los últimos gastos registrados de un
  espacio, el sistema DEBE devolver como mucho el número pedido, de 1 a 20
  y por defecto 5, ordenados del registrado más recientemente al más
  antiguo, de cualquier periodo (decisión 1).
- **RF-2** CUANDO la petición pide solo los gastos propios, el sistema DEBE
  devolver solo los que registró quien llama (decisión 2).
- **RF-3** SI el número pedido no está entre 1 y 20, ENTONCES el sistema
  DEBE rechazar la petición.
- **RF-4** La ruta DEBE pasar por la comprobación de membresía y NUNCA DEBE
  devolver gastos de otro espacio (RF-12 y RF-19 de la 003).

### `/resumen`

- **RF-5** CUANDO el usuario de un chat vinculado envía `/resumen`, el bot
  DEBE mostrar el resumen del mes actual en `TZ` del espacio elegido
  (decisiones 4 y 5).
- **RF-6** El resumen DEBE empezar con el espacio y el mes, y el total
  gastado frente al total presupuestado, con lo que queda o cuánto se pasó.
  Sin ningún presupuesto, DEBE mostrar solo lo gastado e indicarlo.
- **RF-7** El bot DEBE listar después cada categoría con presupuesto o con
  gastos en el mes, en el orden de la API, con lo gastado, su presupuesto y
  lo que queda o cuánto se pasó. NUNCA DEBE listar una categoría sin
  presupuesto ni gastos (decisión 3). Si no queda ninguna, DEBE decir que
  el mes no tiene gastos ni presupuesto.
- **RF-8** El resumen DEBE traer los botones del mes anterior y del mes
  siguiente. CUANDO el usuario toca uno, el bot DEBE mostrar el resumen de
  ese mes en el mismo espacio.

### `/ultimos`

- **RF-9** CUANDO el usuario envía `/ultimos`, el bot DEBE mostrar los
  cinco últimos gastos registrados en el espacio elegido, cada uno con
  monto, categoría, fecha y descripción si la tiene (decisiones 1 y 5).
- **RF-10** El bot DEBE marcar los gastos que registró otro miembro, sin
  mostrar quién (decisión 7).
- **RF-11** SI el espacio no tiene gastos, ENTONCES el bot DEBE decirlo.

### `/deshacer`

- **RF-12** CUANDO el usuario envía `/deshacer`, el bot DEBE buscar el
  último gasto que registró él entre todos sus espacios y mostrarlo
  completo, con su espacio, junto a los botones Borrar y Cancelar
  (decisión 2).
- **RF-13** SI el usuario no registró ningún gasto en ninguno de sus
  espacios, ENTONCES el bot DEBE decir que no hay nada que deshacer.
- **RF-14** El bot NUNCA DEBE borrar un gasto sin que el usuario toque
  Borrar (principio 8; requisito de la 003 para la 005 y la 006).
- **RF-15** CUANDO el usuario toca Borrar, el bot DEBE borrar ese gasto, y
  solo ese, y confirmarlo. SI el gasto ya no existe, por ejemplo porque se
  tocó Borrar dos veces o lo borró otro miembro, ENTONCES el bot DEBE
  decirlo sin borrar nada más.
- **RF-16** CUANDO el usuario toca Cancelar, el bot DEBE decir que no borró
  nada.

### Comunes

- **RF-17** Los tres comandos DEBEN responder a un chat no vinculado con
  las instrucciones para vincularlo, sin consultar datos (RF-7 de la 005).
- **RF-18** Los botones de estos comandos DEBEN seguir funcionando tras
  reiniciar el bot, y usarlos NUNCA DEBE cambiar ni descartar un gasto que
  se está registrando (decisión 6).
- **RF-19** SI la API no responde, ENTONCES el bot DEBE avisarlo sin dar
  por hecho nada.
- **RF-20** La ayuda DEBE incluir los tres comandos, y al arrancar el bot
  DEBE registrar en Telegram la lista de comandos con su descripción
  (decisión 8).

## Criterios de validación

La spec se da por cumplida cuando, además de los tests por requisito:

1. Un test de la API registra gastos en dos espacios y de dos miembros, y
   comprueba que la ruta devuelve los de un solo espacio, por momento de
   registro (incluido uno de otro mes registrado al final), con el límite
   pedido, y solo los propios si se piden (RF-1 a RF-4).
2. Un test de la conversación comprueba el texto de `/resumen` con una
   categoría excedida, una dentro del presupuesto, una sin presupuesto con
   gastos y otra sin nada, que no aparece (RF-6, RF-7).
3. Un test toca ‹ y › y comprueba que el bot pide el resumen del mes
   anterior y del siguiente del mismo espacio, también al cruzar de año
   (RF-8).
4. Un test comprueba que, con dos espacios, `/resumen` y `/ultimos`
   preguntan el espacio, y con uno no (decisión 5).
5. Un test comprueba que `/ultimos` marca el gasto de otro miembro y que un
   espacio vacío lo dice (RF-9 a RF-11).
6. Un test de `/deshacer` con dos espacios comprueba que propone el gasto
   propio más reciente de cualquiera de ellos, que Cancelar no borra nada,
   que Borrar borra solo ese gasto y que un segundo Borrar dice que ya no
   existe (RF-12 a RF-16).
7. Un test comprueba que usar `/resumen` o `/ultimos` en mitad del registro
   de un gasto no descarta ese gasto (RF-18).
8. Un test comprueba que un chat no vinculado recibe las instrucciones en
   los tres comandos (RF-17).
9. `make test` y `make lint` pasan en verde.

## Requisitos para otras specs

- `007-dashboard-web` puede reutilizar la ruta de últimos gastos para una
  lista de "registrados recientemente".
- Si alguna spec decide mostrar quién registró cada gasto, `/ultimos` puede
  cambiar la marca de RF-10 por el nombre.
