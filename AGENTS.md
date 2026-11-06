# AGENTS.md — gastito

## Proyecto
gastito es una app personal para controlar el presupuesto mensual.
Planeo el mes en el computador y registro cada gasto desde el celular, en
la misma app web: la fijo en la pantalla de inicio desde el navegador y se
abre como una aplicación, sin descargar nada de una tienda. Ahí mismo
consulto cuánto llevo gastado frente a lo presupuestado.

También es mi portafolio DevOps: la aplicación se mantiene pequeña a
propósito y la infraestructura crece por fases (Docker, Nginx, GitHub
Actions, AWS, Terraform, Ansible, Prometheus, Grafana, Kubernetes).

## Dónde está cada cosa
- `docs/constitution.md`: principios innegociables. Léelos siempre.
- `docs/roadmap.md`: fase actual, spec activa y specs planeadas. Es la
  fuente de verdad sobre en qué punto está el proyecto.
- `specs/NNN-nombre/`: `spec.md`, `plan.md` y `tasks.md` de cada spec.
- `docs/adr/`: decisiones técnicas.
- `services/api/`, `services/web/`: los dos servicios.
- Si una carpeta tiene su propio `AGENTS.md`, sus reglas se suman a estas
  para los archivos de esa carpeta.

## Dominio
- **Usuario** (`user`): persona que se autentica en la app.
- **Espacio** (`space`): ámbito que contiene el presupuesto y sus datos.
  Gasto, categoría, rubro e ingreso pertenecen siempre a un espacio.
- **Membresía** (`membership`): vincula un usuario con un espacio. Un
  usuario puede pertenecer a varios espacios; hoy todos los miembros de un
  espacio tienen los mismos permisos.
- **Gasto** (`expense`): dinero que salió. Tiene monto, tipo de pago, fecha,
  descripción opcional y el usuario que lo registró. Si estaba planeado, va
  en un rubro de su mes y usa su categoría; si no, lleva su propia
  categoría. Un gasto a crédito es una compra con tarjeta.
- **Tipo de pago** (`payment_type`): `credit` o `debit`.
- **Tarjeta** (`card`): tarjeta de crédito del espacio, con día de corte, día
  límite de pago y tasa mensual opcional. Eliminarla la archiva, y crearla
  de nuevo la restaura.
- **Compra con tarjeta**: gasto a crédito con tarjeta y cuotas. Es deuda o
  gasto del mes (`is_debt`).
- **Gasto del mes con tarjeta**: compra a 1 cuota que estaba en el plan del
  mes. Cuenta el mes de la compra, en su rubro o su categoría, como un
  débito.
- **Cuota** (`installment`): la parte de una compra que se paga en un mes,
  con capital fijo e interés estimado sobre el saldo.
- **Abono** (`prepayment`): pago extra a una compra en un mes, que baja la
  cuota o el plazo. "Pagar todo" salda con abonos las compras del extracto.
- **Valor del extracto** (`card_statement`): lo que de verdad cobra una
  tarjeta en un mes; reemplaza la estimación.
- **Deuda** (`debt`): compra a varias cuotas, o a 1 cuota que no estaba en
  el plan; lleva descripción y categoría, sin rubro. Sus cuotas llegan a
  Deudas en los meses de pago. La deuda del mes de una tarjeta es lo
  estimado, o el extracto menos los gastos del mes, más los abonos.
- **A pagar**: lo que se le paga a una tarjeta en un mes: los gastos del
  mes más la deuda.
- **Categoría** (`category`): agrupa rubros y gastos (hogar, transporte,
  comida...). Eliminarla la archiva: lo que ya la tenía la conserva, y
  crearla de nuevo la restaura.
- **Rubro** (`budget_item`): línea del plan de un mes: nombre libre,
  categoría y monto planeado.
- **Ingreso** (`income`): dinero que se espera recibir en un mes: nombre y
  monto.
- **Plan** (`plan`): rubros e ingresos de un periodo; se copia del mes
  anterior con una acción explícita.
- **Periodo** (`period`): un mes calendario en la zona horaria configurada,
  con formato `YYYY-MM`.
- **Resumen** (`summary`): ingresos, planeado vs. gastado por rubro y por
  categoría, deudas de las tarjetas y lo que hay que pagarles, sin asignar y
  balance de un periodo, dentro de un espacio.

Las reglas concretas de cada concepto están en las specs. Si una regla no
está escrita, pregunta en lugar de suponer.

## Stack de la aplicación
- api: Python 3.12, FastAPI, SQLAlchemy, pytest. Único servicio con acceso a
  la base de datos, que se configura con `DATABASE_URL`.
- web: HTML + JavaScript sin framework; se fija en la pantalla de inicio
  como una app web. Solo habla con la API. El bot de Telegram se retiró
  (ADR 0010).

## Comandos
Usa siempre el `Makefile` de la raíz. Los nombres de los targets no cambian
aunque cambie lo que hacen por dentro en cada fase:
- `make install`: instala dependencias de desarrollo.
- `make run-api`, `make run-web`: ejecutan cada servicio.
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
- Commits y PR van solo a mi nombre: sin `Co-Authored-By` ni ninguna otra
  atribución a un agente de IA. En Claude Code lo aplica
  `.claude/settings.json`.
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
- Si el cambio se verifica a mano (web o infraestructura), explica cómo
  comprobarlo.