"""Test the web app."""

from collections.abc import Sequence
from pathlib import Path
from typing import ClassVar

import curies
import sssom_pydantic
from curies import NamedReference, Reference
from curies.vocabulary import (
    broad_match,
    exact_match,
    lexical_matching_process,
    manual_mapping_curation,
    narrow_match,
)
from pydantic import BaseModel
from sssom_pydantic import MappingTool, SemanticMapping

from sssom_curator.constants import NEGATIVES_NAME, POSITIVES_NAME, UNSURE_NAME
from sssom_curator.web.components import Controller, State
from sssom_curator.web.impl import get_app
from sssom_pydantic.process import UNSURE
from tests import cases

TEST_USER = Reference(prefix="orcid", identifier="0000-0000-0000-0000")
TEST_POSITIVE_MAPPING = SemanticMapping(
    subject=NamedReference.from_curie("chebi:131408", name="glyoxime"),
    predicate=exact_match,
    object=NamedReference.from_curie("mesh:C018305", name="glyoxal dioxime"),
    justification=manual_mapping_curation.pair.to_pydantic(),
)
TEST_PREDICTED_MAPPING = SemanticMapping(
    subject=NamedReference.from_curie("chebi:133530", name="tyramine sulfate"),
    predicate=exact_match,
    object=NamedReference.from_curie("mesh:C027957", name="tyramine O-sulfate"),
    justification=lexical_matching_process.pair.to_pydantic(),
    confidence=0.95,
    mapping_tool=MappingTool(name="test", version=None),
)
TEST_PREDICTED_MAPPING_MARKED_TRUE = SemanticMapping(
    subject=NamedReference.from_curie("chebi:133530", name="tyramine sulfate"),
    predicate=exact_match,
    object=NamedReference.from_curie("mesh:C027957", name="tyramine O-sulfate"),
    justification=manual_mapping_curation.pair.to_pydantic(),
    authors=[TEST_USER],
)
TEST_PREDICTED_MAPPING_MARKED_UNSURE = SemanticMapping(
    subject=NamedReference.from_curie("chebi:133530", name="tyramine sulfate"),
    predicate=exact_match,
    object=NamedReference.from_curie("mesh:C027957", name="tyramine O-sulfate"),
    justification=lexical_matching_process.pair.to_pydantic(),
    confidence=0.95,
    mapping_tool=MappingTool(name="test", version=None),
    curation_rule_text=[UNSURE],
)
TEST_PREDICTED_MAPPING_MARKED_BROAD = SemanticMapping(
    subject=NamedReference.from_curie("chebi:133530", name="tyramine sulfate"),
    predicate=broad_match,
    object=NamedReference.from_curie("mesh:C027957", name="tyramine O-sulfate"),
    justification=manual_mapping_curation.pair.to_pydantic(),
    authors=[TEST_USER],
)
TEST_PREDICTED_MAPPING_MARKED_NARROW = SemanticMapping(
    subject=NamedReference.from_curie("chebi:133530", name="tyramine sulfate"),
    predicate=narrow_match,
    object=NamedReference.from_curie("mesh:C027957", name="tyramine O-sulfate"),
    justification=manual_mapping_curation.pair.to_pydantic(),
    authors=[TEST_USER],
)
TEST_PREDICTED_MAPPING_MARKED_FALSE = SemanticMapping(
    subject=NamedReference.from_curie("chebi:133530", name="tyramine sulfate"),
    predicate=exact_match,
    object=NamedReference.from_curie("mesh:C027957", name="tyramine O-sulfate"),
    justification=manual_mapping_curation.pair.to_pydantic(),
    authors=[TEST_USER],
    predicate_modifier="Not",
)

TEST_CONVERTER = curies.Converter.from_prefix_map(
    {
        "chebi": "http://purl.obolibrary.org/obo/CHEBI_",
        "mesh": "http://id.nlm.nih.gov/mesh/",
        "semapv": "https://w3id.org/semapv/vocab/",
        "skos": "http://www.w3.org/2004/02/skos/core#",
    }
)


class TestFull(cases.RepositoryTestCase):
    """Test a curation app."""

    positive_seed: ClassVar[list[SemanticMapping]] = [TEST_POSITIVE_MAPPING]
    predicted_seed: ClassVar[list[SemanticMapping]] = [TEST_PREDICTED_MAPPING]
    negative_seed: ClassVar[list[SemanticMapping]] = []
    unsure_seed: ClassVar[list[SemanticMapping]] = []
    converter_seed: ClassVar[curies.Converter] = TEST_CONVERTER

    def setUp(self) -> None:
        """Set up the test case."""
        super().setUp()
        self.controller = Controller(
            repository=self.repository,
            user=TEST_USER,
            converter=TEST_CONVERTER,
        )
        self.app = get_app(controller=self.controller)
        self.app.testing = True

        self.assert_file_mapping_count(self.repository.predictions_path, 1)
        self.assert_file_mapping_count(self.repository.positives_path, 1)
        self.assert_file_mapping_count(self.repository.negatives_path, 0)
        self.assert_file_mapping_count(self.repository.unsure_path, 0)

        self.test_prediction_record_curie = self.controller.mapping_hash(
            TEST_PREDICTED_MAPPING
        ).curie

    def assert_file_mapping_count(self, path: Path, n: int) -> None:
        """Check that a SSSOM file has the right number of mappings."""
        self.assertTrue(path.is_file())
        mappings, _, _ = sssom_pydantic.read(path)
        self.assertEqual(n, len(mappings), msg=f"{path.name} had the wrong number of mappings")

    def assert_models_equal(
        self, expected: Sequence[BaseModel], actual: Sequence[BaseModel]
    ) -> None:
        """Assert that a list of models are equal."""
        self.assertEqual(
            [m.model_dump(exclude_none=True, exclude_unset=True) for m in expected],
            [m.model_dump(exclude_none=True, exclude_unset=True) for m in actual],
        )

    def test_query(self) -> None:
        """Test making a query."""
        self.controller.count_predictions(State(query="chebi"))
        self.controller.count_predictions(State(prefix="chebi"))
        self.controller.count_predictions(State(subject_prefix="chebi"))
        self.controller.count_predictions(State(subject_query="chebi"))
        self.controller.count_predictions(State(object_prefix="chebi"))
        self.controller.count_predictions(State(object_query="chebi"))
        self.controller.count_predictions(State(mapping_tool="orcid"))
        self.controller.count_predictions(State(mapping_tool="mira"))
        self.controller.count_predictions(State(sort="desc"))
        self.controller.count_predictions(State(sort="asc"))
        self.controller.count_predictions(State(sort="object"))
        self.controller.count_predictions(State(same_text=True))
        self.controller.count_predictions(State(same_text=False))
        self.controller.count_predictions(State(show_relations=True))
        self.controller.count_predictions(State(show_relations=False))
        self.controller.count_predictions(State(show_lines=True))
        self.controller.count_predictions(State(show_lines=False))
        self.controller.count_predictions(State(limit=5))
        self.controller.count_predictions(State(limit=5_000_000))
        self.controller.count_predictions(State(offset=0))
        self.controller.count_predictions(State(offset=5_000_000))

    def test_mark_out_of_bounds(self) -> None:
        """Test trying to mark a number that's too big."""
        self.assertEqual(1, len(self.controller._predictions))

        # can't pop a number too big!
        with self.app.test_client() as client, self.assertRaises(KeyError):
            client.get("/mark/nope:nope/correct")

        self.assertEqual(1, len(self.controller._predictions))

    def test_bad_mark(self) -> None:
        """Test an incorrect mark."""
        with self.app.test_client() as client:
            res = client.get(f"/mark/{self.test_prediction_record_curie}/bad-call")
            self.assertEqual(400, res.status_code)

    def test_mark_correct(self) -> None:
        """A self-contained scenario for marking an entry correct."""
        self.assertEqual(1, len(self.controller._predictions))

        with self.app.test_client() as client:
            res = client.get(
                f"/mark/{self.test_prediction_record_curie}/correct", follow_redirects=True
            )
            self.assertEqual(200, res.status_code, msg=res.text)

        # now, we have one less than before~
        self.assertEqual(0, len(self.controller._predictions))

        mappings, _converter, mapping_set = sssom_pydantic.read(
            self.controller.repository.positives_path
        )
        self.assertIsNone(mapping_set.title)
        self.assertEqual(f"{self.purl_base}{POSITIVES_NAME}", mapping_set.id)
        self.assert_models_equal(
            [TEST_POSITIVE_MAPPING, TEST_PREDICTED_MAPPING_MARKED_TRUE], mappings
        )

        self.assert_file_mapping_count(self.controller.repository.negatives_path, 0)
        self.assert_file_mapping_count(self.controller.repository.predictions_path, 0)
        self.assert_file_mapping_count(self.controller.repository.unsure_path, 0)

    def test_mark_incorrect(self) -> None:
        """A self-contained scenario for marking an entry incorrect."""
        self.assertEqual(1, len(self.controller._predictions))

        with self.app.test_client() as client:
            res = client.get(
                f"/mark/{self.test_prediction_record_curie}/incorrect", follow_redirects=True
            )
            self.assertEqual(200, res.status_code, msg=res.text)

        # now, we have one less than before~
        self.assertEqual(0, len(self.controller._predictions))

        mappings, _converter, mapping_set = sssom_pydantic.read(
            self.controller.repository.negatives_path
        )
        self.assertIsNone(mapping_set.title)
        self.assertEqual(f"{self.purl_base}{NEGATIVES_NAME}", mapping_set.id)
        self.assert_models_equal([TEST_PREDICTED_MAPPING_MARKED_FALSE], mappings)

        self.assert_file_mapping_count(self.controller.repository.positives_path, 1)
        self.assert_file_mapping_count(self.controller.repository.predictions_path, 0)
        self.assert_file_mapping_count(self.controller.repository.unsure_path, 0)

    def test_mark_unsure(self) -> None:
        """A self-contained scenario for marking an entry as unsure."""
        self.assertEqual(1, len(self.controller._predictions))

        with self.app.test_client() as client:
            res = client.get(
                f"/mark/{self.test_prediction_record_curie}/unsure", follow_redirects=True
            )
            self.assertEqual(200, res.status_code, msg=res.text)

        # now, we have one less than before~
        self.assertEqual(0, len(self.controller._predictions))

        mappings, _converter, mapping_set = sssom_pydantic.read(
            self.controller.repository.unsure_path
        )
        self.assertIsNone(mapping_set.title)
        self.assertEqual(f"{self.purl_base}{UNSURE_NAME}", mapping_set.id)
        self.assert_models_equal([TEST_PREDICTED_MAPPING_MARKED_UNSURE], mappings)

        self.assert_file_mapping_count(self.controller.repository.positives_path, 1)
        self.assert_file_mapping_count(self.controller.repository.predictions_path, 0)
        self.assert_file_mapping_count(self.controller.repository.negatives_path, 0)

    def test_mark_broad(self) -> None:
        """A self-contained scenario for marking an entry as broad."""
        self.assertEqual(1, len(self.controller._predictions))

        with self.app.test_client() as client:
            res = client.get(
                f"/mark/{self.test_prediction_record_curie}/BROAD", follow_redirects=True
            )
            self.assertEqual(200, res.status_code, msg=res.text)

        # now, we have one less than before~
        self.assertEqual(0, len(self.controller._predictions))

        mappings, _converter, mapping_set = sssom_pydantic.read(
            self.controller.repository.positives_path
        )
        self.assertIsNone(mapping_set.title)
        self.assertEqual(f"{self.purl_base}{POSITIVES_NAME}", mapping_set.id)
        self.assert_models_equal(
            [TEST_POSITIVE_MAPPING, TEST_PREDICTED_MAPPING_MARKED_BROAD], mappings
        )

        self.assert_file_mapping_count(self.controller.repository.negatives_path, 0)
        self.assert_file_mapping_count(self.controller.repository.predictions_path, 0)
        self.assert_file_mapping_count(self.controller.repository.unsure_path, 0)

    def test_mark_narrow(self) -> None:
        """A self-contained scenario for marking an entry as narrow."""
        self.assertEqual(1, len(self.controller._predictions))

        with self.app.test_client() as client:
            res = client.get(
                f"/mark/{self.test_prediction_record_curie}/NARROW", follow_redirects=True
            )
            self.assertEqual(200, res.status_code, msg=res.text)

        # now, we have one less than before~
        self.assertEqual(0, len(self.controller._predictions))

        mappings, _converter, mapping_set = sssom_pydantic.read(
            self.controller.repository.positives_path
        )
        self.assertIsNone(mapping_set.title)
        self.assertEqual(f"{self.purl_base}{POSITIVES_NAME}", mapping_set.id)
        self.assert_models_equal(
            [TEST_POSITIVE_MAPPING, TEST_PREDICTED_MAPPING_MARKED_NARROW], mappings
        )

        self.assert_file_mapping_count(self.controller.repository.negatives_path, 0)
        self.assert_file_mapping_count(self.controller.repository.predictions_path, 0)
        self.assert_file_mapping_count(self.controller.repository.unsure_path, 0)
