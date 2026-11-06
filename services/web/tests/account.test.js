// Entrar, crear cuenta y cerrar sesión, sin navegador (spec 011, RF-1 a RF-4).
import { test } from "node:test";
import assert from "node:assert/strict";
import { ApiError } from "../public/js/api.js";
import { logIn, logOut, signUp } from "../public/js/account.js";

function fakeSession() {
  const state = { saved: null, cleared: false, next: null };
  return {
    state,
    save: (value) => (state.saved = value),
    clear: () => (state.cleared = true),
    takeNext: () => {
      const next = state.next;
      state.next = null;
      return next;
    },
  };
}

function fakeApi(handlers) {
  const calls = [];
  return {
    calls,
    post: async (path, body) => {
      calls.push([path, body]);
      return handlers[path](body);
    },
  };
}

const TOKEN = { access_token: "abc", token_type: "bearer" };

test("entrar guarda el token y el correo y va a Registrar", async () => {
  const session = fakeSession();
  const api = fakeApi({ "/auth/login": () => TOKEN });

  const destination = await logIn({ api, session }, { email: " Ana@Example.com ", password: "x" });

  assert.equal(destination, "/registrar");
  assert.deepEqual(session.state.saved, { token: "abc", email: "ana@example.com" });
});

test("entrar vuelve a la pantalla a la que se iba", async () => {
  const session = fakeSession();
  session.state.next = "/unirse/abc";
  const api = fakeApi({ "/auth/login": () => TOKEN });

  const destination = await logIn({ api, session }, { email: "ana@example.com", password: "x" });

  assert.equal(destination, "/unirse/abc");
});

test("crear cuenta registra y entra con la misma contraseña", async () => {
  const session = fakeSession();
  const api = fakeApi({ "/auth/register": () => ({ id: 1 }), "/auth/login": () => TOKEN });

  const destination = await signUp(
    { api, session },
    { email: "ana@example.com", password: "una-contraseña-larga" },
  );

  assert.equal(destination, "/registrar");
  assert.deepEqual(
    api.calls.map(([path]) => path),
    ["/auth/register", "/auth/login"],
  );
  assert.equal(session.state.saved.token, "abc");
});

test("cerrar sesión la cierra en la API y borra el dispositivo", async () => {
  const session = fakeSession();
  const api = fakeApi({ "/auth/logout": () => null });

  const notice = await logOut({ api, session });

  assert.equal(notice, null);
  assert.equal(session.state.cleared, true);
});

test("sin conexión, cerrar sesión borra igual y avisa de los 90 días", async () => {
  const session = fakeSession();
  const api = fakeApi({
    "/auth/logout": () => {
      throw new ApiError({ status: 0, message: "Sin conexión.", offline: true });
    },
  });

  const notice = await logOut({ api, session });

  assert.equal(session.state.cleared, true);
  assert.match(notice, /90 días/);
});
