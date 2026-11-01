from __future__ import annotations
from fastapi import APIRouter, HTTPException, BackgroundTasks, Query
from pydantic import BaseModel, Field
import pathlib
import json
import uuid
import subprocess
import os

router = APIRouter(prefix="/api/inversion", tags=["ResIPy 2D Inversion"])

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RUNS_DIR = PROJECT_ROOT / "runs"
RUNS_DIR.mkdir(parents=True, exist_ok=True)

RESIPY_PYTHON = "/opt/resipy_env/bin/python"
RUNNER_SCRIPT = PROJECT_ROOT / "pipeline_2d" / "resipy_runner.py"

# In-memory tracking untuk job inversi
JOBS_REGISTRY = {}


class InversionRunRequest(BaseModel):
    filename: str = Field(..., description="Nama file survei .dat di folder data/")
    engine: str = Field("cR2", description="Engine solver: cR2 atau R2")
    mesh_typ: str = Field("trian", description="Tipe mesh: trian atau quad")
    b_wgt: float = Field(0.4, description="Parameter pembobotan error b_wgt")
    rho_min: float = Field(1.0, description="Minimum allowable resistivity (ohm.m)")
    max_iter: int = Field(15, description="Maksimum iterasi")
    recip_pct: float = Field(20.0, description="Ambang batas reciprocal error (%)")


def run_inversion_task(job_id: str, req_dict: dict):
    job_dir = RUNS_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    
    input_file = DATA_DIR / req_dict["filename"]
    if not input_file.is_file():
        JOBS_REGISTRY[job_id]["status"] = "failed"
        JOBS_REGISTRY[job_id]["error"] = f"File {req_dict['filename']} tidak ditemukan di data/"
        return

    cmd = [
        RESIPY_PYTHON,
        str(RUNNER_SCRIPT),
        "--data", str(input_file),
        "--out", str(job_dir),
        "--typ", req_dict.get("engine", "cR2"),
        "--mesh", req_dict.get("mesh_typ", "trian"),
        "--b-wgt", str(req_dict.get("b_wgt", 0.4)),
        "--rho-min", str(req_dict.get("rho_min", 1.0)),
        "--max-iter", str(req_dict.get("max_iter", 15)),
        "--recip-pct", str(req_dict.get("recip_pct", 20.0)),
    ]

    log_path = job_dir / "execution.log"
    JOBS_REGISTRY[job_id]["status"] = "running"

    with open(log_path, "w", encoding="utf-8") as log_f:
        try:
            res = subprocess.run(cmd, stdout=log_f, stderr=subprocess.STDOUT, text=True)
            if res.returncode == 0:
                summary_path = job_dir / "inversion_summary.json"
                if summary_path.is_file():
                    with open(summary_path, "r", encoding="utf-8") as sf:
                        summary_data = json.load(sf)
                    JOBS_REGISTRY[job_id]["status"] = "completed"
                    JOBS_REGISTRY[job_id]["summary"] = summary_data
                else:
                    JOBS_REGISTRY[job_id]["status"] = "completed"
            else:
                JOBS_REGISTRY[job_id]["status"] = "failed"
                JOBS_REGISTRY[job_id]["error"] = f"Solver return non-zero code {res.returncode}. Cek execution.log"
        except Exception as exc:
            JOBS_REGISTRY[job_id]["status"] = "failed"
            JOBS_REGISTRY[job_id]["error"] = str(exc)


@router.post("/run")
async def start_inversion(req: InversionRunRequest, background_tasks: BackgroundTasks):
    input_file = DATA_DIR / req.filename
    if not input_file.is_file():
        raise HTTPException(status_code=404, detail=f"File survei {req.filename} belum diunggah.")

    job_id = f"inv_2d_{uuid.uuid4().hex[:8]}"
    JOBS_REGISTRY[job_id] = {
        "job_id": job_id,
        "filename": req.filename,
        "engine": req.engine,
        "status": "queued",
        "created_at": str(pathlib.Path().stat().st_ctime if hasattr(pathlib.Path(), "stat") else 0)
    }

    background_tasks.add_task(run_inversion_task, job_id, req.dict())

    return {
        "success": True,
        "job_id": job_id,
        "status": "queued",
        "message": f"Job inversi 2D {job_id} berhasil dijadwalkan.",
        "params": req.dict()
    }


@router.get("/status/{job_id}")
async def get_inversion_status(job_id: str):
    if job_id not in JOBS_REGISTRY:
        # Coba cek apakah ada folder di runs/
        summary_path = RUNS_DIR / job_id / "inversion_summary.json"
        if summary_path.is_file():
            with open(summary_path, "r", encoding="utf-8") as sf:
                data = json.load(sf)
            return {"job_id": job_id, "status": "completed", "summary": data}
        raise HTTPException(status_code=404, detail="Job ID tidak ditemukan.")

    job_info = dict(JOBS_REGISTRY[job_id])
    return job_info


@router.get("/grid/{job_id}")
async def get_inversion_grid(job_id: str):
    grid_path = RUNS_DIR / job_id / "model_grid_2d.json"
    if not grid_path.is_file():
        raise HTTPException(status_code=404, detail="Model grid 2D belum tersedia untuk job ini.")
    with open(grid_path, "r", encoding="utf-8") as f:
        return json.load(f)


@router.get("/list")
async def list_inversion_runs():
    runs = []
    for d in RUNS_DIR.iterdir():
        if d.is_dir():
            s_file = d / "inversion_summary.json"
            runs.append({
                "job_id": d.name,
                "has_summary": s_file.is_file()
            })
    return {"total_runs": len(runs), "runs": runs}
