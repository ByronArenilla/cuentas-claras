// Comprueba que `make test` corre las pruebas de la web con `node --test`
// (spec 011, T3). Los módulos de la web traen sus propias pruebas desde T4.
import { test } from "node:test";
import assert from "node:assert/strict";

test("node --test corre las pruebas de la web", () => {
  assert.equal(1 + 1, 2);
});
