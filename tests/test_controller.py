"""Test controllers."""

import tempfile
from pathlib import Path
from typing import ClassVar

from sssom_curator.web.components import AbstractController, Controller
from sssom_curator.web.database import DatabaseController
from tests import wsgi_cases


class TestFilepathController(wsgi_cases.TestWSGI):
    """Test the filepath controller."""

    controller_cls: ClassVar[type[AbstractController]] = Controller

    def setUp(self) -> None:
        """Set up the test case."""
        self.controller_kwargs = {}
        super().setUp()


class TestDatabaseController(wsgi_cases.TestWSGI):
    """Test the database controller."""

    controller_cls: ClassVar[type[DatabaseController]] = DatabaseController
    controller: DatabaseController

    def setUp(self) -> None:
        """Set up the test case."""
        self.td = tempfile.TemporaryDirectory()
        self.connection_path = Path(self.td.name).joinpath("test.db")
        self.connection = f"sqlite:///{self.connection_path}"
        self.controller_kwargs = {
            "connection": self.connection,
            "add_date": False,
            "populate": True,
        }
        super().setUp()

    def tearDown(self) -> None:
        """Tear down the test case."""
        self.td.cleanup()
