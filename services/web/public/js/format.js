// Formato de montos, fechas y meses en español de Colombia (spec 011, RF-35).
//
// Las fechas llegan de la API como días `AAAA-MM-DD` o meses `AAAA-MM`, sin
// hora ni zona: se formatean en UTC para que el día nunca se corra por la zona
// del dispositivo (principio 7).

const pesos = new Intl.NumberFormat("es-CO", {
  style: "currency",
  currency: "COP",
  minimumFractionDigits: 0,
  maximumFractionDigits: 0,
});
const number = new Intl.NumberFormat("es-CO");
const dayParts = new Intl.DateTimeFormat("es-CO", {
  weekday: "short",
  day: "numeric",
  month: "short",
  timeZone: "UTC",
});
const monthLong = new Intl.DateTimeFormat("es-CO", { month: "long", timeZone: "UTC" });
const monthShort = new Intl.DateTimeFormat("es-CO", { month: "short", timeZone: "UTC" });

/** `1240000` → `$ 1.240.000`, con espacio duro para que no se parta. */
export function formatPesos(amount) {
  return pesos.format(amount);
}

/** `1240000` → `1.240.000`, para el campo del monto mientras se escribe. */
export function formatNumber(amount) {
  return number.format(amount);
}

/** Solo los dígitos de lo escrito, como entero de pesos; `null` si no hay
 * ninguno (RF-7). El monto nunca lleva decimales (principio 6). */
export function parseAmount(text) {
  const digits = String(text).replace(/\D/g, "");
  return digits ? Number.parseInt(digits, 10) : null;
}

function utcDate(iso) {
  const [year, month = 1, day = 1] = iso.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, day));
}

function clean(text) {
  return text.replace(/\./g, "");
}

/** `2026-11-05` → `jue 5 nov`. */
export function formatDay(iso) {
  const parts = Object.fromEntries(
    dayParts.formatToParts(utcDate(iso)).map((part) => [part.type, part.value]),
  );
  return `${clean(parts.weekday)} ${parts.day} ${clean(parts.month)}`;
}

/** `2026-11` → `noviembre`. */
export function monthName(period) {
  return monthLong.format(utcDate(period));
}

/** `2026-11` → `noviembre 2026`. */
export function formatMonth(period) {
  return `${monthName(period)} ${period.slice(0, 4)}`;
}

/** `2026-11` → `nov 2026`. */
export function formatMonthShort(period) {
  return `${clean(monthShort.format(utcDate(period)))} ${period.slice(0, 4)}`;
}

/** `2026-01` y `-1` → `2025-12`. */
export function shiftPeriod(period, months) {
  const [year, month] = period.split("-").map(Number);
  const index = year * 12 + (month - 1) + months;
  const shiftedYear = Math.floor(index / 12);
  const shiftedMonth = (index % 12) + 1;
  return `${String(shiftedYear).padStart(4, "0")}-${String(shiftedMonth).padStart(2, "0")}`;
}

/** `2026-11-05` → `2026-11`. */
export function periodOf(day) {
  return day.slice(0, 7);
}
