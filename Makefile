# Makefile — interfaz única del proyecto.
# Los nombres de los targets no cambian entre fases; solo cambia lo que hacen.

# Intérprete con el que se crea el entorno virtual. Se puede sobrescribir:
#   make install PYTHON=python3.12
PYTHON ?= python3

# La API (Python con su entorno virtual) y la web (HTML, CSS y JavaScript sin
# compilar, servidos en desarrollo por services/web/serve.py). El servidor de
# la web solo usa la biblioteca estándar, así que sus tests y su lint usan las
# herramientas del entorno de la API.
API_DIR := services/api
API_VENV := $(API_DIR)/.venv
API_BIN := $(API_VENV)/bin
WEB_DIR := services/web

# Estos targets no generan archivos con su nombre: se ejecutan siempre.
.PHONY: install run-api run-web test lint

# Crea el entorno virtual de la API (si no existe) y la instala en modo
# editable junto con sus herramientas de desarrollo.
install:
	test -d $(API_VENV) || $(PYTHON) -m venv $(API_VENV)
	$(API_BIN)/pip install --upgrade pip
	$(API_BIN)/pip install -e "$(API_DIR)[dev]"

# Carga .env (si existe) en el entorno de la receta: `set -a` exporta cada
# variable que el shell define al leerlo con `.`. Los tests no lo usan: su
# entorno lo fija tests/conftest.py.
LOAD_ENV := set -a; if [ -f .env ]; then . ./.env; fi; set +a

# Primero se importa la configuración: si falta una variable obligatoria el
# error la nombra y make se detiene (RF-33). Sin esta comprobación, el proceso
# de --reload de uvicorn mostraría el error pero seguiría vivo sin servir nada.
# --reload reinicia el servidor al cambiar el código (solo para desarrollo).
# BIND_HOST (por defecto 127.0.0.1) decide desde dónde se puede entrar: con
# 0.0.0.0 escucha también en la red de la casa, para probar desde el celular.
run-api:
	$(LOAD_ENV); cd $(API_DIR) \
		&& .venv/bin/python -c "import app.config" \
		&& .venv/bin/uvicorn app.main:app --reload --host $${BIND_HOST:-127.0.0.1} --port 8000

# La web en el puerto 8080, con la URL de la API de API_URL (spec 011).
run-web:
	$(LOAD_ENV); python3 $(WEB_DIR)/serve.py --host $${BIND_HOST:-127.0.0.1} --port 8080

# Los tests de la API; los del servidor de la web (pytest); y los de la lógica
# de la web con el test runner de Node, sin npm ni dependencias (spec 011).
test:
	cd $(API_DIR) && .venv/bin/pytest
	cd $(WEB_DIR) && ../api/.venv/bin/pytest tests
	node --test $(WEB_DIR)/tests/

# Lint y formato en modo comprobación: no modifica archivos.
lint:
	cd $(API_DIR) && .venv/bin/ruff check . && .venv/bin/ruff format --check .
	cd $(WEB_DIR) && ../api/.venv/bin/ruff check . && ../api/.venv/bin/ruff format --check .
