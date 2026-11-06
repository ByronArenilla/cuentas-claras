// Contraste de los tokens de color en los dos temas (spec 011, RF-32 y
// criterio 2). Lee `tokens.css` tal cual está: si alguien cambia un color y
// baja del mínimo de WCAG 2.2 AA, este test falla.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const css = readFileSync(new URL("../public/css/tokens.css", import.meta.url), "utf8");

/** Variables `--nombre: #rrggbb` de un bloque de CSS. */
function colors(block) {
  const found = {};
  for (const [, name, hex] of block.matchAll(/--([\w-]+):\s*(#[0-9a-fA-F]{6})\b/g)) {
    found[name] = hex;
  }
  return found;
}

/** El primer bloque `:root { ... }` (tema claro) y el de `prefers-color-scheme: dark`. */
function themes() {
  const light = css.match(/^:root\s*\{([^}]*)\}/m)[1];
  const darkMedia = css.slice(css.indexOf("prefers-color-scheme: dark"));
  const dark = darkMedia.match(/:root[^{]*\{([^}]*)\}/)[1];
  return { claro: colors(light), oscuro: colors(dark) };
}

// https://www.w3.org/TR/WCAG22/#dfn-relative-luminance
function luminance(hex) {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
  const linear = (c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
  return 0.2126 * linear(r) + 0.7152 * linear(g) + 0.0722 * linear(b);
}

function contrast(a, b) {
  const [light, dark] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (light + 0.05) / (dark + 0.05);
}

// Texto: 4,5:1. Bordes de controles y foco: 3:1.
const TEXT = [
  ["ink", "paper"],
  ["ink", "field"],
  ["muted", "paper"],
  ["muted", "field"],
  ["red", "paper"],
  ["red", "field"],
  ["paper", "ink"], // texto del botón principal
];
const NON_TEXT = [
  ["rule-strong", "paper"],
  ["rule-strong", "field"],
  ["focus", "paper"],
  ["focus", "field"],
];

for (const [name, tokens] of Object.entries(themes())) {
  test(`tema ${name}: los tokens existen`, () => {
    for (const token of ["paper", "field", "ink", "rule", "rule-strong", "red", "muted", "focus"]) {
      assert.ok(tokens[token], `falta --${token}`);
    }
  });

  for (const [fg, bg] of TEXT) {
    test(`tema ${name}: --${fg} sobre --${bg} pasa 4,5:1`, () => {
      const ratio = contrast(tokens[fg], tokens[bg]);
      assert.ok(ratio >= 4.5, `${ratio.toFixed(2)}:1`);
    });
  }

  for (const [fg, bg] of NON_TEXT) {
    test(`tema ${name}: --${fg} sobre --${bg} pasa 3:1`, () => {
      const ratio = contrast(tokens[fg], tokens[bg]);
      assert.ok(ratio >= 3, `${ratio.toFixed(2)}:1`);
    });
  }
}
