import os

import pytest


@pytest.fixture(autouse=True)
def _dbee_env_is_put_back():
    """`config.apply_env` writes DBEE_* into the process (as the service does): each
    test gets the environment back as it found it, so no test reads another's."""
    kept = {k: v for k, v in os.environ.items() if k.startswith("DBEE_")}
    yield
    for k in [k for k in os.environ if k.startswith("DBEE_")]:
        if k not in kept:
            del os.environ[k]
    os.environ.update(kept)
