"""A test case with a repository."""

import tempfile
import unittest
from pathlib import Path
from typing import ClassVar

from sssom_pydantic import MappingSet

from sssom_curator import Repository
from sssom_curator.initialize import initialize_folder

__all__ = [
    "RepositoryTestCase",
]


class RepositoryTestCase(unittest.TestCase):
    """Test initializing a SSSOM curation folder."""

    purl_base: ClassVar[str | None] = "https://example.org/ms/components/"

    mapping_set: ClassVar[MappingSet | None] = MappingSet(
        id="https://example.org/ms/test.sssom.tsv",
    )

    directory: Path
    repository: Repository

    def setUp(self) -> None:
        """Set up the test case."""
        self.directory_obj = tempfile.TemporaryDirectory()
        self.directory = Path(self.directory_obj.name)
        self.repository = initialize_folder(
            self.directory,
            purl_base=self.purl_base,
            mapping_set=self.mapping_set,
        )
        self.repository.update_relative_paths(self.directory)

    def tearDown(self) -> None:
        """Tear down the test case."""
        self.directory_obj.cleanup()
