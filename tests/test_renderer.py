"""Tests for renderer.py helper functions."""
import os
import sys

import pytest
from PIL import Image, ImageDraw
from shapely.geometry import (
    GeometryCollection,
    LineString,
    MultiLineString,
    MultiPolygon,
    Point,
    Polygon,
    box,
)

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import renderer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_canvas(w=100, h=100):
    img = Image.new("RGB", (w, h), "white")
    draw = ImageDraw.Draw(img)
    return img, draw


def _sf_box(d=0.005):
    """Return a small Polygon centred in SF_BOUNDS (lon, lat order for Shapely)."""
    lat_mid = (renderer.SF_BOUNDS["lat_min"] + renderer.SF_BOUNDS["lat_max"]) / 2
    lon_mid = (renderer.SF_BOUNDS["lon_min"] + renderer.SF_BOUNDS["lon_max"]) / 2
    return box(lon_mid - d, lat_mid - d, lon_mid + d, lat_mid + d)


def _sf_line():
    """Return a LineString crossing the centre of SF_BOUNDS (lon, lat order)."""
    lat_mid = (renderer.SF_BOUNDS["lat_min"] + renderer.SF_BOUNDS["lat_max"]) / 2
    lon_mid = (renderer.SF_BOUNDS["lon_min"] + renderer.SF_BOUNDS["lon_max"]) / 2
    return LineString([
        (lon_mid - 0.01, lat_mid),
        (lon_mid + 0.01, lat_mid),
    ])


def _any_red(img):
    return any(p[0] > 200 and p[1] < 50 and p[2] < 50 for p in img.getdata())


def _any_blue(img):
    return any(p[2] >= 200 and p[0] < 50 for p in img.getdata())


# ---------------------------------------------------------------------------
# draw_geom — Polygon
# ---------------------------------------------------------------------------

class TestDrawGeomPolygon:
    def test_fills_polygon_with_color(self):
        img, draw = _make_canvas()
        renderer.draw_geom(draw, _sf_box(), 100, 100, fill="red")
        assert _any_red(img), "expected red pixels inside polygon"

    def test_draws_outline(self):
        img, draw = _make_canvas()
        renderer.draw_geom(draw, _sf_box(), 100, 100, fill="white", outline=(0, 0, 200))
        assert _any_blue(img), "expected blue outline pixels"

    def test_none_geom_does_not_raise(self):
        _, draw = _make_canvas()
        renderer.draw_geom(draw, None, 100, 100, fill="red")  # should not raise

    def test_empty_geom_does_not_raise(self):
        _, draw = _make_canvas()
        renderer.draw_geom(draw, Polygon(), 100, 100, fill="red")  # should not raise


# ---------------------------------------------------------------------------
# draw_geom — LineString
# ---------------------------------------------------------------------------

class TestDrawGeomLineString:
    def test_draws_line(self):
        img, draw = _make_canvas()
        renderer.draw_geom(draw, _sf_line(), 100, 100, outline=(255, 0, 0), line_width=2)
        assert _any_red(img), "expected red pixels along line"

    def test_single_point_line_does_not_raise(self):
        _, draw = _make_canvas()
        line = LineString()
        renderer.draw_geom(draw, line, 100, 100, outline="red")


# ---------------------------------------------------------------------------
# draw_geom — Multi* types
# ---------------------------------------------------------------------------

class TestDrawGeomMulti:
    def test_multipolygon_fills_both_parts(self):
        img, draw = _make_canvas()
        mp = MultiPolygon([_sf_box(0.002), _sf_box(0.001)])
        renderer.draw_geom(draw, mp, 100, 100, fill="red")
        assert _any_red(img)

    def test_multilinestring_draws_all_segments(self):
        img, draw = _make_canvas()
        mls = MultiLineString([_sf_line(), _sf_line()])
        renderer.draw_geom(draw, mls, 100, 100, outline=(255, 0, 0), line_width=2)
        assert _any_red(img)

    def test_geometry_collection_handles_mixed_types(self):
        _, draw = _make_canvas()
        gc = GeometryCollection([_sf_box(), _sf_line(), Point(0, 0)])
        renderer.draw_geom(draw, gc, 100, 100, fill="red", outline="blue")
