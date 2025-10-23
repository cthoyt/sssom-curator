"""Test initialization."""

import tempfile
import unittest
from pathlib import Path
from textwrap import dedent

from sssom_curator.initialize import initialize_folder

TEST_PURL_BASE = "https://example.com/test/"


class TestInitializeFolder(unittest.TestCase):
    """Test initializing a SSSOM curation folder."""

    def setUp(self) -> None:
        """Set up the test case."""
        self.directory_obj = tempfile.TemporaryDirectory()
        self.directory = Path(self.directory_obj.name)

    def tearDown(self) -> None:
        """Tear down the test case."""
        self.directory_obj.cleanup()

    def test_initialize_no_mapping_set(self) -> None:
        """Test initializing a SSSOM curation folder."""
        initialize_folder(self.directory)

        script_path = self.directory.joinpath("main.py")
        self.assertTrue(script_path.is_file())

        self.assertEqual(
            dedent("""\
                # /// script
                # requires-python = ">=3.10"
                # dependencies = [
                #     "sssom-curator[web,predict-lexical,exports]",
                # ]
                # ///

                \"\"\"SSSOM Curator.\"\"\"

                from sssom_curator import Repository
                from pathlib import Path

                HERE = Path(__file__).parent.resolve()

                repository = Repository(
                    positives_path=HERE.joinpath("positive.sssom.tsv"),
                    negatives_path=HERE.joinpath("negative.sssom.tsv"),
                    predictions_path=HERE.joinpath("predictions.sssom.tsv"),
                    unsure_path=HERE.joinpath("unsure.sssom.tsv"),
                )

                main = repository.get_cli()

                if __name__ == "__main__":
                    main()
            """).rstrip(),
            script_path.read_text().rstrip(),
        )

        readme_path = self.directory.joinpath("README.md")
        self.assertTrue(readme_path.is_file())
        self.assertEqual(
            dedent("""\
            # SSSOM Curator

            Run the curator with:

            ```console
            $ uv run main.py web
            ```

            Predict new mappings, e.g., between Medical Subject Headings (MeSH)
            and the Medical Actions Ontology (MaxO) with:

            ```console
            $ uv run main.py predict mesh maxo
            ```

            ## Colophon

            This repository was generated using SSSOM-Curator.
            """).rstrip(),
            readme_path.read_text().rstrip(),
        )
