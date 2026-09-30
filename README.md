# budget-ops

App para controlar el presupuesto mensual, en solitario o compartido con
otras personas: los gastos se registran conversando con un bot de Telegram y
se consultan en un dashboard web.

Es mi proyecto de portafolio DevOps. La aplicación es pequeña a propósito y
la infraestructura crece por fases: Docker, Nginx, GitHub Actions, AWS,
Terraform, Ansible, Prometheus, Grafana y Kubernetes.

Se desarrolla con **Spec-Driven Development (SDD)**: todo empieza por una spec.

## Estado
Fase actual y spec activa: ver [`docs/roadmap.md`](docs/roadmap.md).

## Puesta en marcha (API)
Requiere Python 3.12 y `make`.

```sh
make install          # crea services/api/.venv e instala dependencias
cp .env.example .env  # y rellena los valores
make run-api          # http://localhost:8000
make test             # tests
make lint             # ruff check y ruff format --check
```

Si falta `DATABASE_URL`, `TZ` o `WEB_BASE_URL`, la API no arranca y dice
cuál falta. La documentación interactiva de la API está en
http://localhost:8000/docs.

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
página `/unirse/...` de la web llegará con `007-dashboard-web`; hasta
entonces, `<invitación>` es la última parte de la `url` y el canje se hace
contra la API.

**Espacios.** `GET /spaces` lista los tuyos y `POST /spaces` crea uno.
`DELETE /spaces/{id}/members/me` te saca de un espacio. Si eres su único
miembro, `DELETE /spaces/{id}?confirm=<nombre exacto>` lo borra con todos sus
datos. Nadie puede quedarse sin ningún espacio.

## Documentos clave
- [`docs/constitution.md`](docs/constitution.md): principios innegociables.
- [`docs/roadmap.md`](docs/roadmap.md): fases y specs.
- [`docs/adr/`](docs/adr/): decisiones técnicas.
- [`AGENTS.md`](AGENTS.md): instrucciones para agentes de IA.
