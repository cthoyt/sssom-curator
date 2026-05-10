"""Tests for merging."""

import datetime
from textwrap import dedent

import curies
from curies.vocabulary import charlie, manual_mapping_curation
from sssom_pydantic import SemanticMapping

from sssom_curator.export.merge import _get_merged_sssom, merge
from sssom_curator.initialize import (
    EXAMPLE_NEGATIVE_MAPPING,
    EXAMPLE_POSITIVE_MAPPING,
    EXAMPLE_PREDICTED_MAPPING,
    EXAMPLE_UNSURE_MAPPING,
)
from tests import cases

TODAY = datetime.date.today()
TODAY_STR = TODAY.strftime("%Y-%m-%d")


class TestMerge(cases.RepositoryTestCase):
    """Test merge."""

    def setUp(self) -> None:
        """Set up the test case with an extra output directory."""
        super().setUp()
        self.output_directory = self.directory.joinpath("output")
        self.output_directory.mkdir()
        self.output_tsv_path = self.output_directory.joinpath(f"{self.directory.name}.sssom.tsv")

    @property
    def mapping_set_id(self) -> str:
        """Get the mapping set ID."""
        if self.mapping_set is None:
            raise ValueError
        return str(self.mapping_set.id)

    def assert_semantic_mappings_equal(
        self, expected: list[SemanticMapping], actual: list[SemanticMapping] | None
    ) -> None:
        """Assert semantic mapping lists are equal."""
        if actual is None:
            raise self.fail()
        self.assertEqual(
            [m.model_dump(exclude_none=True) for m in expected],
            [m.model_dump(exclude_none=True) for m in actual],
        )

    def test_merge_api(self) -> None:
        """Test the merge API works."""
        self.assertEqual(1, len(self.repository.read_positive_mappings()))
        self.assertEqual(1, len(self.repository.read_negative_mappings()))
        self.assertEqual(
            1,
            len(self.repository.read_predicted_mappings()),
            msg=f"predicted mappings not loaded from {self.repository.predictions_path}:"
            f"\n\n{self.repository.predictions_path.read_text()}",
        )
        self.assertEqual(
            1,
            len(self.repository.read_unsure_mappings()),
            msg=f"unsure mappings not loaded from {self.repository.unsure_path}:"
            f"\n\n{self.repository.unsure_path.read_text()}",
        )

        mappings, _converter = _get_merged_sssom(self.repository)
        self.assert_semantic_mappings_equal(
            [
                EXAMPLE_POSITIVE_MAPPING,
                EXAMPLE_NEGATIVE_MAPPING,
                EXAMPLE_PREDICTED_MAPPING,
                EXAMPLE_UNSURE_MAPPING,
            ],
            mappings,
        )

    def test_merge_empty(self) -> None:
        """Test merge works directly after initialization."""
        merge(self.repository, self.output_directory, output_owl=False, output_json=False)

        self.assertTrue(self.output_tsv_path.is_file())
        self.assertEqual(
            dedent(f"""\
                #curie_map:
                #  CHEBI: http://purl.obolibrary.org/obo/CHEBI_
                #  mesh: http://id.nlm.nih.gov/mesh/
                #  orcid: https://orcid.org/
                #  semapv: https://w3id.org/semapv/vocab/
                #  skos: http://www.w3.org/2004/02/skos/core#
                #  wikidata: http://www.wikidata.org/entity/
                #license: https://spdx.org/licenses/CC0-1.0
                #mapping_set_id: {self.mapping_set_id}
                #mapping_set_title: {self.directory.name}
                subject_id\tsubject_label\tpredicate_id\tpredicate_modifier\tobject_id\tobject_label\tmapping_justification\tauthor_id\treviewer_id\tmapping_tool\tmapping_tool_id\tmapping_tool_version\tmapping_date\treview_date\tconfidence\treviewer_agreement
                CHEBI:11986\t4-fluoro-L-threonine\tskos:exactMatch\t\tmesh:C048271\t4-fluorothreonine\tsemapv:ManualMappingCuration\torcid:0000-0003-4423-4370\t\t2026-05-08\t\t1.0\t
                CHEBI:10057\t9H-xanthene\tskos:exactMatch\tNot\tmesh:C002563\txanthan gum\tsemapv:ManualMappingCuration\torcid:0000-0003-4423-4370\t\t2026-05-08\t\t1.0\t
                CHEBI:61700\t(+)-valencene\tskos:exactMatch\t\tmesh:C506706\tvalencene\tsemapv:ManualMappingCuration\t\torcid:0000-0003-4423-4370\t\t2026-05-08\t\t0.0
                CHEBI:101096\tethoxzolamide\tskos:exactMatch\t\tmesh:C523270\t6-ethoxybenzothiazole-2-sulfonamide\tsemapv:LexicalMatching\t\t\t\t\t\t
            """).rstrip(),  # noqa:E501
            self.output_tsv_path.read_text().rstrip(),
        )

    def test_merge_with_curations(self) -> None:
        """Test adding some extra mappings that also have preferred prefixes."""
        mapping = SemanticMapping(
            subject=curies.NamedReference(prefix="chebi", identifier="10001", name="Visnadin"),
            predicate=curies.NamableReference(prefix="skos", identifier="exactMatch"),
            object=curies.NamedReference(prefix="mesh", identifier="C067604", name="visnadin"),
            justification=manual_mapping_curation,
            authors=[charlie],
        )
        self.repository.append_positive_mappings([mapping])

        merge(self.repository, self.output_directory, output_owl=False, output_json=False)

        self.assertTrue(self.output_tsv_path.is_file())
        # note that `chebi` gets capitalized to `CHEBI` because of Bioregistry preferred prefixes
        self.assertEqual(
            dedent(f"""\
                #curie_map:
                #  CHEBI: http://purl.obolibrary.org/obo/CHEBI_
                #  mesh: http://id.nlm.nih.gov/mesh/
                #  orcid: https://orcid.org/
                #  semapv: https://w3id.org/semapv/vocab/
                #  skos: http://www.w3.org/2004/02/skos/core#
                #  wikidata: http://www.wikidata.org/entity/
                #license: https://spdx.org/licenses/CC0-1.0
                #mapping_set_id: {self.mapping_set_id}
                #mapping_set_title: {self.directory.name}
                subject_id\tsubject_label\tpredicate_id\tpredicate_modifier\tobject_id\tobject_label\tmapping_justification\tauthor_id\treviewer_id\tmapping_tool\tmapping_tool_id\tmapping_tool_version\tmapping_date\treview_date\tconfidence\treviewer_agreement
                CHEBI:10001\tVisnadin\tskos:exactMatch\t\tmesh:C067604\tvisnadin\tsemapv:ManualMappingCuration\torcid:0000-0003-4423-4370\t\t\t\t\t
                CHEBI:11986\t4-fluoro-L-threonine\tskos:exactMatch\t\tmesh:C048271\t4-fluorothreonine\tsemapv:ManualMappingCuration\torcid:0000-0003-4423-4370\t\t2026-05-08\t\t1.0\t
                CHEBI:10057\t9H-xanthene\tskos:exactMatch\tNot\tmesh:C002563\txanthan gum\tsemapv:ManualMappingCuration\torcid:0000-0003-4423-4370\t\t2026-05-08\t\t1.0\t
                CHEBI:61700\t(+)-valencene\tskos:exactMatch\t\tmesh:C506706\tvalencene\tsemapv:ManualMappingCuration\t\torcid:0000-0003-4423-4370\t\t2026-05-08\t\t0.0
                CHEBI:101096\tethoxzolamide\tskos:exactMatch\t\tmesh:C523270\t6-ethoxybenzothiazole-2-sulfonamide\tsemapv:LexicalMatching\t\t\t\t\t\t
      """).rstrip(),  # noqa:E501
            self.output_tsv_path.read_text().rstrip(),
        )

    def test_merge_with_curations_no_standardization(self) -> None:
        """Test adding some extra mappings that also have preferred prefixes."""
        self.repository.merge_standardize_bioregistry = False
        mapping = SemanticMapping(
            subject=curies.NamedReference(prefix="chebi", identifier="10001", name="Visnadin"),
            predicate=curies.Reference(prefix="skos", identifier="exactMatch"),
            object=curies.NamedReference(prefix="mesh", identifier="C067604", name="visnadin"),
            justification=manual_mapping_curation,
            authors=[charlie],
        )
        self.repository.append_positive_mappings([mapping])

        merge(self.repository, self.output_directory, output_owl=False, output_json=False)

        self.assertTrue(self.output_tsv_path.is_file())
        # note that `chebi` doesn't get capitalized because this test explicitly turns
        # off bioregistry normalization. The MeSH URI is also the non-RDF one here, too
        self.assertEqual(
            dedent(f"""\
                #curie_map:
                #  CHEBI: http://purl.obolibrary.org/obo/CHEBI_
                #  ex: https://example.org/
                #  mesh: https://meshb.nlm.nih.gov/record/ui?ui=
                #  orcid: https://orcid.org/
                #  semapv: https://w3id.org/semapv/vocab/
                #  skos: http://www.w3.org/2004/02/skos/core#
                #  wikidata: http://www.wikidata.org/entity/
                #license: https://spdx.org/licenses/CC0-1.0
                #mapping_set_id: {self.mapping_set_id}
                #mapping_set_title: {self.directory.name}
                subject_id\tsubject_label\tpredicate_id\tpredicate_modifier\tobject_id\tobject_label\tmapping_justification\tauthor_id\treviewer_id\tmapping_tool\tmapping_tool_id\tmapping_tool_version\tmapping_date\treview_date\tconfidence\treviewer_agreement
                CHEBI:10001\tVisnadin\tskos:exactMatch\t\tmesh:C067604\tvisnadin\tsemapv:ManualMappingCuration\torcid:0000-0003-4423-4370\t\t\t\t\t
                CHEBI:11986\t4-fluoro-L-threonine\tskos:exactMatch\t\tmesh:C048271\t4-fluorothreonine\tsemapv:ManualMappingCuration\torcid:0000-0003-4423-4370\t\t2026-05-08\t\t1.0\t
                CHEBI:10057\t9H-xanthene\tskos:exactMatch\tNot\tmesh:C002563\txanthan gum\tsemapv:ManualMappingCuration\torcid:0000-0003-4423-4370\t\t2026-05-08\t\t1.0\t
                CHEBI:61700\t(+)-valencene\tskos:exactMatch\t\tmesh:C506706\tvalencene\tsemapv:ManualMappingCuration\t\torcid:0000-0003-4423-4370\t\t2026-05-08\t\t0.0
                CHEBI:101096\tethoxzolamide\tskos:exactMatch\t\tmesh:C523270\t6-ethoxybenzothiazole-2-sulfonamide\tsemapv:LexicalMatching\t\t\t\t\t\t
            """).rstrip(),  # noqa:E501
            self.output_tsv_path.read_text().rstrip(),
        )
