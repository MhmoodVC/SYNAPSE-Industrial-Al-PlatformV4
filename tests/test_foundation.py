from pathlib import Path

from config.settings import load_settings
from utils.logging import configure_logging


PROJECT_ROOT = Path(__file__).parents[1]


def test_development_settings_load() -> None:
    settings = load_settings(PROJECT_ROOT / "configs" / "development.toml")

    assert settings.name == "SYNAPSE"
    assert settings.environment == "development"
    assert settings.model_version == "unimplemented"
    assert settings.feature_version == "unimplemented"
    assert settings.log_level == "INFO"


def test_logging_configuration_is_callable() -> None:
    configure_logging("INFO")
