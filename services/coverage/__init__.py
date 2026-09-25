"""Couverture fonctionnelle : référentiel déclaré × code des tests."""

from services.coverage.analyzer import (
    analyse,
    build_report,
    check_references,
    collect_code,
    load_referentiel,
)
from services.coverage.catalogue import (
    CATALOGUE_PATH,
    build_catalogue,
    load_catalogue,
    refresh_catalogue,
    write_catalogue,
)
from services.coverage.html_report import render_html, write_html
from services.coverage.tests_index import (
    INDEX_PATH,
    build_index,
    is_stale,
    load_index,
    refresh_index,
    write_index,
)

__all__ = [
    "CATALOGUE_PATH",
    "INDEX_PATH",
    "analyse",
    "build_catalogue",
    "build_index",
    "build_report",
    "check_references",
    "collect_code",
    "is_stale",
    "load_catalogue",
    "load_index",
    "load_referentiel",
    "refresh_catalogue",
    "refresh_index",
    "render_html",
    "write_catalogue",
    "write_html",
    "write_index",
]
