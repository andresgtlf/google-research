"""Bounded, read-only DOCX text extraction. Never execute embedded content."""

from io import BytesIO
from pathlib import Path
from zipfile import ZipFile, BadZipFile
import xml.etree.ElementTree as ET

FORMATS = {"auto", "concept_note", "next_ladder_intake"}
MAX_XML_BYTES = 20 * 1024 * 1024


def docx_text(content: bytes) -> str:
    try:
        with ZipFile(BytesIO(content)) as archive:
            if len(archive.infolist()) > 2000:
                raise ValueError("Word document contains too many components")
            info = archive.getinfo("word/document.xml")
            if info.file_size > MAX_XML_BYTES:
                raise ValueError("Word document text exceeds the 20 MB limit")
            xml = archive.read(info)
            if b"<!DOCTYPE" in xml or b"<!ENTITY" in xml:
                raise ValueError("Unsupported Word XML declarations")
            root = ET.fromstring(xml)
            links = {}
            if "word/_rels/document.xml.rels" in archive.namelist():
                rel_info = archive.getinfo("word/_rels/document.xml.rels")
                if rel_info.file_size > 2 * 1024 * 1024:
                    raise ValueError("Word relationship data exceeds limit")
                rel_xml = archive.read(rel_info)
                if b"<!DOCTYPE" in rel_xml or b"<!ENTITY" in rel_xml:
                    raise ValueError("Unsupported Word XML declarations")
                for rel in ET.fromstring(rel_xml):
                    target = rel.get("Target", "")
                    if rel.get("Type", "").endswith("/hyperlink") and target.startswith(
                        ("https://", "http://")
                    ):
                        links[rel.get("Id")] = target
            for link in root.iter(
                "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}hyperlink"
            ):
                target = links.get(
                    link.get(
                        "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
                    )
                )
                if target:
                    ET.SubElement(
                        link,
                        "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t",
                    ).text = " (" + target + ")"
            ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
            # Paragraph order includes table cells, preserving question/answer order.
            text = "\n".join(
                "".join(t.text or "" for t in p.findall(".//w:t", ns))
                for p in root.findall(".//w:p", ns)
            )
            if not text.strip():
                raise ValueError(
                    "Word document has no readable text; upload a PDF for scanned/image-only content"
                )
            return text
    except (BadZipFile, KeyError, ET.ParseError, RuntimeError) as exc:
        raise ValueError(
            "Invalid or unsupported Word document; upload PDF or DOCX"
        ) from exc


def validate_document(content: bytes, filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf" and content.startswith(b"%PDF"):
        return "pdf"
    if suffix == ".docx":
        docx_text(content)
        return "docx"
    raise ValueError("Upload a valid PDF or Word (.docx) document")
