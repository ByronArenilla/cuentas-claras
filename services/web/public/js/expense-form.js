// Estado del formulario de Registrar y el gasto que se envía a la API (spec
// 011, RF-6 a RF-16, decisiones 10 a 13). Sin DOM: se prueba con
// `node --test`. Cada función devuelve un estado nuevo y no cambia el que
// recibe.
//
// Un gasto se nombra con un solo campo, "Qué fue" (decisión 26 de la 009). En
// un gasto del mes (débito, o tarjeta a 1 cuota que estaba en el plan) sugiere
// los rubros del mes; elegir uno lo liga al rubro y la categoría sale de él.
// Si no se elige ninguno, se pide la categoría y el texto es la descripción.

import { periodOf } from "./format.js";

const TILDE = "̃";

/** La clave con la que la API compara nombres (`category_key`, ADR 0006):
 * sin mayúsculas, tildes ni diéresis, y sin espacios alrededor. La ñ cuenta:
 * "Año" y "Ano" son distintos. */
export function nameKey(name) {
  const decomposed = name.trim().toLowerCase().normalize("NFD");
  let kept = "";
  for (const char of decomposed) {
    const combining = /\p{Mn}/u.test(char);
    const enye = char === TILDE && kept.endsWith("n");
    if (combining && !enye) continue;
    kept += char;
  }
  return kept.normalize("NFC");
}

/** Un formulario vacío. "Hoy" es `date: null`: la web no calcula hoy
 * (decisión 12). */
export function newForm({ paymentType = "debit", cardId = null, date = null } = {}) {
  return {
    amount: null,
    paymentType,
    description: "",
    itemId: null,
    itemPeriod: null,
    categoryId: null,
    date,
    cardId,
    installments: 1,
    // Solo a crédito y a 1 cuota: ¿estaba en el plan del mes? Sin respuesta
    // hasta que se elige (decisión 26).
    inPlan: null,
  };
}

/** Los rubros cuyo nombre contiene lo escrito (RF-8). Sin texto, todos. */
export function suggestItems(items, text) {
  const key = nameKey(text);
  if (!key) return items;
  return items.filter((item) => nameKey(item.name).includes(key));
}

export function chooseItem(form, item, period) {
  return {
    ...form,
    itemId: item.id,
    itemPeriod: period,
    description: item.name,
    categoryId: item.category_id,
  };
}

/** Escribir en "Qué fue": si ya no es el nombre del rubro elegido, lo suelta. */
export function typeDescription(form, text) {
  const keepsItem = form.itemId !== null && text === form.description;
  return keepsItem ? { ...form, description: text } : { ...form, description: text, itemId: null, itemPeriod: null };
}

/** El mes del gasto: el de la fecha elegida, o el actual si es "Hoy". */
export function formPeriod(form, currentPeriod) {
  return form.date ? periodOf(form.date) : currentPeriod;
}

/** Cambia la fecha (`null` es "Hoy"); un rubro de otro mes se suelta (RF-9). */
export function changeDate(form, date, currentPeriod) {
  const next = { ...form, date };
  if (next.itemId !== null && next.itemPeriod !== formPeriod(next, currentPeriod)) {
    return { ...next, itemId: null, itemPeriod: null };
  }
  return next;
}

/** Qué clase de gasto es: "debit", "month" (tarjeta, del mes), "debt"
 * (tarjeta, deuda) o "undecided" (tarjeta a 1 cuota sin responder). */
export function kindOf(form) {
  if (form.paymentType === "debit") return "debit";
  if (form.installments > 1) return "debt";
  if (form.inPlan === true) return "month";
  if (form.inPlan === false) return "debt";
  return "undecided";
}

/** Un gasto del mes, a débito o con tarjeta, se liga a un rubro o lleva
 * categoría, como en la 008. */
export function usesItems(form) {
  const kind = kindOf(form);
  return kind === "debit" || kind === "month";
}

/** Lo que falta para poder registrar, en el orden del formulario. */
export function missing(form) {
  const found = [];
  if (!form.amount) found.push("Escribe el monto.");
  if (usesItems(form) && form.itemId === null && form.categoryId === null) {
    found.push("Elige un rubro del mes o la categoría.");
  }
  return found;
}

/** El cuerpo de `POST /expenses` (criterio 1). */
export function buildExpense(form) {
  const body = { amount: form.amount, payment_type: form.paymentType };
  const description = form.description.trim();
  if (form.itemId !== null) {
    body.budget_item_id = form.itemId;
  } else {
    body.category_id = form.categoryId;
    if (description) body.description = description;
  }
  if (form.date) body.spent_on = form.date;
  return body;
}

/** El formulario listo para el siguiente gasto: se limpian monto y qué fue, y
 * se conservan el tipo de pago, la tarjeta y la fecha (RF-14). */
export function afterRecord(form) {
  return newForm({ paymentType: form.paymentType, cardId: form.cardId, date: form.date });
}
