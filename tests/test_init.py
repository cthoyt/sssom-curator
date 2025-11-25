"""Test initialization."""

import tempfile
import unittest
from pathlib import Path
from textwrap import dedent

from sssom_pydantic import MappingSet

from sssom_curator.constants import NEGATIVES_NAME, POSITIVES_NAME, PREDICTIONS_NAME
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

    def test_initialize(self) -> None:
        """Test initializing a SSSOM curation folder."""
        initialize_folder(
            self.directory,
            purl_base="https://example.org/ms/components/",
            mapping_set=MappingSet(
                id="https://example.org/ms/test.sssom.tsv",
            ),
        )

        script_path = self.directory.joinpath("main.py")
        self.assertTrue(script_path.is_file())

        self.assertEqual(
            dedent(f"""\
                #!/usr/bin/env -S uv run --script

                # /// script
                # requires-python = ">=3.10"
                # dependencies = [
                #     "sssom-curator[web,predict-lexical,exports]",
                # ]
                # ///

                \"\"\"SSSOM Curator for {self.directory.name}.\"\"\"

                from sssom_curator import Repository
                from pathlib import Path

                HERE = Path(__file__).parent.resolve()

                repository_path = HERE.joinpath("sssom-curator.json")
                repository = Repository.model_validate_json(repository_path.read_text())

                if __name__ == "__main__":
                    repository.run_cli()
            """).rstrip(),
            script_path.read_text().rstrip(),
        )

        readme_path = self.directory.joinpath("README.md")
        self.assertTrue(readme_path.is_file())
        self.assertEqual(
            dedent("""\
        # SSSOM Curator

        ## Workflows

        Predict new mappings, e.g., between Medical Subject Headings (MeSH)
        and the Medical Actions Ontology (MaxO) with:

        ```console
        $ uv run main.py predict lexical mesh maxo
        ```

        Run the curator with:

        ```console
        $ uv run main.py web
        ```

        ### Export

        Output summary charts and tables with:

        ```console
        $ mkdir output/
        $ uv run main.py summarize --output-directory output/
        ```

        Merge the positive, negative, and predicted mappings together
        and output several SSSOM flavors (TSV, OWL, JSON) in a given directory with:

        ```console
        $ mkdir sssom/
        $ uv run main.py merge --sssom-directory sssom/
        ```

        ### Maintenance

        Format/lint the mappings with:

        ```console
        $ uv run main.py lint
        ```

        Test the integrity of mappings with:

        ```console
        $ uv run main.py test
        ```

        ## License

        Semantic mappings curated in this directory are licensed under the
        [Creative Commons Zero v1.0 Universal (CC0-1.0) License](https://creativecommons.org/publicdomain/zero/1.0/legalcode).

        ## Colophon

        This repository was generated using [SSSOM-Curator](https://github.com/cthoyt/sssom-curator).
            """),
            readme_path.read_text(),
        )

        positives_path = self.directory.joinpath("data", POSITIVES_NAME)
        self.assertTrue(positives_path.is_file())
        self.assertEqual(
            dedent(f"""\
                #curie_map:
                #  ex: https://example.org/
                #  skos: http://www.w3.org/2004/02/skos/core#
                #mapping_set_id: https://example.org/ms/components/{POSITIVES_NAME}
                subject_id\tsubject_label\tpredicate_id\tobject_id\tobject_label\tmapping_justification\tauthor_id
                ex:1\t1\tskos:exactMatch\tex:2\t2\tsemapv:ManualMappingCuration\torcid:0000-0003-4423-4370
            """).rstrip(),
            positives_path.read_text().rstrip(),
        )

        negatives_path = self.directory.joinpath("data", NEGATIVES_NAME)
        self.assertTrue(negatives_path.is_file())
        self.assertEqual(
            dedent(f"""\
                    #curie_map:
                    #  ex: https://example.org/
                    #  skos: http://www.w3.org/2004/02/skos/core#
                    #mapping_set_id: https://example.org/ms/components/{NEGATIVES_NAME}
                    subject_id\tsubject_label\tpredicate_id\tpredicate_modifier\tobject_id\tobject_label\tmapping_justification\tauthor_id
                    ex:3\t3\tskos:exactMatch\tNot\tex:4\t4\tsemapv:ManualMappingCuration\torcid:0000-0003-4423-4370
                """).rstrip(),
            negatives_path.read_text().rstrip(),
        )

        predictions_path = self.directory.joinpath("data", PREDICTIONS_NAME)
        self.assertTrue(predictions_path.is_file())
        self.assertEqual(
            dedent(f"""\
                #curie_map:
                #  ex: https://example.org/
                #  skos: http://www.w3.org/2004/02/skos/core#
                #mapping_set_id: https://example.org/ms/components/{PREDICTIONS_NAME}
                subject_id\tsubject_label\tpredicate_id\tobject_id\tobject_label\tmapping_justification
                ex:7\t7\tskos:exactMatch\tex:8\t8\tsemapv:LexicalMatching
            """).rstrip(),
            predictions_path.read_text().rstrip(),
        )
