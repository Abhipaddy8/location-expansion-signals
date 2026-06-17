"""M0 smoke: the package imports and settings load."""

import signal_connector
from signal_connector.observability.logging import get_logger
from signal_connector.settings import settings


def test_version():
    assert signal_connector.__version__


def test_settings_load():
    assert settings.emit_threshold == 0.60
    assert settings.db_path.name == "signals.db"


def test_logger():
    log = get_logger("test")
    log.info("smoke", ok=True)
