# ADR 0014 — Una compra con tarjeta es gasto del mes o deuda

- Fecha: 2026-11-06
- Estado: aceptada
- Fase / spec: 1 / 010-compras-del-mes-con-tarjeta
- Cambia: la decisión 1 del ADR 0013

## Contexto

El ADR 0013 decidió que toda compra con tarjeta, también a 1 cuota, cuenta
el mes en que se paga la tarjeta, en Deudas. Al especificar la web quedó
claro que así no se piensa el mes:

- El mercado de noviembre estaba en el plan de noviembre. Pagarlo con la
  tarjeta es solo una forma de pago: debería descontarse del rubro
  "Mercado" de noviembre.
- La deuda es lo que se compró sin tener la plata, y es lo que hay que
  mirar para decidir. Mezclarla con los gastos del plan pagados con
  tarjeta la infla.
- El mes en que se paga la tarjeta sí tiene que mostrar todo lo que hay que
  pagarle, porque es la plata que sale ese día.

Lo que separa los dos casos no se puede deducir: hay compras a 1 cuota con
la plata en el plan y otras sin ella.

## Decisión

1. **Una compra con tarjeta es deuda o gasto del mes**, guardado en
   `expenses.is_debt`.
2. **A varias cuotas, siempre es deuda.** A 1 cuota, la persona dice si
   estaba en el plan del mes; si no lo dice, es gasto del mes.
3. **Un gasto del mes con tarjeta cuenta el mes de la compra**, en su rubro
   o su categoría, como un débito. Una deuda sigue el ADR 0013.
4. **El mes del pago muestra lo que hay que pagar a cada tarjeta** (gastos
   del mes más cuotas de deudas), aparte. Solo la deuda suma en lo
   planeado y lo gastado.
5. **El valor real del extracto es el total a pagar.** La deuda del mes es
   ese total menos los gastos del mes que incluye, sin bajar de `0`.
6. **Las compras con tarjeta que ya existían quedan como deuda**: la
   migración `0005` no cambia ningún resumen.

## Alternativas descartadas

- **Decidirlo por las cuotas** (1 cuota, gasto del mes): una compra a 1
  cuota sin la plata quedaría como si estuviera en el plan.
- **Decidirlo por tener rubro**: mezcla dos preguntas, y una compra a cuotas
  con rubro descuadraría los meses.
- **Que el extracto real sea solo la parte de deuda**: habría que calcularla
  a mano a partir del extracto.
- **Mostrar lo que hay que pagar solo en la pantalla de tarjetas**: el
  resumen del mes no diría cuánta plata sale el día de pago.

## Consecuencias

- Una pregunta más al registrar a 1 cuota con tarjeta, con la respuesta más
  común por defecto.
- El resumen tiene dos cifras por tarjeta: la deuda (para decidir) y lo que
  hay que pagar (para tener la plata).
- **Copiar `expenses` en SQLite exige desactivar las claves foráneas**
  mientras corre la migración, porque desde la 0004 `prepayments` apunta a
  esa tabla. `run_migrations` lo hace en SQLite y comprueba con
  `PRAGMA foreign_key_check` que no quede ninguna rota.
- Qué aprendí: la forma de pago no dice si algo es deuda. Lo dice la
  intención con la que se compró, y esa solo la sabe la persona.
