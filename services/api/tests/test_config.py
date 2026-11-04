import os
import subprocess
import sys

import pytest

from app.config import (
    InvalidSettingError,
    MissingSettingError,
    Settings,
    load_settings,
)

VALID_ENV = {
    "DATABASE_URL": "sqlite://",
    "TZ": "America/Bogota",
    "WEB_BASE_URL": "http://localhost:8080",
    "BOT_API_KEY": "k" * 32,
}


def import_config_with(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """Importa la configuración en un proceso nuevo con el entorno indicado."""
    base = {key: value for key, value in os.environ.items() if key not in VALID_ENV}
    return subprocess.run(
        [sys.executable, "-c", "import app.config"],
        env={**base, **env},
        capture_output=True,
        text=True,
    )


def test_import_fails_without_database_url() -> None:
    env = {key: value for key, value in VALID_ENV.items() if key != "DATABASE_URL"}
    result = import_config_with(env)

    assert result.returncode != 0
    assert "DATABASE_URL" in result.stderr


def test_import_succeeds_with_required_variables() -> None:
    result = import_config_with(VALID_ENV)

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "missing", ["DATABASE_URL", "TZ", "WEB_BASE_URL", "BOT_API_KEY"]
)
def test_missing_variable_is_named(missing: str) -> None:
    env = {key: value for key, value in VALID_ENV.items() if key != missing}

    with pytest.raises(MissingSettingError, match=missing):
        load_settings(env)


def test_all_missing_variables_are_named() -> None:
    with pytest.raises(MissingSettingError) as error:
        load_settings({})

    assert "DATABASE_URL" in str(error.value)
    assert "TZ" in str(error.value)
    assert "WEB_BASE_URL" in str(error.value)
    assert "BOT_API_KEY" in str(error.value)


@pytest.mark.parametrize("value", ["", "   "])
def test_empty_value_counts_as_missing(value: str) -> None:
    with pytest.raises(MissingSettingError, match="DATABASE_URL"):
        load_settings({**VALID_ENV, "DATABASE_URL": value})


def test_settings_are_read_from_environment() -> None:
    settings = load_settings(VALID_ENV)

    assert settings == Settings(
        database_url="sqlite://",
        tz="America/Bogota",
        web_base_url="http://localhost:8080",
        bot_api_key="k" * 32,
    )


def test_settings_repr_hides_the_bot_api_key() -> None:
    assert "k" * 32 not in repr(load_settings(VALID_ENV))


@pytest.mark.parametrize("value", ["Marte/Olimpo", "../Marte"])
def test_invalid_time_zone_is_named(value: str) -> None:
    # Sin esta comprobación la API arrancaría y cada petición de gastos
    # fallaría con 500 al calcular "hoy" (plan 003).
    with pytest.raises(InvalidSettingError, match="TZ"):
        load_settings({**VALID_ENV, "TZ": value})


def test_import_fails_with_invalid_time_zone() -> None:
    result = import_config_with({**VALID_ENV, "TZ": "Marte/Olimpo"})

    assert result.returncode != 0
    assert "TZ" in result.stderr


@pytest.mark.parametrize("value", ["http://localhost:8080/", "http://localhost:8080//"])
def test_trailing_slash_is_removed_from_web_base_url(value: str) -> None:
    # Sin esto, el enlace de invitación saldría con `//unirse` (RF-15).
    settings = load_settings({**VALID_ENV, "WEB_BASE_URL": value})

    assert settings.web_base_url == "http://localhost:8080"


# --- Llave del bot (spec 005) ---


def test_empty_bot_api_key_counts_as_missing() -> None:
    with pytest.raises(MissingSettingError, match="BOT_API_KEY"):
        load_settings({**VALID_ENV, "BOT_API_KEY": "   "})


def test_short_bot_api_key_is_rejected_and_named() -> None:
    # Una llave corta se adivina; mejor no arrancar (plan 005).
    with pytest.raises(InvalidSettingError, match="BOT_API_KEY"):
        load_settings({**VALID_ENV, "BOT_API_KEY": "k" * 31})


def test_bot_api_key_of_32_characters_is_loaded() -> None:
    assert load_settings(VALID_ENV).bot_api_key == "k" * 32


def test_the_error_never_shows_the_key() -> None:
    # Principio 12: el valor de un secreto no sale en los mensajes.
    with pytest.raises(InvalidSettingError) as error:
        load_settings({**VALID_ENV, "BOT_API_KEY": "secreto-corto"})
    assert "secreto-corto" not in str(error.value)
