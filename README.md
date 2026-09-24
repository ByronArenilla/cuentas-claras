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

Si falta `DATABASE_URL` o `TZ`, la API no arranca y dice cuál falta. La
documentación interactiva de la API está en http://localhost:8000/docs.

## Usuarios, espacios e invitaciones
Los datos pertenecen a un **espacio**, no a una persona. Cada usuario tiene
un espacio "Personal" y puede crear otros o unirse a los de otras personas
para compartir presupuesto. Dos espacios nunca ven los datos del otro.

**Primer usuario.** Con la base de datos vacía, el registro no pide código:

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

**Invitar.** A partir del primer usuario el registro es cerrado: hace falta
un código de invitación, de un solo uso y válido durante 24 horas.

| Para… | Pide el código con | Y quien lo recibe… |
|---|---|---|
| Que alguien tenga su presupuesto independiente | `POST /invitations/instance` | se registra con `"invitation_code"` en el cuerpo |
| Compartir un espacio con alguien sin cuenta | `POST /spaces/{id}/invitations` | se registra con `"invitation_code"` y entra ya en el espacio |
| Compartir un espacio con alguien con cuenta | `POST /spaces/{id}/invitations` | lo canjea con `POST /invitations/{code}/redeem` |

**Espacios.** `GET /spaces` lista los tuyos y `POST /spaces` crea uno.
`DELETE /spaces/{id}/members/me` te saca de un espacio. Si eres su único
miembro, `DELETE /spaces/{id}?confirm=<nombre exacto>` lo borra con todos sus
datos. Nadie puede quedarse sin ningún espacio.

## Documentos clave
- [`docs/constitution.md`](docs/constitution.md): principios innegociables.
- [`docs/roadmap.md`](docs/roadmap.md): fases y specs.
- [`docs/adr/`](docs/adr/): decisiones técnicas.
- [`AGENTS.md`](AGENTS.md): instrucciones para agentes de IA.
