// Sesión, espacio actual y pantalla a la que volver (spec 011, RF-2 a RF-4,
// RF-23; decisiones 16 y 17).
import { test } from "node:test";
import assert from "node:assert/strict";
import { createSession, isSafePath } from "../public/js/session.js";

function memoryStorage() {
  const data = new Map();
  return {
    getItem: (key) => (data.has(key) ? data.get(key) : null),
    setItem: (key, value) => data.set(key, String(value)),
    removeItem: (key) => data.delete(key),
    data,
  };
}

function session() {
  const local = memoryStorage();
  const temporary = memoryStorage();
  return { session: createSession({ local, temporary }), local, temporary };
}

test("guarda y lee el token y el correo", () => {
  const { session: s } = session();
  assert.equal(s.token(), null);

  s.save({ token: "abc", email: "ana@example.com" });

  assert.equal(s.token(), "abc");
  assert.equal(s.email(), "ana@example.com");
  assert.equal(s.isLoggedIn(), true);
});

test("cerrar sesión borra token y espacio", () => {
  const { session: s, local } = session();
  s.save({ token: "abc", email: "ana@example.com" });
  s.setSpace(3);

  s.clear();

  assert.equal(s.token(), null);
  assert.equal(s.spaceId(), null);
  assert.equal(local.data.size, 0);
});

test("el espacio guardado se conserva si sigue en la lista", () => {
  const { session: s } = session();
  s.setSpace(2);

  const chosen = s.chooseSpace([{ id: 1, name: "Personal" }, { id: 2, name: "Casa" }]);

  assert.deepEqual(chosen, { id: 2, name: "Casa" });
});

test("si el espacio guardado ya no está, pasa al primero", () => {
  const { session: s } = session();
  s.setSpace(9);

  const chosen = s.chooseSpace([{ id: 1, name: "Personal" }, { id: 2, name: "Casa" }]);

  assert.deepEqual(chosen, { id: 1, name: "Personal" });
  assert.equal(s.spaceId(), 1);
});

test("la ruta siguiente solo acepta rutas propias", () => {
  assert.equal(isSafePath("/gastos"), true);
  assert.equal(isSafePath("/unirse/abc"), true);
  assert.equal(isSafePath("//otro.example"), false);
  assert.equal(isSafePath("https://otro.example"), false);
  assert.equal(isSafePath("/\\otro.example"), false);
  assert.equal(isSafePath(""), false);
});

test("la ruta siguiente se guarda una vez y se consume", () => {
  const { session: s } = session();

  s.setNext("/unirse/abc");

  assert.equal(s.takeNext(), "/unirse/abc");
  assert.equal(s.takeNext(), null);
});

test("una ruta siguiente insegura se ignora", () => {
  const { session: s } = session();

  s.setNext("//otro.example");

  assert.equal(s.takeNext(), null);
});

test("si el almacenamiento falla, la sesión sigue sin romperse", () => {
  const broken = {
    getItem: () => {
      throw new Error("bloqueado");
    },
    setItem: () => {
      throw new Error("bloqueado");
    },
    removeItem: () => {
      throw new Error("bloqueado");
    },
  };
  const s = createSession({ local: broken, temporary: broken });

  s.save({ token: "abc", email: "a@b.co" });
  assert.equal(s.token(), null);
  s.clear();
});
