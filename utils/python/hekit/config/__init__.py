"""Configuration: schema 2, layering, validation (03).

    from hekit.config import load_config
    config = load_config("configs/PhotoProduction/eic.toml")
"""

from .model import Config, Study, load_config  # noqa: F401
from .fields import Field, Section  # noqa: F401
from .schema import SCHEMA_VERSION, SECTIONS  # noqa: F401
