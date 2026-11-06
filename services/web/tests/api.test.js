// Cliente de la API (spec 011, RF-3, RF-14, RF-15 y RF-30; criterio 1).
import { test } from "node:test";
import assert from "node:assert/strict";
import { ApiError, createApi } from "../public/js/api.js";

/** `fetch` simulado: responde lo que se le diga y guarda cada petición. */
function fakeFetch(reply) {
  const calls = [];
  const fetch = async (url, options) => {
    calls.push({ url, options });
    if (reply instanceof Error) throw reply;
    const { status = 200, body = null } = reply;
    return {
      ok: status >= 200 && status < 300,
      status,
      json: async () => body,
    };
  };
  return { fetch, calls };
}

function api(reply, overrides = {}) {
  const fake = fakeFetch(reply);
  const events = [];
  const client = createApi({
    baseUrl: "http://api.test",
    fetch: fake.fetch,
    token: () => "abc",
    onUnauthorized: (message) => events.push(["401", message]),
    onNetwork: (online) => events.push(["red", online]),
    ...overrides,
  });
  return { client, calls: fake.calls, events };
}

test("manda el token y el cuerpo en JSON", async () => {
  const { client, calls } = api({ status: 201, body: { id: 1 } });

  const data = await client.post("/spaces/1/expenses", { amount: 52000 });

  assert.deepEqual(data, { id: 1 });
  const [{ url, options }] = calls;
  assert.equal(url, "http://api.test/spaces/1/expenses");
  assert.equal(options.method, "POST");
  assert.equal(options.headers.Authorization, "Bearer abc");
  assert.equal(options.headers["Content-Type"], "application/json");
  assert.equal(options.body, '{"amount":52000}');
});

test("sin token no manda Authorization", async () => {
  const { client, calls } = api({ body: [] }, { token: () => null });

  await client.get("/spaces");

  assert.equal(calls[0].options.headers.Authorization, undefined);
});

test("los parámetros van en la consulta", async () => {
  const { client, calls } = api({ status: 204 });

  const data = await client.del("/spaces/1/expenses/3", { confirm: "true" });

  assert.equal(data, null);
  assert.equal(calls[0].url, "http://api.test/spaces/1/expenses/3?confirm=true");
});

test("un 401 avisa para borrar la sesión y lanza el mensaje de la API", async () => {
  const message = "Sesión no válida o caducada. Inicia sesión de nuevo.";
  const { client, events } = api({ status: 401, body: { detail: message } });

  await assert.rejects(client.get("/me"), (error) => {
    assert.ok(error instanceof ApiError);
    assert.equal(error.status, 401);
    assert.equal(error.message, message);
    return true;
  });
  // La respuesta también confirma que hay conexión.
  assert.deepEqual(events, [
    ["red", true],
    ["401", message],
  ]);
});

test("un fallo de red marca sin conexión", async () => {
  const { client, events } = api(new TypeError("Failed to fetch"));

  await assert.rejects(client.get("/spaces"), (error) => {
    assert.equal(error.offline, true);
    assert.match(error.message, /conexión/);
    return true;
  });
  assert.deepEqual(events, [["red", false]]);
});

test("una respuesta marca que hay conexión", async () => {
  const { client, events } = api({ body: [] });

  await client.get("/spaces");

  assert.deepEqual(events, [["red", true]]);
});

test("un 422 de validación se reparte por campo", async () => {
  const detail = [
    { loc: ["body", "amount"], msg: "El monto debe ser mayor que cero.", type: "x" },
    { loc: ["body"], msg: "Una deuda necesita su categoría.", type: "y" },
    { loc: ["body", "password"], msg: "Field required", type: "missing" },
  ];
  const { client } = api({ status: 422, body: { detail } });

  await assert.rejects(client.post("/x", {}), (error) => {
    assert.equal(error.status, 422);
    assert.deepEqual(error.fields, {
      amount: "El monto debe ser mayor que cero.",
      _form: "Una deuda necesita su categoría.",
      password: "Este campo es obligatorio.",
    });
    assert.equal(error.message, "El monto debe ser mayor que cero.");
    return true;
  });
});

test("un 409 o un 404 traen el detalle de la API", async () => {
  const { client } = api({ status: 409, body: { detail: "Ya existe la tarjeta «Visa»." } });

  await assert.rejects(client.post("/x", {}), /Ya existe la tarjeta «Visa»\./);
});
