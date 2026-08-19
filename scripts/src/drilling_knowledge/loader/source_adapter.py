"""Document source adapter for Industrial Knowledge Loader."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
import mimetypes
import shutil
import zipfile

from drilling_knowledge.common.ids import EntityId
from drilling_knowledge.loader.artifact_registry import DiscoveredDocument, DownloadedArtifact, LoadPolicy, SourceDefinition


class _AnchorParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() != "a":
            return
        for key, value in attrs:
            if key.lower() == "href" and value:
                self.links.append(str(value))


class _SitemapParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self._in_loc = False

    def handle_starttag(self, tag: str, attrs) -> None:
        self._in_loc = tag.lower() == "loc"

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "loc":
            self._in_loc = False

    def handle_data(self, data: str) -> None:
        if self._in_loc and data.strip():
            self.links.append(data.strip())


@dataclass(slots=True)
class SourceAdapter:
    definitions: tuple[SourceDefinition, ...]
    workspace_root: Path

    _DEFAULT_HEADERS = {"User-Agent": "IndustrialKnowledgeLoader/1.0 (+https://github.com/github/copilot)"}
    _DISCOVERY_ROUTE_HINTS = (
        "document-library",
        "documentation",
        "docs",
        "download",
        "downloads",
        "manual",
        "manuals",
        "user-guide",
        "installation",
        "datasheet",
        "datasheets",
        "specification",
        "specifications",
        "brochure",
        "brochures",
        "application-note",
        "application-notes",
        "white-paper",
        "white_papers",
        "product-bulletins",
        "literature-library",
        "resource-library",
        "doc-group-type",
        "all-products",
        "knowledge",
        "standards/energistics-standards",
    )
    _NAVIGATION_ROUTE_HINTS = (
        "document-library",
        "documentation",
        "download",
        "downloads",
        "product-bulletins",
        "literature-library",
        "resource-library",
        "doc-group-type",
        "all-products",
    )
    _FINAL_ROUTE_HINTS = (
        "docs/",
        "/docs",
        "manual",
        "manuals",
        "user-guide",
        "installation",
        "datasheet",
        "datasheets",
        "specification",
        "specifications",
        "brochure",
        "brochures",
        "application-note",
        "application-notes",
        "white-paper",
        "white_papers",
        "knowledge",
        "standards/energistics-standards",
    )

    @classmethod
    def create_default(cls, workspace_root: str | Path) -> "SourceAdapter":
        return cls(definitions=_default_source_definitions(), workspace_root=Path(workspace_root))

    def definition_for(self, source_name: str) -> SourceDefinition:
        normalized = source_name.strip().lower()
        for definition in self.definitions:
            if definition.source_name == normalized:
                return definition
        raise ValueError(f"Unknown source: {source_name}")

    def discover(self, source_name: str, policy: LoadPolicy) -> tuple[DiscoveredDocument, ...]:
        definition = self.definition_for(source_name)
        discovered: list[DiscoveredDocument] = []
        seen_urls: set[str] = set()
        for seed in definition.seed_urls:
            discovered.extend(self._discover_from_seed(definition, seed, seen_urls))
        ordered = tuple(sorted(discovered, key=lambda item: item.document_url))
        if policy.max_documents_per_run is not None:
            return ordered[: policy.max_documents_per_run]
        return ordered

    def download(self, documents: tuple[DiscoveredDocument, ...], policy: LoadPolicy) -> tuple[DownloadedArtifact, ...]:
        artifacts: list[DownloadedArtifact] = []
        download_root = self.workspace_root / "downloads"
        download_root.mkdir(parents=True, exist_ok=True)
        for document in documents:
            artifact = self._download_document(document, download_root)
            artifacts.append(artifact)
            if policy.expand_archives and artifact.local_path.lower().endswith(".zip"):
                artifacts.extend(self._expand_archive(artifact, download_root))
        return tuple(sorted(artifacts, key=lambda item: (item.original_url, item.local_path)))

    def _discover_from_seed(self, definition: SourceDefinition, seed: str, seen_urls: set[str]) -> list[DiscoveredDocument]:
        parsed = urlparse(seed)
        if self._is_supported_document_url(seed, definition.allowed_formats):
            candidate = self._candidate(definition, seed, None)
            if candidate.document_url not in seen_urls:
                seen_urls.add(candidate.document_url)
                return [candidate]
            return []
        parser, seed_links = self._extract_links(seed)
        documents: list[DiscoveredDocument] = []
        navigation_candidates: list[str] = []
        for link in seed_links:
            absolute = urljoin(seed, link)
            candidate_parsed = urlparse(absolute)
            if parsed.scheme == "file":
                allowed_domain = True
            else:
                allowed_domain = self._allowed_domain(candidate_parsed.netloc.lower(), definition.allowed_domains)
            if not allowed_domain:
                continue
            if not self._is_supported_document_url(absolute, definition.allowed_formats):
                if self._should_follow_link(absolute):
                    navigation_candidates.append(absolute)
                continue
            candidate = self._candidate(definition, absolute, seed)
            if candidate.document_url in seen_urls:
                continue
            seen_urls.add(candidate.document_url)
            documents.append(candidate)
        for navigation_url in tuple(sorted(set(navigation_candidates))):
            _, nested_links = self._extract_links(navigation_url)
            for link in nested_links:
                absolute = urljoin(navigation_url, link)
                candidate_parsed = urlparse(absolute)
                if parsed.scheme != "file" and not self._allowed_domain(candidate_parsed.netloc.lower(), definition.allowed_domains):
                    continue
                if not self._is_supported_document_url(absolute, definition.allowed_formats):
                    continue
                candidate = self._candidate(definition, absolute, navigation_url)
                if candidate.document_url in seen_urls:
                    continue
                seen_urls.add(candidate.document_url)
                documents.append(candidate)
        return documents

    def _extract_links(self, url: str) -> tuple[HTMLParser, list[str]]:
        parsed = urlparse(url)
        with self._open_url(url) as response:
            payload = response.read().decode("utf-8", errors="ignore")
        parser = _SitemapParser() if parsed.path.lower().endswith(".xml") else _AnchorParser()
        parser.feed(payload)
        return parser, list(parser.links)

    def _download_document(self, document: DiscoveredDocument, download_root: Path) -> DownloadedArtifact:
        with self._open_url(document.document_url) as response:
            payload = response.read()
            content_type = response.headers.get_content_type() or mimetypes.guess_type(document.document_url)[0] or "application/octet-stream"
        file_name = Path(urlparse(document.document_url).path).name or "downloaded.bin"
        suffix = Path(file_name).suffix.lower()
        if content_type == "text/html" and suffix not in {".html", ".htm"}:
            file_name = f"{Path(file_name).name}.html"
        elif suffix == "":
            inferred_suffix = mimetypes.guess_extension(content_type, strict=False) or ""
            if content_type == "text/html":
                inferred_suffix = ".html"
            if inferred_suffix:
                file_name = f"{file_name}{inferred_suffix}"
        artifact_id = EntityId.from_seed("loader.artifact", f"{document.document_url}:{len(payload)}:{datetime.now(UTC).isoformat()}")
        local_path = download_root / f"{artifact_id}-{file_name}"
        local_path.write_bytes(payload)
        return DownloadedArtifact(
            artifact_id=artifact_id,
            source_name=document.source_name,
            original_url=document.document_url,
            canonical_url=document.document_url,
            local_path=str(local_path),
            content_type=content_type,
            size_bytes=len(payload),
            downloaded_at=datetime.now(UTC),
        )

    def _expand_archive(self, artifact: DownloadedArtifact, download_root: Path) -> tuple[DownloadedArtifact, ...]:
        expanded: list[DownloadedArtifact] = []
        with zipfile.ZipFile(artifact.local_path) as archive:
            for member in archive.infolist():
                if member.is_dir():
                    continue
                target_path = download_root / f"{artifact.artifact_id}-{Path(member.filename).name}"
                with archive.open(member) as source, target_path.open("wb") as target:
                    shutil.copyfileobj(source, target)
                content_type = mimetypes.guess_type(target_path.name)[0] or "application/octet-stream"
                expanded.append(
                    DownloadedArtifact(
                        artifact_id=EntityId.from_seed("loader.artifact", f"{artifact.artifact_id}:{member.filename}:{member.file_size}"),
                        source_name=artifact.source_name,
                        original_url=f"{artifact.original_url}!{member.filename}",
                        canonical_url=f"{artifact.canonical_url}!{member.filename}",
                        local_path=str(target_path),
                        content_type=content_type,
                        size_bytes=member.file_size,
                        downloaded_at=artifact.downloaded_at,
                        archive_parent_artifact_id=artifact.artifact_id,
                    )
                )
        return tuple(expanded)

    def _open_url(self, url: str):
        return urlopen(Request(url, headers=self._DEFAULT_HEADERS))

    @staticmethod
    def _matches_format(url: str, allowed_formats: tuple[str, ...]) -> bool:
        suffix = Path(urlparse(url).path).suffix.lower()
        return suffix in allowed_formats

    @classmethod
    def _is_supported_document_url(cls, url: str, allowed_formats: tuple[str, ...]) -> bool:
        parsed = urlparse(url)
        if parsed.scheme == "file":
            suffix = Path(parsed.path).suffix.lower()
            if suffix in {".html", ".htm"}:
                normalized_path = parsed.path.lower()
                return any(token in normalized_path for token in cls._DISCOVERY_ROUTE_HINTS)
            if suffix == "":
                normalized_path = parsed.path.lower().strip("/")
                return any(token in normalized_path for token in cls._FINAL_ROUTE_HINTS)
        if cls._matches_format(url, allowed_formats):
            return True
        path = parsed.path.lower().strip("/")
        if not path:
            return False
        if path.endswith(".wika"):
            return any(token in path for token in ("knowledge", "white_papers", "brochures_and_flyers", "webinars", "media"))
        if Path(path).suffix:
            return False
        return any(token in path for token in cls._DISCOVERY_ROUTE_HINTS)

    @staticmethod
    def _allowed_domain(candidate: str, allowed_domains: tuple[str, ...]) -> bool:
        normalized = candidate.strip().lower()
        return any(normalized == domain or normalized.endswith(f".{domain}") for domain in allowed_domains if domain)

    @classmethod
    def _should_follow_link(cls, url: str) -> bool:
        path = urlparse(url).path.lower().strip("/")
        if not path or Path(path).suffix:
            return False
        return any(token in path for token in cls._NAVIGATION_ROUTE_HINTS)

    @staticmethod
    def _candidate(definition: SourceDefinition, url: str, referrer_url: str | None) -> DiscoveredDocument:
        detected_format = Path(urlparse(url).path).suffix.lower() or ".html"
        return DiscoveredDocument(
            source_name=definition.source_name,
            manufacturer_name=definition.manufacturer_name,
            document_url=url,
            referrer_url=referrer_url,
            detected_format=detected_format,
            discovered_at=datetime.now(UTC),
        )


def _default_source_definitions() -> tuple[SourceDefinition, ...]:
    return (
        SourceDefinition(
            "energistics",
            "Energistics",
            ("https://docs.energistics.org/", "https://publications.opengroup.org/standards/energistics-standards"),
            ("docs.energistics.org", "publications.opengroup.org"),
            (".pdf", ".docx", ".xlsx", ".html", ".zip"),
            "mixed",
        ),
        SourceDefinition(
            "pwls",
            "PWLS",
            ("https://publications.opengroup.org/standards/energistics-standards",),
            ("publications.opengroup.org",),
            (".pdf", ".docx", ".xlsx", ".html", ".zip"),
            "mixed",
        ),
        SourceDefinition(
            "iadc",
            "IADC",
            ("https://iadc.org/", "https://iadclexicon.org/"),
            ("iadc.org", "www.iadc.org", "iadclexicon.org", "www.iadclexicon.org"),
            (".pdf", ".docx", ".xlsx", ".html", ".zip"),
            "mixed",
        ),
        SourceDefinition(
            "eia",
            "EIA",
            ("https://www.eia.gov/analysis/studies/usshalegas/", "https://www.eia.gov/petroleum/drilling/"),
            ("eia.gov", "www.eia.gov"),
            (".pdf", ".docx", ".xlsx", ".html", ".zip"),
            "mixed",
        ),
        SourceDefinition(
            "usgs",
            "USGS",
            ("https://www.usgs.gov/programs/energy-resources-program",),
            ("usgs.gov", "www.usgs.gov"),
            (".pdf", ".docx", ".xlsx", ".html", ".zip"),
            "mixed",
        ),
        SourceDefinition("nov", "NOV", ("https://www.nov.com/sitemap.xml", "https://www.nov.com/products-and-services/document-library"), ("www.nov.com", "nov.com", "assets.nov.com"), (".pdf", ".docx", ".xlsx", ".html", ".zip"), "mixed"),
        SourceDefinition("pason", "Pason", ("https://www.pason.com/products/downloads", "https://www.pason.com/products/all-products"), ("www.pason.com", "pason.com", "wp-content.pason.com"), (".pdf", ".docx", ".xlsx", ".html", ".zip"), "mixed"),
        SourceDefinition("canrig", "Canrig", ("https://www.canrig.com/page-sitemap.xml", "https://www.canrig.com/product-bulletins/"), ("www.canrig.com", "canrig.com"), (".pdf", ".docx", ".xlsx", ".html", ".zip"), "mixed"),
        SourceDefinition("halliburton", "Halliburton", ("https://www.halliburton.com/", "https://www.halliburton.com/en/search-results#cf-contenttype=Resource"), ("www.halliburton.com", "halliburton.com", "halliburton-sds.thewercs.com"), (".pdf", ".docx", ".xlsx", ".html", ".zip"), "mixed"),
        SourceDefinition("baker-hughes", "Baker Hughes", ("https://www.bakerhughes.com/sitemap.xml",), ("www.bakerhughes.com", "bakerhughes.com"), (".pdf", ".docx", ".xlsx", ".html", ".zip"), "mixed"),
        SourceDefinition("schlumberger", "Schlumberger", ("https://www.slb.com/sitemap.xml", "https://www.slb.com/resource-library/"), ("www.slb.com", "slb.com", "cdn.slb.com", "cloud.slb.com"), (".pdf", ".docx", ".xlsx", ".html", ".zip"), "mixed"),
        SourceDefinition("weatherford", "Weatherford", ("https://www.weatherford.com/sitemap.xml", "https://www.weatherford.com/"), ("www.weatherford.com", "weatherford.com", "cdn.bfldr.com", "brandfolder.io"), (".pdf", ".docx", ".xlsx", ".html", ".zip"), "mixed"),
        SourceDefinition("rockwell", "Rockwell Automation", ("https://www.rockwellautomation.com/en-us/support/documentation.html", "https://www.rockwellautomation.com/en-us/support/documentation/literature-library.html"), ("www.rockwellautomation.com", "rockwellautomation.com", "literature.rockwellautomation.com", "rockwellautomation.scene7.com"), (".pdf", ".docx", ".xlsx", ".html", ".zip"), "mixed"),
        SourceDefinition("schneider-electric", "Schneider Electric", ("https://www.se.com/us/en/download/", "https://www.se.com/us/en/download/doc-group-type/120246088490-Installation+&+User+Guides/"), ("www.se.com", "se.com", "cdn.se.com", "content.se.com"), (".pdf", ".docx", ".xlsx", ".html", ".zip"), "mixed"),
        SourceDefinition("inductive-automation", "Inductive Automation", ("https://docs.inductiveautomation.com/",), ("docs.inductiveautomation.com", "inductiveautomation.com"), (".pdf", ".docx", ".xlsx", ".html", ".zip"), "mixed"),
        SourceDefinition("wika", "WIKA", ("https://www.wika.com/en-en/knowledge.WIKA", "https://www.wika.com/en-en/white_papers.WIKA", "https://www.wika.com/en-en/brochures_and_flyers.WIKA"), ("www.wika.com", "wika.com", "blog.wika.com"), (".pdf", ".docx", ".xlsx", ".html", ".zip"), "mixed"),
    )