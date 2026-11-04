# Spec 004 — Presupuesto mensual

- Fase: 1 — Aplicación y SDD
- Estado: aprobada
- Base: spec 001 (RF-28 a RF-32, aislamiento entre espacios), spec 002
  (categorías), spec 003 (gastos y regla de periodo), ADR 0001

## Por qué

Registrar gastos solo sirve si se pueden comparar con lo que se quería
gastar. Esta spec añade esa comparación: un presupuesto por categoría y un
resumen del mes con lo gastado frente a lo presupuestado. Es lo que van a
mostrar el comando `/resumen` del bot (006) y el dashboard (007). Por el
principio 10, el cálculo vive en la API y se prueba ahí; el bot y la web
solo lo muestran.

Un hogar no cambia su presupuesto cada mes: lo fija una vez y lo ajusta de
vez en cuando. Por eso un presupuesto rige desde un mes en adelante hasta
que se cambie, y nadie tiene que volver a escribirlo el día 1 de cada mes.

## Qué entra

- Fijar, cambiar y quitar el presupuesto de una categoría desde un periodo.
- El resumen de un periodo: por categoría y en total, el presupuesto
  vigente, lo gastado y lo que queda.
- Ampliar con presupuestos los tests de aislamiento de las specs 001 y 003.

## Qué NO entra

- Un presupuesto total del espacio independiente de las categorías: el
  total presupuestado es la suma de las categorías.
- Porcentajes, colores, gráficos o avisos al acercarse o superar el
  presupuesto. La API devuelve montos; cómo se muestran lo deciden el bot
  (006) y la web (007).
- Desglose del resumen por tipo de pago, por miembro o por día.
- Pasar lo que sobró de un mes al siguiente.
- Historial de quién cambió un presupuesto y cuándo.
- Las pantallas o comandos para fijar el presupuesto: ver "Requisitos para
  otras specs".
- Qué pasa con el presupuesto al borrar una categoría: las categorías
  todavía no se borran (spec 002).

## Conceptos

- **Presupuesto** (`budget`): monto máximo que un espacio quiere gastar en
  una categoría cada mes. Se fija **desde** un periodo y rige en ese
  periodo y en los siguientes hasta que se fije otro (decisión 1).
- **Presupuesto vigente** de una categoría en un periodo: el último que se
  fijó desde ese periodo o desde uno anterior. Si no hay ninguno, o el
  último quitó el presupuesto, la categoría no tiene presupuesto en ese
  periodo.
- **Gastado**: suma de los montos de los gastos de una categoría cuya fecha
  cae en el periodo, con la regla de periodo de la spec 003 (RF-9).
- **Lo que queda**: presupuesto vigente menos gastado. Si es negativo, el
  presupuesto se excedió.
- **Resumen** (`summary`): para un periodo, cada categoría del espacio con
  su presupuesto vigente, lo gastado y lo que queda, más los totales.

## Decisiones de clarificación (2026-11-04)

1. **El presupuesto rige desde un periodo en adelante hasta que se
   cambie.** Fijar 400.000 para Comida desde `2026-11` deja 400.000 en
   noviembre, diciembre y los meses siguientes. Fijar 500.000 desde
   `2026-12` cambia diciembre en adelante y no toca noviembre. Se descartó
   un presupuesto por mes, que empieza vacío cada mes aunque se pueda copiar
   del anterior: obliga a repetir cada mes un dato que casi nunca cambia, y
   el día 1 el resumen saldría sin presupuesto.
2. **El resumen incluye todas las categorías del espacio**, en el orden de
   creación de la spec 002 (decisión 5 de la 002), aunque no tengan
   presupuesto ni gastos, y además los totales. Así la web y el bot
   muestran siempre la misma lista. El total presupuestado suma solo las
   categorías con presupuesto, y el total gastado suma todos los gastos del
   periodo, también los de categorías sin presupuesto.
3. **Se puede fijar o quitar el presupuesto desde cualquier periodo**,
   pasado, actual o futuro. Sirve para planear el mes siguiente y para
   cargar o corregir el de meses anteriores. Cambiar un periodo pasado
   cambia su resumen.
4. **Quitar el presupuesto es fijarlo sin monto**: la categoría queda sin
   presupuesto desde ese periodo hasta que se fije otro. No pide
   confirmación, porque no borra gastos y se recupera volviendo a fijar el
   monto. El monto de un presupuesto sigue las reglas del monto de un gasto
   (decisiones 1 y 7 de la 003): entero de pesos, de 1 a un billón. No
   existe el presupuesto cero: "sin presupuesto" se expresa quitándolo.
5. **Cualquier miembro fija y quita el presupuesto de cualquier categoría
   del espacio**, porque hoy todos los miembros tienen los mismos permisos
   (ADR 0001).

## Requisitos funcionales

### Fijar y quitar el presupuesto

- **RF-1** CUANDO un miembro fija el presupuesto de una categoría de su
  espacio desde un periodo con un monto válido, el sistema DEBE guardarlo y
  devolverlo con la categoría, el periodo y el monto (decisiones 1 y 5).
- **RF-2** SI no se indica el periodo, ENTONCES el sistema DEBE usar el
  periodo actual en la zona horaria configurada.
- **RF-3** El presupuesto fijado desde un periodo DEBE regir en ese periodo
  y en cada periodo siguiente hasta el primero desde el que se fije otro
  presupuesto para la misma categoría (decisión 1).
- **RF-4** CUANDO se fija el presupuesto de una categoría desde un periodo,
  el sistema NUNCA DEBE cambiar el presupuesto vigente en los periodos
  anteriores ni en los periodos desde los que ya se fijó otro después.
- **RF-5** SI ya había un presupuesto fijado para esa categoría desde ese
  mismo periodo, ENTONCES el sistema DEBE reemplazarlo. Nunca hay dos
  presupuestos de la misma categoría desde el mismo periodo, aunque lleguen
  dos peticiones a la vez.
- **RF-6** CUANDO un miembro quita el presupuesto de una categoría desde un
  periodo, el sistema DEBE dejarla sin presupuesto desde ese periodo hasta
  el siguiente desde el que se fije otro, sin pedir confirmación y sin
  tocar ningún gasto (decisión 4).
- **RF-7** SI el monto no es un número entero mayor que cero o supera el
  monto máximo, ENTONCES el sistema DEBE rechazar el presupuesto sin
  guardar nada e indicar el requisito incumplido. El sistema NUNCA DEBE
  aceptar ni redondear montos con decimales (principio 6, decisión 4).
- **RF-8** SI el periodo no tiene el formato `YYYY-MM` o no es un mes
  válido, ENTONCES el sistema DEBE rechazar la petición sin guardar nada e
  indicar el formato esperado.
- **RF-9** SI la categoría no existe en el espacio indicado, incluso si
  pertenece a otro espacio del que quien llama también es miembro,
  ENTONCES el sistema DEBE responder `404` sin guardar nada y sin
  distinguir un caso del otro (RF-30 de la 001).
- **RF-10** El sistema DEBE permitir fijar y quitar el presupuesto desde
  cualquier periodo válido, sea pasado, actual o futuro (decisión 3).

### Resumen

- **RF-11** CUANDO un miembro pide el resumen de un periodo, el sistema
  DEBE devolver todas las categorías del espacio, en orden de creación, cada
  una con su presupuesto vigente en ese periodo o la indicación de que no
  tiene, lo gastado y lo que queda (decisión 2).
- **RF-12** El sistema DEBE calcular lo gastado de cada categoría sumando
  los gastos de ese espacio y esa categoría cuya fecha cae en el periodo,
  con la regla de RF-9 de la 003. Una categoría sin gastos en el periodo
  tiene gastado `0`.
- **RF-13** El sistema DEBE calcular lo que queda como presupuesto vigente
  menos gastado, negativo si el presupuesto se excedió. Una categoría sin
  presupuesto no tiene "lo que queda".
- **RF-14** El sistema DEBE devolver en el resumen el total gastado, que
  suma todos los gastos del periodo; el total presupuestado, que suma los
  presupuestos vigentes, y el total que queda, que es la resta de los dos.
  Si ninguna categoría tiene presupuesto, no hay total presupuestado ni
  total que queda (decisión 2).
- **RF-15** SI no se indica periodo en el resumen, ENTONCES el sistema DEBE
  usar el periodo actual en la zona horaria configurada. Un periodo mal
  escrito se rechaza como en RF-8.
- **RF-16** Todos los montos del resumen DEBEN ser enteros en la unidad
  mínima de la moneda (principio 6).

### Aislamiento y ciclo de vida

- **RF-17** Toda operación sobre presupuestos y resúmenes DEBE indicar el
  espacio y pasar por la comprobación de membresía de la spec 001 (RF-28,
  RF-29 de la 001). Si quien llama no es miembro, el sistema DEBE responder
  `404` sin guardar nada (RF-30 de la 001). Una petición sin sesión válida
  recibe `401` y no modifica nada (RF-11 de la 001).
- **RF-18** El resumen de un espacio NUNCA DEBE contar gastos ni
  presupuestos de otro espacio, aunque quien llama sea miembro de los dos.
- **RF-19** CUANDO un miembro sale de un espacio, el sistema DEBE conservar
  los presupuestos del espacio (RF-21 de la 001).
- **RF-20** CUANDO se borra un espacio, el sistema DEBE borrar sus
  presupuestos y NUNCA DEBE tocar los de otros espacios (RF-23 y RF-27 de
  la 001).

## Criterios de validación

La spec se da por cumplida cuando, además de los tests por requisito:

1. Un test fija 400.000 para Comida desde `2026-09` y comprueba que el
   resumen de `2026-08` la muestra sin presupuesto y los de `2026-09` a
   `2026-12`, con 400.000. Después fija 500.000 desde `2026-11` y comprueba
   que septiembre y octubre siguen en 400.000, y noviembre y diciembre
   pasan a 500.000 (RF-3, RF-4, RF-10).
2. Un test quita el presupuesto de Comida desde `2026-12` y comprueba que
   diciembre en adelante queda sin presupuesto, que noviembre sigue en
   500.000 y que ningún gasto cambia (RF-6).
3. Un test con gastos del 30 de septiembre, del 1 y del 31 de octubre y del
   1 de noviembre comprueba que el resumen de `2026-10` solo suma los dos de
   octubre, que una categoría sin gastos tiene gastado `0`, que una
   categoría excedida tiene lo que queda en negativo y que los totales
   cuadran, incluidos los gastos de categorías sin presupuesto (RF-11 a
   RF-14).
4. Un test fija el reloj en el 31 de octubre a las 20:00 en Bogotá (ya 1 de
   noviembre en UTC) y comprueba que un presupuesto fijado sin periodo rige
   desde `2026-10` y que el resumen sin periodo es el de `2026-10` (RF-2,
   RF-15, principio 7).
5. Un test comprueba que un monto con decimales, negativo, cero, mayor que
   el máximo, enviado como texto o como booleano se rechaza y no guarda nada
   (RF-7).
6. Un test crea dos usuarios en espacios distintos y comprueba que ninguno
   puede fijar presupuestos ni pedir el resumen del espacio del otro, que
   todo responde `404` y que los gastos y presupuestos de uno no aparecen en
   el resumen del otro (RF-17, RF-18). Amplía el criterio 1 de la spec 003.
7. Un test comprueba que fijar el presupuesto de una categoría del espacio B
   por la ruta del espacio A responde `404`, aunque quien llama sea miembro
   de los dos (RF-9).
8. Un test comprueba que dos miembros del mismo espacio ven el mismo
   resumen y que uno cambia el presupuesto que fijó el otro (RF-11,
   decisión 5).
9. Un test comprueba que borrar un espacio borra sus presupuestos y no toca
   los de otro espacio del mismo usuario, y que salir de un espacio los
   conserva (RF-19, RF-20). Amplía el criterio 6 de la spec 003.
10. `make test` y `make lint` pasan en verde.

## Requisitos para otras specs

- `006-bot-consultas` muestra con `/resumen` el resumen de RF-11 a RF-14.
- `007-dashboard-web` muestra el resumen del mes. **Ninguna spec planeada
  permite todavía fijar el presupuesto desde la web o el bot**: hasta
  entonces solo se fija con la API. Se propone que la 007 lo incluya, y
  que al fijarlo explique que rige desde ese mes en adelante (decisión 1).
- La spec que añada el borrado de categorías debe decidir qué pasa con sus
  presupuestos, además de con sus gastos (principio 8).
