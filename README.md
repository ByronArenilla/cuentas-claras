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

## Registrar gastos mientras llega la web
Hasta la spec 010 no hay app web, así que los gastos se registran con la
API, de dos formas:

- **Con `curl`**, como en los ejemplos de este README: primero
  `POST /auth/login` para obtener el token y después
  `POST /spaces/{id}/expenses` (ver "Gastos").
- **Desde http://localhost:8000/docs**: inicia sesión con
  `POST /auth/login` en "Try it out", copia el `token`, pégalo en el botón
  **Authorize** y prueba cualquier ruta desde el navegador.

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
Cada gasto pertenece a una categoría, y cada espacio tiene las suyas.
Todo espacio nuevo nace con siete predefinidas: Hogar, Comida, Transporte,
Salud, Servicios, Ocio y Otros. Desde ese momento son del espacio, y
cualquier miembro puede añadir más.

**Listar.** Devuelve las categorías del espacio en orden de creación:
primero las predefinidas y después las nuevas.

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
mismo: si ya existe "Comida", crear "cómida" responde `409` con "Ya existe
la categoría «Comida» en este espacio.". La ñ sí cuenta, así que "Año" y
"Ano" pueden convivir. Otro espacio puede tener su propia "Comida". El
porqué de esta comparación está en el
[ADR 0006](docs/adr/0006-clave-normalizada-para-nombres-de-categoria.md).

## Gastos
Un gasto es dinero que ya salió. Tiene monto, tipo de pago (`credit` o
`debit`), categoría del espacio, fecha y una descripción opcional. Cualquier
miembro del espacio puede registrar, editar y borrar cualquier gasto, y cada
gasto recuerda quién lo registró (`created_by`).

- **Monto**: pesos enteros, sin decimales y sin moneda (`20000` son 20.000
  pesos). Debe ser mayor que cero y como máximo un billón. `20000.5` o
  `"20000"` se rechazan; nunca se redondean.
- **Fecha** (`spent_on`): un día `AAAA-MM-DD`, no posterior a hoy. Si no se
  envía, es hoy en la zona horaria `TZ`. Por qué es un día y no un instante:
  [ADR 0007](docs/adr/0007-fecha-del-gasto-como-dia-calendario.md).
- **Descripción**: hasta 200 caracteres. Vacía o solo con espacios cuenta
  como ausente.

**Registrar.** Responde `201` con el gasto. La categoría tiene que ser del
mismo espacio.

```sh
curl -X POST localhost:8000/spaces/1/expenses \
  -H 'Authorization: Bearer <token de Ana>' \
  -H 'content-type: application/json' \
  -d '{"amount": 20000, "payment_type": "debit", "category_id": 2, "description": "Mercado"}'
# {"id": 1, "amount": 20000, "payment_type": "debit", "category_id": 2,
#  "spent_on": "2026-11-04", "description": "Mercado", "created_by": 1,
#  "created_at": "2026-11-04T20:00:05Z"}
```

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
la deja como estaba.

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

## Presupuesto y resumen
Cada categoría puede tener un presupuesto: lo máximo que el espacio quiere
gastar en ella cada mes. **Un presupuesto rige desde el mes en que se fija
y en los siguientes, hasta que se cambie**: no hay que repetirlo cada mes, y
cambiarlo desde un mes no toca los anteriores. Por qué:
[ADR 0008](docs/adr/0008-presupuesto-vigente-desde-un-periodo.md).
Cualquier miembro del espacio puede fijarlo, cambiarlo o quitarlo.

- **Monto**: las mismas reglas que el monto de un gasto, de 1 a un billón
  de pesos enteros. No existe el presupuesto cero: para dejar una categoría
  sin presupuesto, se quita.
- **Periodo** (`period`): el mes `AAAA-MM` desde el que rige. Puede ser
  pasado, actual o futuro; si no se envía, es el mes actual en `TZ`.
  Cambiar un mes pasado cambia también los meses que lo heredan.

Por ahora el presupuesto solo se fija con la API; la web lo mostrará a
partir de la spec 010.

**Fijar.** `PUT` sobre la categoría (aquí la 2, Comida). Repetirlo con el
mismo mes reemplaza el monto.

```sh
curl -X PUT localhost:8000/spaces/1/budgets/2 \
  -H 'Authorization: Bearer <token de Ana>' \
  -H 'content-type: application/json' \
  -d '{"period": "2026-10", "amount": 400000}'
# {"category_id": 2, "period": "2026-10", "amount": 400000}
```

**Quitar.** `"amount": null` deja la categoría sin presupuesto desde ese mes
hasta que se fije otro. No pide confirmación porque no borra gastos.
`amount` es obligatorio: un cuerpo `{}` responde `422` y no quita nada.

```sh
curl -X PUT localhost:8000/spaces/1/budgets/2 \
  -H 'Authorization: Bearer <token de Ana>' \
  -H 'content-type: application/json' \
  -d '{"period": "2026-12", "amount": null}'
# {"category_id": 2, "period": "2026-12", "amount": null}
```

**Resumen.** Gastado frente a presupuestado de un mes, por defecto el actual
en `TZ`. Trae todas las categorías del espacio en orden de creación, aunque
no tengan presupuesto ni gastos, y los totales.

```sh
curl 'localhost:8000/spaces/1/summary?period=2026-11' \
  -H 'Authorization: Bearer <token de Ana>'
# {"period": "2026-11",
#  "categories": [
#    {"category_id": 1, "name": "Hogar", "budget": null, "spent": 0, "remaining": null},
#    {"category_id": 2, "name": "Comida", "budget": 400000, "spent": 20000, "remaining": 380000},
#    ...],
#  "total": {"budget": 400000, "spent": 20000, "remaining": 380000}}
```

- `budget: null`: la categoría no tiene presupuesto ese mes, así que
  tampoco hay `remaining`.
- `remaining` negativo: el presupuesto se excedió.
- `total.spent` suma todos los gastos del mes, también los de categorías
  sin presupuesto; `total.budget` suma solo los presupuestos que existen.

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
