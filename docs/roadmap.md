# Roadmap — gastito

> **Fase actual:** 1 — Aplicación y SDD
> **Spec activa:** 011-app-web
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
- [x] 007-retirar-bot — Quitar el bot de Telegram; el registro pasa a la app web.
  - Sale `services/bot/` y, de la API, las rutas `/telegram/*` y
    `BOT_API_KEY`. Se queda `GET /spaces/{space_id}/expenses/recent`, que
    también usa la web.
- [x] 008-rubros-e-ingresos — Rubros con nombre libre y categoría, ingresos del mes y plan copiado del mes anterior.
  - Cambia el presupuesto por categoría con vigencia de la 004 (ADR 0008) y
    da a cada gasto un rubro o la marca de "no planeado".
  - Se llamaba "partidas"; se cambió a "rubro" en la clarificación
    (2026-11-05).
  - Incluye eliminar categorías: se archivan, los rubros y gastos que ya
    las tenían las conservan, y crearlas de nuevo las restaura.
  - Cambia tablas que ya están en `main`, así que **entran las migraciones
    con Alembic** con un ADR que reemplaza al 0004 y otro que reemplaza al
    0008. La primera migración decide qué pasa con las tablas de Telegram
    que dejan las bases ya creadas (spec 007).
- [x] 009-tarjetas-y-cuotas — Tarjetas con corte, pago y tasa; compras a cuotas y la deuda que llega cada mes.
  - Toda compra con tarjeta, también a 1 cuota, cuenta el mes en que se
    paga la tarjeta, no el de la compra: cada cuota entra en Deudas ese
    mes. Lleva categoría, pero no rubro. El mes del pago sale del día de
    corte y del día límite de pago. Antes decía que la compra a 1 cuota
    contaba en su rubro el mes de la compra; se cambió en la clarificación
    (2026-11-06).
  - Los intereses son una estimación con la tasa mensual de la tarjeta, que
    es opcional. Al planear se escribe el valor real del extracto.
  - Entran los abonos a una compra, que bajan la cuota o el plazo, y
    cancelarla antes de tiempo. El roadmap los dejaba fuera; se cambió en
    la clarificación (2026-11-06).
- [x] 010-compras-del-mes-con-tarjeta — Distinguir un gasto del mes pagado con tarjeta de una deuda.
  - Surgió al especificar la web (2026-11-06) y cambia la decisión 1 de la
    009: no toda compra con tarjeta es deuda.
  - **A varias cuotas, siempre es deuda**, como en la 009.
  - **A 1 cuota, se pregunta al registrar si estaba en el plan del mes.** Si
    sí, es un gasto del mes: va en su rubro o su categoría y cuenta el mes
    de la compra, como un débito. Si no, es deuda y llega a Deudas el mes
    del pago.
  - **El mes del pago**, el resumen muestra por tarjeta lo que hay que pagar
    (gastos del mes anterior y cuotas de deudas), pero solo las cuotas de
    deudas suman en lo gastado: el gasto del mes ya contó.
  - **El valor real del extracto es el total a pagar**; la deuda del mes es
    ese total menos los gastos del mes que incluye.
  - Se hace antes de la web, que pasa a ser la 011, y las specs siguientes
    corren un número.
- [ ] 011-app-web — Entrar y registrarse, registrar gastos desde el celular, fijarla en la pantalla de inicio y diseño responsive.
  - **Se fija desde el navegador, no se instala ni se descarga.** En el
    celular se usa "Añadir a pantalla de inicio" (Safari en iPhone, Chrome
    en Android) y la app enseña esos pasos; en el computador se fija desde
    Chrome o Edge. Con un manifiesto web y sus íconos, el acceso directo se
    abre a pantalla completa, sin la barra del navegador. Se descartó
    publicarla en Play Store o App Store (ADR 0010).
  - No se registran gastos sin conexión: sin internet, la app lo avisa. Sin
    *service worker*: Chrome y Safari ya no lo exigen para fijar la web
    (plan, 2026-11-06).
  - Diseño responsive con una sola app: navegación abajo en el celular,
    menú lateral desde 1024 px, y botones de al menos 44 px.
  - Absorbe la antigua 008-control-acceso (sesión en la web).
  - **Se entra una sola vez**: la sesión se renueva con el uso y caduca tras
    90 días sin abrir la app. Cambia los 15 días fijos de la 001
    (clarificación, 2026-11-06).
  - **El diseño de la app se fija en esta spec** (dirección "Libro
    auxiliar", elegida en un prototipo nuevo el 2026-11-06), y la 012 lo
    reutiliza.
- [ ] 012-tablero-y-planear — Tablero del mes, planear el mes y tarjetas, con gráficos para decidir.
  - **Prototipo visual antes de escribir código.** El de la antigua 007
    (2026-11-04) no se conservó; la 011 hizo uno nuevo (2026-11-06). Son
    desechables: no entran al repositorio.
  - **Reutiliza el diseño de la 011** (sección "Diseño" de su spec): pensada
    primero para el celular; colores, tipografía y espacios como variables
    CSS; montos en pesos colombianos con `Intl.NumberFormat`
    (`$ 1.240.000`); estados de vacío, carga y error; contraste suficiente
    y uso completo con teclado. La 012 lo extiende a sus pantallas.
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
- [ ] 013-contenedores

## Fase 3 — Nginx
- [ ] 014-reverse-proxy
  - Límite de peticiones (*rate limiting*) en `POST /auth/register` y
    `POST /auth/login`: con el registro abierto, frena la creación masiva de
    cuentas, la prueba de contraseñas y el recorrido de correos (ADR 0005).
  - Enmascarar en los logs de acceso el token de invitación de
    `/invitations/<token>` y `/unirse/<token>`: quien lea los logs no debe
    poder canjear un enlace todavía sin usar (plan 001).

## Fase 4 — GitHub Actions
- [ ] 015-integracion-continua
- [ ] 016-publicacion-imagenes

## Fase 5 — AWS + Terraform
- [ ] 017-cuenta-aws-segura
- [ ] 018-infraestructura-aws
- [ ] 019-https-dominio
  - Se adelantó desde la fase 9 (2026-11-04). Sin HTTPS, el ícono fijado
    en el celular abre la web en el navegador y no a pantalla completa
    (ADR 0010). Además, con la app en internet, entrar sin HTTPS enviaría
    la contraseña sin cifrar.

## Fase 6 — Ansible + despliegue continuo
- [ ] 020-configuracion-servidores
- [ ] 021-despliegue-continuo

## Fase 7 — Prometheus + Grafana
- [ ] 022-metricas
- [ ] 023-dashboards
- [ ] 024-alertas

## Fase 8 — Kubernetes
- [ ] 025-kubernetes-local
- [ ] 026-kubernetes-k3s
- [ ] 027-helm

## Fase 9 — Extras
- [ ] 028-backups
- [ ] 029-gitops
