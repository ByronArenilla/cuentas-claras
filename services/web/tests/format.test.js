// Formato de pesos, fechas y meses, y limpieza del monto escrito (spec 011,
// RF-7 y RF-35).
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  formatDay,
  formatMonth,
  formatMonthShort,
  formatNumber,
  formatPesos,
  monthName,
  parseAmount,
  periodOf,
  shiftPeriod,
} from "../public/js/format.js";

const NBSP = " ";

test("pesos colombianos con punto de miles y sin decimales", () => {
  assert.equal(formatPesos(1240000), `$${NBSP}1.240.000`);
  assert.equal(formatPesos(0), `$${NBSP}0`);
  assert.equal(formatPesos(-12000), `-$${NBSP}12.000`);
});

test("cifra sin símbolo, para el campo del monto", () => {
  assert.equal(formatNumber(1240000), "1.240.000");
  assert.equal(formatNumber(52000), "52.000");
});

test("el monto escrito se limpia a un entero de pesos", () => {
  assert.equal(parseAmount("1.240.000"), 1240000);
  assert.equal(parseAmount("$ 52 000"), 52000);
  assert.equal(parseAmount("52abc000"), 52000);
  assert.equal(parseAmount(""), null);
  assert.equal(parseAmount("abc"), null);
  assert.equal(parseAmount("000"), 0);
});

test("un día se muestra como 'jue 5 nov'", () => {
  assert.equal(formatDay("2026-11-05"), "jue 5 nov");
  assert.equal(formatDay("2027-01-01"), "vie 1 ene");
});

test("los meses se muestran en español", () => {
  assert.equal(formatMonth("2026-11"), "noviembre 2026");
  assert.equal(formatMonthShort("2026-11"), "nov 2026");
  assert.equal(monthName("2026-12"), "diciembre");
});

test("mes anterior y siguiente", () => {
  assert.equal(shiftPeriod("2026-01", -1), "2025-12");
  assert.equal(shiftPeriod("2026-12", 1), "2027-01");
  assert.equal(shiftPeriod("2026-11", 0), "2026-11");
});

test("el mes de un día", () => {
  assert.equal(periodOf("2026-11-05"), "2026-11");
});
