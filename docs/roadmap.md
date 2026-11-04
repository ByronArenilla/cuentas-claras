# Roadmap — gastito

> **Fase actual:** 1 — Aplicación y SDD
> **Spec activa:** 007-retirar-bot
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
  - Las specs 005 y 006 quedan como historia: el bot se retira en la 007
    (ADR 0010).
- [ ] 007-retirar-bot — Quitar el bot de Telegram; el registro pasa a la app web.
  - Sale `services/bot/` y, de la API, las rutas `/telegram/*` y
    `BOT_API_KEY`. Se queda `GET /spaces/{space_id}/expenses/recent`, que
    también usa la web.
- [ ] 008-partidas-e-ingresos — Partidas con nombre libre y categoría, ingresos del mes y plan copiado del mes anterior.
  - Cambia el presupuesto por categoría con vigencia de la 004 (ADR 0008) y
    da a cada gasto una partida o la marca de "no planeado".
  - Cambia tablas que ya están en `main`, así que **entran las migraciones
    con Alembic** con un ADR que reemplaza al 0004 y otro que reemplaza al
    0008. La primera migración decide qué pasa con las tablas de Telegram
    que dejan las bases ya creadas (spec 007).
- [ ] 009-tarjetas-y-cuotas — Tarjetas con corte, pago y tasa; compras a cuotas y la deuda que llega cada mes.
  - Una compra a 1 cuota cuenta en su partida el mes de la compra. Una a
    varias cuotas no se descuenta de su partida: cada cuota entra en Deudas
    el mes en que se paga. El mes del pago sale del día de corte.
  - Los intereses son una estimación con la tasa mensual de la tarjeta, que
    es opcional. Al planear se escribe el valor real del extracto.
  - Fuera: abonar o cancelar antes de tiempo una compra a cuotas.
- [ ] 010-app-web — Entrar y registrarse, registrar gastos desde el celular, fijarla en la pantalla de inicio y diseño responsive.
  - **Se fija desde el navegador, no se instala ni se descarga.** En el
    celular se usa "Añadir a pantalla de inicio" (Safari en iPhone, Chrome
    en Android) y la app enseña esos pasos; en el computador se fija desde
    Chrome o Edge. Con un manifiesto web y sus íconos, el acceso directo se
    abre a pantalla completa, sin la barra del navegador. Se descartó
    publicarla en Play Store o App Store (ADR 0010).
  - No se registran gastos sin conexión: sin internet, la app lo avisa. El
    plan decide si hace falta un *service worker* para ese aviso.
  - Diseño responsive con una sola app: navegación abajo en el celular,
    menú lateral desde 1024 px, y botones de al menos 44 px.
  - Absorbe la antigua 008-control-acceso (sesión en la web).
- [ ] 011-tablero-y-planear — Tablero del mes, planear el mes y tarjetas, con gráficos para decidir.
  - **Prototipo visual antes de escribir código.** Se hizo en la
    clarificación de la antigua 007 (2026-11-04) y sirve de base para la
    010 y la 011. Es desechable: no entra al repositorio.
  - **Decisiones de diseño escritas en la spec**, en una sección propia:
    pensada primero para el celular; colores, tipografía y espacios como
    variables CSS; montos en pesos colombianos con `Intl.NumberFormat`
    (`$ 1.240.000`); estados de vacío, carga y error; contraste suficiente
    y uso completo con teclado.
  - **Framework: se evaluó y se mantiene la web sin framework (2026-11-04).**
    Que la web quede bonita depende del diseño (tipografía, espacios,
    color, jerarquía), no de React o Vue. Un framework con librería de
    componentes añadiría Node, `npm` y un paso de compilación que arrastran
    Docker, CI e imágenes (principio 2). La opción es CSS propio con
    variables y módulos de JavaScript nativos. Si el estado de la edición
    en línea se complica, la clarificación puede evaluar una librería
    pequeña sin compilación (por ejemplo Alpine.js) con su ADR.
  - Los gráficos del prototipo son SVG y CSS propios. Chart.js entra solo
    si la spec lo justifica.

## Fase 2 — Docker
- [ ] 012-contenedores

## Fase 3 — Nginx
- [ ] 013-reverse-proxy
  - Límite de peticiones (*rate limiting*) en `POST /auth/register` y
    `POST /auth/login`: con el registro abierto, frena la creación masiva de
    cuentas, la prueba de contraseñas y el recorrido de correos (ADR 0005).
  - Enmascarar en los logs de acceso el token de invitación de
    `/invitations/<token>` y `/unirse/<token>`: quien lea los logs no debe
    poder canjear un enlace todavía sin usar (plan 001).

## Fase 4 — GitHub Actions
- [ ] 014-integracion-continua
- [ ] 015-publicacion-imagenes

## Fase 5 — AWS + Terraform
- [ ] 016-cuenta-aws-segura
- [ ] 017-infraestructura-aws

## Fase 6 — Ansible + despliegue continuo
- [ ] 018-configuracion-servidores
- [ ] 019-despliegue-continuo

## Fase 7 — Prometheus + Grafana
- [ ] 020-metricas
- [ ] 021-dashboards
- [ ] 022-alertas

## Fase 8 — Kubernetes
- [ ] 023-kubernetes-local
- [ ] 024-kubernetes-k3s
- [ ] 025-helm

## Fase 9 — Extras
- [ ] 026-backups
- [ ] 027-https-dominio
- [ ] 028-gitops
