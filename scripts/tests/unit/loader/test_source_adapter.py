from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
import zipfile

from drilling_knowledge.loader import LoadPolicy, SourceAdapter, SourceDefinition


class SourceAdapterTests(unittest.TestCase):
    def test_discovers_and_downloads_local_listing_and_zip(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            document = root / "manual.md"
            document.write_text("# Manual\n\n4 mA = 0 psi\n", encoding="utf-8")
            archive = root / "bundle.zip"
            with zipfile.ZipFile(archive, "w") as handle:
                handle.writestr("archive.md", "# Archive\n\n20 mA = 5000 psi\n")
            listing = root / "index"
            listing.write_text(
                f'<html><body><a href="{document.as_uri()}">manual</a><a href="{archive.as_uri()}">archive</a></body></html>',
                encoding="utf-8",
            )
            adapter = SourceAdapter(
                definitions=(SourceDefinition("nov", "NOV", (listing.as_uri(),), ("",), (".md", ".zip"), "html_listing"),),
                workspace_root=root,
            )

            discovered = adapter.discover("nov", LoadPolicy())
            downloaded = adapter.download(discovered, LoadPolicy())

            self.assertEqual(len(discovered), 2)
            self.assertEqual(len(downloaded), 3)
            self.assertTrue(any(item.archive_parent_artifact_id is not None for item in downloaded))

    def test_discovers_sitemap_document_library_routes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            sitemap = root / "sitemap.xml"
            sitemap.write_text(
                "<urlset>"
                "<url><loc>https://www.nov.com/products-and-services/document-library</loc></url>"
                "<url><loc>https://www.nov.com/about</loc></url>"
                "<url><loc>https://www.nov.com/our-business-units/process-and-flow-technologies/document-library</loc></url>"
                "</urlset>",
                encoding="utf-8",
            )
            adapter = SourceAdapter(
                definitions=(SourceDefinition("nov", "NOV", (sitemap.as_uri(),), ("www.nov.com", "nov.com", ""), (".pdf", ".docx", ".xlsx", ".html", ".zip"), "mixed"),),
                workspace_root=root,
            )

            discovered = adapter.discover("nov", LoadPolicy())

            self.assertEqual(
                tuple(document.document_url for document in discovered),
                (
                    "https://www.nov.com/our-business-units/process-and-flow-technologies/document-library",
                    "https://www.nov.com/products-and-services/document-library",
                ),
            )

    def test_discovers_campaign_v2_extensionless_and_vendor_routes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            listing = root / "index"
            listing.write_text(
                "<html><body>"
                '<a href="https://docs.inductiveautomation.com/docs/8.3/intro">docs</a>'
                '<a href="https://publications.opengroup.org/standards/energistics-standards">standards</a>'
                '<a href="https://www.se.com/us/en/download/">download</a>'
                '<a href="https://www.wika.com/en-en/white_papers.WIKA">white papers</a>'
                "</body></html>",
                encoding="utf-8",
            )
            adapter = SourceAdapter(
                definitions=(
                    SourceDefinition(
                        "campaign-v2",
                        "Campaign V2",
                        (listing.as_uri(),),
                        (
                            "docs.inductiveautomation.com",
                            "publications.opengroup.org",
                            "www.se.com",
                            "www.wika.com",
                            "",
                        ),
                        (".pdf", ".docx", ".xlsx", ".html", ".zip"),
                        "mixed",
                    ),
                ),
                workspace_root=root,
            )

            discovered = adapter.discover("campaign-v2", LoadPolicy())

            self.assertEqual(
                tuple(document.document_url for document in discovered),
                (
                    "https://docs.inductiveautomation.com/docs/8.3/intro",
                    "https://publications.opengroup.org/standards/energistics-standards",
                    "https://www.se.com/us/en/download",
                    "https://www.wika.com/en-en/white_papers.WIKA",
                ),
            )

    def test_default_definitions_use_verified_campaign_v2_seeds(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            adapter = SourceAdapter.create_default(temp_dir)

            self.assertEqual(
                adapter.definition_for("pwls").seed_urls,
                ("https://publications.opengroup.org/standards/energistics-standards",),
            )
            self.assertEqual(
                adapter.definition_for("iadc").seed_urls,
                ("https://iadc.org/", "https://iadclexicon.org/"),
            )
            self.assertEqual(
                adapter.definition_for("eia").seed_urls,
                ("https://www.eia.gov/analysis/studies/usshalegas/", "https://www.eia.gov/petroleum/drilling/"),
            )
            self.assertEqual(
                adapter.definition_for("usgs").seed_urls,
                ("https://www.usgs.gov/programs/energy-resources-program",),
            )
            self.assertEqual(
                adapter.definition_for("schlumberger").seed_urls,
                ("https://www.slb.com/sitemap.xml", "https://www.slb.com/resource-library/"),
            )
            self.assertEqual(
                adapter.definition_for("weatherford").seed_urls,
                ("https://www.weatherford.com/sitemap.xml", "https://www.weatherford.com/"),
            )
            self.assertEqual(
                adapter.definition_for("canrig").seed_urls,
                ("https://www.canrig.com/page-sitemap.xml", "https://www.canrig.com/product-bulletins/"),
            )
            self.assertEqual(
                adapter.definition_for("rockwell").seed_urls,
                (
                    "https://www.rockwellautomation.com/en-us/support/documentation.html",
                    "https://www.rockwellautomation.com/en-us/support/documentation/literature-library.html",
                ),
            )
            self.assertEqual(
                adapter.definition_for("schneider-electric").seed_urls,
                (
                    "https://www.se.com/us/en/download/",
                    "https://www.se.com/us/en/download/doc-group-type/120246088490-Installation+&+User+Guides/",
                ),
            )
            self.assertEqual(
                adapter.definition_for("inductive-automation").seed_urls,
                ("https://docs.inductiveautomation.com/",),
            )
            self.assertEqual(
                adapter.definition_for("wika").seed_urls,
                (
                    "https://www.wika.com/en-en/knowledge.WIKA",
                    "https://www.wika.com/en-en/white_papers.WIKA",
                    "https://www.wika.com/en-en/brochures_and_flyers.WIKA",
                ),
            )

    def test_default_definitions_resolve_v5_documentary_sources_without_runtime_injection(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            adapter = SourceAdapter.create_default(temp_dir)

            self.assertEqual(adapter.definition_for("iadc").manufacturer_name, "IADC")
            self.assertEqual(adapter.definition_for("eia").manufacturer_name, "EIA")
            self.assertEqual(adapter.definition_for("usgs").manufacturer_name, "USGS")

    def test_discovers_supported_documents_through_official_navigation_hop(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            seed = root / "seed.html"
            library = root / "document-library"
            manual = root / "rig-instrumentation-manual.pdf"
            manual.write_text("pdf placeholder", encoding="utf-8")
            seed.write_text('<html><body><a href="document-library">library</a></body></html>', encoding="utf-8")
            library.write_text(f'<html><body><a href="{manual.as_uri()}">manual</a></body></html>', encoding="utf-8")
            adapter = SourceAdapter(
                definitions=(SourceDefinition("nov", "NOV", (seed.as_uri(),), ("",), (".pdf", ".html"), "mixed"),),
                workspace_root=root,
            )

            discovered = adapter.discover("nov", LoadPolicy())

            self.assertEqual(tuple(document.document_url for document in discovered), (manual.as_uri(),))
            self.assertEqual(discovered[0].referrer_url, library.as_uri())

    def test_download_normalizes_vendor_html_suffix_to_processable_html(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            payload = b"<html><body><h1>WIKA Knowledge</h1></body></html>"

            class _Headers:
                @staticmethod
                def get_content_type() -> str:
                    return "text/html"

            class _Response:
                def __init__(self, content: bytes) -> None:
                    self._content = content
                    self.headers = _Headers()

                def read(self) -> bytes:
                    return self._content

                def __enter__(self):
                    return self

                def __exit__(self, exc_type, exc, tb) -> None:
                    return None

            class _TestAdapter(SourceAdapter):
                def _open_url(self, url: str):
                    return _Response(payload)

            adapter = _TestAdapter(
                definitions=(SourceDefinition("wika", "WIKA", ("https://www.wika.com/en-en/knowledge.WIKA",), ("www.wika.com",), (".html", ".zip"), "mixed"),),
                workspace_root=root,
            )
            vendor_page = adapter._candidate(adapter.definition_for("wika"), "https://www.wika.com/en-en/knowledge.WIKA", None)

            downloaded = adapter.download((vendor_page,), LoadPolicy())

            self.assertEqual(len(downloaded), 1)
            self.assertTrue(downloaded[0].local_path.endswith(".html"))