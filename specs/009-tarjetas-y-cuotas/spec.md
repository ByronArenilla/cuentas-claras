# Spec 009 — Tarjetas y cuotas

- Fase: 1 — Aplicación y SDD
- Estado: aprobada (2026-11-06)
- Base: spec 001 (aislamiento entre espacios), spec 002 (comparación de
  nombres, ADR 0006), spec 003 (gastos, tipo de pago y borrado con
  confirmación), spec 008 (rubros, gastos planeados, categorías eliminadas,
  resumen y migraciones, ADR 0011 y ADR 0012), ADR 0010

## Por qué

Hoy un gasto a crédito cuenta el día de la compra, como uno a débito. Pero
la plata de una compra con tarjeta no sale ese día: sale cuando se paga la
tarjeta, y si la compra es a cuotas, sale en varios meses y con intereses.
Un televisor de 1.200.000 a 6 cuotas comprado en noviembre no le quita
1.200.000 a noviembre. Le quita unos 220.000 a cada mes de diciembre a mayo.

Sin eso el plan del mes miente en los dos sentidos: el mes de la compra
parece más caro de lo que fue y los meses siguientes parecen tener plata
libre que ya está comprometida.

Esta spec añade **tarjetas** (con día de corte, día límite de pago y tasa
mensual), **compras con tarjeta** a una o varias cuotas, y la **deuda**
que llega cada mes por cada tarjeta. La deuda se estima con la tasa de la
tarjeta, se corrige con el valor real del extracto y baja con **abonos**.

## Qué entra

- Tarjetas: crear, listar, editar y eliminar (archivar), y restaurarlas al
  crearlas de nuevo.
- Compras con tarjeta: un gasto a crédito lleva tarjeta y número de
  cuotas, y cuenta el mes en que se paga la tarjeta.
- El plan de cuotas de cada compra: capital, intereses estimados y mes de
  pago de cada cuota.
- Abonos a una compra, que bajan la cuota o el plazo, incluido pagar todo
  el saldo.
- Pagar el total de una tarjeta en un mes: salda todas sus compras que ya
  están en el extracto.
- El valor real del extracto de una tarjeta en un mes.
- La sección Deudas en el resumen del mes y sus totales.
- El estado de una tarjeta: saldo pendiente y deuda de los próximos meses.
- Simular una compra con tarjeta sin guardarla.
- Una migración que añade todo esto sin cambiar ningún dato.

## Qué NO entra

- Las pantallas: el formulario de registro es de la 010; la pantalla de
  tarjetas, de la 011.
- Registrar el pago de la tarjeta como un gasto (decisión 3).
- Pagar menos que el extracto, el pago mínimo y los intereses de mora.
- Abonar a la tarjeta un monto parcial sin elegir la compra: el abono
  parcial es a una compra, y a la tarjeta solo se paga el total
  (decisión 28).
- Editar un abono: se borra y se crea de nuevo (decisión 18).
- Cupo y disponible de la tarjeta, avances en efectivo, compras en otra
  moneda, rediferir una compra ya hecha.
- La cuota de manejo y los seguros como datos de la tarjeta: entran en el
  valor real del extracto.
- Intereses por días exactos o con una tasa distinta por compra o por mes:
  la estimación es mensual con la tasa actual de la tarjeta (decisión 14).
- Cambiar el mes de pago de las compras ya registradas cuando cambian los
  días de la tarjeta (decisión 13).
- Estadísticas por categoría que incluyan las compras con tarjeta: la
  categoría queda guardada para una spec futura (decisión 6).
- Tarjetas débito o cuentas bancarias como entidades.

## Conceptos

- **Tarjeta** (`card`): tarjeta de crédito del espacio. Tiene nombre ("Visa
  Bancolombia"), día de corte, día límite de pago y, si se conoce, tasa de
  interés mensual.
- **Día de corte**: el día del mes en que el banco cierra el extracto. Las
  compras hasta ese día, incluido, entran en ese extracto.
- **Día límite de pago**: el día del mes en que vence el pago del extracto.
- **Compra con tarjeta**: gasto a crédito con tarjeta y número de cuotas.
  Lleva descripción (obligatoria) y categoría, pero no rubro, y no cuenta
  el día de la compra sino en los meses en que se pagan sus cuotas.
- **Cuota**: la parte de una compra que se paga en un mes. Tiene número
  ("2 de 6"), mes de pago, capital e interés estimado.
- **Mes de pago**: el mes del día límite de pago del extracto que incluye
  la compra. Es el de la primera cuota; cada cuota siguiente cae un mes
  después.
- **Saldo** de una compra: el capital que falta pagar.
- **Abono**: pago extra a una compra en un mes, además de su cuota, que
  baja el saldo. Se elige si baja la **cuota** (mismo número de cuotas,
  más bajas) o el **plazo** (misma cuota de capital, menos cuotas).
- **Pagar todo**: pagar en un mes el total de una tarjeta. Salda con un
  abono cada compra que ya está en el extracto de ese mes.
- **Valor real del extracto**: lo que de verdad cobra una tarjeta en un
  mes según su extracto. Reemplaza la estimación de ese mes.
- **Deuda** de una tarjeta en un mes: el valor real del extracto o, si no
  se escribió, la suma estimada de sus cuotas de ese mes; más los abonos
  de ese mes.
- **Deudas**: la sección del resumen con la deuda de cada tarjeta en el
  mes.
- **Gasto a crédito sin tarjeta**: gasto a crédito registrado antes de
  esta spec. Sigue contando el día del gasto, como en la 008.

## Decisiones de clarificación (2026-11-06)

1. **Todo gasto con tarjeta cuenta el mes en que se paga la tarjeta,
   también a 1 cuota.** Un gasto a débito cuenta el día del gasto. Un
   mercado de 200.000 con la Visa el 5 de noviembre (corte 25, pago 10)
   cuenta en diciembre. Cambia la nota del roadmap ("una compra a 1 cuota
   cuenta en su rubro el mes de la compra") y el requisito que la 008 dejó
   para esta spec. Se descartó contar la compra a 1 cuota en su mes: el
   valor real del extracto (decisión 4) incluiría compras ya contadas.
2. **Una compra con tarjeta lleva descripción y categoría, no rubro.** En
   los meses de pago, Deudas muestra cada cuota con el nombre de la compra
   ("Compra TV · cuota 1 de 6"). Se descartó ligarla a un rubro del mes de
   la compra solo de referencia: el rubro mostraría un gasto que no suma.
   La descripción pasó a ser obligatoria en la segunda ronda (decisión 26).
3. **La deuda de un mes cuenta sola en lo planeado y en lo gastado.** Baja
   lo sin asignar y el balance de ese mes sin registrar nada. El pago de la
   tarjeta no se registra como gasto. Se descartaron contarla como gastada
   solo al registrar el pago (una acción más cada mes) y mostrarla solo
   como información (el balance diría que sobra plata comprometida).
4. **El valor real del extracto reemplaza la deuda estimada de esa tarjeta
   en ese mes**: capital, intereses, cuota de manejo y lo que cobre el
   banco. Si no se escribe, cuenta la estimación. Se descartó escribir solo
   los intereses reales: hay que buscar ese dato en el extracto y no cubre
   otros cargos.
5. **Los intereses se estiman con capital fijo e interés sobre el saldo**,
   como los extractos en Colombia: el capital de cada cuota es el valor
   entre el número de cuotas, y el interés, el saldo pendiente por la tasa
   mensual de la tarjeta. La tasa es opcional. Se descartaron la cuota fija
   (sistema francés), que no se parece a un extracto de tarjeta, y no
   estimar intereses.
6. **Deudas es una sección aparte del resumen**, por tarjeta. Las compras
   con tarjeta no suman en el gastado de su categoría en ningún mes: cada
   peso cuenta una sola vez, y el valor real del extracto cabe entero en
   Deudas. La categoría de la compra se guarda para estadísticas futuras.
   Se descartó sumar cada cuota en la categoría de su compra: la diferencia
   entre lo estimado y el extracto no tendría categoría.
7. **Los abonos entran en esta spec**, aunque el roadmap los dejaba fuera.
   Un abono es una acción sobre una compra: monto, mes y si baja la cuota
   o el plazo, elegido en cada abono, como permite la
   [Ley 1555 de 2012](http://www.secretariasenado.gov.co/senado/basedoc/ley_1555_2012.html).
   Un abono por todo el saldo cancela la compra. Suma en la deuda de su
   tarjeta en su mes, aparte del valor del extracto. Se descartaron
   contar lo que se escribe sin recalcular las cuotas, guardar el extracto
   y el pago como dos valores, y tomar como abono lo que pase del
   extracto (hay que elegir la compra igual, y depende de tener el
   extracto escrito).
8. **Desde esta spec, un gasto a crédito nuevo exige tarjeta.** Los que ya
   existen quedan sin tarjeta y siguen contando el día del gasto, con su
   rubro si lo tenían. La migración no cambia ningún gasto (principio 8).
   Se descartó la tarjeta opcional: dos caminos para el crédito que la web
   tendría que explicar.
9. **Eliminar una tarjeta la archiva**, como una categoría: deja de
   ofrecerse para compras nuevas, sus cuotas siguen llegando a Deudas, y
   crearla de nuevo con el mismo nombre la restaura. Se descartó impedirlo
   mientras tenga cuotas pendientes.
10. **Una compra tiene de 1 a 48 cuotas.**
11. **La API da el estado de cada tarjeta**: saldo pendiente, compras con
    cuotas pendientes y deuda de los próximos meses, para la pantalla de
    tarjetas (011).

## Decisiones tomadas al redactar la spec

12. **El mes de pago sale del día de corte y del día límite de pago.** La
    compra entra en el primer corte en su fecha o después: una compra el
    mismo día de corte entra en ese corte. El pago es el primer día límite
    después del corte. Un día 29, 30 o 31 en un mes que no lo tiene es el
    último día de ese mes. Ejemplos:
    - Corte 25, pago 10: compra el 25 de noviembre → corte 25 de
      noviembre → pago 10 de diciembre → mes de pago `2026-12`. Compra el
      26 de noviembre → `2027-01`.
    - Corte 15, pago 30: compra el 10 de noviembre → pago el 30 de
      noviembre → `2026-11`, el mismo mes de la compra. Compra el 10 de
      febrero de 2027 → pago el 28 de febrero → `2027-02`.
    - Corte 10, pago 10: compra el 10 de noviembre → pago el 10 de
      diciembre → `2026-12`.
13. **El mes de pago se guarda al registrar la compra.** Cambiar el día de
    corte o de pago de una tarjeta solo afecta las compras nuevas y las
    que se editan en fecha, tarjeta, monto o cuotas. Así un cambio de
    fechas del banco no reacomoda los meses pasados.
14. **La estimación usa la tasa actual de la tarjeta.** Cambiarla cambia
    los intereses estimados de todas sus cuotas, también las de meses
    pasados que no tengan valor real del extracto. Los bancos en Colombia
    cambian la tasa casi cada mes, así que guardar la tasa de cada compra
    tampoco sería exacto; el mes queda fijo al escribir su extracto.
15. **Los montos de las cuotas son pesos enteros** (principio 6). Si el
    valor no se divide exacto entre las cuotas, cada una de las primeras
    lleva un peso más: 1.000.000 a 3 cuotas son 333.334, 333.333 y
    333.333. El interés de cada cuota se redondea al peso más cercano, con
    el medio peso hacia arriba. **Una compra a 1 cuota no genera
    intereses**: en Colombia no los cobra si se paga completa.
16. **La tasa es un porcentaje mensual con hasta dos decimales**, de 0,01 %
    a 10 % (1,89 % mensual). Sin tasa, los intereses estimados son `0`.
    Cómo se escribe y se calcula lo fija la decisión 27.
17. **Una compra con abonos solo cambia su descripción y su categoría**, y
    no se puede borrar hasta borrar sus abonos: cambiar el monto, la fecha,
    la tarjeta o las cuotas dejaría abonos calculados sobre otra compra, y
    un abono es plata que salió (principio 8).
18. **Una compra tiene a lo sumo un abono por mes, y cada abono nuevo es de
    un mes posterior al último que ya tiene.** Así un abono nuevo nunca deja
    a otro por encima del saldo. Los abonos no se editan: se borran con
    confirmación, como un gasto (decisión 3 de la 003), y se crean de nuevo.
19. **Un abono puede ser de cualquier mes en que la compra tenga una cuota
    y le quede saldo después de ella**, también de un mes futuro: planear un
    abono es parte de planear el mes.
20. **El valor real del extracto se escribe para cualquier mes**, de `0` a
    un billón, y se puede reemplazar o quitar. Quitarlo vuelve a la
    estimación y no pide confirmación: es un dato del plan, como un rubro.
    No se copia con el plan del mes (cada extracto es de su mes).
21. **Deudas incluye las tarjetas archivadas** que tengan cuotas, abonos o
    valor real en el mes, marcadas como eliminadas, como las categorías en
    el resumen de la 008 (decisión 18 de la 008).
22. **La API simula una compra sin guardarla**: con la tarjeta, el monto,
    las cuotas y la fecha, devuelve el mes de pago y las cuotas estimadas.
    El ADR 0010 pide que el formulario muestre el mes del pago y el costo
    de las cuotas antes de guardar, y esa cuenta es lógica de negocio
    (principio 10).
23. **En Deudas, una cuota se nombra con la descripción de su compra.**
    Decía "o, si no tiene, con el nombre de su categoría"; ya no hace falta
    porque la descripción es obligatoria (decisión 26).
24. **Restaurar una tarjeta conserva su nombre, sus días y su tasa
    originales**, como las categorías conservan el nombre (decisión 21 de
    la 008). Para cambiarlos se edita después.
25. **Una tarjeta archivada se puede editar** (por ejemplo, corregir la tasa
    con la que se estiman sus cuotas pendientes) y recibe abonos y valores
    del extracto. Lo único que no admite son compras nuevas.

## Segunda ronda de clarificación (2026-11-06)

26. **Al registrar un gasto hay un solo campo para nombrarlo: la
    descripción.** El rubro y la descripción no aparecen a la vez:
    - **Compra con tarjeta**: la descripción es obligatoria ("Compra TV") y
      es el nombre con el que cada cuota sale en Deudas. Lleva categoría y
      nunca rubro.
    - **Gasto a débito**: mientras se escribe la descripción, la web sugiere
      los rubros del mes. Si se elige uno ("Mercado"), el gasto cuenta en
      ese rubro y toma su categoría. Si se escribe otra cosa, se elige la
      categoría y queda no planeado.

    Para el débito, la API de la 008 no cambia: el gasto sigue ligado al
    rubro por dentro. Lo que cambia es el formulario (010). Se descartaron
    ligar el gasto al rubro por el nombre (frágil: "Mercado Éxito" no
    contaría en "Mercado", y renombrar un rubro le quitaría sus gastos) y
    quitar el rubro de los gastos (se pierde cuánto queda en cada rubro).
27. **La tasa se escribe como número decimal (`1.89`) y se calcula de forma
    exacta**, nunca con `float`. Se descartaron `float` (algunos intereses
    quedarían un peso arriba o abajo por la representación binaria) y
    escribirla como entero en puntos básicos (`189`), que es menos natural.
28. **Pagar todo** salda en un mes todas las compras de una tarjeta que ya
    están en el extracto de ese mes: a cada una con saldo después de su
    cuota de ese mes le crea un abono por ese saldo. Desde el mes siguiente
    esas compras ya no salen en Deudas. Las compras hechas después del
    corte no están en ese extracto, así que siguen llegando en su mes, como
    en el banco. Ejemplo con la Visa (corte 25, pago 10): pagar todo en
    diciembre salda la "Compra TV" (abono de 1.000.000) y la deuda de
    diciembre queda en 1.422.800; unos "Zapatos" de 150.000 comprados el 30
    de noviembre siguen llegando en enero. Se descartó un abono a la
    tarjeta con cualquier monto, repartido entre las compras: hay que fijar
    el orden del reparto y si baja la cuota o el plazo, y el caso pedido
    era pagar el total.

## Cambios a la spec 008

- **RF-17 de la 008** (rubro o categoría, exactamente uno) sigue valiendo
  para los gastos a débito y los gastos a crédito sin tarjeta. Una compra
  con tarjeta lleva categoría y nunca rubro (RF-9).
- **RF-23 de la 008** (resumen): lo gastado por rubro y por categoría deja
  fuera las compras con tarjeta, se añade la sección Deudas, y lo planeado
  y lo gastado del mes incluyen las deudas (RF-37 a RF-39).
- El requisito que la 008 dejó para esta spec ("una compra a 1 cuota cuenta
  en su rubro el mes de la compra") se reemplaza por la decisión 1.

## Requisitos funcionales

### Tarjetas

- **RF-1** CUANDO un miembro crea una tarjeta con nombre, día de corte, día
  límite de pago y, si quiere, tasa mensual válidos, el sistema DEBE
  guardarla y devolverla con su identificador y esos datos.
- **RF-2** El sistema DEBE guardar el nombre sin los espacios de alrededor
  y DEBE rechazarlo si queda vacío o pasa de 50 caracteres. SI otra tarjeta
  activa del mismo espacio tiene un nombre equivalente según la comparación
  de la 002 (decisión 22 de la 008), ENTONCES el sistema DEBE rechazarla
  sin guardar nada y nombrar la que ya existe, aunque lleguen dos
  peticiones a la vez.
- **RF-3** Los días de corte y de pago DEBEN ser enteros de 1 a 31. La tasa,
  si se indica, DEBE ser un número decimal de 0,01 a 10 (porcentaje
  mensual) con hasta dos decimales (decisiones 16 y 27). El sistema NUNCA
  DEBE aceptar ni redondear una tasa con más decimales, ni guardarla o
  calcular con ella como `float`.
- **RF-4** CUANDO un miembro lista las tarjetas, el sistema DEBE devolver
  las activas del espacio en orden de creación.
- **RF-5** CUANDO un miembro edita una tarjeta, activa o archivada, el
  sistema DEBE cambiar solo el nombre, los días o la tasa que se envían,
  con las reglas de RF-2 y RF-3; la tasa se puede quitar. Cambiar los días
  NO DEBE cambiar el mes de pago de las compras ya registradas
  (decisión 13).
- **RF-6** CUANDO un miembro elimina una tarjeta, el sistema DEBE dejar de
  devolverla en el listado y de aceptarla en compras nuevas, sin pedir
  confirmación, aunque tenga cuotas pendientes (decisión 9). NUNCA DEBE
  borrar ni cambiar sus compras, abonos ni valores del extracto. La
  respuesta DEBE traer un aviso que nombre la tarjeta, diga que sus cuotas
  siguen llegando a Deudas y que se puede volver a usar creándola de nuevo
  con el mismo nombre.
- **RF-7** CUANDO un miembro crea una tarjeta con un nombre equivalente al
  de una archivada del mismo espacio, el sistema DEBE restaurar esa tarjeta
  con su identificador, su nombre, sus días y su tasa originales, en lugar
  de crear otra, e indicar que se restauró (decisión 24).
- **RF-8** SI la tarjeta de la ruta no existe en el espacio, incluso si
  pertenece a otro espacio del que quien llama también es miembro,
  ENTONCES el sistema DEBE responder `404` sin cambiar nada y sin
  distinguir un caso del otro. Eliminar una tarjeta ya archivada también
  responde `404`.

### Compras con tarjeta

- **RF-9** CUANDO un miembro registra un gasto a crédito, DEBE indicar una
  tarjeta, una descripción, una categoría y, si quiere, el número de cuotas
  (por defecto 1), y NO DEBE indicar rubro. SI falta la tarjeta, la
  descripción o la categoría, o llega un rubro, ENTONCES el sistema DEBE
  rechazar el gasto sin guardar nada y explicar la regla (decisiones 2, 8 y
  26).
- **RF-10** SI un gasto a débito trae tarjeta o cuotas, ENTONCES el sistema
  DEBE rechazarlo sin guardar nada. Un gasto a débito sigue las reglas de
  rubro o categoría de la 008 (RF-17 de la 008).
- **RF-11** El número de cuotas DEBE ser un entero de 1 a 48 (decisión 10).
  El sistema DEBE rechazar decimales, texto, booleanos y números fuera de
  ese rango sin guardar nada.
- **RF-12** SI la tarjeta no existe en el espacio, incluso si pertenece a
  otro espacio del que quien llama también es miembro, ENTONCES el sistema
  DEBE rechazar el gasto sin guardar nada y con el mismo mensaje en los
  dos casos. SI la tarjeta está archivada, ENTONCES DEBE rechazarlo e
  indicar cómo restaurarla. La categoría sigue RF-5 de la 003 y RF-41 de la
  008.
- **RF-13** CUANDO se registra una compra con tarjeta, el sistema DEBE
  calcular con la regla de la decisión 12 el mes de pago de la primera
  cuota, guardarlo y devolverlo con el gasto. La cuota número *k* DEBE
  caer *k − 1* meses después del mes de pago.
- **RF-14** CUANDO un miembro edita una compra con tarjeta sin abonos, el
  sistema DEBE permitir cambiar el monto, la fecha, la tarjeta, las cuotas,
  la categoría y la descripción, con las reglas de RF-9 a RF-12; la
  descripción no se puede quitar. SI cambia
  el monto, la fecha, la tarjeta o las cuotas, ENTONCES el sistema DEBE
  recalcular el mes de pago con los días actuales de la tarjeta.
- **RF-15** CUANDO un gasto cambia de débito a crédito, la petición DEBE
  traer la tarjeta, quitar el rubro si lo tenía y dejar el gasto con
  descripción; CUANDO una compra con
  tarjeta cambia a débito, el sistema DEBE quitarle la tarjeta y las cuotas
  y la petición DEBE cumplir la regla de rubro o categoría de la 008. SI no
  se cumple, ENTONCES el sistema DEBE rechazar el cambio sin guardar nada.
- **RF-16** SI una compra tiene abonos, ENTONCES el sistema DEBE rechazar
  cualquier cambio que no sea de descripción o de categoría, y DEBE
  rechazar borrarla, en los dos casos sin cambiar nada e indicando que
  primero hay que borrar sus abonos (decisión 17).
- **RF-17** Un gasto a crédito sin tarjeta, registrado antes de esta spec,
  DEBE conservar sus datos y seguir las reglas de la 008: cuenta el día del
  gasto, con su rubro o su categoría, y su descripción sigue siendo
  opcional. Se DEBE poder editar sin ponerle tarjeta. SI se le pone
  tarjeta, ENTONCES pasa a ser compra con tarjeta con las reglas de RF-9 a
  RF-15 (decisión 8).
- **RF-18** El sistema DEBE devolver cada gasto con su tarjeta, su número de
  cuotas y el mes de pago de su primera cuota, o nulos si no es compra con
  tarjeta. Las demás reglas de los gastos de la 003, la 006 y la 008 NO
  DEBEN cambiar: el listado por periodo sigue usando la fecha de la compra.

### Cuotas e intereses

- **RF-19** El capital de las cuotas DEBE ser el monto de la compra entre el
  número de cuotas, en pesos enteros, con un peso más en cada una de las
  primeras cuotas si la división no es exacta. La suma del capital de las
  cuotas DEBE ser igual al monto (decisión 15).
- **RF-20** El interés estimado de cada cuota DEBE ser el saldo antes de esa
  cuota por la tasa mensual actual de la tarjeta, redondeado al peso con el
  medio peso hacia arriba. SI la compra es a 1 cuota o la tarjeta no tiene
  tasa, ENTONCES el interés DEBE ser `0` (decisiones 5, 14 y 15).
- **RF-21** CUANDO un miembro pide el plan de cuotas de una compra con
  tarjeta, el sistema DEBE devolver cada cuota con su número, el total de
  cuotas, su mes de pago, capital, interés, total y saldo después de ella,
  y los abonos de la compra. SI el gasto no es compra con tarjeta, ENTONCES
  DEBE responder que no tiene cuotas.

### Abonos

- **RF-22** CUANDO un miembro abona a una compra con tarjeta con un monto,
  un mes (por defecto el actual) y si baja la cuota o el plazo, el sistema
  DEBE guardar el abono y devolverlo con el plan de cuotas nuevo de la
  compra (decisión 7).
- **RF-23** El mes del abono DEBE ser un mes con cuota de la compra y con
  saldo después de esa cuota (decisión 19). El monto DEBE cumplir las
  reglas del monto de un gasto (RF-3 y RF-4 de la 003) y NO DEBE pasar de
  ese saldo. SI no se cumple, ENTONCES el sistema DEBE rechazar el abono
  sin guardar nada e indicar el saldo máximo o los meses posibles.
- **RF-24** SI la compra ya tiene un abono en ese mes o en uno posterior,
  ENTONCES el sistema DEBE rechazar el abono sin guardar nada, aunque
  lleguen dos peticiones a la vez (decisión 18).
- **RF-25** CUANDO el abono baja el plazo, las cuotas siguientes DEBEN
  conservar el capital que tenía la cuota siguiente, y la última DEBE
  llevar lo que falte. CUANDO baja la cuota, el número de cuotas DEBE
  quedar igual y el saldo DEBE repartirse entre las que faltan con la regla
  de RF-19. Los intereses de las cuotas siguientes DEBEN calcularse sobre el
  saldo nuevo.
- **RF-26** CUANDO un abono es igual al saldo, la compra DEBE quedar sin
  cuotas después de ese mes.
- **RF-27** CUANDO un miembro borra un abono con confirmación explícita, el
  sistema DEBE borrarlo y recalcular las cuotas de la compra. Sin
  confirmación, el sistema DEBE rechazar el borrado sin cambiar nada, como
  el de un gasto (RF-16 de la 003).
- **RF-28** Un abono NUNCA DEBE cambiar el monto, la fecha, la tarjeta, la
  categoría ni las cuotas pactadas de la compra. SI el gasto de la ruta no
  es una compra con tarjeta, ENTONCES el sistema DEBE rechazar el abono.

### Pagar todo

- **RF-29** CUANDO un miembro paga el total de una tarjeta, activa o
  archivada, en un mes (por defecto el actual), el sistema DEBE crear, en
  una sola operación, un abono por el saldo completo a cada compra de la
  tarjeta que tenga una cuota en ese mes y saldo después de ella, y DEBE
  devolver los abonos creados y la deuda de la tarjeta en ese mes
  (decisión 28). Esas compras DEBEN quedar sin cuotas después de ese mes
  (RF-26).
- **RF-30** Pagar todo NO DEBE tocar las compras cuya primera cuota es de
  un mes posterior: siguen llegando a Deudas en su mes. SI ninguna compra
  tiene saldo que saldar, o alguna de las que salda ya tiene un abono en
  ese mes o en uno posterior, ENTONCES el sistema DEBE rechazar la
  operación sin crear ningún abono e indicar el motivo y, si aplica, la
  compra. Los abonos creados son abonos como los de RF-22 y se borran uno a
  uno (RF-27).

### Valor real del extracto

- **RF-31** CUANDO un miembro escribe el valor real del extracto de una
  tarjeta, activa o archivada, en un mes, el sistema DEBE guardarlo y, si
  ya había uno, reemplazarlo. El valor DEBE ser un entero de `0` a un
  billón (decisión 20).
- **RF-32** CUANDO un miembro quita el valor real de un mes, el sistema DEBE
  borrarlo sin pedir confirmación, y la deuda de ese mes DEBE volver a ser
  la estimada. SI ese mes no tiene valor real, ENTONCES DEBE responder
  `404`.
- **RF-33** El valor real NUNCA DEBE cambiar compras, cuotas ni abonos, y
  copiar el plan del mes NO DEBE copiarlo.

### Deudas y resumen

- **RF-34** La deuda estimada de una tarjeta en un mes DEBE ser la suma del
  capital y el interés de las cuotas de sus compras que caen en ese mes.
- **RF-35** La deuda de una tarjeta en un mes DEBE ser su valor real del
  extracto o, si no tiene, su deuda estimada; más los abonos de ese mes a
  sus compras (decisiones 4 y 7).
- **RF-36** CUANDO un miembro pide el resumen de un periodo, el sistema DEBE
  devolver además la sección Deudas: cada tarjeta con cuotas, abonos o
  valor real en el periodo, activa o archivada y marcada si lo está
  (decisión 21), con cada cuota (compra, nombre según la decisión 23,
  número, total de cuotas, capital, interés y total), cada abono, la deuda
  estimada, el valor real o su ausencia, y la deuda.
- **RF-37** Las compras con tarjeta NO DEBEN sumar en lo gastado de ningún
  rubro ni de ninguna categoría, en ningún mes (decisión 6). Los gastos a
  débito y los gastos a crédito sin tarjeta DEBEN contar como en la 008.
- **RF-38** Los totales del resumen DEBEN incluir las deudas del mes: lo
  planeado DEBE ser lo planeado en rubros más las deudas, y lo gastado, lo
  gastado en rubros más lo no planeado más las deudas. Sin asignar
  (ingresos − planeado) y balance (ingresos − gastado) se calculan con esos
  totales (decisión 3).
- **RF-39** Todos los montos de Deudas DEBEN ser enteros en la unidad mínima
  de la moneda (principio 6). Pedir el resumen NUNCA DEBE crear ni cambiar
  datos.

### Estado de la tarjeta y simulación

- **RF-40** CUANDO un miembro pide el estado de una tarjeta, activa o
  archivada, el sistema DEBE devolver, tomando como pendientes las cuotas
  del periodo actual en adelante: el saldo pendiente (su capital), cada
  compra con cuotas pendientes (nombre, monto, total de cuotas, número de
  la siguiente y saldo), y la deuda de la tarjeta (RF-35) en cada mes desde
  el actual hasta el de su última cuota o su último valor real o abono.
- **RF-41** CUANDO un miembro simula una compra con una tarjeta activa, un
  monto, un número de cuotas y una fecha (por defecto hoy), el sistema DEBE
  devolver el mes de pago y las cuotas como en RF-21, con las mismas
  validaciones que registrar la compra, y NUNCA DEBE guardar nada
  (decisión 22).

### Aislamiento y ciclo de vida

- **RF-42** Toda operación sobre tarjetas, compras con tarjeta, abonos,
  valores del extracto, pagar todo, el estado y la simulación DEBE indicar
  el espacio y pasar por la comprobación de membresía de la 001. Si quien
  llama no es miembro, el sistema DEBE responder `404` sin cambiar nada;
  sin sesión válida, `401`.
- **RF-43** Ninguna de esas operaciones DEBE leer ni escribir datos de otro
  espacio, aunque quien llama sea miembro de los dos. Una tarjeta del
  espacio B no sirve para una compra del espacio A.
- **RF-44** CUANDO un miembro sale de un espacio, el sistema DEBE conservar
  las tarjetas, abonos y valores del extracto que registró. CUANDO se borra
  un espacio, el sistema DEBE borrar sus tarjetas, abonos y valores del
  extracto y NUNCA DEBE tocar los de otros espacios.

### Esquema

- **RF-45** Una migración DEBE añadir las tablas y columnas de esta spec al
  arrancar la API (RF-31 de la 008), sin cambiar ningún dato: todo gasto
  existente queda sin tarjeta (decisión 8). Tras migrar, el esquema DEBE
  coincidir con el de los modelos.

## Criterios de validación

La spec se da por cumplida cuando, además de los tests por requisito:

1. Un test sin HTTP comprueba los meses de pago de la decisión 12: con
   corte 25 y pago 10, el 25 de noviembre da `2026-12` y el 26, `2027-01`;
   con corte 15 y pago 30, el 10 de noviembre da `2026-11` y el 10 de
   febrero de 2027, `2027-02`; con corte 10 y pago 10, el 10 de noviembre
   da `2026-12`; con corte 31 y pago 5, el 30 de abril da `2026-05`
   (RF-13).
2. Un test sin HTTP calcula la "Compra TV" de 1.200.000 a 6 cuotas con
   tasa 1,90 % y primera cuota en `2026-12`: capital de 200.000 en cada
   cuota e intereses de 22.800, 19.000, 15.200, 11.400, 7.600 y 3.800 de
   diciembre a mayo. Otro comprueba que 1.000.000 a 3 cuotas da 333.334,
   333.333 y 333.333 de capital, y que una compra a 1 cuota o con una
   tarjeta sin tasa no tiene intereses (RF-19, RF-20).
3. Un test abona 400.000 a la "Compra TV" en `2026-12`:
   - bajando el plazo, quedan cuotas de 211.400, 207.600 y 203.800 de
     enero a marzo, y ninguna después;
   - bajando la cuota, quedan cuotas de 131.400, 129.120, 126.840,
     124.560 y 122.280 de enero a mayo;
   - un abono de 1.000.000 en `2026-12` cancela la compra; uno de
     1.000.001, uno en `2026-11` (antes de la primera cuota) y uno en
     `2027-05` (sin saldo después) se rechazan;
   - un segundo abono en `2026-12`, o uno en `2027-01` cuando ya hay uno
     en `2027-02`, se rechaza sin guardar nada;
   - borrar el abono sin `confirm=true` se rechaza, y con él vuelven las
     6 cuotas originales
   (RF-22 a RF-27).
4. Un test arma noviembre y diciembre de 2026 con la Visa (corte 25, pago
   10, 1,90 %), el ingreso "Salario" (5.000.000) y el rubro "Arriendo"
   (Hogar, 1.500.000) de diciembre pagado con débito. Registra con la Visa
   un "Mercado" de 200.000 a 1 cuota el 5 de noviembre y la "Compra TV"
   (Hogar) el 12 de noviembre. Comprueba que:
   - en noviembre ninguna de las dos compras suma en ningún rubro ni
     categoría;
   - en diciembre, Deudas tiene la Visa con "Mercado · 1 de 1" por
     200.000 y "Compra TV · 1 de 6" por 222.800, deuda de 422.800; Hogar
     suma 1.500.000 y no la cuota de la TV; lo planeado y lo gastado son
     1.922.800, y sin asignar y balance, 3.077.200;
   - con el valor real de 431.500 la deuda es 431.500, y con un abono de
     400.000 en diciembre, 831.500; al quitar el valor real vuelve a
     822.800
   (RF-31 a RF-38).
5. Un test comprueba que un gasto a crédito sin tarjeta creado antes de
   migrar sigue contando en su rubro el día del gasto, se puede editar sin
   tarjeta, y al ponerle tarjeta pasa a Deudas (RF-17, RF-37).
6. Un test comprueba que se rechazan sin guardar nada: un gasto a crédito
   sin tarjeta, con rubro, sin descripción o sin categoría; quitarle la
   descripción a una compra con tarjeta; uno a débito con tarjeta o con
   cuotas; cuotas `0`, `49`, `"3"`, `3.0` y `true`; una tarjeta archivada;
   y una tarjeta de otro espacio aunque quien llama sea miembro de los dos
   (RF-9 a RF-12, RF-43).
7. Un test crea "Visa", comprueba que "visa" choca, la elimina con su
   aviso, comprueba que ya no sale en el listado, que no acepta compras
   nuevas pero sus cuotas siguen en Deudas y acepta abonos y valores del
   extracto, y que crear "VISA" la restaura con el mismo identificador,
   nombre, días y tasa. Otro comprueba que la tasa `1.89` se guarda y se
   devuelve exacta, y que `1.895`, `0`, `10.01`, `"1.89"` y `true` se
   rechazan (RF-1 a RF-8).
8. Un test cambia el corte de la Visa de 25 a 5 y comprueba que la "Compra
   TV" sigue con primera cuota en `2026-12`; al cambiarle la fecha, se
   recalcula con el corte nuevo. Otro cambia la tasa a 2 % y comprueba que
   cambian las cuotas estimadas de los meses sin valor real y no la deuda
   de un mes con valor real (RF-5, RF-14, RF-20).
9. Un test comprueba que una compra con abonos solo admite cambios de
   descripción y categoría, que borrarla se rechaza hasta borrar sus
   abonos, y que el `PATCH` rechazado no cambia nada (RF-16).
10. Con el reloj fijado el 15 de enero de 2027, un test pide el estado de
    la Visa: saldo pendiente de 1.000.000, la "Compra TV" con siguiente
    cuota 2 de 6 y saldo 1.000.000, el "Mercado" fuera de la lista, y la
    deuda de enero a mayo de 2027. Otro simula la "Compra TV" y obtiene el
    mes `2026-12` y las cuotas del criterio 2 sin que se guarde ningún
    gasto (RF-40, RF-41).
11. Un test migra a `head` una base en la `0003` con gastos a crédito y a
    débito, y comprueba que siguen iguales y sin tarjeta, y que
    `compare_metadata` no ve diferencias (RF-45).
12. Tests de aislamiento: dos usuarios en espacios distintos no pueden
    crear, editar, eliminar ni ver tarjetas, abonos, valores del extracto,
    estado, simulación o pagar todo del otro; todo responde `404` y nada de uno
    aparece en las Deudas del otro. Borrar un espacio borra sus tarjetas,
    abonos y valores del extracto y no los de otro, y salir de un espacio
    los conserva (RF-8, RF-42 a RF-44).
13. Un test registra con la Visa la "Compra TV" (12 de noviembre), el
    "Mercado" (5 de noviembre, 1 cuota) y unos "Zapatos" de 150.000 a 1
    cuota el 30 de noviembre, después del corte. Pagar todo en `2026-12`
    crea un solo abono, de 1.000.000, a la "Compra TV"; la deuda de la Visa
    en diciembre es 1.422.800; en enero, Deudas solo trae "Zapatos · 1 de
    1" por 150.000. Pagar todo otra vez en diciembre se rechaza sin crear
    nada. Otro test con un abono de la "Compra TV" en `2027-02` comprueba
    que pagar todo en `2027-01` se rechaza nombrando la compra y no crea
    ningún abono (RF-29, RF-30).
14. `make test` y `make lint` pasan en verde.

## Requisitos para otras specs y documentos

- **010-app-web:** el formulario de registro tiene un solo campo para
  nombrar el gasto, la descripción (decisión 26). A débito, mientras se
  escribe sugiere los rubros del mes con lo presupuestado y lo que queda;
  si se elige uno, envía `budget_item_id` sin descripción, y si no, pide la
  categoría y envía la descripción. A crédito, pide tarjeta, cuotas,
  descripción y categoría, y no sugiere rubros; antes de guardar muestra
  el mes de pago y las cuotas estimadas con la simulación (RF-41,
  ADR 0010). Al eliminar una
  tarjeta, muestra el aviso de la API (RF-6).
- **011-tablero-y-planear:** la pantalla de planear muestra Deudas por
  tarjeta y permite escribir el valor real del extracto de cada una. La
  pantalla de tarjetas muestra el estado (RF-40), el plan de cuotas de cada
  compra (RF-21) y permite abonar eligiendo cuota o plazo, y pagar todo
  (RF-29), avisando que las compras posteriores al corte siguen llegando.
- **Roadmap:** la nota de la 009 cambia: la compra a 1 cuota cuenta el mes
  del pago (decisión 1) y los abonos y pagar todo entran (decisiones 7 y
  28). Ya está actualizada.
- **AGENTS.md:** el glosario no tiene tarjeta, cuota, abono, deuda ni valor
  del extracto, y su definición de gasto no cubre las compras con tarjeta.
  Hay que actualizarlo al cerrar la spec, con aprobación explícita.
