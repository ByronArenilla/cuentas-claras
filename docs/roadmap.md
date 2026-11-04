# Roadmap — gastito

> **Fase actual:** 1 — Aplicación y SDD
> **Spec activa:** 007-dashboard-web
>
> Este es el único lugar donde se actualiza el estado del proyecto.

Cada fase introduce una herramienta. Una spec empieza cuando la anterior
está validada. Marca con [x] las specs terminadas.

## Fase 1 — Aplicación y SDD
- [x] 001-usuarios-y-espacios — Usuarios, espacios y membresías; todo dato cuelga de un espacio.
- [x] 002-categorias — Categorías predefinidas y creación de nuevas.
- [x] 003-api-gastos — Registrar, listar, editar y borrar gastos.
- [x] 004-presupuesto-mensual — Presupuesto por categoría y mes; resumen gastado vs. presupuestado.
- [x] 005-bot-registro-guiado — Vinculación del chat y registro conversacional en Telegram con confirmación.
- [x] 006-bot-consultas — Comandos /resumen, /ultimos y /deshacer.
- [ ] 007-dashboard-web — Vista del mes: total, por categoría, presupuesto vs. real.
  - **Incluye fijar, cambiar y quitar el presupuesto** de cada categoría desde
    la vista del mes. Al guardar, la pantalla dice que rige "desde este mes en
    adelante" (spec 004, decisión 1; ADR 0008). Hoy solo se fija con la API.
  - **Prototipo visual antes de escribir código.** En la clarificación se
    hace un prototipo navegable con datos de ejemplo para acordar estética,
    colores, tipografía y flujos. Es desechable: no entra al repositorio ni
    cuenta como código de la app, y la spec se escribe a partir de él.
  - **Decisiones de diseño escritas en la spec**, en una sección propia:
    pensada primero para el celular; colores, tipografía y espacios como
    variables CSS; montos en pesos colombianos con `Intl.NumberFormat`
    (`$ 1.240.000`); estados de vacío, carga y error; contraste suficiente
    y uso completo con teclado.
  - **Framework: se evaluó y se mantiene la web sin framework (2026-11-04).**
    Que la web quede bonita depende del diseño (tipografía, espacios, color,
    jerarquía), no de React o Vue. Con cuatro pantallas no hay estado que
    justifique un framework, y uno con librería de componentes añadiría Node,
    `npm` y un paso de compilación que arrastran Docker, CI e imágenes
    (principio 2). La opción es CSS propio con variables y módulos de
    JavaScript nativos. Si el estado
    de la edición en línea se complica, la clarificación puede evaluar una
    librería pequeña sin compilación (por ejemplo Alpine.js) con su ADR.
    También se revisa si Chart.js hace falta: unas barras de progreso en CSS
    son más ligeras y minimalistas que un gráfico.
- [ ] 008-control-acceso — Sesión en la web.
  - La vinculación del `chat_id` a un usuario se adelantó a la 005 (ADR
    0009). Falta mostrar en la web el código de vinculación y, si hace
    falta, la lista de chats vinculados para quitarlos.

## Fase 2 — Docker
- [ ] 009-contenedores

## Fase 3 — Nginx
- [ ] 010-reverse-proxy
  - Límite de peticiones (*rate limiting*) en `POST /auth/register` y
    `POST /auth/login`: con el registro abierto, frena la creación masiva de
    cuentas, la prueba de contraseñas y el recorrido de correos (ADR 0005).
  - Enmascarar en los logs de acceso el token de invitación de
    `/invitations/<token>` y `/unirse/<token>`: quien lea los logs no debe
    poder canjear un enlace todavía sin usar (plan 001).

## Fase 4 — GitHub Actions
- [ ] 011-integracion-continua
- [ ] 012-publicacion-imagenes

## Fase 5 — AWS + Terraform
- [ ] 013-cuenta-aws-segura
- [ ] 014-infraestructura-aws

## Fase 6 — Ansible + despliegue continuo
- [ ] 015-configuracion-servidores
- [ ] 016-despliegue-continuo

## Fase 7 — Prometheus + Grafana
- [ ] 017-metricas
- [ ] 018-dashboards
- [ ] 019-alertas

## Fase 8 — Kubernetes
- [ ] 020-kubernetes-local
- [ ] 021-kubernetes-k3s
- [ ] 022-helm

## Fase 9 — Extras
- [ ] 023-backups
- [ ] 024-https-dominio
- [ ] 025-gitops
- [ ] 026-bot-lenguaje-natural
- [ ] 027-whatsapp
