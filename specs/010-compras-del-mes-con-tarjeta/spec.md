# Spec 010 — Compras del mes con tarjeta

- Fase: 1 — Aplicación y SDD
- Estado: aprobada (2026-11-06)
- Base: spec 008 (rubros, gastos planeados y resumen), spec 009 (tarjetas,
  cuotas, deudas, abonos y valor real del extracto; ADR 0013)

## Por qué

La 009 trata toda compra con tarjeta como una deuda: no cuenta el mes de la
compra, y sus cuotas llegan a Deudas en los meses de pago. Al especificar
la web quedó claro que no es así como se piensa el mes:

- El mercado de noviembre estaba en el plan de noviembre. Pagarlo con la
  tarjeta es solo una forma de pago: el gasto es de noviembre y debe
  descontarse del rubro "Mercado" de noviembre.
- Diciembre tiene que mostrar que hay que pagar ese mercado a la Visa, pero
  no como deuda: la deuda es lo que se compró sin tener la plata, y es lo
  que hay que mirar para decidir.

Esta spec distingue dos clases de compra con tarjeta: el **gasto del mes**,
que estaba en el plan y cuenta en su mes como un débito, y la **deuda**,
que llega a Deudas en los meses de pago como hasta ahora.

## Qué entra

- Marcar cada compra con tarjeta como gasto del mes o como deuda.
- Gastos del mes con tarjeta: en su rubro o su categoría, el mes de la
  compra.
- En el resumen del mes de pago: lo que hay que pagar a cada tarjeta, con
  los gastos del mes aparte de la deuda.
- El valor real del extracto como total a pagar, y la deuda como la resta.
- La migración de las compras con tarjeta que ya existen.

## Qué NO entra

- Pantallas: el formulario que pregunta es de la 011 (decisión 26 de la
  011).
- Pasar un gasto del mes a deuda (o al revés) desde un abono, un pago parcial
  o un mes sin pagar la tarjeta: si no se paga el total, el banco cobra
  intereses, y eso queda fuera como en la 009.
- Repartir el valor real del extracto entre compras.

## Conceptos

- **Gasto del mes con tarjeta**: compra con tarjeta a 1 cuota que estaba en
  el plan del mes. Cuenta el mes de la compra, en su rubro o en su
  categoría, como un débito. No es deuda.
- **Deuda**: compra con tarjeta a varias cuotas, o a 1 cuota que no estaba en
  el plan. Sus cuotas llegan a Deudas en los meses de pago (spec 009).
- **A pagar** a una tarjeta en un mes: los gastos del mes que se pagan ese
  mes más la deuda del mes. Es lo que sale de la cuenta el día de pago.
- **Deuda del mes** de una tarjeta: la estimada (cuotas de deudas) o, si se
  escribió el valor real del extracto, ese valor menos los gastos del mes
  que incluye; más los abonos del mes.

## Decisiones de clarificación (2026-11-06)

1. **A varias cuotas, una compra siempre es deuda**, aunque la plata
   estuviera en el plan.
2. **A 1 cuota, la persona dice si estaba en el plan del mes.** Si sí, es un
   gasto del mes; si no, es deuda. No se deduce de nada más: hay compras a 1
   cuota con la plata en el plan y otras sin ella. Se descartaron decidirlo
   por las cuotas (una compra a 1 cuota sin la plata sería gasto del mes) y
   por tener rubro.
3. **El mes del pago muestra lo que hay que pagar a cada tarjeta**, con los
   gastos del mes aparte, pero solo la deuda suma en lo planeado y lo
   gastado de ese mes: el gasto del mes ya contó en su mes. Se descartó
   mostrarlo solo en la pantalla de tarjetas.
4. **El valor real del extracto es el total a pagar**, y la deuda del mes es
   ese total menos los gastos del mes que incluye. Así los intereses reales
   y la cuota de manejo caen en la deuda. Se descartó escribir solo la parte
   de deuda: habría que calcularla a mano.
5. **Esta spec va antes de la web**, que pasa a ser la 011; las specs
   siguientes corren un número.

## Decisiones tomadas al redactar la spec

6. **Un gasto del mes con tarjeta sigue las reglas de un gasto a débito**
   (spec 008): un rubro de su mes o una categoría, nunca los dos, y
   descripción opcional. Sigue siendo una compra con tarjeta: tiene tarjeta,
   1 cuota y mes de pago.
7. **Una deuda sigue las reglas de la 009**: categoría, descripción
   obligatoria y nunca rubro.
8. **Si no se dice, una compra a 1 cuota es gasto del mes.** Es lo más
   común (el mercado, la gasolina) y la respuesta por defecto del formulario
   (decisión 26 de la 011). A varias cuotas no hace falta decirlo.
9. **Las compras con tarjeta que ya existen quedan como deuda**, porque así
   las trataba la 009: la migración no cambia ningún resumen.
10. **Si el valor real del extracto es menor que los gastos del mes que
    incluye, la deuda del mes es `0`**, no negativa. Una deuda negativa
    bajaría lo gastado del mes sin que haya entrado plata.
11. **Un gasto del mes con tarjeta no recibe abonos** (no le queda saldo
    después de su única cuota), y pagar todo no lo toca. Las reglas de la
    009 ya lo dan.
12. **Cambiar una compra a varias cuotas la vuelve deuda**: si tenía rubro,
    la petición tiene que quitárselo, como al pasar un gasto de débito a
    crédito en la 009.
13. **El estado de la tarjeta** cuenta en el saldo pendiente y en cada mes
    tanto las deudas como los gastos del mes que todavía no se pagan: es lo
    que se le debe al banco.

## Cambios a la spec 009

- **Decisión 1 de la 009**: una compra con tarjeta a 1 cuota que estaba en
  el plan cuenta el mes de la compra (decisión 2). Lo demás de la decisión
  sigue.
- **RF-9 de la 009**: la descripción obligatoria y "nunca rubro" valen solo
  para las deudas (decisiones 6 y 7).
- **RF-35 a RF-38 de la 009**: Deudas y sus totales cambian como dice
  "Resumen" (abajo).

## Requisitos funcionales

### Registrar y editar

- **RF-1** CUANDO un miembro registra una compra con tarjeta, PUEDE indicar
  si es deuda. SI son varias cuotas, ENTONCES el sistema DEBE tratarla como
  deuda y DEBE rechazar sin guardar nada que se indique que no lo es. SI es
  a 1 cuota y no se indica, ENTONCES DEBE tratarla como gasto del mes
  (decisiones 1, 2 y 8).
- **RF-2** Un gasto del mes con tarjeta DEBE llevar exactamente uno de los
  dos, un rubro de su mismo mes o una categoría activa, con las reglas de
  RF-17 a RF-19 de la 008, y la descripción DEBE ser opcional (decisión 6).
- **RF-3** Una deuda DEBE llevar categoría y descripción y NO DEBE llevar
  rubro, como RF-9 de la 009 (decisión 7).
- **RF-4** El sistema DEBE devolver cada gasto con la indicación de si es
  deuda: verdadero o falso en una compra con tarjeta, nulo en un gasto sin
  tarjeta.
- **RF-5** CUANDO un miembro edita una compra con tarjeta, el sistema DEBE
  permitir cambiar si es deuda, con las reglas de RF-1 a RF-3 sobre cómo
  queda la compra. SI la compra queda a varias cuotas, ENTONCES DEBE quedar
  como deuda; si tenía rubro, la petición DEBE quitárselo (decisión 12).
  Una compra con abonos sigue sin poder cambiar más que descripción y
  categoría (RF-16 de la 009).

### Resumen

- **RF-6** Un gasto del mes con tarjeta DEBE contar en lo gastado de su
  rubro y de su categoría en el mes de su fecha, como un débito (decisión
  2), y NUNCA en Deudas.
- **RF-7** La deuda estimada de una tarjeta en un mes DEBE ser la suma de las
  cuotas de sus deudas en ese mes. CON valor real del extracto, la deuda
  del mes DEBE ser ese valor menos los gastos del mes con esa tarjeta que se
  pagan ese mes, y nunca menos de `0` (decisiones 4 y 10). En los dos
  casos se suman los abonos del mes.
- **RF-8** CUANDO un miembro pide el resumen, cada tarjeta de Deudas DEBE
  traer además los gastos del mes que se pagan con ella ese mes (compra,
  nombre y monto) y lo que hay que pagarle: el valor real del extracto o la
  suma de cuotas de deudas y gastos del mes, más los abonos (decisión 3).
  Una tarjeta DEBE aparecer si tiene cualquiera de esas cosas en el mes.
- **RF-9** Los totales del resumen DEBEN incluir lo que hay que pagar a todas
  las tarjetas, aparte. Lo planeado y lo gastado DEBEN seguir incluyendo
  solo la deuda del mes (decisión 3).
- **RF-10** El nombre de un gasto del mes en Deudas DEBE ser su descripción,
  o el nombre de su rubro si no tiene, o el de su categoría si no tiene
  ninguno.

### Estado de la tarjeta

- **RF-11** El estado de la tarjeta DEBE contar en el saldo pendiente y en
  la lista de compras pendientes los gastos del mes que todavía no se
  pagan, marcados como tales, y cada mes DEBE traer lo que hay que pagar
  además de la deuda (decisión 13).

### Migración

- **RF-12** Una migración DEBE añadir la marca de deuda y dejar como deuda
  toda compra con tarjeta existente, sin cambiar ningún otro dato ni ningún
  resumen (decisión 9).

## Criterios de validación

Con la Visa (corte 25, pago 10, 1,90 %), el ingreso "Salario" (5.000.000)
de noviembre y de diciembre, y el rubro "Mercado" (Comida, 800.000) de
noviembre:

1. Un test registra el "Mercado" de 200.000 a 1 cuota el 5 de noviembre con
   la Visa en el rubro "Mercado", sin decir si es deuda, y comprueba que es
   gasto del mes, que el rubro "Mercado" de noviembre suma 200.000 y que
   Comida de noviembre también (RF-1, RF-2, RF-6).
2. Un test registra la "Compra TV" (1.200.000, 6 cuotas, 12 de noviembre) y
   unos "Zapatos" de 150.000 a 1 cuota el 20 de noviembre marcados como
   deuda, y comprueba que:
   - noviembre no suma ninguno de los dos;
   - en diciembre la Visa trae como cuotas "Compra TV · 1 de 6" (222.800) y
     "Zapatos · 1 de 1" (150.000), como gasto del mes "Mercado" (200.000),
     deuda 372.800 y a pagar 572.800;
   - los totales de diciembre tienen deudas 372.800, planeado y gastado
     372.800 y a pagar a tarjetas 572.800
   (RF-7 a RF-9).
3. Con el valor real del extracto de diciembre en 581.500, la deuda es
   381.500 y a pagar 581.500; con un abono de 400.000 a la TV en diciembre,
   781.500 y 981.500; con el valor real en 150.000, la deuda es 0 y a pagar
   150.000 (RF-7, RF-8, decisión 10).
4. Un test comprueba que se rechazan sin guardar nada: varias cuotas
   marcadas como no deuda; una deuda con rubro o sin descripción; un gasto
   del mes con rubro y categoría, sin ninguno, o con un rubro de otro mes
   (RF-1 a RF-3).
5. Un test edita el "Mercado": a deuda sin quitarle el rubro se rechaza; con
   `budget_item_id: null` y descripción pasa a Deudas de diciembre y sale de
   noviembre; a 3 cuotas queda como deuda. Otro pasa los "Zapatos" a gasto
   del mes en el rubro "Mercado" (RF-5).
6. Un test con el reloj el 1 de diciembre pide el estado de la Visa y
   comprueba que el saldo pendiente incluye el "Mercado" marcado como gasto
   del mes, y que diciembre trae la deuda y lo que hay que pagar (RF-11).
7. Un test migra una base en `0004` con compras con tarjeta a 1 y a varias
   cuotas y comprueba que todas quedan como deuda, que sus resúmenes no
   cambian y que `compare_metadata` no ve diferencias (RF-12).
8. Los tests de la 009 siguen en verde; los que registran compras a 1 cuota
   como deuda lo dicen explícitamente.
9. `make test` y `make lint` pasan en verde.

## Requisitos para otras specs y documentos

- **011-app-web:** a crédito y a 1 cuota, el formulario pregunta "¿Estaba en
  el plan de este mes?" y envía `is_debt` (decisión 26 de la 011). Un gasto
  del mes con tarjeta sugiere rubros como un débito.
- **012-tablero-y-planear:** muestra lo que hay que pagar a cada tarjeta y
  separa la deuda.
- **ADR 0013:** su decisión 1 cambia; lo explica el ADR 0014.
- **AGENTS.md:** el glosario necesita "gasto del mes con tarjeta" y ajustar
  "compra con tarjeta" y "deuda", con aprobación explícita.
