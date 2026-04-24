"""Tests for geodata/loader.py — cache hit/miss behaviour and geometry filtering."""
import os
import sys

import geopandas as gpd
import pytest
from shapely.geometry import LineString, Point, box
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _boundary_gdf():
    return gpd.GeoDataFrame(
        {"geometry": [box(-122.52, 37.70, -122.35, 37.83)]},
        crs="EPSG:4326",
    )


def _mixed_gdf():
    """GeoDataFrame with polygon + non-polygon rows (points should be filtered)."""
    return gpd.GeoDataFrame(
        {"geometry": [
            box(-122.51, 37.76, -122.45, 37.77),   # Polygon — keep
            box(-122.46, 37.74, -122.44, 37.75),   # Polygon — keep
            Point(-122.4, 37.8),                    # Point — filter out
        ]},
        crs="EPSG:4326",
    )


def _edges_gdf():
    return gpd.GeoDataFrame(
        {"geometry": [
            LineString([(-122.42, 37.77), (-122.41, 37.78)]),
            LineString([(-122.43, 37.76), (-122.42, 37.77)]),
        ]},
        crs="EPSG:4326",
    )


# ---------------------------------------------------------------------------
# get_boundary
# ---------------------------------------------------------------------------

class TestGetBoundary:
    def test_cold_cache_calls_osmnx_and_saves_gpkg(self, tmp_path, monkeypatch):
        import geodata.loader as loader
        monkeypatch.setattr(loader, "CACHE_DIR", str(tmp_path))

        with patch.object(loader.ox, "geocode_to_gdf", return_value=_boundary_gdf()) as mock_fn:
            result = loader.get_boundary()

        mock_fn.assert_called_once_with("San Francisco, California, USA")
        assert (tmp_path / "boundary.gpkg").exists(), "cache file should be written"
        assert len(result) >= 1
        assert "geometry" in result.columns

    def test_warm_cache_skips_osmnx(self, tmp_path, monkeypatch):
        import geodata.loader as loader
        monkeypatch.setattr(loader, "CACHE_DIR", str(tmp_path))
        _boundary_gdf()[["geometry"]].to_file(tmp_path / "boundary.gpkg", driver="GPKG")

        with patch.object(loader.ox, "geocode_to_gdf") as mock_fn:
            result = loader.get_boundary()

        mock_fn.assert_not_called()
        assert len(result) >= 1


# ---------------------------------------------------------------------------
# get_parks
# ---------------------------------------------------------------------------

class TestGetParks:
    def test_cold_cache_filters_to_polygons_only(self, tmp_path, monkeypatch):
        import geodata.loader as loader
        monkeypatch.setattr(loader, "CACHE_DIR", str(tmp_path))

        with patch.object(loader.ox, "features_from_place", return_value=_mixed_gdf()):
            result = loader.get_parks()

        # Must contain only Polygon/MultiPolygon rows
        assert len(result) == 2
        assert all(
            t in ("Polygon", "MultiPolygon")
            for t in result.geometry.geom_type
        )

    def test_warm_cache_skips_osmnx(self, tmp_path, monkeypatch):
        import geodata.loader as loader
        monkeypatch.setattr(loader, "CACHE_DIR", str(tmp_path))
        _mixed_gdf()[["geometry"]].to_file(tmp_path / "parks.gpkg", driver="GPKG")

        with patch.object(loader.ox, "features_from_place") as mock_fn:
            loader.get_parks()

        mock_fn.assert_not_called()


# ---------------------------------------------------------------------------
# get_water
# ---------------------------------------------------------------------------

class TestGetWater:
    def test_cold_cache_filters_to_polygons_only(self, tmp_path, monkeypatch):
        import geodata.loader as loader
        monkeypatch.setattr(loader, "CACHE_DIR", str(tmp_path))

        with patch.object(loader.ox, "features_from_place", return_value=_mixed_gdf()):
            result = loader.get_water()

        assert all(
            t in ("Polygon", "MultiPolygon")
            for t in result.geometry.geom_type
        )

    def test_warm_cache_skips_osmnx(self, tmp_path, monkeypatch):
        import geodata.loader as loader
        monkeypatch.setattr(loader, "CACHE_DIR", str(tmp_path))
        _mixed_gdf()[["geometry"]].to_file(tmp_path / "water.gpkg", driver="GPKG")

        with patch.object(loader.ox, "features_from_place") as mock_fn:
            loader.get_water()

        mock_fn.assert_not_called()


# ---------------------------------------------------------------------------
# get_streets
# ---------------------------------------------------------------------------

class TestGetStreets:
    def test_cold_cache_returns_linestrings(self, tmp_path, monkeypatch):
        import geodata.loader as loader
        monkeypatch.setattr(loader, "CACHE_DIR", str(tmp_path))

        fake_graph = MagicMock()
        with patch.object(loader.ox, "graph_from_place", return_value=fake_graph):
            with patch.object(loader.ox, "graph_to_gdfs", return_value=_edges_gdf()):
                result = loader.get_streets()

        assert (tmp_path / "streets.gpkg").exists()
        assert len(result) == 2
        assert "geometry" in result.columns

    def test_warm_cache_skips_osmnx(self, tmp_path, monkeypatch):
        import geodata.loader as loader
        monkeypatch.setattr(loader, "CACHE_DIR", str(tmp_path))
        _edges_gdf()[["geometry"]].to_file(tmp_path / "streets.gpkg", driver="GPKG")

        with patch.object(loader.ox, "graph_from_place") as mock_fn:
            loader.get_streets()

        mock_fn.assert_not_called()


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestErrorHandling:
    def test_get_boundary_returns_empty_on_network_error(self, tmp_path, monkeypatch):
        import geodata.loader as loader
        monkeypatch.setattr(loader, "CACHE_DIR", str(tmp_path))

        with patch.object(loader.ox, "geocode_to_gdf", side_effect=Exception("network error")):
            result = loader.get_boundary()

        assert isinstance(result, gpd.GeoDataFrame)
        assert len(result) == 0


# ---------------------------------------------------------------------------
# get_muni_routes
# ---------------------------------------------------------------------------

class TestGetMuniRoutes:
    def _muni_gdf(self):
        return gpd.GeoDataFrame(
            {
                "geometry": [
                    LineString([(-122.42, 37.77), (-122.40, 37.79)]),
                    LineString([(-122.46, 37.76), (-122.44, 37.75)]),
                ],
                "ref": ["N", "J"],
            },
            crs="EPSG:4326",
        )

    def test_cold_cache_filters_to_known_routes(self, tmp_path, monkeypatch):
        import geodata.loader as loader
        monkeypatch.setattr(loader, "CACHE_DIR", str(tmp_path))

        mock_gdf = gpd.GeoDataFrame(
            {
                "geometry": [
                    LineString([(-122.42, 37.77), (-122.40, 37.79)]),
                    LineString([(-122.46, 37.76), (-122.44, 37.75)]),
                ],
                "ref": ["N", "X"],   # X is not a Muni line
            },
            crs="EPSG:4326",
        )
        with patch.object(loader.ox, "features_from_place", return_value=mock_gdf):
            result = loader.get_muni_routes()

        assert (tmp_path / "muni_routes.gpkg").exists(), "cache file should be written"
        assert "N" in result["ref"].values
        assert "X" not in result["ref"].values

    def test_warm_cache_skips_osmnx(self, tmp_path, monkeypatch):
        import geodata.loader as loader
        monkeypatch.setattr(loader, "CACHE_DIR", str(tmp_path))
        self._muni_gdf().to_file(tmp_path / "muni_routes.gpkg", driver="GPKG")

        with patch.object(loader.ox, "features_from_place") as mock_fn:
            result = loader.get_muni_routes()

        mock_fn.assert_not_called()
        assert len(result) == 2
        assert "ref" in result.columns

    def test_returns_empty_on_error(self, tmp_path, monkeypatch):
        import geodata.loader as loader
        monkeypatch.setattr(loader, "CACHE_DIR", str(tmp_path))

        with patch.object(loader.ox, "features_from_place", side_effect=Exception("network error")):
            result = loader.get_muni_routes()

        assert isinstance(result, gpd.GeoDataFrame)
        assert len(result) == 0
        assert "ref" in result.columns
