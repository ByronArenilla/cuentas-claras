# AGENTS.md — budget-ops

## Proyecto
budget-ops es una app personal para controlar el presupuesto mensual.
Registro cada gasto conversando con un bot de Telegram y consulto en un
dashboard web cuánto llevo gastado por categoría frente a lo presupuestado.

También es mi portafolio DevOps: la aplicación se mantiene pequeña a
propósito y la infraestructura crece por fases (Docker, Nginx, GitHub
Actions, AWS, Terraform, Ansible, Prometheus, Grafana, Kubernetes).

## Dónde está cada cosa
- `docs/constitution.md`: principios innegociables. Léelos siempre.
- `docs/roadmap.md`: fase actual, spec activa y specs planeadas. Es la
  fuente de verdad sobre en qué punto está el proyecto.
- `specs/NNN-nombre/`: `spec.md`, `plan.md` y `tasks.md` de cada spec.
- `docs/adr/`: decisiones técnicas.
- `services/api/`, `services/bot/`, `services/web/`: los tres servicios.
- Si una carpeta tiene su propio `AGENTS.md`, sus reglas se suman a estas
  para los archivos de esa carpeta.

## Dominio
- **Usuario** (`user`): persona que se autentica en la app.
- **Espacio** (`space`): ámbito que contiene el presupuesto y sus datos.
  Gasto, categoría y presupuesto pertenecen siempre a un espacio.
- **Membresía** (`membership`): vincula un usuario con un espacio. Un
  usuario puede pertenecer a varios espacios; hoy todos los miembros de un
  espacio tienen los mismos permisos.
- **Gasto** (`expense`): dinero que salió. Tiene monto, tipo de pago,
  categoría, fecha, descripción opcional y el usuario que lo registró.
- **Tipo de pago** (`payment_type`): `credit` o `debit`.
- **Categoría** (`category`): agrupa gastos (hogar, transporte, comida...).
- **Presupuesto** (`budget`): monto máximo por categoría para un periodo.
- **Periodo** (`period`): un mes calendario en la zona horaria configurada,
  con formato `YYYY-MM`.
- **Resumen** (`summary`): gastado vs. presupuestado por categoría en un
  periodo, dentro de un espacio.

Las reglas concretas de cada concepto están en las specs. Si una regla no
está escrita, pregunta en lugar de suponer.

## Stack de la aplicación
- api: Python 3.12, FastAPI, SQLAlchemy, pytest. Único servicio con acceso a
  la base de datos, que se configura con `DATABASE_URL`.
- bot: Python 3.12, python-telegram-bot, httpx. Solo habla con la API.
- web: HTML + JavaScript sin framework, Chart.js. Solo habla con la API.

## Comandos
Usa siempre el `Makefile` de la raíz. Los nombres de los targets no cambian
aunque cambie lo que hacen por dentro en cada fase:
- `make install`: instala dependencias de desarrollo.
- `make run-api`, `make run-bot`, `make run-web`: ejecutan cada servicio.
- `make test`: tests de todos los servicios.
- `make lint`: `ruff check` y `ruff format --check`.
- `make up` / `make down`: levantan y detienen el stack completo (desde la
  fase de contenedores).

Si un target todavía no existe, no lo inventes: indica que falta y en qué
spec debería crearse.

## Convenciones
- Type hints en todas las funciones públicas; `ruff` para lint y formato.
- Identificadores en inglés; mensajes al usuario, specs y docs en español.
- Tests de cada servicio en su carpeta `tests/`.
- Commits con Conventional Commits y número de spec:
  `feat(api): registrar gasto [001]`.
- Una rama por spec (`NNN-nombre`); se integra a `main` mediante PR.

## Flujo SDD
Cada spec pasa por: spec → clarificación → plan → tareas → implementación
→ validación.
- En las etapas de spec, clarificación, plan y tareas no escribas código.
- Implementa una sola tarea de `tasks.md` por vez: primero los tests, luego
  el código. Márcala como hecha y detente.
- Si al implementar descubres algo que la spec no cubre, detente y propón el
  cambio en la spec antes de seguir.

## Límites
- No modifiques `docs/constitution.md`, `AGENTS.md` ni ningún `spec.md` salvo
  petición explícita.
- No añadas dependencias, servicios ni herramientas que no estén en el plan
  de la spec activa.
- Nunca leas, muestres ni escribas valores reales de `.env`, tokens o
  credenciales. Trabaja con `.env.example`.
- Pide aprobación explícita antes de cualquier comando con efecto remoto,
  destructivo o con costo: `git push`, `docker push`, `terraform apply` o
  `destroy`, `ansible-playbook` contra servidores, `kubectl apply` o `delete`
  fuera de un clúster local, o borrar datos. Los comandos de solo lectura o
  validación (`terraform plan`, `kubectl get`) sí puedes ejecutarlos.

## Modo aprendizaje
Estoy aprendiendo DevOps con este proyecto. Por eso:
- Antes de crear o cambiar un archivo de infraestructura o configuración,
  explica en 3 a 5 líneas qué vas a hacer y por qué.
- Comenta los bloques no obvios de los archivos de infraestructura.
- Cuando aparezca un concepto nuevo, nómbralo y enlaza la documentación
  oficial.
- Si te pido algo que contradice la constitución o la fase actual, dímelo en
  lugar de hacerlo.
- Prefiere la solución simple y explicable a la "más profesional" si esta
  añade complejidad que todavía no necesito.

## Al terminar cualquier tarea
- Ejecuta `make test` y `make lint` y muestra el resultado.
- Marca la tarea en `tasks.md` e indica qué RF cubre.
- Si el cambio se verifica a mano (bot, web o infraestructura), explica cómo
  comprobarlo.