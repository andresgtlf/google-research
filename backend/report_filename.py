"""Consistent, filesystem-safe names for report exports and downloads."""

import unicodedata


def report_filename(organization: str | None, extension: str) -> str:
    name = unicodedata.normalize("NFKC", organization or "")
    name = "".join(c for c in name if c.isalnum() or c in "-_ ")
    name = " ".join(name.split())[:100].strip() or "Grantee"
    return f"{name}_Research.{extension}"
