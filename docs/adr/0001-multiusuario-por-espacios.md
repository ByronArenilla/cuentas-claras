# ADR 0001 — Multiusuario mediante espacios compartidos

- Fecha: 2026-09-22
- Estado: aceptada
- Fase / spec: 1 / 001-usuarios-y-espacios (nueva)

## Contexto

La constitución fija en el principio 5 que budget-ops es de **un solo
usuario**, sin registro de cuentas ni multiusuario, y el principio 13
restringe el acceso a un único `chat_id` de Telegram más una web
autenticada. Toda la fase 1 del roadmap (specs 001 a 007) está escrita
bajo ese supuesto.

El producto necesita dos casos que ese supuesto impide:

1. **Presupuesto compartido**: varias personas (por ejemplo una pareja o
   un hogar) registran gastos contra el mismo presupuesto mensual y ven
   el mismo resumen.
2. **Usuarios independientes**: varias personas usan la misma instancia
   con presupuestos y gastos completamente separados, sin verse entre sí.

Restricciones que aplican:

- El principio 8 ("los datos no se pierden") encarece introducir esto
  más tarde: habría que migrar gastos ya registrados hacia un dueño.
- El principio 16 limita el gasto en la nube a 15 USD/mes, así que la
  solución no puede pasar por un proveedor de identidad de pago ni por
  una instancia desplegada por usuario.
- Hoy no hay código ni specs escritas (`services/` está vacío, ninguna
  spec creada), por lo que el costo del cambio es solo documental.

## Decisión

Se sustituye el principio 5 "Un solo usuario" por **multiusuario con
espacios compartidos**: se introducen tres conceptos de dominio —
`user` (persona que se autentica), `space` (ámbito que contiene el
presupuesto) y `membership` (la relación entre ambos) — y
**todo gasto, categoría y presupuesto pertenece a un espacio**, nunca
directamente a un usuario.

    user ──< membership >── space
                              ├── category
                              ├── budget  (space + category + period)
                              └── expense (space + user que lo registró)

La membresía todavía no distingue roles: todos los miembros de un
espacio son iguales. Los roles se añadirán solo cuando exista la
necesidad concreta de invitar a alguien con permisos limitados.

Con un solo modelo se cubren los dos casos: un espacio con varios
miembros es el presupuesto compartido; varios espacios de un miembro
cada uno son los usuarios independientes. El uso personal original
sigue siendo válido: es un espacio con un único miembro.

El multiusuario entra **desde el inicio de la fase 1**, en una spec
nueva anterior a la de gastos, para no migrar datos después.

## Alternativas descartadas

- **Seguir monousuario y desplegar una instancia por persona**: no
  resuelve el presupuesto compartido, y multiplica el costo de la nube
  y el trabajo de operación, contra el principio 16.
- **Usuarios independientes sin espacios** (cada gasto cuelga del
  usuario): más simple, pero deja fuera el caso del presupuesto
  compartido, que es la mitad de la necesidad.
- **Un único presupuesto global con gastos atribuidos al usuario**:
  cubre el caso compartido pero no permite presupuestos independientes
  en la misma instancia.
- **Introducirlo al final de la fase 1, junto con `007-control-acceso`**:
  obligaría a migrar gastos y presupuestos ya registrados hacia un
  espacio, riesgo innecesario cuando todavía no existe ningún dato.
- **Delegar la identidad en un proveedor externo** (Auth0, Cognito):
  añade una dependencia y un costo que la fase 1 no contempla y que el
  principio 2 prohíbe adelantar.

## Consecuencias

Lo que gana el proyecto:

- Cubre los dos casos de uso reales con un solo modelo de datos, sin
  bifurcar el producto.
- El aislamiento entre espacios es un ejercicio realista de
  *multi-tenancy*, que es exactamente el tipo de problema que aparece
  en cualquier sistema operado de verdad.

Lo que cuesta:

- **La autenticación deja de ser opcional y se adelanta.** Hoy el bot
  se protege con un `chat_id` fijo en `.env`; con varios usuarios el
  bot debe reconocer *quién* escribe, así que hace falta vincular cada
  `chat_id` a un usuario registrado (por ejemplo con un código de
  vinculación de un solo uso). `TELEGRAM_ALLOWED_CHAT_ID` desaparece.
- **Cada consulta de la API debe filtrar por espacio.** Un `SELECT` sin
  el filtro del espacio filtra datos de otro usuario; es el fallo de
  seguridad más común en aplicaciones multiusuario (OWASP lo clasifica
  como *Broken Access Control*:
  https://owasp.org/Top10/A01_2021-Broken_Access_Control/). La spec de
  gastos debe exigir tests que comprueben que un usuario no ve los
  datos de otro espacio.
- **Una spec más en la fase 1** y más superficie en las demás: todas
  las rutas de la API pasan a depender del usuario autenticado.
- Las contraseñas se guardan con un algoritmo de hash de contraseñas
  (no un hash genérico); la decisión concreta se toma en el plan de la
  spec de usuarios.

Lo que no cambia: los principios 6 (dinero exacto), 7 (fechas), 8
(los datos no se pierden), 9 a 11 (arquitectura) y 16 (costo) siguen
intactos. El costo en la nube no sube, porque siguen siendo los mismos
tres servicios y la misma base de datos.

## Cambios que se aplican si se acepta este ADR

1. `docs/constitution.md`, principio 5: reemplazar "Un solo usuario"
   por el principio de multiusuario por espacios descrito aquí.
2. `docs/constitution.md`, principio 13: sustituir "el bot solo atiende
   al `chat_id` autorizado" por "el bot solo atiende a chats vinculados
   a un usuario registrado, y toda respuesta se limita a los espacios
   de ese usuario".
3. `AGENTS.md`, sección Dominio: añadir `user`, `space` y `membership`,
   y anotar que gasto, categoría y presupuesto pertenecen a un espacio.
4. `docs/roadmap.md`, fase 1: insertar `001-usuarios-y-espacios` y
   renumerar las specs siguientes.
5. `.env.example`: retirar `TELEGRAM_ALLOWED_CHAT_ID`.

> Nota (2026-09-22): al clarificar la spec 001 se decidió que las sesiones
> se guardan en la base de datos y el token es opaco, no firmado. Por eso
> el punto 5 no añade ninguna llave de firma: `API_SECRET_KEY` se propuso
> y se descartó antes de existir.
