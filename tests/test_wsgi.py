"""Test the web app."""

import curies
import sssom_pydantic
from curies import NamableReference
from sssom_pydantic import MappingTool, SemanticMapping

from sssom_curator.constants import POSITIVES_NAME
from sssom_curator.web.components import Controller, State
from sssom_curator.web.impl import get_app
from tests import cases

TEST_USER = NamableReference(
    prefix="orcid", identifier="0000-0000-0000-0000", name="Max Mustermann"
)
TEST_MAPPING = SemanticMapping(
    subject=NamableReference.from_curie("chebi:131408", name="glyoxime"),
    predicate="skos:exactMatch",
    object=NamableReference.from_curie("mesh:C018305", name="glyoxal dioxime"),
    justification="semapv:ManualMappingCuration",
    confidence=0.95,
    mapping_tool=MappingTool(name="test", version=None),
)

TEST_CONVERTER = curies.Converter.from_prefix_map(
    {
        "chebi": "http://purl.obolibrary.org/obo/CHEBI_",
        "mesh": "http://id.nlm.nih.gov/mesh/",
        "semapv": "https://w3id.org/semapv/vocab/",
        "skos": "http://www.w3.org/2004/02/skos/core#",
    }
)


class TestWeb(cases.RepositoryTestCase):
    """Test the web app."""

    def setUp(self) -> None:
        """Set up the test case with a controller."""
        super().setUp()
        self.controller = Controller(
            user=TEST_USER,
            positives_path=self.repository.positives_path,
            negatives_path=self.repository.negatives_path,
            unsure_path=self.repository.unsure_path,
            predictions_path=self.repository.predictions_path,
            converter=TEST_CONVERTER,
        )

    def test_query(self) -> None:
        """Test making a query."""
        self.controller.count_predictions_from_state(State(query="chebi"))
        self.controller.count_predictions_from_state(State(prefix="chebi"))
        self.controller.count_predictions_from_state(State(source_prefix="chebi"))
        self.controller.count_predictions_from_state(State(source_query="chebi"))
        self.controller.count_predictions_from_state(State(target_prefix="chebi"))
        self.controller.count_predictions_from_state(State(target_query="chebi"))
        self.controller.count_predictions_from_state(State(provenance="orcid"))
        self.controller.count_predictions_from_state(State(provenance="mira"))
        self.controller.count_predictions_from_state(State(sort="desc"))
        self.controller.count_predictions_from_state(State(sort="asc"))
        self.controller.count_predictions_from_state(State(sort="object"))
        self.controller.count_predictions_from_state(State(same_text=True))
        self.controller.count_predictions_from_state(State(same_text=False))
        self.controller.count_predictions_from_state(State(show_relations=True))
        self.controller.count_predictions_from_state(State(show_relations=False))
        self.controller.count_predictions_from_state(State(show_lines=True))
        self.controller.count_predictions_from_state(State(show_lines=False))
        self.controller.count_predictions_from_state(State(limit=5))
        self.controller.count_predictions_from_state(State(limit=5_000_000))
        self.controller.count_predictions_from_state(State(offset=0))
        self.controller.count_predictions_from_state(State(offset=5_000_000))


class TestFull(cases.RepositoryTestCase):
    """Test a curation app."""

    def setUp(self) -> None:
        """Set up the test case."""
        super().setUp()
        self.controller = Controller(
            predictions_path=self.repository.predictions_path,
            positives_path=self.repository.positives_path,
            negatives_path=self.repository.negatives_path,
            unsure_path=self.repository.unsure_path,
            user=TEST_USER,
            converter=TEST_CONVERTER,
        )
        self.app = get_app(controller=self.controller)
        self.app.testing = True

    def test_mark_out_of_bounds(self) -> None:
        """Test trying to mark a number that's too big."""
        self.assertEqual(1, len(self.controller._predictions))
        self.assertEqual(0, len(self.controller._marked))

        # can't pop a number too big!
        with self.app.test_client() as client, self.assertRaises(IndexError):
            client.get("/mark/10000/yup")

        self.assertEqual(1, len(self.controller._predictions))
        self.assertEqual(0, len(self.controller._marked))

    def test_mark_correct(self) -> None:
        """A self-contained scenario for marking an entry correct."""
        self.assertEqual(1, len(self.controller._predictions))
        self.assertEqual(0, len(self.controller._marked))

        with self.app.test_client() as client:
            res = client.get("/mark/0/yup", follow_redirects=True)
            self.assertEqual(200, res.status_code, msg=res.text)

        # now, we have one less than before~
        self.assertEqual(0, len(self.controller._predictions))

        mappings, _converter, mapping_set = sssom_pydantic.read(self.controller.positives_path)
        self.assertIsNone(mapping_set.title)
        self.assertEqual(f"{self.purl_base}{POSITIVES_NAME}", mapping_set.id)
        self.assertEqual([], mappings)
