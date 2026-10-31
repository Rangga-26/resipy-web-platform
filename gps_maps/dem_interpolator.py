"""
Topography Correction & DEM Integration Module for ResIPy.
Extracts and applies elevation (Z) to 2D/3D electrical resistivity electrode nodes.
Supports ASCII DEM grids, synthetic terrain generators, and ResIPy-compatible topography exporters.
"""

import math
from typing import Dict, List, Tuple, Optional, Any

class DEMInterpolator:
    def __init__(self):
        self.grid_data = None
        self.header = {}

    def load_ascii_grid(self, filepath: str):
        """Loads ESRI ASCII Grid (.asc) into memory for bilinear sampling."""
        header = {}
        data = []
        with open(filepath, 'r', encoding='utf-8') as f:
            for _ in range(6):
                line = f.readline().strip().split()
                if len(line) == 2:
                    header[line[0].lower()] = float(line[1])
            for line in f:
                parts = line.strip().split()
                if parts:
                    data.append([float(val) for val in parts])

        self.header = header
        self.grid_data = data
        return True

    def sample_grid_elevation(self, easting: float, northing: float) -> Optional[float]:
        """Bilinear interpolation on loaded ASCII Grid."""
        if not self.grid_data or not self.header:
            return None

        ncols = int(self.header.get('ncols', 0))
        nrows = int(self.header.get('nrows', 0))
        xll = self.header.get('xllcorner', 0.0)
        yll = self.header.get('yllcorner', 0.0)
        cellsize = self.header.get('cellsize', 1.0)
        nodata = self.header.get('nodata_value', -9999.0)

        col_f = (easting - xll) / cellsize
        row_f = (yll + nrows * cellsize - northing) / cellsize

        col = int(math.floor(col_f))
        row = int(math.floor(row_f))

        if col < 0 or col >= ncols - 1 or row < 0 or row >= nrows - 1:
            return None

        # 4 nearest neighbors
        z00 = self.grid_data[row][col]
        z10 = self.grid_data[row][col + 1]
        z01 = self.grid_data[row + 1][col]
        z11 = self.grid_data[row + 1][col + 1]

        if nodata in (z00, z10, z01, z11):
            return z00 if z00 != nodata else None

        dx = col_f - col
        dy = row_f - row

        # Bilinear interpolation
        val = (z00 * (1.0 - dx) * (1.0 - dy) +
               z10 * dx * (1.0 - dy) +
               z01 * (1.0 - dx) * dy +
               z11 * dx * dy)
        return round(val, 2)

    @classmethod
    def apply_elevation_profile(
        cls,
        electrodes: List[Dict[str, Any]],
        base_elevation_m: float = 120.0,
        slope_pct: float = 2.5,
        terrain_type: str = "undulating"
    ) -> List[Dict[str, Any]]:
        """
        Applies topography to survey nodes if DEM raster is not provided.
        Ensures continuous realistic elevation suitable for ResIPy mesh generation.
        """
        updated = []
        for i, el in enumerate(electrodes):
            x = el["cumulative_distance_2d"]
            if terrain_type == "flat":
                z = base_elevation_m
            elif terrain_type == "linear_slope":
                z = base_elevation_m + (x * (slope_pct / 100.0))
            elif terrain_type == "undulating":
                # Realistic geomorphological undulation with subtle slope
                z = base_elevation_m + (x * (slope_pct / 100.0)) + 3.5 * math.sin(x / 45.0) + 1.2 * math.cos(x / 20.0)
            else:
                z = el.get("elevation_m", base_elevation_m)

            item = dict(el)
            item["elevation_m"] = round(z, 2)
            # Recompute 3D spacing
            if i == 0:
                item["spacing_step_3d"] = 0.0
                item["cumulative_distance_3d"] = 0.0
            else:
                prev = updated[i - 1]
                de = item["easting"] - prev["easting"]
                dn = item["northing"] - prev["northing"]
                dz = item["elevation_m"] - prev["elevation_m"]
                step_3d = math.sqrt(de**2 + dn**2 + dz**2)
                item["spacing_step_3d"] = round(step_3d, 3)
                item["cumulative_distance_3d"] = round(prev["cumulative_distance_3d"] + step_3d, 3)

            updated.append(item)
        return updated

    @classmethod
    def smooth_gps_elevations(cls, electrodes: List[Dict[str, Any]], window_size: int = 3) -> List[Dict[str, Any]]:
        """Moving average smoothing on noisy field GPS orthometric heights."""
        if len(electrodes) < window_size:
            return electrodes

        raw_z = [e.get("elevation_m", 0.0) for e in electrodes]
        smoothed_z = []
        half = window_size // 2

        for i in range(len(raw_z)):
            start = max(0, i - half)
            end = min(len(raw_z), i + half + 1)
            subset = raw_z[start:end]
            avg = sum(subset) / len(subset)
            smoothed_z.append(round(avg, 2))

        result = []
        for i, el in enumerate(electrodes):
            item = dict(el)
            item["elevation_m"] = smoothed_z[i]
            if i == 0:
                item["spacing_step_3d"] = 0.0
                item["cumulative_distance_3d"] = 0.0
            else:
                prev = result[i - 1]
                de = item["easting"] - prev["easting"]
                dn = item["northing"] - prev["northing"]
                dz = item["elevation_m"] - prev["elevation_m"]
                step_3d = math.sqrt(de**2 + dn**2 + dz**2)
                item["spacing_step_3d"] = round(step_3d, 3)
                item["cumulative_distance_3d"] = round(prev["cumulative_distance_3d"] + step_3d, 3)
            result.append(item)

        return result

    @classmethod
    def export_resipy_topography(cls, electrodes: List[Dict[str, Any]]) -> str:
        """
        Exports topography file format directly readable by ResIPy R2 engine:
        Header: '# Distance_X_m Elevation_Z_m' followed by pairs.
        """
        lines = ["# ResIPy Topography Correction File", "# Distance_X_m Elevation_Z_m"]
        for el in electrodes:
            x = el["cumulative_distance_2d"]
            z = el["elevation_m"]
            lines.append(f"{x:.3f}\t{z:.3f}")
        return "\n".join(lines)

    @classmethod
    def to_geojson(cls, electrodes: List[Dict[str, Any]], survey_name: str = "ResIPy Survey Line") -> Dict[str, Any]:
        """
        Converts electrodes and trajectory into GeoJSON FeatureCollection
        ready for Leaflet.js / MapLibre visualization.
        """
        if not electrodes:
            return {"type": "FeatureCollection", "features": []}

        features = []

        # Survey line feature (LineString)
        coordinates = [[el["longitude"], el["latitude"], el["elevation_m"]] for el in electrodes]
        line_feature = {
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": coordinates
            },
            "properties": {
                "survey_name": survey_name,
                "total_electrodes": len(electrodes),
                "total_length_2d_m": electrodes[-1]["cumulative_distance_2d"],
                "total_length_3d_m": electrodes[-1]["cumulative_distance_3d"],
                "min_elevation_m": min(el["elevation_m"] for el in electrodes),
                "max_elevation_m": max(el["elevation_m"] for el in electrodes),
                "utm_zone": electrodes[0].get("zone", 49),
                "utm_hemisphere": electrodes[0].get("hemisphere", "S")
            }
        }
        features.append(line_feature)

        # Electrode markers (Points)
        for el in electrodes:
            pt_feature = {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [el["longitude"], el["latitude"], el["elevation_m"]]
                },
                "properties": {
                    "electrode_id": el["electrode_id"],
                    "easting": el["easting"],
                    "northing": el["northing"],
                    "elevation_m": el["elevation_m"],
                    "cumulative_dist_m": el["cumulative_distance_2d"],
                    "step_dist_2d_m": el["spacing_step_2d"],
                    "azimuth_deg": el.get("azimuth_deg", 0.0)
                }
            }
            features.append(pt_feature)

        return {
            "type": "FeatureCollection",
            "features": features
        }
