import os
import subprocess
import sys

import pytest

from app.config import MissingSettingError, Settings, load_settings

VALID_ENV = {"DATABASE_URL": "sqlite://", "TZ": "America/Bogota"}


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
    result = import_config_with({"TZ": "America/Bogota"})

    assert result.returncode != 0
    assert "DATABASE_URL" in result.stderr


def test_import_succeeds_with_required_variables() -> None:
    result = import_config_with(VALID_ENV)

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("missing", ["DATABASE_URL", "TZ"])
def test_missing_variable_is_named(missing: str) -> None:
    env = {key: value for key, value in VALID_ENV.items() if key != missing}

    with pytest.raises(MissingSettingError, match=missing):
        load_settings(env)


def test_all_missing_variables_are_named() -> None:
    with pytest.raises(MissingSettingError) as error:
        load_settings({})

    assert "DATABASE_URL" in str(error.value)
    assert "TZ" in str(error.value)


@pytest.mark.parametrize("value", ["", "   "])
def test_empty_value_counts_as_missing(value: str) -> None:
    with pytest.raises(MissingSettingError, match="DATABASE_URL"):
        load_settings({**VALID_ENV, "DATABASE_URL": value})


def test_settings_are_read_from_environment() -> None:
    settings = load_settings(VALID_ENV)

    assert settings == Settings(database_url="sqlite://", tz="America/Bogota")
