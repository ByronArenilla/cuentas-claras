import pytest

from bot.config import (
    InvalidSettingError,
    MissingSettingError,
    Settings,
    load_settings,
)

VALID_ENV = {
    "TELEGRAM_BOT_TOKEN": "123:abc",
    "API_URL": "http://localhost:8000/",
    "BOT_API_KEY": "k" * 32,
    "TZ": "America/Bogota",
}


def test_all_missing_variables_are_named() -> None:
    with pytest.raises(MissingSettingError) as error:
        load_settings({})

    for name in VALID_ENV:
        assert name in str(error.value)


@pytest.mark.parametrize("missing", list(VALID_ENV))
def test_empty_variable_counts_as_missing(missing: str) -> None:
    with pytest.raises(MissingSettingError, match=missing):
        load_settings({**VALID_ENV, missing: "  "})


def test_invalid_time_zone_is_named() -> None:
    with pytest.raises(InvalidSettingError, match="TZ"):
        load_settings({**VALID_ENV, "TZ": "Marte/Olimpo"})


def test_settings_are_read_from_environment() -> None:
    settings = load_settings(VALID_ENV)

    assert settings == Settings(
        telegram_bot_token="123:abc",
        # Sin la `/` final, para armar las rutas como `<api_url>/spaces`.
        api_url="http://localhost:8000",
        bot_api_key="k" * 32,
        tz="America/Bogota",
    )


def test_secrets_are_hidden_from_repr() -> None:
    # Principio 12: ni el token de Telegram ni la llave salen al imprimir.
    text = repr(load_settings(VALID_ENV))

    assert "123:abc" not in text
    assert "k" * 32 not in text
