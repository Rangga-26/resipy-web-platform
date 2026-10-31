"""
FastAPI Router for Tim 4: Interactive Maps & GPS Integration (Healtrack).
Provides REST endpoints for NMEA parsing, UTM projections, ResIPy topography injection,
and GeoJSON generation for Leaflet.js.
"""

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import PlainTextResponse
from typing import Optional, List, Dict, Any
import json

from .nmea_parser import NMEAParser
from .utm_converter import UTMConverter
from .dem_interpolator import DEMInterpolator

router = APIRouter(prefix="/api/gps", tags=["GPS & Maps"])

# In-memory storage for active survey line
CURRENT_SURVEY: Dict[str, Any] = {
    "survey_name": "Lintasan Geolistrik Lapangan 1",
    "electrodes": [],
    "geojson": None
}

@router.get("/status")
def gps_status():
    """Returns status of GPS telemetry & mapping engine."""
    return {
        "status": "active",
        "module": "Tim 4 - GPS Maps & Telemetry",
        "active_electrodes_count": len(CURRENT_SURVEY["electrodes"]),
        "has_geojson": CURRENT_SURVEY["geojson"] is not None
    }

@router.post("/parse-nmea")
async def parse_nmea_file(
    file: Optional[UploadFile] = File(None),
    raw_nmea: Optional[str] = Form(None),
    survey_name: str = Form("Survei Lapangan NMEA"),
    smooth_altitude: bool = Form(True)
):
    """
    Parses $GPGGA sentences from uploaded log file or raw text stream,
    projects coordinates to UTM, and calculates electrode spacings.
    """
    content = ""
    if file:
        file_bytes = await file.read()
        content = file_bytes.decode("utf-8", errors="ignore")
    elif raw_nmea:
        content = raw_nmea
    else:
        raise HTTPException(status_code=400, detail="Mohon sertakan file NMEA atau string raw_nmea.")

    parsed_fixes = NMEAParser.parse_stream(content)
    if not parsed_fixes:
        raise HTTPException(status_code=422, detail="Tidak ditemukan kalimat $GPGGA valid dengan GPS fix.")

    # Convert geodetic to UTM
    projected = []
    for fix in parsed_fixes:
        utm = UTMConverter.wgs84_to_utm(fix["latitude"], fix["longitude"])
        item = {
            **fix,
            "easting": utm["easting"],
            "northing": utm["northing"],
            "zone": utm["zone"],
            "hemisphere": utm["hemisphere"],
            "elevation_m": fix["altitude_m"]
        }
        projected.append(item)

    # Compute step spacings and cumulative distances
    electrodes = UTMConverter.calculate_electrode_spacings(projected)

    if smooth_altitude and len(electrodes) >= 3:
        electrodes = DEMInterpolator.smooth_gps_elevations(electrodes, window_size=3)

    geojson = DEMInterpolator.to_geojson(electrodes, survey_name=survey_name)

    CURRENT_SURVEY["survey_name"] = survey_name
    CURRENT_SURVEY["electrodes"] = electrodes
    CURRENT_SURVEY["geojson"] = geojson

    return {
        "success": True,
        "survey_name": survey_name,
        "total_fixes_parsed": len(parsed_fixes),
        "total_electrodes": len(electrodes),
        "utm_zone": electrodes[0]["zone"] if electrodes else 49,
        "utm_hemisphere": electrodes[0]["hemisphere"] if electrodes else "S",
        "total_length_2d_m": electrodes[-1]["cumulative_distance_2d"] if electrodes else 0.0,
        "total_length_3d_m": electrodes[-1]["cumulative_distance_3d"] if electrodes else 0.0,
        "electrodes": electrodes,
        "geojson": geojson
    }

@router.post("/generate-plan")
def generate_planned_survey(
    start_lat: float = Form(-7.7700),
    start_lon: float = Form(110.3700),
    azimuth_deg: float = Form(45.0),
    spacing_m: float = Form(5.0),
    num_electrodes: int = Form(32),
    terrain_type: str = Form("undulating"),
    base_elevation_m: float = Form(125.0),
    survey_name: str = Form("Rencana Lintasan 2D")
):
    """Generates synthetic equidistant survey line with specified topography profile."""
    nodes = UTMConverter.generate_linear_survey(
        start_lat=start_lat,
        start_lon=start_lon,
        azimuth_deg=azimuth_deg,
        spacing_m=spacing_m,
        num_electrodes=num_electrodes
    )

    nodes = DEMInterpolator.apply_elevation_profile(
        nodes,
        base_elevation_m=base_elevation_m,
        slope_pct=2.0,
        terrain_type=terrain_type
    )

    geojson = DEMInterpolator.to_geojson(nodes, survey_name=survey_name)

    CURRENT_SURVEY["survey_name"] = survey_name
    CURRENT_SURVEY["electrodes"] = nodes
    CURRENT_SURVEY["geojson"] = geojson

    return {
        "success": True,
        "survey_name": survey_name,
        "total_electrodes": len(nodes),
        "spacing_nominal_m": spacing_m,
        "total_length_2d_m": nodes[-1]["cumulative_distance_2d"],
        "total_length_3d_m": nodes[-1]["cumulative_distance_3d"],
        "electrodes": nodes,
        "geojson": geojson
    }

@router.get("/geojson")
def get_survey_geojson():
    """Returns active survey GeoJSON for Leaflet / MapLibre."""
    if not CURRENT_SURVEY["geojson"]:
        # Fallback to default sample
        return get_sample_survey()["geojson"]
    return CURRENT_SURVEY["geojson"]

@router.get("/sample")
def get_sample_survey():
    """Loads sample 32-electrode survey from sample NMEA file."""
    import pathlib
    sample_file = pathlib.Path(__file__).parent / "sample_survey_gga.nmea"
    if sample_file.exists():
        text = sample_file.read_text(encoding="utf-8")
        parsed = NMEAParser.parse_stream(text)
        projected = []
        for fix in parsed:
            utm = UTMConverter.wgs84_to_utm(fix["latitude"], fix["longitude"])
            projected.append({
                **fix,
                "easting": utm["easting"],
                "northing": utm["northing"],
                "zone": utm["zone"],
                "hemisphere": utm["hemisphere"],
                "elevation_m": fix["altitude_m"]
            })
        electrodes = UTMConverter.calculate_electrode_spacings(projected)
        geojson = DEMInterpolator.to_geojson(electrodes, survey_name="Survei Demo ResIPy Tim 4")
        return {
            "success": True,
            "survey_name": "Survei Demo ResIPy Tim 4",
            "total_electrodes": len(electrodes),
            "electrodes": electrodes,
            "geojson": geojson
        }
    raise HTTPException(status_code=404, detail="File sample_survey_gga.nmea tidak ditemukan.")

@router.get("/export-resipy-topography", response_class=PlainTextResponse)
def export_resipy_topography():
    """Exports active survey electrodes into ResIPy R2 topography format."""
    electrodes = CURRENT_SURVEY["electrodes"]
    if not electrodes:
        sample = get_sample_survey()
        electrodes = sample["electrodes"]
    
    topo_txt = DEMInterpolator.export_resipy_topography(electrodes)
    return PlainTextResponse(
        content=topo_txt,
        headers={"Content-Disposition": 'attachment; filename="resipy_topography.dat"'}
    )
