"""
Comprehensive Test Suite for Tim 4: Interactive Maps & GPS Integration (Healtrack).
Tests NMEA parsing, UTM projections, ResIPy topography export, and API router.
"""

import unittest
import math
from fastapi.testclient import TestClient

from gps_maps.nmea_parser import NMEAParser
from gps_maps.utm_converter import UTMConverter
from gps_maps.dem_interpolator import DEMInterpolator
from backend.app import app

class TestGPSMapsModule(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_nmea_parser_checksum_and_coords(self):
        # Valid GGA sentence
        raw = "$GPGGA,081530.00,0746.2000,S,11022.2000,E,4,12,0.8,124.5,M,-23.4,M,1.0,0001*71"
        self.assertTrue(NMEAParser.verify_checksum(raw))
        parsed = NMEAParser.parse_gga(raw)
        self.assertIsNotNone(parsed)
        self.assertAlmostEqual(parsed["latitude"], -7.770000, places=4)
        self.assertAlmostEqual(parsed["longitude"], 110.370000, places=4)
        self.assertEqual(parsed["fix_quality"], 4) # RTK Fixed
        self.assertEqual(parsed["altitude_m"], 124.5)

    def test_nmea_parser_corrupted_checksum(self):
        # Corrupted checksum
        raw_bad = "$GPGGA,081530.00,0746.2000,S,11022.2000,E,4,12,0.8,124.5,M,-23.4,M,1.0,0001*FF"
        self.assertFalse(NMEAParser.verify_checksum(raw_bad))
        self.assertIsNone(NMEAParser.parse_gga(raw_bad))

    def test_utm_converter_yogyakarta_and_inverse(self):
        lat, lon = -7.770000, 110.370000
        utm = UTMConverter.wgs84_to_utm(lat, lon)
        self.assertEqual(utm["zone"], 49)
        self.assertEqual(utm["hemisphere"], "S")
        self.assertAlmostEqual(utm["easting"], 430534.8, delta=1.0)
        self.assertAlmostEqual(utm["northing"], 9141077.2, delta=1.0)

        # Inverse conversion
        rec_lat, rec_lon = UTMConverter.utm_to_wgs84(utm["easting"], utm["northing"], utm["zone"], utm["hemisphere"])
        self.assertAlmostEqual(rec_lat, lat, places=5)
        self.assertAlmostEqual(rec_lon, lon, places=5)

    def test_linear_survey_and_spacings(self):
        electrodes = UTMConverter.generate_linear_survey(
            start_lat=-7.7700,
            start_lon=110.3700,
            azimuth_deg=90.0, # Heading East
            spacing_m=5.0,
            num_electrodes=10
        )
        self.assertEqual(len(electrodes), 10)
        # Check nominal spacing
        for i in range(1, 10):
            self.assertAlmostEqual(electrodes[i]["spacing_step_2d"], 5.0, delta=0.01)
        self.assertAlmostEqual(electrodes[-1]["cumulative_distance_2d"], 45.0, delta=0.05)

    def test_resipy_topography_export(self):
        electrodes = UTMConverter.generate_linear_survey(
            start_lat=-7.7700,
            start_lon=110.3700,
            azimuth_deg=0.0,
            spacing_m=5.0,
            num_electrodes=4
        )
        electrodes = DEMInterpolator.apply_elevation_profile(electrodes, base_elevation_m=100.0, terrain_type="flat")
        topo_text = DEMInterpolator.export_resipy_topography(electrodes)
        lines = topo_text.splitlines()
        self.assertIn("# ResIPy Topography Correction File", lines[0])
        self.assertEqual(len(lines), 6) # 2 header lines + 4 electrodes
        self.assertIn("0.000\t100.000", lines[2])
        self.assertIn("15.000\t100.000", lines[5])

    def test_api_status_and_sample(self):
        resp = self.client.get("/api/gps/status")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "active")

        # Test sample endpoint
        resp_sample = self.client.get("/api/gps/sample")
        self.assertEqual(resp_sample.status_code, 200)
        sample_data = resp_sample.json()
        self.assertTrue(sample_data["success"])
        self.assertEqual(sample_data["total_electrodes"], 32)
        self.assertEqual(sample_data["geojson"]["type"], "FeatureCollection")

    def test_api_export_resipy_topo(self):
        resp = self.client.get("/api/gps/export-resipy-topography")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("ResIPy Topography Correction", resp.text)

if __name__ == "__main__":
    unittest.main()
