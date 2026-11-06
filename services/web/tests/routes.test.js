// Rutas de la app (spec 011, plan "Pantallas y datos").
import { test } from "node:test";
import assert from "node:assert/strict";
import { matchRoute } from "../public/js/routes.js";

test("cada ruta encuentra su pantalla y si pide sesión", () => {
  assert.deepEqual(matchRoute("/entrar"), { view: "login", params: {}, access: "guest" });
  assert.deepEqual(matchRoute("/crear-cuenta"), { view: "register", params: {}, access: "guest" });
  assert.deepEqual(matchRoute("/registrar"), { view: "record", params: {}, access: "member" });
  assert.deepEqual(matchRoute("/gastos"), { view: "expenses", params: {}, access: "member" });
  assert.deepEqual(matchRoute("/espacio"), { view: "space", params: {}, access: "member" });
});

test("las rutas con parámetros los extraen", () => {
  assert.deepEqual(matchRoute("/gastos/12"), {
    view: "edit",
    params: { id: 12 },
    access: "member",
  });
  assert.deepEqual(matchRoute("/unirse/abc-_9"), {
    view: "join",
    params: { token: "abc-_9" },
    access: "any",
  });
});

test("la raíz y una ruta desconocida van a Registrar", () => {
  assert.deepEqual(matchRoute("/"), { redirect: "/registrar" });
  assert.deepEqual(matchRoute("/no-existe"), { redirect: "/registrar" });
  assert.deepEqual(matchRoute("/gastos/abc"), { redirect: "/registrar" });
});

test("una barra final no cambia la ruta", () => {
  assert.equal(matchRoute("/gastos/").view, "expenses");
});
