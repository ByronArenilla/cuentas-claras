// Espacios: crear, salir y compartir (spec 011, RF-23 a RF-26; decisión 18).
import { test } from "node:test";
import assert from "node:assert/strict";
import { ApiError } from "../public/js/api.js";
import { createSpace, leaveSpace, shareInvitation, shareText } from "../public/js/spaces.js";

function fakeSession() {
  const state = { space: null };
  return {
    state,
    setSpace: (id) => (state.space = id),
    chooseSpace(spaces) {
      const chosen = spaces.find((space) => space.id === state.space) ?? spaces[0] ?? null;
      if (chosen) state.space = chosen.id;
      return chosen;
    },
  };
}

const INVITATION = {
  url: "http://web.test/unirse/abc",
  expires_at: "2026-11-07T17:00:00Z",
};

test("crear un espacio pasa a él", async () => {
  const session = fakeSession();
  const api = { post: async (path, body) => ({ id: 5, name: body.name }) };

  const space = await createSpace({ api, session }, "Viajes");

  assert.deepEqual(space, { id: 5, name: "Viajes" });
  assert.equal(session.state.space, 5);
});

test("salir de un espacio pasa al primero que queda", async () => {
  const session = fakeSession();
  session.state.space = 2;
  const calls = [];
  const api = { del: async (path) => calls.push(path) };
  const spaces = [
    { id: 1, name: "Personal" },
    { id: 2, name: "Casa" },
  ];

  const next = await leaveSpace({ api, session }, spaces[1], spaces);

  assert.deepEqual(calls, ["/spaces/2/members/me"]);
  assert.deepEqual(next, { id: 1, name: "Personal" });
  assert.equal(session.state.space, 1);
});

test("si la API no deja salir, el error llega con su mensaje", async () => {
  const message = "No puedes salir de tu único espacio.";
  const api = {
    del: async () => {
      throw new ApiError({ status: 409, message });
    },
  };

  await assert.rejects(leaveSpace({ api, session: fakeSession() }, { id: 1 }, [{ id: 1 }]), {
    message,
  });
});

test("el texto de la invitación dice un solo uso y 24 horas", () => {
  const share = shareText(INVITATION, "Casa");

  assert.equal(share.url, INVITATION.url);
  assert.match(share.text, /«Casa»/);
  assert.match(share.text, /un solo uso/);
  assert.match(share.text, /24 horas/);
});

test("compartir usa el menú del sistema si existe", async () => {
  const shared = [];
  const api = { post: async () => INVITATION };

  const { how, url } = await shareInvitation({ api }, { id: 2, name: "Casa" }, {
    share: async (data) => shared.push(data),
    copy: async () => assert.fail("no debía copiar"),
  });

  assert.equal(how, "shared");
  assert.equal(shared[0].url, INVITATION.url);
});

test("sin menú de compartir, copia el enlace", async () => {
  const copied = [];
  const api = { post: async () => INVITATION };

  const { how, url } = await shareInvitation({ api }, { id: 2, name: "Casa" }, {
    share: null,
    copy: async (text) => copied.push(text),
  });

  assert.equal(how, "copied");
  assert.deepEqual(copied, [INVITATION.url]);
});

test("cerrar el menú de compartir no es un error", async () => {
  const api = { post: async () => INVITATION };
  const abort = Object.assign(new Error("cancelado"), { name: "AbortError" });

  const { how, url } = await shareInvitation({ api }, { id: 2, name: "Casa" }, {
    share: async () => {
      throw abort;
    },
    copy: async () => {},
  });

  assert.equal(how, "cancelled");
});

test("si no se puede copiar, devuelve el enlace para mostrarlo", async () => {
  const api = { post: async () => INVITATION };

  const { how, url } = await shareInvitation({ api }, { id: 2, name: "Casa" }, {
    share: null,
    copy: async () => {
      throw new Error("sin permiso");
    },
  });

  assert.equal(how, "manual");
  assert.equal(url, INVITATION.url);
});
