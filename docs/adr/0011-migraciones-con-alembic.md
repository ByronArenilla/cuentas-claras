# ADR 0011 — Migraciones con Alembic al arrancar la API

- Fecha: 2026-11-05
- Estado: aceptada
- Fase / spec: 1 / 008-rubros-e-ingresos
- Reemplaza a: ADR 0004

## Contexto

El ADR 0004 dejó el esquema en manos de `create_all` con una condición de
reemplazo: la primera spec que cambie una tabla que ya está en `main` trae
[Alembic](https://alembic.sqlalchemy.org/). La 008 la cumple:

- añade `budget_item_id` a `expenses` y `deleted_at` a `categories`;
- convierte la tabla `budgets` de la 004 en rubros y la borra;
- borra las tablas de Telegram que dejó la 007 (decisión 1 de la 007).

Restricciones:

- Las bases locales se crearon con `create_all` en distintas specs. Una de
  la 003 no tiene `budgets`; una que viene de la 005 tiene las tablas del
  bot. Ninguna tiene `alembic_version`.
- Principio 8: ningún cambio de estructura destruye datos.
- Principio 14: nada de pasos manuales sin documentar.
- Los tests crean ~480 bases nuevas; tienen que seguir siendo rápidos.

## Decisión

1. **Alembic gestiona el esquema y la API aplica las migraciones pendientes
   al arrancar** (`run_migrations` en el `lifespan`), una por una y cada
   una en su transacción. Si una falla, la API no arranca y el error dice
   cuál.
2. **La migración `0001` es idempotente**: crea cada tabla del esquema de la
   007 solo si falta, y borra las tablas de Telegram si existen. Así adopta
   cualquier base, vacía o creada con `create_all` en cualquier spec, sin
   `alembic stamp`.
3. **Las migraciones no tienen `downgrade`.** La vuelta atrás es restaurar
   la copia de la base que el README pide hacer antes de actualizar.
4. **Los cambios de esquema siguen el patrón expandir y contraer**
   ([*parallel change*](https://martinfowler.com/bliki/ParallelChange.html)):
   una migración que solo añade (`0002`), el código que lo usa, y otra que
   convierte y borra (`0003`).
5. **Los tests siguen creando sus bases con `Base.metadata.create_all`.** Un
   test aplica las migraciones a una base vacía y comprueba con
   [`compare_metadata`](https://alembic.sqlalchemy.org/en/latest/api/autogenerate.html#alembic.autogenerate.compare_metadata)
   que el esquema coincide con el de los modelos.
6. En SQLite, `env.py` usa el
   [modo *batch*](https://alembic.sqlalchemy.org/en/latest/batch.html),
   porque `ALTER TABLE` no puede añadir claves foráneas.

## Alternativas descartadas

- **`alembic stamp` sobre una migración inicial**, como proponía el ADR
  0004: solo sirve si la base coincide exactamente con la migración, y las
  bases locales no coinciden entre sí. Además obliga a detectar el caso y
  marcar la base a mano.
- **Un target `make migrate` aparte**: es un paso que hay que acordarse de
  correr antes de arrancar. Con la API migrando sola, la base y el código
  nunca quedan desalineados.
- **Migrar en cada test**: cada test tardaría bastante más. `compare_metadata`
  cubre el mismo riesgo con un solo test.
- **Escribir `downgrade`**: la `0003` convierte datos y no se puede deshacer
  sin perder información; un `downgrade` que nadie prueba da una falsa
  seguridad.

## Consecuencias

- Cambiar un modelo ahora exige una migración. Si se olvida, el test de
  `compare_metadata` falla: el riesgo que el ADR 0004 dejaba sin vigilar ya
  tiene un test.
- **En SQLite una migración que falla a la mitad puede dejar la base a
  medias**: el driver no abre transacción antes de un `CREATE` o un `DROP`.
  Lo cubren la copia previa y los tests de cada migración. En PostgreSQL
  (desde la fase 2) el DDL es transaccional.
- `compare_metadata` no compara restricciones `CHECK`. Las que copia el modo
  *batch* tienen su propio test.
- Con varias réplicas de la API (fase 8), migrar al arrancar puede correr
  la misma migración a la vez. Esa fase decide si pasa a un paso propio,
  como un `Job` de Kubernetes.
- Qué aprendí: una migración inicial idempotente adopta bases que llegaron
  por caminos distintos, y expandir y contraer permite cambiar el esquema
  sin romper la aplicación en ningún paso.
