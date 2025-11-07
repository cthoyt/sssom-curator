"""Test lexical mapping."""

import unittest
import unittest.mock

import pandas as pd
import ssslm
import sssom_pydantic
from curies import NamedReference
from curies.vocabulary import exact_match, manual_mapping_curation
from sssom_pydantic import SemanticMapping

from sssom_curator.predict.embedding import _calculate_similarities
from sssom_curator.predict.lexical import (
    _predict_lexical_mappings_all_by_all,
)
from tests import cases

a1 = NamedReference(prefix="mesh", identifier="C000089", name="ammeline")
b1 = NamedReference(prefix="chebi", identifier="28646", name="ammeline")


class TestLexical(unittest.TestCase):
    """Test lexical mappings."""

    def test_all_by_all(self) -> None:
        """Test all-by-all predictions."""
        literal_mappings = [
            ssslm.LiteralMapping(reference=a1, text="test"),
            ssslm.LiteralMapping(reference=b1, text="test"),
        ]
        grounder = ssslm.make_grounder(literal_mappings)
        if not isinstance(grounder, ssslm.GildaGrounder):
            self.fail()
        self.assertEqual(1, len(grounder._grounder.entries))

        mappings = list(_predict_lexical_mappings_all_by_all(grounder))
        self.assertEqual(1, len(mappings))
        mapping = mappings[0]
        self.assertEqual(a1.pair, mapping.object.pair)
        self.assertEqual(b1.pair, mapping.subject.pair)


class TestAppend(cases.RepositoryTestCase):
    """Test appending lexical predictions."""

    def test_append_lexical_predictions(self) -> None:
        """Test."""
        _, converter, _ = sssom_pydantic.read(self.repository.predictions_path)
        self.assertIsNone(converter.get_record(a1.prefix, strict=False))
        self.assertIsNone(converter.get_record(b1.prefix, strict=False))

        sm = SemanticMapping(
            subject=a1, predicate=exact_match, object=b1, justification=manual_mapping_curation
        )
        with unittest.mock.patch("sssom_curator.predict.lexical.get_predictions") as p:
            p.return_value = [sm]
            self.repository.append_lexical_predictions("a", "b")

        self.assertIn(sm, self.repository.read_predicted_mappings())
        self.assertNotIn(sm, self.repository.read_unsure_mappings())
        self.assertNotIn(sm, self.repository.read_negative_mappings())
        self.assertNotIn(sm, self.repository.read_positive_mappings())

        # Test that the prefixes got added properly
        _, converter, _ = sssom_pydantic.read(self.repository.predictions_path)
        self.assertIsNotNone(converter.get_record(a1.prefix, strict=False))
        self.assertIsNotNone(converter.get_record(b1.prefix, strict=False))


class TestEmbeddingSimilarity(unittest.TestCase):
    """Test embedding similarity."""

    def test_calculate_similarities(self) -> None:
        """Test calculating similarities in batch."""
        left_df = pd.DataFrame(
            [
                (0.0, 0.0, 1.0),
                (0.0, 1.0, 0.0),
                (1.0, 0.0, 0.0),
            ],
            index=["49E2512", "48C3522 ", "49G621"],
        )
        # iconclass:49E2512 	microscope 	chmo:0000102
        right_df = pd.DataFrame(
            [
                (0.0, 1.0, 1.0),
                (1.0, 1.0, 0.0),
                (1.0, 0.0, 1.0),
                (1.0, 1.0, 1.0),
            ],
            index=["0000005", "0000102", "0000953", "0001088"],
        )

        for batch_size, cutoff in [
            (2, -1),
            (10, -1),
            (2, 0),
            (10, 0),
        ]:
            unbatched = _calculate_similarities(
                left_df, right_df, batch_size=None, cutoff=cutoff, progress=False
            )
            batched_2 = _calculate_similarities(
                left_df, right_df, batch_size=batch_size, cutoff=cutoff, progress=False
            )
            self.assertEqual(
                sorted(unbatched),
                sorted(batched_2),
            )
