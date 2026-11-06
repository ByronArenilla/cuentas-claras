# gastito

App para controlar el presupuesto mensual, en solitario o compartido con
otras personas. El mes se planea en el computador y cada gasto se registra
desde el celular, en la misma app web: se fija en la pantalla de inicio desde
el navegador y se abre como una aplicación, sin descargar nada de una tienda.
La web llega con la spec 010; mientras tanto, todo se hace con la API (ver
"Registrar gastos mientras llega la web").

Es mi proyecto de portafolio DevOps. La aplicación es pequeña a propósito y
la infraestructura crece por fases: Docker, Nginx, GitHub Actions, AWS,
Terraform, Ansible, Prometheus, Grafana y Kubernetes.

Se desarrolla con **Spec-Driven Development (SDD)**: todo empieza por una spec.

## Estado
Fase actual y spec activa: ver [`docs/roadmap.md`](docs/roadmap.md).

## Puesta en marcha
Requiere Python 3.12 y `make`.

```sh
make install          # crea el entorno virtual de la API
cp .env.example .env  # y rellena los valores
make run-api          # http://localhost:8000
make test             # tests de la API
make lint             # ruff check y ruff format --check
```

Si falta `DATABASE_URL`, `TZ` o `WEB_BASE_URL`, la API no arranca y dice
cuál falta. La documentación interactiva de la API está en
http://localhost:8000/docs.

**Si tu `.env` es de antes de la spec 007**, puede tener `TELEGRAM_BOT_TOKEN`
y `BOT_API_KEY`. Ya no se usan y puedes borrarlas; si se quedan, la API
arranca igual y las ignora.

## Base de datos y migraciones
El esquema de la base de datos lo gestiona
[Alembic](https://alembic.sqlalchemy.org/) con **migraciones**: archivos
versionados en `services/api/app/migrations/versions/`, cada uno con un
cambio. La tabla `alembic_version` de la base dice cuál fue el último que se
aplicó. Por qué así:
[ADR 0011](docs/adr/0011-migraciones-con-alembic.md).

**Corren solas al arrancar.** `make run-api` aplica las que falten antes de
atender la primera petición. Si una falla, la API no arranca y el error dice
cuál fue. Una base creada antes de la spec 008, sin Alembic, se adopta sola:
la primera migración crea las tablas que le falten y borra las del bot de
Telegram.

**Antes de arrancar con la 008 por primera vez, copia tu base.** Las
migraciones no se deshacen, y la 008 convierte el presupuesto de la 004 en
rubros:

```sh
cp services/api/budget.db services/api/budget.db.antes-008
```

Para volver atrás: detén la API, restaura la copia y vuelve a la rama
anterior.

```sh
cp services/api/budget.db.antes-008 services/api/budget.db
```

**La spec 009 añade la migración `0004`**, que solo crea las tablas de
tarjetas, abonos y extractos y tres columnas nuevas en `expenses`: no cambia
ningún dato. Los gastos a crédito que ya tenías quedan sin tarjeta y siguen
contando el día del gasto. Igual conviene copiar la base antes
(`budget.db.antes-009`): en SQLite la migración copia la tabla de gastos.

**La spec 010 añade la migración `0005`**, que marca cada compra con tarjeta
como deuda o gasto del mes. Las que ya tenías quedan como deuda, así que
ningún resumen cambia. También copia la tabla de gastos en SQLite
(`budget.db.antes-010`). Mientras corre una migración, la API desactiva las
claves foráneas de SQLite (así lo pide el modo *batch* cuando otra tabla
apunta a la que se copia) y al final comprueba que ninguna quedó rota.

**Crear una migración nueva** (al cambiar un modelo), desde `services/api`:

```sh
set -a; . ../../.env; set +a
.venv/bin/alembic revision --autogenerate --rev-id 0005 -m "que cambia"
```

Revisa siempre el archivo generado: es un borrador. Si olvidas la
migración, el test `test_an_empty_database_ends_with_the_schema_of_the_models`
falla porque el esquema migrado ya no coincide con los modelos.

## Registrar gastos mientras llega la web
Hasta la spec 010 no hay app web, así que los gastos se registran con la
API, de dos formas:

- **Con `curl`**, como en los ejemplos de este README: primero
  `POST /auth/login` para obtener el token y después
  `POST /spaces/{id}/expenses` (ver "Gastos").
- **Desde http://localhost:8000/docs**: inicia sesión con
  `POST /auth/login` en "Try it out", copia el `access_token`, pégalo en el
  botón **Authorize** y prueba cualquier ruta desde el navegador.

## Usuarios, espacios e invitaciones
Los datos pertenecen a un **espacio**, no a una persona. Cada usuario tiene
un espacio "Personal" y puede crear otros o unirse a los de otras personas
para compartir presupuesto. Dos espacios nunca ven los datos del otro.

**Registrarse.** El registro es abierto: basta un correo y una contraseña de
al menos 12 caracteres. Crea el usuario y su espacio "Personal".

```sh
curl -X POST localhost:8000/auth/register -H 'content-type: application/json' \
  -d '{"email": "ana@example.com", "password": "al-menos-12-caracteres"}'
```

**Iniciar sesión.** Devuelve un token que dura 15 días y se envía en la
cabecera `Authorization: Bearer <token>` de cada petición. `POST /auth/logout`
lo invalida en el momento.

```sh
curl -X POST localhost:8000/auth/login -H 'content-type: application/json' \
  -d '{"email": "ana@example.com", "password": "al-menos-12-caracteres"}'
```

**Compartir un espacio.** Se hace con un enlace de un solo uso que caduca a
las 24 horas. Quien tiene el enlace puede unirse, así que conviene mandarlo
solo a quien se invita.

1. **Compartir.** Un miembro pide el enlace del espacio (su `id` sale de
   `GET /spaces`):

   ```sh
   curl -X POST localhost:8000/spaces/2/invitations \
     -H 'Authorization: Bearer <token de Ana>'
   # {"url": "http://localhost:8080/unirse/<invitación>", "expires_at": "..."}
   ```

2. **Consultar.** Cualquiera con el enlace ve a qué espacio lo invitan, sin
   sesión. Consultarlo no lo gasta ni une a nadie, así que las vistas
   previas de Telegram o WhatsApp no lo estropean:

   ```sh
   curl localhost:8000/invitations/<invitación>
   # {"space_name": "Casa", "expires_at": "..."}
   ```

3. **Canjear.** Quien recibe el enlace inicia sesión (o se registra primero
   si no tiene cuenta) y se une con una petición explícita:

   ```sh
   curl -X POST localhost:8000/invitations/<invitación>/redeem \
     -H 'Authorization: Bearer <token de Bea>'
   # {"id": 2, "name": "Casa"}
   ```

Un enlace desconocido, usado o caducado se rechaza con el mismo mensaje. La
página `/unirse/...` de la web llegará con `010-app-web`; hasta
entonces, `<invitación>` es la última parte de la `url` y el canje se hace
contra la API.

**Espacios.** `GET /spaces` lista los tuyos y `POST /spaces` crea uno.
`DELETE /spaces/{id}/members/me` te saca de un espacio. Si eres su único
miembro, `DELETE /spaces/{id}?confirm=<nombre exacto>` lo borra con todos sus
datos. Nadie puede quedarse sin ningún espacio.

## Categorías
Cada gasto y cada rubro pertenecen a una categoría, y cada espacio tiene
las suyas. Todo espacio nuevo nace con siete predefinidas: Hogar, Comida,
Transporte, Salud, Servicios, Ocio y Otros. Desde ese momento son del
espacio, no de un mes: cualquier miembro puede añadir más o eliminarlas, y
siguen disponibles mes tras mes.

**Listar.** Devuelve las categorías activas del espacio en orden de
creación: primero las predefinidas y después las nuevas. Las eliminadas no
salen.

```sh
curl localhost:8000/spaces/1/categories \
  -H 'Authorization: Bearer <token de Ana>'
# [{"id": 1, "name": "Hogar"}, {"id": 2, "name": "Comida"}, ...]
```

**Crear.** El nombre se guarda tal como se escribió, sin los espacios de
alrededor, y debe tener entre 1 y 50 caracteres.

```sh
curl -X POST localhost:8000/spaces/1/categories \
  -H 'Authorization: Bearer <token de Ana>' \
  -H 'content-type: application/json' -d '{"name": "Mascotas"}'
# {"id": 8, "name": "Mascotas"}
```

Dos nombres que solo se diferencian en mayúsculas, tildes o diéresis son el
mismo: "Ahorro" = "ahorro" y "Acción" = "accion". Si ya existe "Comida",
crear "cómida" responde `409` con "Ya existe la categoría «Comida» en este
espacio.". La ñ sí cuenta, así que "Año" y "Ano" pueden convivir. Otro
espacio puede tener su propia "Comida". La misma comparación vale para los
nombres de rubros e ingresos. El porqué está en el
[ADR 0006](docs/adr/0006-clave-normalizada-para-nombres-de-categoria.md).

**Eliminar.** No pide confirmación y no borra nada: la categoría deja de
salir como opción para rubros y gastos nuevos, pero los que ya la tenían, de
cualquier mes, la conservan y siguen contando en el resumen. Sus rubros
dejan de copiarse al planear. La respuesta lo explica:

```sh
curl -X DELETE localhost:8000/spaces/1/categories/8 \
  -H 'Authorization: Bearer <token de Ana>'
# {"id": 8, "name": "Mascotas", "message": "Eliminaste «Mascotas». Sus rubros
#  y gastos la conservan, pero sus rubros ya no se copiarán al planear. Para
#  volver a usarla, créala de nuevo con el mismo nombre."}
```

Usarla después en un rubro o un gasto no planeado responde `422` con "La
categoría «Mascotas» fue eliminada. Para usarla de nuevo, créala otra vez con
el mismo nombre.".

**Restaurar.** Crear una categoría con el nombre de una eliminada la
restaura con su `id`, su nombre original y su historia, y responde `200` en
lugar de `201`. Así "mascotas" devuelve `{"id": 8, "name": "Mascotas"}`.

## Gastos
Un gasto es dinero que ya salió. Tiene monto, tipo de pago (`credit` o
`debit`), fecha, una descripción opcional y, según si estaba planeado o no,
un rubro o una categoría. Esta sección trata los gastos a débito; un gasto a
crédito es una **compra con tarjeta**, que tiene sus propias reglas (ver
"Tarjetas y compras a cuotas"). Cualquier miembro del espacio puede registrar,
editar y borrar cualquier gasto, y cada gasto recuerda quién lo registró
(`created_by`).

- **Planeado** (`budget_item_id`): va en un rubro del plan de su mismo mes
  (ver "Plan del mes") y su categoría es la del rubro; no se escribe.
- **No planeado** (`category_id`): no tiene rubro y lleva su categoría.

Se envía uno de los dos, nunca los dos ni ninguno.

- **Monto**: pesos enteros, sin decimales y sin moneda (`20000` son 20.000
  pesos). Debe ser mayor que cero y como máximo un billón. `20000.5` o
  `"20000"` se rechazan; nunca se redondean.
- **Fecha** (`spent_on`): un día `AAAA-MM-DD`, no posterior a hoy. Si no se
  envía, es hoy en la zona horaria `TZ`. Por qué es un día y no un instante:
  [ADR 0007](docs/adr/0007-fecha-del-gasto-como-dia-calendario.md).
- **Descripción**: hasta 200 caracteres. Vacía o solo con espacios cuenta
  como ausente.

**Registrar.** Responde `201` con el gasto. El rubro o la categoría tienen
que ser del mismo espacio, y la categoría no puede estar eliminada. Un gasto
planeado en el rubro "Mercado" (el 1, de noviembre):

```sh
curl -X POST localhost:8000/spaces/1/expenses \
  -H 'Authorization: Bearer <token de Ana>' \
  -H 'content-type: application/json' \
  -d '{"amount": 412000, "payment_type": "debit", "budget_item_id": 1,
       "spent_on": "2026-11-03", "description": "Mercado de la semana"}'
# {"id": 1, "amount": 412000, "payment_type": "debit", "category_id": 2,
#  "spent_on": "2026-11-03", "description": "Mercado de la semana",
#  "created_by": 1, "created_at": "2026-11-05T22:30:33Z", "budget_item_id": 1}
```

Uno no planeado, en Transporte:

```sh
curl -X POST localhost:8000/spaces/1/expenses \
  -H 'Authorization: Bearer <token de Ana>' \
  -H 'content-type: application/json' \
  -d '{"amount": 38000, "payment_type": "debit", "category_id": 3}'
# {..., "category_id": 3, "budget_item_id": null, "card_id": null,
#  "installments": null, "first_due_period": null}
```

Un rubro de otro mes se rechaza: "El rubro «Mercado» es de 2026-10 y el
gasto es de 2026-11. Elige un rubro de 2026-11 o regístralo como no
planeado.".

**Listar por periodo.** Gastos de un mes `AAAA-MM`, del día más reciente al
más antiguo. Sin `period`, el mes actual en `TZ`.

```sh
curl 'localhost:8000/spaces/1/expenses?period=2026-10' \
  -H 'Authorization: Bearer <token de Ana>'
# [{"id": 2, "amount": 85000, "spent_on": "2026-10-28", ...}]
```

`GET /spaces/1/expenses/1` devuelve un solo gasto. Un gasto que no existe o
que es de otro espacio responde `404` "Gasto no encontrado.".

**Editar.** Solo cambia lo que se envía, con las mismas reglas que al
registrar. `"description": null` (o `""`) quita la descripción; no enviarla
la deja como estaba. Con el rubro:

- `"budget_item_id": 2` lo pasa a ese rubro, y a su categoría.
- `"budget_item_id": null` lo deja no planeado, con la categoría que tenía
  o con la que envíes en `category_id`.
- Cambiar solo la categoría de un gasto planeado se rechaza: primero hay que
  quitarle el rubro.
- Cambiar la fecha de un gasto planeado a otro mes se rechaza, salvo que
  envíes también un rubro de ese mes.

```sh
curl -X PATCH localhost:8000/spaces/1/expenses/1 \
  -H 'Authorization: Bearer <token de Ana>' \
  -H 'content-type: application/json' -d '{"amount": 18500}'
```

**Borrar.** Es definitivo, así que exige `confirm=true`. Sin la
confirmación responde `400` y no borra nada. La web preguntará antes de
enviarla.

```sh
curl -X DELETE 'localhost:8000/spaces/1/expenses/2?confirm=true' \
  -H 'Authorization: Bearer <token de Ana>'
# 204, sin cuerpo
```

**Últimos registrados.** Los últimos gastos registrados del espacio, de
cualquier mes, del registrado más recientemente al más antiguo. `limit` va
de 1 a 20 (5 por defecto) y `mine=true` deja solo los tuyos.

```sh
curl 'localhost:8000/spaces/1/expenses/recent?limit=5&mine=false' \
  -H 'Authorization: Bearer <token de Ana>'
```

## Plan del mes: rubros e ingresos
Cada mes tiene su **plan**: los **rubros**, que son lo que piensas gastar
("Mercado", "Arriendo"), y los **ingresos**, que son lo que esperas recibir
("Salario"). Un rubro tiene nombre libre, una categoría y un monto; un
ingreso, nombre y monto. Los dos son de un mes `AAAA-MM`, pasado, actual o
futuro, que no cambia. Por qué así:
[ADR 0012](docs/adr/0012-plan-mensual-con-rubros-e-ingresos.md).

- **Montos**: las mismas reglas que el monto de un gasto.
- **Nombres**: de 1 a 50 caracteres. Dos rubros (o dos ingresos) del mismo
  mes no pueden llamarse igual, con la comparación de las categorías:
  "mercado" choca con "Mercado". En otro mes, sí.
- Sin `period`, se usa el mes actual en `TZ`.
- Cualquier miembro del espacio puede crear, editar y borrar.

**Crear un rubro.**

```sh
curl -X POST localhost:8000/spaces/1/budget-items \
  -H 'Authorization: Bearer <token de Ana>' \
  -H 'content-type: application/json' \
  -d '{"period": "2026-11", "name": "Mercado", "category_id": 2, "amount": 800000}'
# {"id": 1, "period": "2026-11", "name": "Mercado", "category_id": 2, "amount": 800000}
```

**Crear un ingreso.**

```sh
curl -X POST localhost:8000/spaces/1/incomes \
  -H 'Authorization: Bearer <token de Ana>' \
  -H 'content-type: application/json' \
  -d '{"period": "2026-11", "name": "Salario", "amount": 5000000}'
# {"id": 1, "period": "2026-11", "name": "Salario", "amount": 5000000}
```

**Editar y borrar.** `PATCH /spaces/1/budget-items/1` cambia el nombre, la
categoría o el monto; `PATCH /spaces/1/incomes/1`, el nombre o el monto. El
mes no se cambia: para moverlo, se borra y se crea en el otro mes. Borrar
(`DELETE`) no pide confirmación.

- Si un rubro cambia de categoría, sus gastos cambian con él.
- Borrar un rubro **no borra sus gastos**: quedan no planeados, con la
  categoría que tenía el rubro.

**Copiar el plan del mes anterior.** Crea en el mes indicado los mismos
rubros e ingresos del mes inmediatamente anterior, con sus montos, y
responde con el resumen del mes nuevo. Solo funciona si el mes destino
todavía no tiene plan: nunca mezcla ni reemplaza. Los rubros de categorías
eliminadas no se copian y salen en `skipped`.

```sh
curl -X POST localhost:8000/spaces/1/plan/copy \
  -H 'Authorization: Bearer <token de Ana>' \
  -H 'content-type: application/json' -d '{"period": "2026-12"}'
# {"summary": {"period": "2026-12", ...}, "skipped": []}
```

Si diciembre ya tiene plan responde `409` "2026-12 ya tiene un plan; no se
copió nada."; si noviembre no tiene nada que copiar, `409` "2026-11 no tiene
un plan para copiar.".

**Resumen.** El mes frente a su plan, por defecto el actual en `TZ`. Pedirlo
nunca crea nada: un mes sin plan sale con listas vacías y montos en 0.

```sh
curl 'localhost:8000/spaces/1/summary?period=2026-11' \
  -H 'Authorization: Bearer <token de Ana>'
# {"period": "2026-11",
#  "incomes": [{"id": 1, "name": "Salario", "amount": 5000000}],
#  "budget_items": [
#    {"id": 1, "name": "Mercado", "category_id": 2,
#     "planned": 800000, "spent": 412000, "remaining": 388000},
#    {"id": 2, "name": "Arriendo", "category_id": 1,
#     "planned": 1500000, "spent": 1500000, "remaining": 0}],
#  "categories": [
#    {"category_id": 1, "name": "Hogar", "planned": 1500000, "spent": 1500000, "deleted": false},
#    {"category_id": 2, "name": "Comida", "planned": 800000, "spent": 412000, "deleted": false},
#    ...],
#  "debts": [],
#  "total": {"income": 5000000, "planned": 2300000, "debts": 0,
#            "spent_planned": 1912000, "spent_unplanned": 38000, "spent": 1950000,
#            "unassigned": 2700000, "balance": 3050000}}
```

- `remaining` de un rubro: planeado menos gastado; negativo si se excedió.
- `categories`: todas las activas, y las eliminadas solo si tienen rubros o
  gastos ese mes (`"deleted": true`). Su `spent` suma los gastos planeados y
  los no planeados.
- `debts`: lo que cobran las tarjetas ese mes (ver "Tarjetas y compras a
  cuotas"). `total.planned` y `total.spent` las incluyen, y `total.debts`
  las separa.
- `unassigned` (sin asignar): ingresos menos planeado. `balance`: ingresos
  menos todo lo gastado. Los dos pueden ser negativos.

**El presupuesto de la 004 ya no existe.** `PUT /spaces/{id}/budgets/...`
responde `404`. Al migrar, cada presupuesto guardado pasó a ser un rubro del
mes desde el que regía, con el nombre de su categoría, y los gastos que ya
había quedaron como no planeados.

## Tarjetas y compras a cuotas
Una compra con tarjeta es una de dos cosas:

- **Gasto del mes**: estaba en el plan del mes y la tarjeta es solo la forma
  de pago (el mercado). Cuenta el día de la compra, en su rubro o su
  categoría, como un débito.
- **Deuda**: se compró sin tener la plata. No cuenta el día de la compra:
  cuenta en los meses en que se paga la tarjeta, una cuota por mes, en la
  sección **Deudas** del resumen.

A varias cuotas, una compra siempre es deuda. A 1 cuota, tú dices si estaba
en el plan (`is_debt`); si no lo dices, es gasto del mes. Por qué así:
[ADR 0013](docs/adr/0013-compras-con-tarjeta-cuentan-al-pagar.md) y
[ADR 0014](docs/adr/0014-compras-del-mes-con-tarjeta.md).

**Tarjetas.** Una tarjeta tiene nombre, día de corte, día límite de pago y,
si la conoces, tasa de interés mensual en porcentaje (`1.89` es 1,89 %, con
hasta dos decimales). Los nombres se comparan como los de las categorías.

```sh
curl -X POST localhost:8000/spaces/1/cards \
  -H 'Authorization: Bearer <token de Ana>' \
  -H 'content-type: application/json' \
  -d '{"name": "Visa", "cutoff_day": 25, "due_day": 10, "monthly_rate": 1.9}'
# {"id": 1, "name": "Visa", "cutoff_day": 25, "due_day": 10,
#  "monthly_rate": 1.9, "deleted": false}
```

`GET /spaces/1/cards` lista las activas y `PATCH /spaces/1/cards/1` cambia
lo que envíes (`"monthly_rate": null` quita la tasa). Cambiar los días de
corte o de pago no mueve las compras ya registradas. `DELETE` la archiva:
deja de aceptar compras nuevas, pero sus cuotas siguen llegando a Deudas.
Crear de nuevo una tarjeta con el mismo nombre la restaura como era y
responde `200`.

**Registrar una compra con tarjeta.** Es un gasto a crédito con tarjeta
(`card_id`) y cuotas (de 1 a 48, por defecto 1). La API calcula el **mes de
pago** de la primera cuota: la compra entra en el primer corte en su fecha o
después, y se paga en el primer día límite después de ese corte.

- **Deuda**: **descripción obligatoria** y categoría; nunca rubro.
- **Gasto del mes**: un rubro de su mes o una categoría, como un débito; la
  descripción es opcional.

Una deuda a 6 cuotas:

```sh
curl -X POST localhost:8000/spaces/1/expenses \
  -H 'Authorization: Bearer <token de Ana>' \
  -H 'content-type: application/json' \
  -d '{"amount": 1200000, "payment_type": "credit", "card_id": 1,
       "installments": 6, "category_id": 1, "description": "Compra TV",
       "spent_on": "2026-11-05"}'
# {"id": 1, ..., "card_id": 1, "installments": 6, "is_debt": true,
#  "first_due_period": "2026-12"}
```

El mercado de noviembre pagado con la Visa, en el rubro "Mercado" (el 1):

```sh
curl -X POST localhost:8000/spaces/1/expenses \
  -H 'Authorization: Bearer <token de Ana>' \
  -H 'content-type: application/json' \
  -d '{"amount": 200000, "payment_type": "credit", "card_id": 1,
       "budget_item_id": 1, "spent_on": "2026-11-03"}'
# {"id": 2, ..., "category_id": 2, "budget_item_id": 1, "card_id": 1,
#  "installments": 1, "is_debt": false, "first_due_period": "2026-12"}
```

Unos zapatos a 1 cuota sin la plata en el plan llevan `"is_debt": true`,
`category_id` y `description`. Marcar como no deuda una compra a varias
cuotas se rechaza: "Una compra a varias cuotas siempre es deuda.".

Un gasto a crédito sin tarjeta se rechaza: "Un gasto a crédito necesita la
tarjeta con la que se pagó.". Los que ya existían antes de la 009 se quedan
sin tarjeta y cuentan el día del gasto.

**Plan de cuotas.** Capital fijo e interés sobre el saldo, como en los
extractos, con la tasa actual de la tarjeta. Una compra a 1 cuota no genera
intereses.

```sh
curl localhost:8000/spaces/1/expenses/1/installments \
  -H 'Authorization: Bearer <token de Ana>'
# {"expense_id": 1, "card_id": 1, "installments": [
#    {"number": 1, "count": 6, "period": "2026-12", "capital": 200000,
#     "interest": 22800, "amount": 222800, "balance_after": 1000000},
#    {"number": 2, "count": 6, "period": "2027-01", "capital": 200000,
#     "interest": 19000, "amount": 219000, "balance_after": 800000},
#    ...],
#  "prepayments": []}
```

**Simular antes de comprar.** `POST /spaces/1/cards/1/simulate` con
`amount`, `installments` y, si quieres, `spent_on` (por defecto hoy)
devuelve el mes de pago y las cuotas sin guardar nada.

**Valor real del extracto.** La estimación no será igual a lo que cobra el
banco (intereses por días, cuota de manejo). Cuando llega el extracto,
escribe su valor y reemplaza lo estimado de esa tarjeta en ese mes.
`DELETE` sobre la misma ruta lo quita y vuelve a la estimación.

```sh
curl -X PUT localhost:8000/spaces/1/cards/1/statements/2026-12 \
  -H 'Authorization: Bearer <token de Ana>' \
  -H 'content-type: application/json' -d '{"amount": 431500}'
# {"card_id": 1, "period": "2026-12", "amount": 431500}
```

**Abonar.** Un pago extra a una compra en un mes, además de su cuota. Eliges
si baja el plazo (`"reduces": "term"`, menos cuotas) o la cuota
(`"installment"`, cuotas más bajas). Un abono por todo el saldo cancela la
compra. Va en un mes con cuota y saldo después de ella, uno por mes y
siempre posterior al último abono de la compra.

```sh
curl -X POST localhost:8000/spaces/1/expenses/1/prepayments \
  -H 'Authorization: Bearer <token de Ana>' \
  -H 'content-type: application/json' \
  -d '{"amount": 400000, "period": "2026-12", "reduces": "term"}'
# {"prepayment": {"id": 1, "expense_id": 1, "period": "2026-12",
#                 "amount": 400000, "reduces": "term"},
#  "schedule": {... 4 cuotas, de 2026-12 a 2027-03 ...}}
```

Borrar un abono exige `confirm=true`, como un gasto:
`DELETE /spaces/1/expenses/1/prepayments/1?confirm=true`. Una compra con
abonos solo deja cambiar su descripción y su categoría, y no se borra hasta
borrar sus abonos.

**Pagar todo.** Paga en un mes el total de la tarjeta: salda con un abono
cada compra que ya está en el extracto de ese mes. Las compras hechas
después del corte no están en ese extracto y siguen llegando en su mes. Un
gasto del mes no tiene saldo que saldar. Con el extracto de diciembre en
581.500, `debt` es la deuda del mes con el abono nuevo:

```sh
curl -X POST localhost:8000/spaces/1/cards/1/payoff \
  -H 'Authorization: Bearer <token de Ana>' \
  -H 'content-type: application/json' -d '{"period": "2026-12"}'
# {"period": "2026-12",
#  "prepayments": [{"id": 1, "expense_id": 1, "period": "2026-12",
#                   "amount": 1000000, "reduces": "term"}],
#  "debt": 1381500}
```

**Deudas en el resumen.** Cada tarjeta con algo en el mes trae:

- `installments`: las cuotas de sus deudas;
- `month_expenses`: los gastos del mes que se pagan con ella ese mes (ya
  contaron en su mes);
- `prepayments`: los abonos;
- `estimated`, y `statement` (el valor real o `null`);
- `amount`: la **deuda** del mes. Es lo estimado o, con valor real, ese
  valor menos los gastos del mes (nunca menos de 0); más los abonos;
- `to_pay`: lo que hay que **pagarle** a la tarjeta. Es el valor real o
  cuotas más gastos del mes; más los abonos.

Solo la deuda suma en `planned` y `spent`; `total.cards_to_pay` suma lo que
hay que pagar a todas las tarjetas. Con la "Compra TV", el "Mercado" del
mes y los "Zapatos" como deuda:

```sh
curl 'localhost:8000/spaces/1/summary?period=2026-12' \
  -H 'Authorization: Bearer <token de Ana>'
# {...,
#  "debts": [{"card_id": 1, "name": "Visa", "deleted": false,
#    "installments": [
#      {"expense_id": 1, "name": "Compra TV", "number": 1, "count": 6,
#       "capital": 200000, "interest": 22800, "amount": 222800},
#      {"expense_id": 3, "name": "Zapatos", "number": 1, "count": 1,
#       "capital": 150000, "interest": 0, "amount": 150000}],
#    "prepayments": [], "estimated": 372800, "statement": null,
#    "amount": 372800,
#    "month_expenses": [{"expense_id": 2, "name": "Mercado", "amount": 200000}],
#    "to_pay": 572800}],
#  "total": {..., "planned": 372800, "debts": 372800, "cards_to_pay": 572800,
#            "spent": 372800, ...}}
```

Con el extracto de diciembre en 581.500, la deuda es 381.500 y a pagar
581.500: los 200.000 del mercado ya contaron en noviembre.

**Estado de la tarjeta.** `GET /spaces/1/cards/1/status` da el saldo
pendiente, las compras con cuotas del mes actual en adelante y la deuda de
cada mes hasta la última cuota.

## Historia: el bot de Telegram
Las specs 005 y 006 registraban gastos conversando con un bot de Telegram.
Se retiró en la spec 007: los gastos se registran solo desde la app web,
que en el celular se fija en la pantalla de inicio. El porqué está en el
[ADR 0010](docs/adr/0010-registro-solo-desde-la-app-web.md). Las tablas
`telegram_link_codes` y `telegram_chats` que tengan las bases creadas antes
siguen ahí sin uso; las borra la primera migración de la spec 008.

## Documentos clave
- [`docs/constitution.md`](docs/constitution.md): principios innegociables.
- [`docs/roadmap.md`](docs/roadmap.md): fases y specs.
- [`docs/adr/`](docs/adr/): decisiones técnicas.
- [`AGENTS.md`](AGENTS.md): instrucciones para agentes de IA.
