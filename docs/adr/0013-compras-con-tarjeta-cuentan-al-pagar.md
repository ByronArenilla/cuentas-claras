# ADR 0013 — Las compras con tarjeta cuentan el mes en que se paga la tarjeta

- Fecha: 2026-11-06
- Estado: aceptada; su decisión 1 la cambia el ADR 0014 (un gasto del mes
  con tarjeta a 1 cuota cuenta el mes de la compra)
- Fase / spec: 1 / 009-tarjetas-y-cuotas

## Contexto

Hasta la 008, un gasto a crédito contaba el día de la compra, como uno a
débito. Pero la plata de una compra con tarjeta sale cuando se paga la
tarjeta, y si la compra es a cuotas, sale en varios meses y con intereses.
Un televisor de 1.200.000 a 6 cuotas comprado en noviembre no le quita
1.200.000 a noviembre: le quita unos 220.000 a cada mes de diciembre a mayo.

Restricciones:

- Montos en pesos enteros, nunca `float` (principio 6).
- La lógica vive en la API y se prueba sin HTTP (principio 10).
- SQLite es la base de datos hasta la fase 2: no tiene un tipo decimal
  exacto.
- El banco calcula los intereses por días y cobra cargos que la app no
  conoce: la estimación nunca será igual al extracto.

## Decisión

1. **Toda compra con tarjeta, también a 1 cuota, cuenta el mes en que se
   paga la tarjeta**, en una sección Deudas del resumen. No suma en su rubro
   ni en su categoría. La deuda del mes cuenta sola en lo planeado y en lo
   gastado: el pago de la tarjeta no se registra como gasto.
2. **El mes de pago sale del día de corte y del día límite de pago**, y se
   guarda en la compra al registrarla (`first_due_start`). Si el banco
   cambia los días de la tarjeta, las compras ya registradas no cambian de
   mes.
3. **Los intereses se estiman con capital fijo e interés sobre el saldo**,
   como los extractos en Colombia, con la tasa mensual actual de la
   tarjeta. El valor real del extracto, si se escribe, reemplaza la
   estimación de ese mes.
4. **Las cuotas se calculan al leer y no se guardan.** `app/installments.py`
   las arma con funciones puras a partir de la compra, la tasa y los
   abonos.
5. **La tasa se escribe como decimal (`1.89`) y se guarda como entero en
   puntos básicos (`189`).** El interés de cada cuota es
   `(saldo * bp + 5000) // 10000`: pesos enteros redondeados con el medio
   peso hacia arriba, sin `float` ni `Decimal` en el cálculo.
6. **Un abono baja la cuota o el plazo, a elección**, como permite la
   [Ley 1555 de 2012](http://www.secretariasenado.gov.co/senado/basedoc/ley_1555_2012.html).
   Pagar todo lo de una tarjeta en un mes es un abono por el saldo a cada
   compra que ya está en el extracto.
7. **Una compra con tarjeta lleva descripción obligatoria y categoría,
   nunca rubro.** La descripción es el nombre con el que sus cuotas salen
   en Deudas.

## Alternativas descartadas

- **Contar la compra a 1 cuota en su rubro el mes de la compra** (lo que
  decía el roadmap): el valor real del extracto incluiría compras ya
  contadas, y habría dos reglas para el crédito.
- **Sumar cada cuota en la categoría de su compra**: la diferencia entre lo
  estimado y el extracto (intereses por días, cuota de manejo) no tendría
  categoría.
- **Registrar el pago de la tarjeta como un gasto**: una acción más cada mes,
  y hasta hacerla el balance diría que sobra plata comprometida.
- **Guardar las cuotas en una tabla**: cada cambio de tasa y cada abono
  obligaría a reescribir filas y mantenerlas de acuerdo con la compra. Es
  un caché que se puede desalinear; calcular son como mucho 48 cuotas.
- **Cuota fija (sistema francés)**: no se parece a un extracto de tarjeta.
- **Tasa como `float`**: algunos intereses quedarían un peso arriba o abajo.
  **Tasa como `Numeric`**: exacta en PostgreSQL, pero SQLite la guarda como
  `REAL`.
- **Recalcular el mes de pago con los días actuales de la tarjeta al leer**:
  un cambio de fechas del banco reacomodaría meses pasados.
- **Abonar a la tarjeta un monto parcial repartido entre las compras**: hay
  que fijar el orden del reparto y el modo; el caso pedido era pagar el
  total.

## Consecuencias

- El resumen dice cuánto sale de verdad cada mes: el mes de la compra ya no
  parece más caro, y los meses siguientes no parecen tener plata libre que
  ya está comprometida.
- `planned` y `spent` del resumen incluyen las deudas; `debts` las separa.
- Cambiar la tasa cambia las estimaciones de los meses sin valor real del
  extracto, también los pasados. Escribir el extracto fija el mes.
- La estimación no es exacta: el valor real del extracto la corrige.
- Una compra con abonos solo cambia su descripción y su categoría, y no se
  borra hasta borrar sus abonos.
- Los gastos a crédito de antes de la 009 quedan sin tarjeta y siguen
  contando el día del gasto.
- Qué aprendí: un dato que depende de otros (las cuotas) se calcula; uno
  que se fija en un momento y no debe moverse después (el mes de pago) se
  guarda.
