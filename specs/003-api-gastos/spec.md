# Spec 003 — API de gastos

- Fase: 1 — Aplicación y SDD
- Estado: borrador, pendiente de clarificación
- Base: spec 001 (RF-28 a RF-32, aislamiento entre espacios), spec 002
  (categorías), ADR 0001

## Por qué

Registrar gastos es la razón de ser de la app: sin gastos no hay resumen
mensual (004), ni bot (005, 006), ni dashboard (007). Por el principio 10,
el bot y la web son capas finas, así que todo lo que hagan con un gasto
tiene que existir antes en la API y estar probado ahí.

La spec 001 dejó lista la regla que los gastos deben cumplir: todo dato
cuelga de un espacio y solo lo alcanzan sus miembros. Esta spec es la
primera que guarda datos del presupuesto de verdad, así que también es la
primera que pone a prueba esa regla con datos reales.

## Qué entra

- Registrar, consultar, listar por periodo, editar y borrar gastos de un
  espacio.
- Las validaciones de monto, tipo de pago, categoría, fecha y descripción.
- Ampliar con gastos reales los tests de aislamiento de la spec 001.

## Qué NO entra

- Crear categorías y las categorías predefinidas: spec 002, que va antes
  porque todo gasto necesita una categoría.
- Qué pasa con los gastos al renombrar o borrar una categoría: ninguna spec
  planeada lo cubre todavía.
- Presupuestos y resumen gastado vs. presupuestado: spec 004.
- La conversación en Telegram, las preguntas de confirmación en pantalla y
  el comando `/deshacer`: specs 005 y 006.
- Las pantallas de la web: spec 007.
- Varias monedas o conversión entre monedas, gastos recurrentes, ingresos,
  adjuntos o fotos de recibos, búsqueda por texto.
- Mover un gasto de un espacio a otro.

## Conceptos

- **Gasto** (`expense`): dinero que salió. Tiene monto, tipo de pago,
  categoría, fecha, descripción opcional, el espacio al que pertenece y el
  usuario que lo registró.
- **Monto**: número entero mayor que cero, en la unidad mínima de la moneda
  (principio 6). Ver P2.
- **Tipo de pago** (`payment_type`): `credit` o `debit`.
- **Fecha del gasto**: cuándo salió el dinero, que no tiene por qué
  coincidir con cuándo se registró. Ver P3.
- **Periodo**: mes calendario `YYYY-MM` en la zona horaria configurada
  (`TZ`). Un gasto pertenece al periodo que contiene su fecha.
- **Quien lo registró**: el usuario autenticado que creó el gasto. No cambia
  al editar el gasto ni cuando ese usuario sale del espacio.

## Preguntas para la clarificación

Cada pregunta lleva una propuesta. Los RF que dependen de una respuesta lo
indican con *(P-n)*. Al cerrar la clarificación, esta sección se reemplaza
por "Decisiones de clarificación", como en la spec 001.

- **P2 — Moneda.** *Propuesta:* una sola moneda por instancia. La API solo
  sabe que el monto es un entero en la unidad mínima y no guarda la moneda;
  cómo se escribe y se muestra el monto (por ejemplo, `20.000` pesos) lo
  deciden el bot y la web. ¿Es el peso colombiano y la unidad mínima es el
  peso, sin centavos?
- **P3 — ¿La fecha del gasto es un día o un instante?** El principio 7 dice
  que las fechas se guardan en UTC y que el periodo se calcula en `TZ`.
  - (a) Un día calendario (`2026-10-01`), más un sello `created_at` en UTC
    de cuándo se registró. Si no se indica, el día de hoy en `TZ`. El
    periodo sale directo del día y nunca depende de la hora.
  - (b) Un instante en UTC. El periodo se calcula convirtiéndolo a `TZ`.
    Exige inventar una hora cuando el usuario dice "ayer".
  - *Propuesta: (a).* Lo que el usuario sabe de un gasto es el día, no la
    hora. El principio 7 se sigue cumpliendo: los instantes (`created_at`)
    se guardan en UTC y "hoy" se calcula en `TZ`.
- **P4 — ¿Cómo se cumple "ningún gasto se borra sin confirmación
  explícita" (principio 8)?**
  - (a) La API exige en la petición de borrado una confirmación explícita
    y el borrado es definitivo. El bot y la web preguntan antes de
    enviarla.
  - (b) Borrado lógico: el gasto se marca como borrado, deja de aparecer y
    se puede recuperar. Toda consulta tendría que excluir los borrados,
    otro filtro que no se puede olvidar nunca, igual que el de espacio.
  - *Propuesta: (a).* Es la forma que ya usa la 001 para borrar espacios
    (RF-25 de la 001), y sin tablas ni filtros extra.
- **P5 — Permisos.** *Propuesta:* cualquier miembro edita y borra cualquier
  gasto del espacio, aunque lo haya registrado otro. Es lo que dice el
  ADR 0001: hoy todos los miembros de un espacio tienen los mismos permisos.
- **P6 — Listado.** *Propuesta:* se lista siempre por periodo (por defecto,
  el actual en `TZ`), del más reciente al más antiguo, sin paginación: un
  mes de gastos de un hogar son decenas o pocos cientos de filas.
- **P7 — Límites.** *Propuesta:* se rechazan las fechas posteriores a hoy en
  `TZ` (un gasto es dinero que ya salió), la descripción tiene como máximo
  200 caracteres y el monto no tiene tope.

## Requisitos funcionales

### Registrar

- **RF-1** CUANDO un miembro registra en un espacio un gasto con monto,
  tipo de pago y categoría válidos, el sistema DEBE guardarlo en ese
  espacio junto con el usuario que lo registró (RF-31 de la 001) y
  devolverlo con su identificador.
- **RF-2** SI no se indica la fecha del gasto, ENTONCES el sistema DEBE
  usar el día actual en la zona horaria configurada. *(P3)*
- **RF-3** SI el monto no es un número entero mayor que cero, ENTONCES el
  sistema DEBE rechazar el gasto e indicar el requisito incumplido. El
  sistema NUNCA DEBE aceptar ni redondear montos con decimales
  (principio 6).
- **RF-4** SI el tipo de pago no es `credit` ni `debit`, ENTONCES el
  sistema DEBE rechazar el gasto e indicar los valores admitidos.
- **RF-5** SI la categoría no existe en el espacio indicado, ENTONCES el
  sistema DEBE rechazar el gasto sin crearlo. Una categoría de otro espacio
  cuenta como inexistente (las categorías son de la spec 002).
- **RF-6** SI la fecha del gasto es posterior al día actual en la zona
  horaria configurada, ENTONCES el sistema DEBE rechazar el gasto. *(P7)*
- **RF-7** SI la descripción supera la longitud máxima, ENTONCES el
  sistema DEBE rechazar el gasto e indicar el límite. Una descripción vacía
  o solo con espacios se guarda como ausente. *(P7)*

### Consultar y listar

- **RF-8** CUANDO un miembro pide un gasto de su espacio, el sistema DEBE
  devolverlo con todos sus campos, incluido quién lo registró.
- **RF-9** CUANDO un miembro lista los gastos de un espacio para un
  periodo, el sistema DEBE devolver todos los gastos de ese espacio cuya
  fecha cae en ese periodo, del más reciente al más antiguo. *(P6)*
- **RF-10** SI no se indica periodo al listar, ENTONCES el sistema DEBE
  usar el periodo actual en la zona horaria configurada.
- **RF-11** SI el periodo no tiene el formato `YYYY-MM` o no es un mes
  válido, ENTONCES el sistema DEBE rechazar la petición e indicar el
  formato esperado.
- **RF-12** SI el gasto pedido no existe o pertenece a otro espacio,
  incluso a otro espacio del que quien llama también es miembro, ENTONCES
  el sistema DEBE responder `404` sin distinguir un caso del otro (RF-30 de
  la 001).

### Editar

- **RF-13** CUANDO un miembro edita un gasto de su espacio, el sistema DEBE
  cambiar solo los campos enviados, aplicando las mismas validaciones que
  al registrar (RF-3 a RF-7).
- **RF-14** El sistema NUNCA DEBE cambiar al editar un gasto el espacio al
  que pertenece ni el usuario que lo registró.
- **RF-15** MIENTRAS un usuario sea miembro de un espacio, el sistema DEBE
  permitirle editar y borrar cualquier gasto de ese espacio, aunque lo haya
  registrado otro miembro. *(P5)*

### Borrar

- **RF-16** CUANDO un miembro pide borrar un gasto de su espacio con
  confirmación explícita, el sistema DEBE eliminarlo. *(P4)*
- **RF-17** SI la petición de borrado no trae la confirmación, ENTONCES el
  sistema DEBE rechazarla sin borrar nada (principio 8). *(P4)*
- **RF-18** CUANDO se borra un gasto, el sistema NUNCA DEBE tocar otros
  gastos ni ningún otro dato del espacio.

### Aislamiento y ciclo de vida

- **RF-19** Toda operación sobre gastos DEBE indicar el espacio y pasar por
  la comprobación de membresía de la spec 001 (RF-28, RF-29 de la 001). Una
  petición sin sesión válida recibe `401` y no modifica nada (RF-11 de la
  001).
- **RF-20** CUANDO un miembro sale de un espacio, el sistema DEBE conservar
  los gastos que registró, que siguen visibles para el resto de miembros
  con su autor original (RF-21 de la 001).
- **RF-21** CUANDO se borra un espacio, el sistema DEBE borrar sus gastos y
  NUNCA DEBE tocar los gastos de otros espacios (RF-23 y RF-27 de la 001).

## Criterios de validación

La spec se da por cumplida cuando, además de los tests por requisito:

1. Un test crea dos usuarios en espacios distintos, registra un gasto en
   cada uno y comprueba que ninguno puede ver, listar, editar ni borrar el
   gasto del otro, y que todo responde `404` (RF-12, RF-19). Amplía el
   criterio 1 de la spec 001.
2. Un test comprueba que un gasto del espacio A pedido por la ruta del
   espacio B responde `404`, aunque quien llama sea miembro de los dos
   (RF-12).
3. Un test comprueba que dos miembros del mismo espacio ven la misma lista
   y que uno puede editar el gasto que registró el otro (RF-9, RF-15).
4. Un test fija el reloj en el 31 de octubre a las 20:00 en Bogotá (ya 1 de
   noviembre en UTC) y comprueba que un gasto sin fecha cae en el periodo
   `YYYY-10` (RF-2, principio 7).
5. Un test comprueba que un monto con decimales, negativo, cero o enviado
   como texto se rechaza y no guarda nada (RF-3).
6. Un test comprueba que borrar un espacio borra sus gastos y no toca los
   de otro espacio del mismo usuario (RF-21). Amplía el criterio 6 de la
   spec 001.
7. Un test comprueba que, tras salir de un espacio, los gastos que
   registró ese usuario siguen en la lista de los demás miembros (RF-20).
8. `make test` y `make lint` pasan en verde.

## Requisitos para otras specs

- `004-presupuesto-mensual` calcula el gastado por categoría con la misma
  regla de periodo de RF-9 y RF-10.
- `005-bot-registro-guiado` y `007-dashboard-web` deben pedir confirmación
  al usuario antes de enviar un borrado (RF-16, principio 8), si P4 se
  resuelve con la opción (a).
- `006-bot-consultas` define `/ultimos` y `/deshacer`. Si `/ultimos` debe
  ordenar por momento de registro y no por fecha del gasto, ese orden se
  añade en la 006.
