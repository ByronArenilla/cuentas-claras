# ADR 0007 — La fecha del gasto es un día calendario

- Fecha: 2026-11-04
- Estado: aceptada
- Fase / spec: 1 / 003-api-gastos

## Contexto

La spec 003 es la primera que guarda cuándo salió el dinero. El principio 7
dice que las fechas "se guardan en UTC y el mes al que pertenece un gasto
se calcula en la zona horaria configurada (`TZ`)".

- Quien registra un gasto piensa en días: "hoy", "ayer", "el 1 de octubre".
  Casi nunca sabe, ni le importa, la hora exacta del pago.
- El periodo de un gasto (`YYYY-MM`) decide en qué presupuesto cuenta
  (spec 004). Un gasto no puede cambiar de mes por un detalle de horas.
- El caso que obliga a decidir: el 31 de octubre a las 20:00 en Bogotá
  (UTC-5) ya es 1 de noviembre en UTC. Ese gasto es de octubre.

## Decisión

La fecha del gasto se guarda como un **día calendario sin hora ni zona**
(columna `Date` llamada `spent_on`, por ejemplo `2026-10-31`), y su periodo
sale directamente del día.

El principio 7 se cumple así:

- **Los instantes van en UTC.** El momento en que se registró el gasto
  (`created_at`) es un instante y se guarda en UTC, como en el resto de
  tablas.
- **"Hoy" se calcula en `TZ`.** Si el gasto llega sin fecha, `spent_on` es
  el día actual en `TZ` (`app/dates.py`: `today()` convierte `now()`, en
  UTC, a [`zoneinfo.ZoneInfo`](https://docs.python.org/3/library/zoneinfo.html)
  de `TZ`). Nunca se usa `date.today()`, que depende de la zona del proceso.
- **El mes se calcula en `TZ` una sola vez**: al decidir qué día es "hoy".
  Desde ahí el día ya es del mes que es, sin más cálculos.

## Alternativas descartadas

- **Guardar un instante en UTC** (`2026-11-01T01:00:00Z`) y calcular el
  día al consultar: obliga a inventar una hora cuando el usuario dice
  "ayer" o "el 1 de octubre", y una hora inventada puede cruzar la
  medianoche al convertirla y mover el gasto de día o de mes. Además, cada
  consulta por periodo tendría que convertir zonas, y el filtro sería más
  difícil de escribir y de probar.
- **Guardar el instante en la hora local de `TZ`**: viola el principio 7 y
  vuelve ambigua la hora en zonas con horario de verano.

## Consecuencias

- El filtro por periodo es una comparación simple de días
  (`start <= spent_on < next`), que la spec 004 reutiliza para el resumen.
- **Cambiar `TZ` no mueve gastos de mes.** Los gastos guardan un día, no un
  instante, así que se quedan donde están. Solo cambia qué día es "hoy" a
  partir de ese momento.
- Se pierde la hora del pago. Si algún día hace falta (por ejemplo, para
  ordenar por momento de registro en `/ultimos` de la 006), está
  `created_at`.
- Qué aprendí: un principio como "fechas en UTC" habla de instantes. Un día
  calendario es otro tipo de dato, y forzarlo a instante crea la ambigüedad
  que el principio quería evitar.
