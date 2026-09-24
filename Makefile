# Makefile — interfaz única del proyecto.
# Los nombres de los targets no cambian entre fases; solo cambia lo que hacen.

# Intérprete con el que se crea el entorno virtual. Se puede sobrescribir:
#   make install PYTHON=python3.12
PYTHON ?= python3

API_DIR := services/api
API_VENV := $(API_DIR)/.venv
API_BIN := $(API_VENV)/bin

# Estos targets no generan archivos con su nombre: se ejecutan siempre.
.PHONY: install run-api test lint

# Crea el entorno virtual de la API (si no existe) e instala la app en modo
# editable junto con las herramientas de desarrollo.
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
run-api:
	$(LOAD_ENV); cd $(API_DIR) \
		&& .venv/bin/python -c "import app.config" \
		&& .venv/bin/uvicorn app.main:app --reload --port 8000

test:
	cd $(API_DIR) && .venv/bin/pytest

# Lint y formato en modo comprobación: no modifica archivos.
lint:
	cd $(API_DIR) && .venv/bin/ruff check . && .venv/bin/ruff format --check .
