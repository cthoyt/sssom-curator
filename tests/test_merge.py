"""Tests for merging."""

from textwrap import dedent

import curies
from curies.vocabulary import charlie, manual_mapping_curation
from sssom_pydantic import SemanticMapping

from sssom_curator.export.merge import merge
from tests import cases


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
        return self.mapping_set.id

    def test_merge_empty(self) -> None:
        """Test merge works directly after initialization."""
        merge(self.repository, self.output_directory, output_owl=False, output_json=False)

        self.assertTrue(self.output_tsv_path.is_file())
        self.assertEqual(
            dedent(f"""\
                #curie_map:
                #  ex: https://example.org/
                #  orcid: https://orcid.org/
                #  semapv: https://w3id.org/semapv/vocab/
                #  skos: http://www.w3.org/2004/02/skos/core#
                #license: spdx:CC0-1.0
                #mapping_set_id: {self.mapping_set_id}
                #mapping_set_title: {self.directory.name}
                subject_id\tsubject_label\tpredicate_id\tpredicate_modifier\tobject_id\tobject_label\tmapping_justification\tauthor_id\tconfidence
                ex:1\t1\tskos:exactMatch\t\tex:2\t2\tsemapv:ManualMappingCuration\torcid:0000-0003-4423-4370\t
                ex:3\t3\tskos:exactMatch\tNot\tex:4\t4\tsemapv:ManualMappingCuration\torcid:0000-0003-4423-4370\t
                ex:7\t7\tskos:exactMatch\t\tex:8\t8\tsemapv:LexicalMatching\t\t0.77
            """).rstrip(),
            self.output_tsv_path.read_text().rstrip(),
        )

    def test_merge_with_curations(self) -> None:
        """Test adding some extra mappings that also have preferred prefixes."""
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
        # note that `chebi` gets capitalized to `CHEBI` because of Bioregistry preferred prefixes
        self.assertEqual(
            dedent(f"""\
                #curie_map:
                #  CHEBI: http://purl.obolibrary.org/obo/CHEBI_
                #  ex: https://example.org/
                #  mesh: http://id.nlm.nih.gov/mesh/
                #  orcid: https://orcid.org/
                #  semapv: https://w3id.org/semapv/vocab/
                #  skos: http://www.w3.org/2004/02/skos/core#
                #license: spdx:CC0-1.0
                #mapping_set_id: {self.mapping_set_id}
                #mapping_set_title: {self.directory.name}
                subject_id\tsubject_label\tpredicate_id\tpredicate_modifier\tobject_id\tobject_label\tmapping_justification\tauthor_id\tconfidence
                CHEBI:10001\tVisnadin\tskos:exactMatch\t\tmesh:C067604\tvisnadin\tsemapv:ManualMappingCuration\torcid:0000-0003-4423-4370\t
                ex:1\t1\tskos:exactMatch\t\tex:2\t2\tsemapv:ManualMappingCuration\torcid:0000-0003-4423-4370\t
                ex:3\t3\tskos:exactMatch\tNot\tex:4\t4\tsemapv:ManualMappingCuration\torcid:0000-0003-4423-4370\t
                ex:7\t7\tskos:exactMatch\t\tex:8\t8\tsemapv:LexicalMatching\t\t0.77
            """).rstrip(),
            self.output_tsv_path.read_text().rstrip(),
        )

    def test_merge_with_curations_no_standardization(self) -> None:
        """Test adding some extra mappings that also have preferred prefixes."""
        self.repository.merge_standardize_bioregistry = False
        self.maxDiff = None
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
                #  chebi: http://purl.obolibrary.org/obo/CHEBI_
                #  ex: https://example.org/
                #  mesh: https://meshb.nlm.nih.gov/record/ui?ui=
                #  orcid: https://orcid.org/
                #  semapv: https://w3id.org/semapv/vocab/
                #  skos: http://www.w3.org/2004/02/skos/core#
                #license: spdx:CC0-1.0
                #mapping_set_id: {self.mapping_set_id}
                #mapping_set_title: {self.directory.name}
                subject_id\tsubject_label\tpredicate_id\tpredicate_modifier\tobject_id\tobject_label\tmapping_justification\tauthor_id\tconfidence
                chebi:10001\tVisnadin\tskos:exactMatch\t\tmesh:C067604\tvisnadin\tsemapv:ManualMappingCuration\torcid:0000-0003-4423-4370\t
                ex:1\t1\tskos:exactMatch\t\tex:2\t2\tsemapv:ManualMappingCuration\torcid:0000-0003-4423-4370\t
                ex:3\t3\tskos:exactMatch\tNot\tex:4\t4\tsemapv:ManualMappingCuration\torcid:0000-0003-4423-4370\t
                ex:7\t7\tskos:exactMatch\t\tex:8\t8\tsemapv:LexicalMatching\t\t0.77
            """).rstrip(),
            self.output_tsv_path.read_text().rstrip(),
        )
