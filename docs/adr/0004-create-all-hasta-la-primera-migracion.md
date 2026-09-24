# ADR 0004 — `create_all` hasta la primera migración

- Fecha: 2026-09-24
- Estado: aceptada
- Fase / spec: 1 / 001-usuarios-y-espacios

## Contexto

La spec 001 crea las primeras tablas: `users`, `spaces`, `memberships`,
`invitations` y `sessions`. Hay que decidir cómo se crea y cómo evolucionará
el esquema de la base de datos.

- Todavía no hay datos reales: la app no se ha usado.
- Por ahora las specs de la fase 1 solo **añaden** tablas (gastos,
  categorías, presupuestos); ninguna cambia una tabla que ya exista.
- El principio 2 prohíbe adelantar herramientas "por si acaso".
- El principio 8 exige que ningún cambio de estructura destruya datos.

## Decisión

La API ejecuta
[`Base.metadata.create_all`](https://docs.sqlalchemy.org/en/20/core/metadata.html#sqlalchemy.schema.MetaData.create_all)
al arrancar. Crea las tablas que falten y **nunca modifica** las que ya
existen.

**Condición de reemplazo**: la primera spec que necesite alterar una tabla
existente (añadir o renombrar una columna, cambiar un tipo o una
restricción) introduce [Alembic](https://alembic.sqlalchemy.org/) con un ADR
nuevo que reemplace a este. Esa spec debe incluir en su plan la migración y
la forma de adoptar la base de datos existente sin recrearla (`alembic stamp`
sobre una migración inicial que coincida con el esquema actual).

## Alternativas descartadas

- **Alembic desde el primer día**: es la opción "profesional", pero hoy solo
  generaría una migración inicial equivalente a `create_all`. Añade una
  herramienta, su configuración y una carpeta de migraciones sin que ninguna
  migración real lo justifique todavía. Entrará cuando haga falta, y
  entonces se entenderá mejor por qué existe.
- **Scripts SQL a mano**: no son reproducibles ni verificables (principio 14)
  y duplican lo que ya describen los modelos de SQLAlchemy.
- **Borrar y recrear la base de datos en cada cambio**: viola el principio 8
  en cuanto haya un solo gasto real.

## Consecuencias

- Cero configuración de migraciones durante las specs que solo añaden
  tablas.
- **Riesgo que hay que vigilar**: si alguien cambia un modelo existente,
  `create_all` no avisa. La base de datos local se queda con el esquema
  viejo y el fallo aparece en tiempo de ejecución. Los tests **no** lo
  detectan, porque cada test crea una base de datos nueva desde los modelos.
  Por eso la condición de reemplazo es parte de la decisión, no una nota al
  margen: tocar un modelo existente obliga a traer Alembic en esa misma spec.
- Qué aprendí: posponer una herramienta es una decisión legítima si queda
  escrito cuándo deja de serlo.
