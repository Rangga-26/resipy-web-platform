from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os, shutil, json, pathlib, sys

# Ensure project root is in sys.path
PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from gps_maps.router import router as gps_router

app = FastAPI(
    title="ResIPy & GPS Geophysics Platform API",
    version="1.0.0",
    description="Integrated API for 2D/3D ResIPy Electrical Resistivity Inversion and Field GPS Telemetry."
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Mount GPS & Maps Router (Tim 4 - Healtrack)
app.include_router(gps_router)

# Mount Frontend GUI
FRONTEND_DIR = PROJECT_ROOT / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/gui", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="gui")

@app.get("/")
def read_root():
    return {
        "status": "online",
        "service": "ResIPy 2D/3D & GPS Platform Engine",
        "modules": {
            "gui": "Active (Dashboard & Inversion Control)",
            "resipy_2d": "Active (R2/cR2 Inversion Engine)",
            "design_3d": "Active (3D Voxel & Iso-surface Slicer)",
            "gps_maps": "Active (NMEA-0183 Parser, UTM Planar Projection & DEM Inversion Topo)"
        }
    }

@app.post("/api/survey/upload")
async def upload_survey_data(
    file: UploadFile = File(...),
    array_type: str = Form("Wenner-Schlumberger"),
    spacing: float = Form(5.0)
):
    dest = DATA_DIR / file.filename
    with dest.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    return {
        "success": True,
        "filename": file.filename,
        "array_type": array_type,
        "spacing_m": spacing,
        "file_size": dest.stat().st_size,
        "message": "File survey berhasil diunggah. Siap untuk QC dan inversi ResIPy."
    }

@app.get("/api/survey/status")
def survey_status():
    files = [f.name for f in DATA_DIR.glob("*") if f.is_file()]
    return {
        "total_files": len(files),
        "files": files
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8005)
