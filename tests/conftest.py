import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

from fakes import FakeHermesBridge, FakeTransport  # noqa: E402


@pytest.fixture
def bridge():
    return FakeHermesBridge()


@pytest.fixture
def transport():
    return FakeTransport()
