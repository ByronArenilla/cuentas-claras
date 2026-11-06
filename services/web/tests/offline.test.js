// Estado de la conexión (spec 011, RF-30, decisión 15).
import { test } from "node:test";
import assert from "node:assert/strict";
import { createConnection } from "../public/js/offline.js";

function fakeWindow(onLine) {
  const listeners = {};
  return {
    navigator: { onLine },
    addEventListener: (name, fn) => {
      listeners[name] = fn;
    },
    fire: (name) => listeners[name](),
  };
}

test("parte del estado del navegador", () => {
  assert.equal(createConnection(fakeWindow(true)).online(), true);
  assert.equal(createConnection(fakeWindow(false)).online(), false);
});

test("cambia con los eventos y avisa a quien escucha", () => {
  const win = fakeWindow(true);
  const connection = createConnection(win);
  const seen = [];
  connection.subscribe((online) => seen.push(online));

  win.fire("offline");
  win.fire("online");

  assert.deepEqual(seen, [false, true]);
  assert.equal(connection.online(), true);
});

test("un fallo de red lo marca sin conexión y una respuesta lo devuelve", () => {
  const connection = createConnection(fakeWindow(true));
  const seen = [];
  connection.subscribe((online) => seen.push(online));

  connection.report(false);
  connection.report(false);
  connection.report(true);

  // Solo avisa cuando cambia.
  assert.deepEqual(seen, [false, true]);
});
