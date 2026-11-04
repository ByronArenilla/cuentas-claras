# ADR 0010 — Registro solo desde la app web; se retira el bot de Telegram

- Fecha: 2026-11-04
- Estado: aceptada
- Fase / spec: 1 / 007-retirar-bot
- Reemplaza a: ADR 0009

## Contexto

Al prototipar la web de la 007 cambió el modelo del presupuesto:

- Las partidas tienen nombre libre y una categoría.
- Se registran los ingresos del mes.
- Las compras con tarjeta llevan tarjeta y número de cuotas.

Registrar todo eso conversando exige muchas preguntas seguidas: monto,
partida o "no planeado", tipo de pago, tarjeta, cuotas, fecha y nota. En un
chat cada una es un mensaje con botones. En un formulario es una sola
pantalla, que además muestra el mes del pago y el costo de las cuotas antes
de guardar.

Dos hechos llevan a esta decisión:

- El bot (specs 005 y 006) habría tenido que rehacerse para partidas, para
  tarjetas y para cada cambio que viniera después. Es un segundo cliente que
  mantener al día con cada cambio de la API.
- La web se puede fijar en la pantalla de inicio del celular desde el
  navegador y abrirse como una aplicación, sin descargar nada de una
  tienda. Así cubre el uso en el celular que justificaba el bot.

La constitución nombra el bot en los principios 9, 10 y 13. Solo se modifica
con un ADR aprobado; este lo es.

## Decisión

1. **Los gastos se registran solo desde la app web.** No se instala ni se
   publica en Play Store o App Store: en el celular se fija en la pantalla
   de inicio con la opción del navegador ("Añadir a pantalla de inicio") y
   se abre como una aplicación, gracias a un
   [manifiesto web](https://developer.mozilla.org/es/docs/Web/Manifest).
2. **Se retira el bot de Telegram.**
   - Sale `services/bot/`.
   - Salen de la API las rutas `/telegram/*`, la llave `BOT_API_KEY` con su
     cabecera `X-Bot-Key`, y los modelos y esquemas de la vinculación.
   - Queda `GET /spaces/{space_id}/expenses/recent` (spec 006), porque la
     web también lo usa.
3. **La constitución pasa a tener dos servicios, `api` y `web`** (principio 9).
   El principio 10 deja de nombrar Telegram y el principio 13 deja de nombrar
   los chats vinculados.
4. **Este ADR reemplaza al 0009.** Las specs 005 y 006 quedan como historia:
   no se reescriben.

## Alternativas descartadas

- **Mantener el bot y adaptarlo a partidas y cuotas.** Duplica cada cambio
  del modelo en dos clientes, y la conversación queda más larga que el
  formulario.
- **Dejar el bot solo para gastos simples** (débito y partida conocida). Hay
  que mantener dos caminos de registro con reglas distintas, y el bot no
  podría marcar las compras a crédito, que son justo las que alimentan la
  deuda del mes siguiente.
- **Publicar la app en las tiendas** (empaquetarla con TWA o Capacitor).
  Añade cuentas de desarrollador, revisión y un paso de compilación, y
  contradice el principio 2. Fijar la web desde el navegador es suficiente.

## Consecuencias

- **La infraestructura se simplifica:** dos servicios en vez de tres. Las
  fases de contenedores, CI y Kubernetes siguen teniendo API, web y Nginx.
  Ya no hay que proteger ni rotar un secreto maestro (`BOT_API_KEY`).
- **Hasta que exista la web, los gastos solo se registran con la API**
  (`curl` o `/docs`). Por eso la web sube en el roadmap.
- **En el celular, la app solo se abre como aplicación con HTTPS.** Sin
  HTTPS, el acceso directo funciona pero se abre en el navegador, con la
  barra de direcciones. En el computador basta con `localhost`.
- **Las bases de datos locales ya creadas** conservan las tablas
  `telegram_link_codes` y `telegram_chats`, porque `create_all` no borra
  tablas. La 007 no las toca; la primera migración de Alembic (spec 008)
  las borra. Solo guardan vínculos de chat que ya no sirven a nadie.
- **Se pierde el registro desde una conversación.** El roadmap retira las
  specs de bot con lenguaje natural y de WhatsApp.
