# Spec 002 — Categorías

- Fase: 1 — Aplicación y SDD
- Estado: aprobada
- Base: spec 001 (RF-28 a RF-32, aislamiento entre espacios), ADR 0001

## Por qué

Todo gasto pertenece a una categoría, y el resumen mensual compara lo
gastado con lo presupuestado categoría por categoría. Por eso las
categorías van antes que los gastos (003) y que el presupuesto (004): cada
spec crea sus propias tablas y ninguna tiene que cambiar después una tabla
que ya esté en `main` (ADR 0004).

Esta spec cubre dos necesidades:

- Quien acaba de registrarse puede anotar su primer gasto sin configurar
  nada, porque su espacio ya trae categorías de uso común.
- Cada espacio adapta sus categorías a su realidad (por ejemplo,
  "Mascotas" o "Colegio") sin afectar a otros espacios.

## Qué entra

- Las categorías predefinidas, que se crean con cada espacio.
- Listar las categorías de un espacio.
- Crear categorías nuevas en un espacio.

## Qué NO entra

- Renombrar, borrar o archivar categorías. Borrar una categoría obliga a
  decidir qué pasa con sus gastos y presupuestos, que todavía no existen.
  Ninguna spec planeada lo cubre por ahora.
- Subcategorías, iconos, colores o emojis.
- Asignar una categoría a un gasto: spec 003.
- El presupuesto por categoría: spec 004.

## Conceptos

- **Categoría** (`category`): agrupa gastos de un espacio (hogar,
  transporte, comida...). Tiene un nombre y pertenece siempre a un espacio.
- **Categorías predefinidas**: la lista fija de categorías que el sistema
  crea en cada espacio nuevo (decisiones 1 y 2).

## Decisiones de clarificación (2026-10-01)

1. **Las categorías predefinidas son Hogar, Comida, Transporte, Salud,
   Servicios, Ocio y Otros**, en ese orden. Son pocas a propósito: cada
   espacio crea las que le falten, y una lista larga hace más lento elegir
   en el bot.
2. **Las predefinidas se copian en cada espacio al crearlo** y desde ese
   momento son categorías del espacio como cualquier otra. Así toda
   categoría tiene espacio (principio 5) y la consulta de categorías filtra
   por espacio sin excepciones. Se descartó tenerlas una sola vez para toda
   la instancia: la regla "nada se consulta sin filtrar por espacio"
   tendría una excepción, y renombrar una predefinida afectaría a todos los
   espacios a la vez.
3. **Los espacios que ya existen no se rellenan: se recrea la base de datos
   local de desarrollo**, como con el ADR 0005. No hay datos reales ni
   entornos desplegados, así que no se pierde nada que el principio 8
   proteja. Se descartó que la API añada las predefinidas al arrancar: sería
   código para siempre para un caso que hoy no existe en ningún entorno. La
   base de datos local se borra al implementar, cuando ya existan las
   categorías, y con aprobación previa.
4. **Dos nombres son el mismo si solo se diferencian en mayúsculas, tildes,
   diéresis o espacios alrededor**: "comida" y " Comida ", o "Educacion" y
   "Educación". La ñ es una letra propia y no equivale a la n: "Año" y
   "Ano" son distintos. El nombre se guarda tal como se escribió, solo sin
   los espacios alrededor.
5. **El nombre tiene entre 1 y 50 caracteres, no hay tope de categorías por
   espacio y la lista se devuelve en orden de creación**: primero las
   predefinidas, en el orden de la decisión 1, y después las nuevas. El
   orden alfabético con tildes no es trivial y el orden de creación es
   predecible.
6. **Cualquier miembro del espacio crea categorías**, porque hoy todos los
   miembros tienen los mismos permisos (ADR 0001).

## Requisitos funcionales

### Categorías predefinidas

- **RF-1** CUANDO se crea un espacio, sea el espacio personal al
  registrarse (RF-3 de la 001) o uno nuevo (RF-13 de la 001), el sistema
  DEBE crear en la misma operación las categorías predefinidas en ese
  espacio. O se crea todo o no se crea nada (decisión 1).
- **RF-2** El sistema DEBE guardar cada categoría predefinida como
  categoría del espacio en que se creó; NUNCA DEBE compartir una misma
  categoría entre dos espacios (decisión 2).
- **RF-3** CUANDO un usuario se une a un espacio con una invitación
  (RF-17 de la 001), el sistema NUNCA DEBE crear ni duplicar categorías en
  ese espacio.

### Listar

- **RF-4** CUANDO un miembro lista las categorías de un espacio, el sistema
  DEBE devolver todas las categorías de ese espacio y solo esas, en orden
  de creación, cada una con su identificador y su nombre (decisión 5).

### Crear

- **RF-5** CUANDO un miembro crea en un espacio una categoría con un nombre
  válido, el sistema DEBE crearla en ese espacio y devolverla con su
  identificador (decisión 6).
- **RF-6** El sistema DEBE guardar el nombre de la categoría sin espacios
  alrededor.
- **RF-7** SI el nombre queda vacío o supera la longitud máxima, ENTONCES
  el sistema DEBE rechazar la creación e indicar el límite (decisión 5).
- **RF-8** SI en el espacio ya existe una categoría con el mismo nombre,
  según la decisión 4, ENTONCES el sistema DEBE rechazar la creación sin
  crear nada, aunque lleguen dos peticiones iguales a la vez.
- **RF-9** El sistema DEBE permitir que dos espacios distintos tengan
  categorías con el mismo nombre: cada una pertenece a su espacio.

### Aislamiento y ciclo de vida

- **RF-10** Toda operación sobre categorías DEBE indicar el espacio y pasar
  por la comprobación de membresía de la spec 001 (RF-28, RF-29 de la 001).
  Si quien llama no es miembro del espacio, el sistema DEBE responder `404`
  sin crear nada (RF-30 de la 001). Una petición sin sesión válida recibe
  `401` y no modifica nada (RF-11 de la 001).
- **RF-11** CUANDO se borra un espacio, el sistema DEBE borrar sus
  categorías y NUNCA DEBE tocar las categorías de otros espacios (RF-23 y
  RF-27 de la 001).

## Criterios de validación

La spec se da por cumplida cuando, además de los tests por requisito:

1. Un test comprueba que, tras registrarse, el espacio personal ya tiene
   las categorías predefinidas, en su orden (RF-1, RF-4).
2. Un test crea dos espacios y comprueba que cada uno tiene sus propias
   categorías predefinidas, con identificadores distintos, y que una
   categoría creada en uno no aparece en el otro (RF-2, RF-4, RF-9).
3. Un test comprueba que unirse a un espacio por invitación no cambia sus
   categorías (RF-3).
4. Un test comprueba que dos miembros del mismo espacio ven la misma lista
   y que la categoría que crea uno la ve el otro (RF-4, RF-5).
5. Un test comprueba que crear "comida" o "Cómida" donde ya existe
   "Comida" se rechaza, que "Año" y "Ano" pueden convivir, y que en otro
   espacio sí se acepta "comida" (RF-8, RF-9).
6. Un test comprueba que un usuario que no es miembro recibe `404` al
   listar y al crear, y que no se crea nada (RF-10). Amplía el criterio 1
   de la spec 001.
7. Un test comprueba que borrar un espacio borra sus categorías y no toca
   las de otro espacio del mismo usuario (RF-11). Amplía el criterio 6 de
   la spec 001.
8. `make test` y `make lint` pasan en verde.

## Requisitos para otras specs

- `003-api-gastos` exige que la categoría de un gasto exista en el mismo
  espacio del gasto (su RF-5).
- `004-presupuesto-mensual` fija el presupuesto por categoría del espacio.
- `005-bot-registro-guiado` ofrece al usuario la lista de RF-4 para elegir
  la categoría.
- Renombrar y borrar categorías no tiene spec asignada. Antes de
  añadirlas, hay que decidir qué pasa con los gastos y presupuestos de una
  categoría borrada (principio 8).
