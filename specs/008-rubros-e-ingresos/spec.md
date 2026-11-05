# Spec 008 — Rubros e ingresos del mes

- Fase: 1 — Aplicación y SDD
- Estado: propuesta (2026-11-05)
- Base: spec 001 (aislamiento entre espacios), spec 002 (categorías y
  comparación de nombres, ADR 0006; esta spec añade eliminarlas), spec 003 (gastos y regla de periodo),
  spec 004 (presupuesto y resumen, ADR 0008), spec 007 (tablas de Telegram),
  ADR 0004, ADR 0010

## Por qué

La spec 004 fija un presupuesto por categoría que rige desde un mes en
adelante. Al prototipar la web (ADR 0010) quedó claro que así no se planea
un mes de verdad:

- Dentro de una categoría hay cosas distintas que se planean por separado:
  en Hogar van el arriendo, la administración y el internet.
- Sin los ingresos del mes no se sabe cuánto queda sin asignar ni si el mes
  cierra en positivo.
- Planear es algo que se hace cada mes: se parte del mes anterior y se
  ajusta. Un presupuesto que se hereda solo no invita a revisarlo.

Esta spec cambia el presupuesto por un **plan del mes**: rubros con nombre
libre y categoría, e ingresos. Cada gasto se liga a un rubro o queda como
"no planeado". El plan de un mes se copia del anterior con una acción
explícita.

Es la primera spec que cambia tablas que ya están en `main`, así que
entran las migraciones con [Alembic](https://alembic.sqlalchemy.org/), como
pedía el ADR 0004.

## Qué entra

- Rubros: crear, editar y borrar los rubros de un mes.
- Ingresos: crear, editar y borrar los ingresos de un mes.
- Copiar el plan (rubros e ingresos) del mes anterior a un mes vacío.
- Gastos ligados a un rubro, o "no planeados" con su categoría.
- Eliminar categorías sin perder su historia, y restaurarlas al crearlas
  de nuevo.
- Un resumen nuevo del mes: ingresos, rubros, categorías y totales.
- Retirar el presupuesto por categoría de la 004 sin perder los montos
  guardados.
- Migraciones con Alembic, que adoptan las bases de datos ya creadas.
- Borrar las tablas de Telegram que dejó la 007 (decisión 1 de la 007).

## Qué NO entra

- Tarjetas, cuotas, intereses y deudas: son la 009.
- Las pantallas para planear y registrar: son la 010 y la 011.
- Ingresos reales con fecha (lo que de verdad llegó frente a lo esperado).
- Copiar desde un mes que no sea el inmediatamente anterior, copiar solo
  una parte del plan o mezclarlo con un plan que ya existe.
- Pasar lo que sobró de un rubro al mes siguiente.
- Listar los gastos de un rubro: el listado por periodo ya trae el rubro de
  cada gasto y el cliente puede filtrarlo.
- Historial de cambios del plan.
- Ver la lista de categorías eliminadas o restaurarlas desde ella: se
  restauran creándolas de nuevo con el mismo nombre (decisión 16).
- Renombrar categorías.
- Deshacer las migraciones (`downgrade`): la vuelta atrás es restaurar la
  copia de la base de datos (ver RF-38).

## Conceptos

- **Rubro** (`budget_item`): una línea del plan de un mes. Tiene nombre
  libre ("Mercado", "Arriendo"), una categoría del espacio y un monto
  planeado. Pertenece a un espacio y a un periodo.
- **Ingreso** (`income`): dinero que el espacio espera recibir en un mes.
  Tiene nombre ("Salario Ana") y monto. Pertenece a un espacio y a un
  periodo.
- **Plan del mes** (`plan`): los rubros y los ingresos de un periodo.
- **Gasto planeado**: gasto ligado a un rubro de su mismo mes. Su categoría
  es la del rubro.
- **Gasto no planeado**: gasto sin rubro. Tiene su propia categoría.
- **Categoría eliminada**: categoría que ya no se ofrece para rubros ni
  gastos nuevos. Los rubros y gastos que ya la tenían la conservan, así que
  sigue apareciendo en los meses donde se usó.
- **Planeado**: suma de los montos de los rubros.
- **Sin asignar**: ingresos menos planeado. Negativo si se planeó más de lo
  que entra.
- **Balance**: ingresos menos todo lo gastado en el mes.

## Decisiones de clarificación (2026-11-05)

1. **Cada mes tiene sus propios rubros.** Copiar el plan crea rubros nuevos
   en el mes destino, y cambiar un rubro de octubre no toca noviembre. Se
   descartó un rubro permanente con un monto por mes: son dos tablas, y
   renombrar un rubro cambiaría todos los meses, también los pasados.

   **Se llama "rubro"**, no "partida", que resultaba poco intuitivo. Se
   descartó "registro" porque choca con "registrar un gasto" y con el
   registro de usuarios; "gasto planeado", porque mezcla el plan con el
   gasto real; "concepto" y "línea del plan", por genérico y por largo.
2. **El plan se copia con una acción explícita**, y solo hacia un mes que
   no tiene ni rubros ni ingresos, para no pisar nada. Copia los rubros y
   los ingresos con sus montos. Se descartó copiarlo solo al consultar un
   mes vacío: una consulta escribiría datos y habría que decidir hasta qué
   mes futuro rellenar (el mismo problema que el ADR 0008 vio al revés).
3. **Los ingresos son parte del plan**: nombre y monto por mes, sin fecha,
   y se copian con el plan. Sirven para calcular lo que queda sin asignar y
   el balance. Se descartó registrar ingresos reales con fecha: exige
   distinguir el ingreso esperado del recibido, y nadie lo ha pedido.
4. **Migrar una base existente convierte cada presupuesto guardado en un
   rubro.** Cada fila de presupuesto con monto pasa a ser un rubro del mes
   desde el que regía, con el nombre y la categoría de su categoría. Las
   filas que quitaban el presupuesto no crean nada. Los gastos existentes
   quedan como no planeados, con su categoría. Así se conserva todo monto
   guardado (principio 8) y después la tabla de presupuestos se borra. Se
   descartaron convertir solo el mes en que corre la migración (el
   resultado dependería del día y se perderían los meses pasados) y
   conservar la tabla sin uso (un esquema con tablas huérfanas, lo que la
   007 descartó para Telegram).

## Decisiones tomadas al redactar la spec (6 a 12, a revisar)

5. **Un gasto planeado está siempre en la categoría de su rubro.** Al
   registrarlo se indica el rubro **o** la categoría, nunca los dos. Si el
   rubro cambia de categoría, sus gastos cambian con él. Así el resumen por
   categoría cuadra siempre con el de rubros. Confirmada en la segunda
   ronda (decisión 13).
6. **Un gasto solo se liga a un rubro de su mismo mes.** El rubro "Mercado"
   de octubre no puede llevar un gasto del 3 de noviembre. Cambiar la fecha
   de un gasto planeado a otro mes se rechaza: hay que elegir un rubro del
   mes nuevo o dejarlo como no planeado.
7. **Dos rubros del mismo mes no pueden llamarse igual**, con la misma
   comparación de nombres que las categorías (ADR 0006): "Mercado" y
   "mercado" chocan, y también "Acción" y "accion" (ver decisión 22). En otro mes o en otro espacio, sí pueden repetirse. Lo
   mismo para los ingresos. Los nombres tienen de 1 a 50 caracteres, como
   las categorías.
8. **Borrar un rubro nunca borra gastos.** Sus gastos pasan a ser no
   planeados, en la categoría que tenía el rubro. No pide confirmación,
   igual que quitar un presupuesto en la 004: no se pierde ningún gasto y
   el rubro se vuelve a crear. La web (011) debería avisar cuántos gastos
   quedan sin rubro.
9. **Se copia del mes inmediatamente anterior.** Si ese mes no tiene plan,
   la copia se rechaza. Si un mes quedó sin plan, el siguiente se planea a
   mano.
10. **El resumen de un mes sin plan sale vacío**, con totales en cero, y no
    copia nada (decisión 2).
11. **Las migraciones se aplican solas al arrancar la API**, como hoy hace
    `create_all`, sin un comando aparte que haya que acordarse de correr
    (principio 14). Cuando haya varias réplicas (fase 8), esto se revisa.
12. **El periodo de un rubro o de un ingreso no se cambia.** Para moverlo de
    mes se borra y se crea en el otro: así un rubro nunca deja gastos de
    otro mes colgando.

## Segunda ronda de clarificación (2026-11-05)

13. **Un gasto planeado se registra escribiendo el rubro**, y la categoría
    sale del rubro: no se vuelve a escribir. Mientras se escribe, la web
    sugiere los rubros del mes con lo presupuestado y lo que queda (010).
    Un gasto no planeado sigue llevando su categoría.
14. **Eliminar una categoría la archiva, no la borra.** Deja de salir como
    opción para rubros, gastos no planeados y cambios de categoría. Los
    rubros y gastos que ya la tenían, de cualquier mes, la conservan y
    siguen contando en el resumen. Se permite aunque tenga rubros en el mes
    actual o en meses futuros. Se descartó bloquearla mientras tenga rubros
    actuales o futuros: obliga a moverlos antes, y conservarlos no rompe
    nada. Borrarla de verdad dejaría rubros y gastos sin categoría
    (principio 8).
15. **Copiar el plan omite los rubros de categorías eliminadas** y dice
    cuáles omitió. Eliminar la categoría significa que ya no se planea.
16. **Crear una categoría con el nombre de una eliminada la restaura**, con
    su historia: los meses pasados y los nuevos quedan juntos en la misma
    categoría para las estadísticas. Se descartaron una categoría nueva
    con el mismo nombre (dos "Mascotas" en las estadísticas) y rechazar el
    nombre.

## Decisiones tomadas al redactar la segunda ronda (a revisar)

17. **Un rubro cuya categoría se eliminó sigue funcionando en su mes**: se
    le registran gastos y se le cambian el nombre y el monto. Eliminar la
    categoría solo quita la opción de elegirla.
18. **El resumen de un mes muestra las categorías activas y, además, las
    eliminadas que tengan rubros o gastos en ese mes**, marcadas como
    eliminadas. Así los totales por categoría siempre cuadran.
19. **También se pueden eliminar las categorías predefinidas.** Un espacio
    puede quedarse sin categorías activas: entonces no se pueden crear
    rubros ni gastos no planeados hasta crear o restaurar una.
20. **Eliminar no pide confirmación**, porque no borra ningún dato y se
    deshace creando de nuevo la categoría (decisión 16). La web (011)
    debería decir que sus rubros dejarán de copiarse. Cambiada en la
    tercera ronda (decisión 23): la respuesta avisa cómo volver a usarla.
21. **Restaurar conserva el nombre original.** Si se eliminó "Mascotas" y
    alguien crea "mascotas", vuelve "Mascotas", como se ve en los meses
    pasados.

## Tercera ronda de clarificación (2026-11-05)

22. **Los nombres se comparan sin mayúsculas ni tildes**, en categorías,
    rubros e ingresos: "Ahorro" = "ahorro", y "Acción" = "acción" =
    "Accion" = "accion". Es la comparación de la 002 (ADR 0006), que ya
    funciona así: ignora mayúsculas, tildes, diéresis y espacios alrededor.
    La ñ sí cuenta: "Año" y "Ano" son nombres distintos. Vale para chocar
    con un nombre activo y para restaurar uno eliminado (decisión 16):
    eliminar "Acción" y crear "accion" restaura "Acción".
23. **Al eliminar una categoría, la respuesta avisa que se puede volver a
    usar creándola de nuevo** con el mismo nombre, y que sus rubros dejan
    de copiarse al planear. El aviso lo escribe la API, en español, para
    que la web (010 y 011) lo muestre tal cual. Sigue sin pedir
    confirmación (decisión 20).

## Requisitos funcionales

### Rubros

- **RF-1** CUANDO un miembro crea un rubro con periodo, nombre, categoría y
  monto válidos, el sistema DEBE guardarlo y devolverlo con su
  identificador, periodo, nombre, categoría y monto.
- **RF-2** SI no se indica el periodo, ENTONCES el sistema DEBE usar el
  periodo actual en la zona horaria configurada. El sistema DEBE aceptar
  cualquier periodo válido, pasado, actual o futuro. Un periodo mal escrito
  se rechaza como en RF-8 de la 004.
- **RF-3** El sistema DEBE guardar el nombre sin los espacios de alrededor
  y DEBE rechazarlo si queda vacío o pasa de 50 caracteres. SI otro rubro
  del mismo espacio y periodo tiene un nombre equivalente según la
  comparación de la 002, ENTONCES el sistema DEBE rechazar el rubro sin
  guardar nada y nombrar el que ya existe, aunque lleguen dos peticiones a
  la vez (decisión 7).
- **RF-4** El monto DEBE cumplir las reglas del monto de un gasto (RF-3 y
  RF-4 de la 003): entero de pesos, de 1 a un billón. El sistema NUNCA DEBE
  aceptar ni redondear montos con decimales (principio 6).
- **RF-5** SI la categoría no existe en el espacio, incluso si pertenece a
  otro espacio del que quien llama también es miembro, ENTONCES el sistema
  DEBE rechazar el rubro sin guardar nada y sin distinguir un caso del
  otro. Una categoría eliminada se rechaza como dice RF-41.
- **RF-6** CUANDO un miembro edita un rubro, el sistema DEBE cambiar solo el
  nombre, la categoría o el monto que se envían, con las reglas de RF-3 a
  RF-5. El periodo de un rubro NO DEBE cambiar (decisión 12).
- **RF-7** CUANDO cambia la categoría de un rubro, el sistema DEBE pasar a
  esa categoría todos los gastos ligados a él, en la misma operación
  (decisión 5).
- **RF-8** CUANDO un miembro borra un rubro, el sistema DEBE borrarlo y
  dejar sus gastos como no planeados en la categoría que tenía el rubro,
  sin pedir confirmación. El sistema NUNCA DEBE borrar esos gastos ni
  cambiar su monto, fecha, tipo de pago, descripción o autor (decisión 8,
  principio 8).
- **RF-9** SI el rubro de la ruta no existe en el espacio, incluso si
  pertenece a otro espacio del que quien llama también es miembro,
  ENTONCES el sistema DEBE responder `404` sin cambiar nada y sin distinguir
  un caso del otro.

### Ingresos

- **RF-10** CUANDO un miembro crea un ingreso con periodo, nombre y monto
  válidos, el sistema DEBE guardarlo y devolverlo con su identificador,
  periodo, nombre y monto. El periodo sigue RF-2; el nombre, RF-3 dentro de
  los ingresos del mismo mes; el monto, RF-4.
- **RF-11** CUANDO un miembro edita un ingreso, el sistema DEBE cambiar solo
  el nombre o el monto que se envían, con las mismas reglas. El periodo NO
  DEBE cambiar. CUANDO un miembro borra un ingreso, el sistema DEBE
  borrarlo sin pedir confirmación.
- **RF-12** SI el ingreso de la ruta no existe en el espacio, el sistema
  DEBE responder como en RF-9.

### Copiar el plan

- **RF-13** CUANDO un miembro copia el plan hacia un periodo, el sistema
  DEBE crear en ese periodo un rubro igual (nombre, categoría y monto) por
  cada rubro del periodo inmediatamente anterior cuya categoría no esté
  eliminada, y un ingreso igual (nombre y monto) por cada ingreso, y
  devolver el resumen del periodo destino junto con los rubros que omitió
  (decisiones 2, 9 y 15). Sin periodo, el destino es el periodo actual.
- **RF-14** SI el periodo destino ya tiene algún rubro o ingreso, ENTONCES
  el sistema DEBE rechazar la copia sin crear nada, aunque lleguen dos
  copias a la vez. El sistema NUNCA DEBE mezclar ni reemplazar un plan que
  ya existe.
- **RF-15** SI el periodo anterior no tiene rubros ni ingresos, o solo
  tiene rubros de categorías eliminadas, ENTONCES el sistema DEBE rechazar
  la copia sin crear nada e indicar que ese periodo no tiene nada que
  copiar.
- **RF-16** Copiar el plan NUNCA DEBE cambiar el plan del periodo de origen
  ni ningún gasto. Los gastos del mes de origen siguen ligados a sus rubros
  de origen.

### Gastos

- **RF-17** CUANDO un miembro registra un gasto, DEBE indicar exactamente
  uno de los dos: un rubro (gasto planeado) o una categoría (gasto no
  planeado). SI envía los dos o ninguno, ENTONCES el sistema DEBE rechazar
  el gasto sin guardar nada y explicar la regla (decisión 5).
- **RF-18** SI el rubro no existe en el espacio, incluso si pertenece a
  otro espacio del que quien llama también es miembro, ENTONCES el sistema
  DEBE rechazar el gasto sin guardar nada, con el mismo mensaje en los dos
  casos, como la categoría en RF-5 de la 003.
- **RF-19** SI el periodo de la fecha del gasto no es el periodo del rubro,
  ENTONCES el sistema DEBE rechazar el gasto sin guardar nada e indicar los
  dos periodos (decisión 6). La regla aplica al registrar y al editar, ya
  cambie la fecha, el rubro o los dos.
- **RF-20** La categoría de un gasto planeado DEBE ser siempre la de su
  rubro. El sistema DEBE devolver cada gasto con su categoría y su rubro, o
  la indicación de que no tiene rubro.
- **RF-21** CUANDO un miembro edita un gasto, el sistema DEBE permitir
  ligarlo a otro rubro, quitarle el rubro (queda no planeado en la
  categoría que tenía) o cambiar la categoría de un gasto no planeado. SI
  se intenta cambiar la categoría de un gasto planeado sin quitarle el
  rubro en la misma petición, ENTONCES el sistema DEBE rechazar el cambio
  sin guardar nada y explicar por qué.
- **RF-22** Las demás reglas de los gastos de la 003 y la 006 NO DEBEN
  cambiar: monto, tipo de pago, fecha, descripción, borrado con
  confirmación, listado por periodo y últimos registrados.

### Resumen

- **RF-23** CUANDO un miembro pide el resumen de un periodo, el sistema
  DEBE devolver:
  - cada ingreso del periodo con su nombre y monto;
  - cada rubro del periodo, en orden de creación, con su nombre, su
    categoría, lo planeado, lo gastado (la suma de sus gastos) y lo que
    queda (planeado menos gastado, negativo si se excedió);
  - cada categoría activa del espacio, y cada categoría eliminada con
    rubros o gastos en el periodo, en el orden de la 002, con lo planeado
    (la suma de sus rubros, `0` si no tiene), lo gastado (todos sus gastos
    del periodo, planeados o no) y si está eliminada (decisión 18);
  - los totales: ingresos, planeado, gastado en rubros, gastado no
    planeado, gastado total, sin asignar y balance.
- **RF-24** El sistema DEBE calcular lo gastado con la regla de periodo de
  la 003 (RF-9 de la 003). Todos los montos del resumen DEBEN ser enteros
  en la unidad mínima de la moneda (principio 6). Sin asignar y balance
  pueden ser negativos.
- **RF-25** SI el periodo no tiene plan, ENTONCES el sistema DEBE devolver
  el resumen con las listas de ingresos y rubros vacías, las categorías
  activas con planeado `0`, y los totales calculados igual (decisión 10). Pedir el
  resumen NUNCA DEBE crear ni cambiar datos.
- **RF-26** SI no se indica periodo en el resumen, ENTONCES el sistema DEBE
  usar el periodo actual. Un periodo mal escrito se rechaza como en RF-8 de
  la 004.

### Presupuesto de la 004

- **RF-27** La API NO DEBE exponer la ruta para fijar el presupuesto por
  categoría de la 004 (`PUT /spaces/{space_id}/budgets/{category_id}`).
  Una petición a ella DEBE responder `404`.

### Aislamiento y ciclo de vida

- **RF-28** Toda operación sobre rubros, ingresos, la copia del plan, el
  resumen y la eliminación de categorías DEBE indicar el espacio y pasar por la comprobación de membresía
  de la 001. Si quien llama no es miembro, el sistema DEBE responder `404`
  sin cambiar nada; sin sesión válida, `401`.
- **RF-29** Ningún rubro, ingreso, copia ni resumen de un espacio DEBE leer
  ni escribir datos de otro, aunque quien llama sea miembro de los dos.
- **RF-30** CUANDO un miembro sale de un espacio, el sistema DEBE conservar
  sus rubros e ingresos. CUANDO se borra un espacio, el sistema DEBE borrar
  sus rubros e ingresos y NUNCA DEBE tocar los de otros espacios.

### Esquema y migraciones

- **RF-31** La API DEBE crear y actualizar el esquema de la base de datos
  con migraciones versionadas en el repositorio, y DEBE aplicar las
  pendientes al arrancar, antes de atender la primera petición
  (decisión 11, principio 14).
- **RF-32** Una base de datos creada antes de esta spec con `create_all`,
  en cualquier spec anterior y con o sin las tablas de Telegram, DEBE
  quedar al día al arrancar la API, sin recrearla y sin pasos manuales.
- **RF-33** Al migrar una base existente, el sistema DEBE convertir cada
  fila de presupuesto con monto en un rubro del periodo desde el que regía,
  con el nombre y la categoría de su categoría y el mismo monto, y DEBE
  dejar todos los gastos existentes como no planeados, con su categoría
  (decisión 4). Después DEBE borrar la tabla de presupuestos.
- **RF-34** Al migrar una base existente, el sistema DEBE borrar las tablas
  `telegram_link_codes` y `telegram_chats` si existen (decisión 1 de la
  007). Son vínculos de chat que ya no usa nada; no guardan gastos ni
  presupuesto.
- **RF-35** Ninguna migración DEBE borrar ni cambiar usuarios, espacios,
  membresías, invitaciones, sesiones, categorías o gastos, salvo ligar o no
  un gasto a un rubro como dice RF-33 (principio 8).
- **RF-36** Una base de datos nueva DEBE quedar, tras las migraciones, con
  el mismo esquema que describen los modelos de la API, sin tabla de
  presupuestos ni tablas de Telegram.
- **RF-37** Arrancar la API con una base ya migrada NO DEBE cambiar nada.
  SI una migración falla, ENTONCES la API NO DEBE arrancar y el error DEBE
  decir qué migración falló.
- **RF-38** El README DEBE explicar que las migraciones corren solas al
  arrancar, y que antes de arrancar la API con esta spec por primera vez
  conviene copiar la base de datos local, porque las migraciones no se
  deshacen.

### Categorías eliminadas

- **RF-39** CUANDO un miembro elimina una categoría de su espacio, el
  sistema DEBE dejar de devolverla en el listado de categorías, sin pedir
  confirmación, aunque tenga rubros o gastos en cualquier mes (decisiones
  14, 19 y 20). La respuesta DEBE incluir un aviso que nombre la categoría
  y diga que se puede volver a usar creándola de nuevo con el mismo
  nombre, y que sus rubros dejarán de copiarse al planear (decisión 23).
- **RF-40** Eliminar una categoría NUNCA DEBE borrar ni cambiar rubros ni
  gastos. Los que la tenían, de cualquier mes, DEBEN conservarla y seguir
  contando en el resumen (decisión 14, principio 8).
- **RF-41** SI se intenta usar una categoría eliminada en un rubro nuevo, al
  cambiar la categoría de un rubro, en un gasto no planeado nuevo o al
  cambiar la categoría de un gasto, ENTONCES el sistema DEBE rechazarlo sin
  guardar nada e indicar que la categoría fue eliminada y cómo
  restaurarla.
- **RF-42** Un rubro con categoría eliminada DEBE seguir aceptando gastos de
  su mes y cambios de nombre y monto. Un gasto con categoría eliminada DEBE
  poder editarse sin cambiarle la categoría (decisión 17).
- **RF-43** CUANDO un miembro crea una categoría con un nombre equivalente,
  según la comparación de la 002 (decisión 22), al de una categoría
  eliminada del mismo espacio, el sistema DEBE restaurar esa categoría con su identificador y
  su nombre original, en lugar de crear otra, e indicar que se restauró
  (decisiones 16 y 21). Si el nombre es el de una categoría activa, se
  rechaza como hoy (RF-8 de la 002).
- **RF-44** SI la categoría de la ruta no existe, es de otro espacio o ya
  está eliminada, ENTONCES eliminarla DEBE responder `404` sin cambiar nada.

## Criterios de validación

La spec se da por cumplida cuando, además de los tests por requisito:

1. Un test crea en noviembre los rubros "Mercado" (Comida, 800.000) y
   "Arriendo" (Hogar, 1.500.000) y el ingreso "Salario" (5.000.000),
   registra gastos planeados y no planeados, y comprueba cada fila del
   resumen y cada total, incluidos un rubro excedido con lo que queda
   negativo y un mes con sin asignar negativo (RF-1, RF-10, RF-23, RF-24).
2. Un test comprueba que "mercado" choca con "Mercado" en el mismo mes y en
   el mismo espacio, y que se puede crear en otro mes y en otro espacio. Lo
   mismo con un ingreso (RF-3, RF-10).
3. Un test copia noviembre a diciembre y comprueba que diciembre tiene los
   mismos rubros e ingresos con los mismos montos, que noviembre y sus
   gastos no cambian, y que copiar otra vez a diciembre, o a enero desde un
   diciembre vacío, se rechaza sin crear nada (RF-13 a RF-16).
4. Un test comprueba que un gasto con rubro y categoría a la vez, o sin
   ninguno, se rechaza; que un gasto del 3 de noviembre no se liga a un
   rubro de octubre; y que cambiar la fecha de un gasto planeado a otro mes
   se rechaza (RF-17, RF-19).
5. Un test cambia la categoría de un rubro y comprueba que sus gastos pasan
   a esa categoría en el listado y en el resumen. Luego borra el rubro y
   comprueba que los gastos siguen ahí, no planeados y con la misma
   categoría, monto y fecha (RF-7, RF-8, RF-20).
6. Un test fija el reloj el 31 de octubre a las 20:00 en Bogotá (ya 1 de
   noviembre en UTC) y comprueba que un rubro, un ingreso y una copia sin
   periodo usan `2026-10`, y que la copia toma el plan de `2026-09` (RF-2,
   RF-13, principio 7).
7. Un test comprueba que un monto con decimales, negativo, cero, mayor que
   el máximo, como texto o como booleano se rechaza en rubros e ingresos
   sin guardar nada (RF-4, RF-10).
8. Un test arma una base con el esquema de la 007 sin migraciones, con
   presupuestos (uno con monto desde `2026-09`, otro que lo quita desde
   `2026-12`), gastos y las tablas de Telegram con filas. Arranca las
   migraciones y comprueba que hay un rubro en `2026-09` con el nombre, la
   categoría y el monto del presupuesto, ninguno en `2026-12`, que los
   gastos siguen iguales y no planeados, y que ya no existen la tabla de
   presupuestos ni las de Telegram (RF-32 a RF-35).
9. Un test arma una base de una spec anterior a la 004, sin la tabla de
   presupuestos, y comprueba que las migraciones la dejan al día
   (RF-32).
10. Un test aplica las migraciones a una base vacía y comprueba que el
    esquema coincide con el de los modelos. Otro las aplica dos veces y
    comprueba que la segunda no cambia nada (RF-36, RF-37).
11. Un test comprueba que `PUT /spaces/{id}/budgets/{category_id}` responde
    `404` (RF-27).
12. Tests de aislamiento: dos usuarios en espacios distintos no pueden
    crear, editar, borrar ni copiar rubros o ingresos del otro, ni eliminar
    sus categorías, todo
    responde `404` y nada de uno aparece en el resumen del otro; un rubro
    del espacio B no sirve para un gasto del espacio A aunque quien llama
    sea miembro de los dos; borrar un espacio borra sus rubros e ingresos y
    no los de otro, y salir de un espacio los conserva (RF-9, RF-12, RF-18,
    RF-28 a RF-30).
13. Un test crea "Mascotas" con un rubro en octubre y otro en noviembre, y
    un gasto no planeado en octubre. Elimina "Mascotas" en noviembre y
    comprueba que:
    - ya no sale en el listado de categorías;
    - el resumen de octubre no cambia, y en los de octubre y noviembre sale
      marcada como eliminada;
    - el rubro de noviembre sigue aceptando gastos;
    - un rubro nuevo o un gasto no planeado con "Mascotas" se rechazan;
    - copiar noviembre a diciembre omite su rubro y lo dice;
    - la respuesta de eliminar trae el aviso de que se puede volver a usar
      creándola de nuevo;
    - crear "mascotas" la restaura con el mismo identificador y el nombre
      "Mascotas", y desde entonces se copia y se usa de nuevo
    (RF-13, RF-39 a RF-43).
14. Un test comprueba que eliminar una categoría ya eliminada, de otro
    espacio o inexistente responde `404`, y que se pueden eliminar las
    predefinidas (RF-44, decisión 19).
15. Un test elimina "Acción" y comprueba que crear "accion", "Accion" o
    "ACCIÓN" la restaura como "Acción", y que "Ahorro" activa choca con
    "ahorro". Otro comprueba que "Año" y "Ano" conviven. Lo mismo con los
    nombres de rubros e ingresos de un mes (RF-3, RF-43, decisión 22).
16. `make test` y `make lint` pasan en verde.

## Requisitos para otras specs y documentos

- **009-tarjetas-y-cuotas:** una compra a 1 cuota cuenta en su rubro el mes
  de la compra; una a varias cuotas no se descuenta de su rubro (roadmap).
  Lo que esta spec llama "gasto planeado" es la base de esa regla.
- **010-app-web:** en el formulario de registro se escribe el rubro y salen
  como sugerencias los rubros del mes de la fecha, con lo presupuestado y
  lo que queda; la categoría sale del rubro. Si no estaba planeado, se
  elige "no planeado" y su categoría (RF-17, RF-19, decisión 13). Las
  sugerencias salen de los rubros del resumen: no hace falta otra ruta.
- **011-tablero-y-planear:** la pantalla de planear ofrece "Copiar del mes
  anterior" cuando el mes está vacío y muestra los rubros omitidos, avisa
  cuántos gastos quedan sin rubro al borrar uno (decisión 8) y muestra sin
  asignar y balance. Al eliminar una categoría, dice que sus rubros dejarán
  de copiarse y cómo restaurarla (decisión 20).
- **Fase 8 (Kubernetes):** con varias réplicas de la API, aplicar las
  migraciones al arrancar puede correrlas a la vez. Esa fase decide si pasan
  a un paso propio, por ejemplo un `Job` (decisión 11).
- **AGENTS.md:** el glosario define "Presupuesto" como monto por categoría
  y no tiene "rubro", "ingreso", "plan" ni "categoría eliminada". Hay que actualizarlo al cerrar
  la spec, con aprobación explícita (AGENTS.md no se modifica sin pedirlo).
