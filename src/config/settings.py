"""Application configuration loading for SYNAPSE."""

from dataclasses import dataclass
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib


@dataclass(frozen=True)
class ApplicationSettings:
    name: str
    environment: str
    model_version: str
    feature_version: str
    log_level: str


def load_settings(path: Path) -> ApplicationSettings:
    """Load application settings from a TOML configuration file."""
    with path.open("rb") as config_file:
        values = tomllib.load(config_file)

    application = values["application"]
    logging = values["logging"]
    return ApplicationSettings(
        name=application["name"],
        environment=application["environment"],
        model_version=application["model_version"],
        feature_version=application["feature_version"],
        log_level=logging["level"],
    )
