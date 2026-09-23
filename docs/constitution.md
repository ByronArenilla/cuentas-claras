# Constitución — budget-ops

Principios innegociables para todo el proyecto, de la fase 1 a la 9. Toda
spec, plan, tarea y cambio de infraestructura debe cumplirlos. Solo se
modifican con un ADR aprobado en `docs/adr/`, y eso debería ocurrir casi nunca.

## Proceso
1. **La spec manda**: nada se implementa, ni código ni infraestructura, sin
   una spec aprobada. Si falta una decisión, el trabajo se detiene y se
   pregunta.
2. **Crecimiento por fases**: una herramienta solo entra en la fase que le
   asigna `docs/roadmap.md`. Prohibido adelantar tecnología "por si acaso".
3. **Tests como puerta**: una tarea termina solo con tests en verde y lint
   limpio. Cuando exista CI, nada entra a `main` con el pipeline en rojo.
4. **Documentar para aprender**: cada spec cerrada actualiza el README y cada
   decisión técnica relevante deja un ADR con la alternativa descartada.

## Producto y datos
5. **Multiusuario por espacios**: los datos pertenecen a un *espacio*, no a
   una persona. Todo gasto, categoría y presupuesto vive dentro de un
   espacio, y un usuario accede a los espacios de los que es miembro.
   Varios miembros en un mismo espacio comparten presupuesto; dos espacios
   distintos nunca ven los datos del otro. El uso personal es un espacio
   con un único miembro. (ADR 0001)
6. **Dinero exacto**: los montos se guardan como enteros en la unidad mínima
   de la moneda. Nunca se usa `float` para dinero.
7. **Fechas sin ambigüedad**: se guardan en UTC y el mes al que pertenece un
   gasto se calcula en la zona horaria configurada (`TZ`).
8. **Los datos no se pierden**: ningún gasto se borra sin confirmación
   explícita y ningún cambio de estructura destruye datos existentes.

## Arquitectura
9. **Servicios desacoplados**: `api`, `bot` y `web` son servicios
   independientes. Solo la API accede a la base de datos; el bot y la web la
   usan por HTTP.
10. **Lógica separada de la interfaz**: las reglas de negocio viven en la API
    y se prueban sin HTTP ni Telegram. El bot y la web son capas finas.
11. **Configuración por entorno**: todo lo que cambia entre entornos entra por
    variables de entorno. El mismo código corre en local, en Docker y en
    Kubernetes.

## Operación y seguridad
12. **Secretos fuera de Git**: ningún token, contraseña o llave en el
    repositorio. `.env.example` nunca lleva valores reales.
13. **Acceso restringido**: cada persona se autentica y solo alcanza los
    espacios de los que es miembro. El bot solo atiende a chats vinculados
    a un usuario registrado y la web exige autenticación. Ninguna consulta
    a la base de datos devuelve datos sin filtrar por espacio. (ADR 0001)
14. **Todo como código y reproducible**: infraestructura, configuración,
    despliegues y dashboards viven en el repositorio, y el entorno se recrea
    desde cero sin pasos manuales no documentados. Un cambio manual en un
    servidor es un defecto.
15. **Observable por diseño**: cada servicio expone `/health`. Desde la fase
    de observabilidad también expone métricas, y todo fallo relevante genera
    una alerta.
16. **Costo controlado**: gasto máximo en la nube de 15 USD/mes, con alarma de
    presupuesto activa. Todo recurso que cobre por hora debe poder
    destruirse con un comando.

## Idioma
17. Código e identificadores en inglés; mensajes al usuario, specs y
    documentación en español.
