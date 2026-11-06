// Guía para fijar la app según el navegador (spec 011, RF-29, decisión 20).
import { test } from "node:test";
import assert from "node:assert/strict";
import { detectPlatform, pinGuide } from "../public/js/platform.js";

const UA = {
  iphoneSafari:
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1",
  iphoneChrome:
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/130.0.6723.90 Mobile/15E148 Safari/604.1",
  androidChrome:
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36",
  androidFirefox: "Mozilla/5.0 (Android 14; Mobile; rv:131.0) Gecko/131.0 Firefox/131.0",
  desktopChrome:
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
  desktopEdge:
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0",
  desktopFirefox: "Mozilla/5.0 (X11; Linux x86_64; rv:131.0) Gecko/20100101 Firefox/131.0",
  macSafari:
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_6) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15",
};

test("reconoce cada navegador", () => {
  assert.equal(detectPlatform(UA.iphoneSafari), "ios");
  assert.equal(detectPlatform(UA.iphoneChrome), "ios");
  assert.equal(detectPlatform(UA.androidChrome), "android-chrome");
  assert.equal(detectPlatform(UA.androidFirefox), "other");
  assert.equal(detectPlatform(UA.desktopChrome), "desktop-chrome");
  assert.equal(detectPlatform(UA.desktopEdge), "desktop-edge");
  assert.equal(detectPlatform(UA.desktopFirefox), "other");
  assert.equal(detectPlatform(UA.macSafari), "mac-safari");
});

test("cada navegador trae sus pasos", () => {
  assert.match(pinGuide(UA.iphoneSafari).steps.join(" "), /Compartir/);
  assert.match(pinGuide(UA.iphoneSafari).steps.join(" "), /Añadir a pantalla de inicio/);
  assert.match(pinGuide(UA.androidChrome).steps.join(" "), /⋮/);
  assert.match(pinGuide(UA.androidChrome).steps.join(" "), /pantalla de inicio/);
  assert.match(pinGuide(UA.desktopChrome).steps.join(" "), /Instalar/);
  assert.match(pinGuide(UA.desktopEdge).steps.join(" "), /Aplicaciones/);
  assert.match(pinGuide(UA.macSafari).steps.join(" "), /Agregar al Dock/);
});

test("un navegador que no permite fijarla lo dice", () => {
  const guide = pinGuide(UA.desktopFirefox);

  assert.deepEqual(guide.steps, []);
  assert.match(guide.note, /no permite fijarla/);
});

test("abierta ya fijada, no hay guía", () => {
  assert.equal(pinGuide(UA.androidChrome, { standalone: true }), null);
});
