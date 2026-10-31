"""
UTM Coordinate Converter & Electrode Spacing Metric Module.
Converts Geodetic WGS-84 (Lat, Lon) to Universal Transverse Mercator (UTM).
Calculates nominal vs actual electrode spacing, cumulative distance, and spatial metrics.
"""

import math
from typing import Dict, List, Tuple, Optional, Any

class UTMConverter:
    # WGS-84 Ellipsoid constants
    A = 6378137.0                      # Semi-major axis (meters)
    F = 1.0 / 298.257223563            # Flattening
    B = A * (1.0 - F)                  # Semi-minor axis (~6356752.3142 m)
    E2 = (A**2 - B**2) / (A**2)        # First eccentricity squared (~0.00669438)
    EP2 = (A**2 - B**2) / (B**2)       # Second eccentricity squared (~0.00673950)
    K0 = 0.9996                        # Central scale factor

    @classmethod
    def get_zone(cls, longitude: float) -> int:
        """Determines UTM Zone (1 to 60) from longitude."""
        return int((longitude + 180.0) / 6.0) + 1

    @classmethod
    def wgs84_to_utm(cls, lat: float, lon: float, zone: Optional[int] = None, hemisphere: Optional[str] = None) -> Dict[str, Any]:
        """
        Converts WGS-84 Latitude, Longitude to UTM Easting, Northing.
        Returns sub-centimeter planar coordinates.
        """
        if zone is None:
            zone = cls.get_zone(lon)
        if hemisphere is None:
            hemisphere = 'S' if lat < 0 else 'N'

        lon0 = (zone - 1) * 6 - 180 + 3
        lon0_rad = math.radians(lon0)
        lat_rad = math.radians(lat)
        lon_rad = math.radians(lon)

        N = cls.A / math.sqrt(1.0 - cls.E2 * math.sin(lat_rad)**2)
        T = math.tan(lat_rad)**2
        C = cls.EP2 * math.cos(lat_rad)**2
        A_val = math.cos(lat_rad) * (lon_rad - lon0_rad)

        # True meridian arc length M
        M = cls.A * (
            (1.0 - cls.E2/4.0 - 3.0*cls.E2**2/64.0 - 5.0*cls.E2**3/256.0) * lat_rad
            - (3.0*cls.E2/8.0 + 3.0*cls.E2**2/32.0 + 45.0*cls.E2**3/1024.0) * math.sin(2.0*lat_rad)
            + (15.0*cls.E2**2/256.0 + 45.0*cls.E2**3/1024.0) * math.sin(4.0*lat_rad)
            - (35.0*cls.E2**3/3072.0) * math.sin(6.0*lat_rad)
        )

        easting = cls.K0 * N * (
            A_val + (1.0 - T + C) * (A_val**3) / 6.0
            + (5.0 - 18.0*T + T**2 + 72.0*C - 58.0*cls.EP2) * (A_val**5) / 120.0
        ) + 500000.0

        northing = cls.K0 * (
            M + N * math.tan(lat_rad) * (
                (A_val**2) / 2.0
                + (5.0 - T + 9.0*C + 4.0*C**2) * (A_val**4) / 24.0
                + (61.0 - 58.0*T + T**2 + 600.0*C - 330.0*cls.EP2) * (A_val**6) / 720.0
            )
        )

        if hemisphere.upper() == 'S':
            northing += 10000000.0

        return {
            "easting": round(easting, 3),
            "northing": round(northing, 3),
            "zone": zone,
            "hemisphere": hemisphere.upper(),
            "epsg": 32700 + zone if hemisphere.upper() == 'S' else 32600 + zone
        }

    @classmethod
    def utm_to_wgs84(cls, easting: float, northing: float, zone: int, hemisphere: str = 'S') -> Tuple[float, float]:
        """Converts UTM Easting and Northing back to Geodetic WGS-84 (Lat, Lon)."""
        x = easting - 500000.0
        y = northing
        if hemisphere.upper() == 'S':
            y -= 10000000.0

        M = y / cls.K0
        mu = M / (cls.A * (1.0 - cls.E2/4.0 - 3.0*cls.E2**2/64.0 - 5.0*cls.E2**3/256.0))

        e1 = (1.0 - math.sqrt(1.0 - cls.E2)) / (1.0 + math.sqrt(1.0 - cls.E2))
        J1 = 3.0*e1/2.0 - 27.0*e1**3/32.0
        J2 = 21.0*e1**2/16.0 - 55.0*e1**4/32.0
        J3 = 151.0*e1**3/96.0
        J4 = 1097.0*e1**4/512.0

        fp = (mu + J1*math.sin(2.0*mu) + J2*math.sin(4.0*mu)
              + J3*math.sin(6.0*mu) + J4*math.sin(8.0*mu))

        C1 = cls.EP2 * math.cos(fp)**2
        T1 = math.tan(fp)**2
        R1 = cls.A * (1.0 - cls.E2) / ((1.0 - cls.E2 * math.sin(fp)**2)**1.5)
        N1 = cls.A / math.sqrt(1.0 - cls.E2 * math.sin(fp)**2)
        D = x / (N1 * cls.K0)

        lat = fp - (N1 * math.tan(fp) / R1) * (
            D**2 / 2.0
            - (5.0 + 3.0*T1 + 10.0*C1 - 4.0*C1**2 - 9.0*cls.EP2) * (D**4) / 24.0
            + (61.0 + 90.0*T1 + 298.0*C1 + 45.0*T1**2 - 252.0*cls.EP2 - 3.0*C1**2) * (D**6) / 720.0
        )

        lon0 = (zone - 1) * 6 - 180 + 3
        lon = math.radians(lon0) + (
            D - (1.0 + 2.0*T1 + C1) * (D**3) / 6.0
            + (5.0 - 2.0*C1 + 28.0*T1 - 3.0*C1**2 + 8.0*cls.EP2 + 24.0*T1**2) * (D**5) / 120.0
        ) / math.cos(fp)

        return round(math.degrees(lat), 7), round(math.degrees(lon), 7)

    @classmethod
    def calculate_electrode_spacings(cls, points: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Takes ordered GPS points or electrode positions with UTM coordinates
        and calculates planar interval (a), 3D slope distance, cumulative line distance,
        and azimuth between consecutive electrodes.
        """
        if not points:
            return []

        processed = []
        cum_dist_2d = 0.0
        cum_dist_3d = 0.0

        for i, pt in enumerate(points):
            e = pt["easting"]
            n = pt["northing"]
            z = pt.get("altitude_m", pt.get("elevation_m", 0.0))

            if i == 0:
                step_2d = 0.0
                step_3d = 0.0
                azimuth = 0.0
            else:
                prev = processed[i - 1]
                de = e - prev["easting"]
                dn = n - prev["northing"]
                dz = z - prev["elevation_m"]

                step_2d = math.hypot(de, dn)
                step_3d = math.sqrt(de**2 + dn**2 + dz**2)
                cum_dist_2d += step_2d
                cum_dist_3d += step_3d

                # Azimuth from North (degrees 0-360)
                angle = math.degrees(math.atan2(de, dn))
                azimuth = (angle + 360.0) % 360.0

            node = {
                "electrode_id": i + 1,
                "latitude": pt.get("latitude"),
                "longitude": pt.get("longitude"),
                "easting": e,
                "northing": n,
                "elevation_m": round(z, 2),
                "spacing_step_2d": round(step_2d, 3),
                "spacing_step_3d": round(step_3d, 3),
                "cumulative_distance_2d": round(cum_dist_2d, 3),
                "cumulative_distance_3d": round(cum_dist_3d, 3),
                "azimuth_deg": round(azimuth, 1)
            }
            processed.append(node)

        return processed

    @classmethod
    def generate_linear_survey(
        cls,
        start_lat: float,
        start_lon: float,
        azimuth_deg: float,
        spacing_m: float,
        num_electrodes: int
    ) -> List[Dict[str, Any]]:
        """
        Generates idealized planned survey line with equidistant electrode spacing
        projected along a specified heading.
        """
        utm_start = cls.wgs84_to_utm(start_lat, start_lon)
        zone = utm_start["zone"]
        hemisphere = utm_start["hemisphere"]

        rad = math.radians(azimuth_deg)
        sin_az = math.sin(rad)
        cos_az = math.cos(rad)

        nodes = []
        for i in range(num_electrodes):
            dist = i * spacing_m
            e = utm_start["easting"] + dist * sin_az
            n = utm_start["northing"] + dist * cos_az
            lat, lon = cls.utm_to_wgs84(e, n, zone, hemisphere)

            nodes.append({
                "electrode_id": i + 1,
                "latitude": lat,
                "longitude": lon,
                "easting": round(e, 3),
                "northing": round(n, 3),
                "elevation_m": 0.0,
                "spacing_step_2d": spacing_m if i > 0 else 0.0,
                "spacing_step_3d": spacing_m if i > 0 else 0.0,
                "cumulative_distance_2d": round(dist, 3),
                "cumulative_distance_3d": round(dist, 3),
                "azimuth_deg": round(azimuth_deg, 1)
            })

        return nodes
