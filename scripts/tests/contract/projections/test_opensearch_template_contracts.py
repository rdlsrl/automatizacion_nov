from __future__ import annotations

from pathlib import Path
import json
import unittest

from drilling_knowledge.projections.search import OpenSearchTemplateBundleLoader


class OpenSearchTemplateContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path("/mnt/mariadb/autom_nov/autom_nov/scripts/db/opensearch")

    def test_manifest_aliases_and_templates_recover_stably(self) -> None:
        bundle = OpenSearchTemplateBundleLoader.load(self.root)
        recovered = OpenSearchTemplateBundleLoader.load(self.root)

        self.assertEqual(bundle, recovered)
        self.assertEqual(json.dumps(bundle.as_serializable(), sort_keys=True), json.dumps(recovered.as_serializable(), sort_keys=True))

    def test_bundle_declares_official_index_list(self) -> None:
        bundle = OpenSearchTemplateBundleLoader.load(self.root)

        self.assertEqual(
            set(bundle.required_indices),
            {
                "ikc-aliases-v1",
                "ikc-assets-v1",
                "ikc-assertions-v1",
                "ikc-documents-v1",
                "ikc-facts-v1",
                "ikc-fragments-v1",
                "ikc-processes-v1",
                "ikc-search-suggestions-v1",
                "ikc-variables-v1",
            },
        )