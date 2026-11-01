from __future__ import annotations
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
import pathlib
import json
import uuid
import subprocess
import os
import shutil

router = APIRouter(prefix="/api/inversion", tags=["ResIPy 2D Inversion"])

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RUNS_DIR = PROJECT_ROOT / "runs"
RUNS_DIR.mkdir(parents=True, exist_ok=True)

RUNNER_SCRIPT = PROJECT_ROOT / "pipeline_2d" / "resipy_runner.py"

# Konfigurasi Integrasi Simpul Komputasi Cika (Ubuntu 100.91.228.122)
CIKA_HOST = "rangga@100.91.228.122"
CIKA_RESIPY_ROOT = "/home/rangga/Documents/Project/git-resipy/resipy"
CIKA_PYTHON = f"{CIKA_RESIPY_ROOT}/resipy_env/bin/python"
CIKA_SRC = f"{CIKA_RESIPY_ROOT}/src"
CIKA_WORKER_DIR = "/home/rangga/resipy_worker"

# In-memory tracking untuk job inversi
JOBS_REGISTRY = {}


class InversionRunRequest(BaseModel):
    filename: str = Field(..., description="Nama file survei (.dat atau .csv) di folder data/")
    engine: str = Field("cR2", description="Engine solver: cR2 atau R2")
    mesh_typ: str = Field("trian", description="Tipe mesh: trian atau quad")
    b_wgt: float = Field(0.4, description="Parameter pembobotan error b_wgt")
    rho_min: float = Field(1.0, description="Minimum allowable resistivity (ohm.m)")
    max_iter: int = Field(15, description="Maksimum iterasi")
    recip_pct: float = Field(20.0, description="Ambang batas reciprocal error (%)")


def check_cika_readiness() -> dict:
    """Verifikasi kesiapan integrasi node Cika dan environment ResIPy."""
    test_cmd = (
        f"test -d {CIKA_SRC}/resipy && "
        f"PYTHONPATH={CIKA_SRC} MPLBACKEND=Agg {CIKA_PYTHON} -c "
        f"\"import resipy; from resipy import Project; print('CIKA_RESIPY_READY')\""
    )
    try:
        res = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", CIKA_HOST, test_cmd],
            capture_output=True,
            text=True,
            timeout=15
        )
        ready = (res.returncode == 0 and "CIKA_RESIPY_READY" in res.stdout)
        return {
            "status": "ready" if ready else "error",
            "host": CIKA_HOST,
            "resipy_src": f"{CIKA_SRC}/resipy",
            "python_env": CIKA_PYTHON,
            "output": res.stdout.strip() or res.stderr.strip()
        }
    except Exception as exc:
        return {
            "status": "offline",
            "host": CIKA_HOST,
            "error": str(exc)
        }


def run_inversion_task(job_id: str, req_dict: dict):
    job_dir = RUNS_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    
    input_file = DATA_DIR / req_dict["filename"]
    if not input_file.is_file():
        JOBS_REGISTRY[job_id]["status"] = "failed"
        JOBS_REGISTRY[job_id]["error"] = f"File {req_dict['filename']} tidak ditemukan di data/"
        return

    log_path = job_dir / "execution.log"
    JOBS_REGISTRY[job_id]["status"] = "running"
    JOBS_REGISTRY[job_id]["node"] = "Ubuntu Cika (100.91.228.122)"

    with open(log_path, "w", encoding="utf-8") as log_f:
        try:
            log_f.write(f"[*] Inisialisasi job {job_id} pada simpul Cika ({CIKA_HOST})...\n")
            log_f.write(f"[*] Folder ResIPy: {CIKA_RESIPY_ROOT}\n")
            log_f.flush()

            # 1. Pastikan folder kerja di Cika ada
            remote_job_dir = f"{CIKA_WORKER_DIR}/{job_id}"
            subprocess.run(
                ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", CIKA_HOST, f"mkdir -p {remote_job_dir}"],
                check=True, stdout=log_f, stderr=subprocess.STDOUT, timeout=20
            )

            # 2. Transfer file survei dan runner script ke Cika
            subprocess.run(
                ["scp", "-o", "BatchMode=yes", str(input_file), f"{CIKA_HOST}:{remote_job_dir}/{input_file.name}"],
                check=True, stdout=log_f, stderr=subprocess.STDOUT, timeout=30
            )
            subprocess.run(
                ["scp", "-o", "BatchMode=yes", str(RUNNER_SCRIPT), f"{CIKA_HOST}:{CIKA_WORKER_DIR}/resipy_runner.py"],
                check=True, stdout=log_f, stderr=subprocess.STDOUT, timeout=30
            )

            # 3. Eksekusi Inversi Headless di Cika menggunakan resipy_env Cika
            remote_cmd = (
                f"cd {remote_job_dir} && "
                f"PYTHONPATH={CIKA_SRC} MPLBACKEND=Agg {CIKA_PYTHON} {CIKA_WORKER_DIR}/resipy_runner.py "
                f"--data {input_file.name} "
                f"--out . "
                f"--typ {req_dict.get('engine', 'cR2')} "
                f"--mesh {req_dict.get('mesh_typ', 'trian')} "
                f"--b-wgt {req_dict.get('b_wgt', 0.4)} "
                f"--rho-min {req_dict.get('rho_min', 1.0)} "
                f"--max-iter {req_dict.get('max_iter', 15)} "
                f"--recip-pct {req_dict.get('recip_pct', 20.0)}"
            )
            log_f.write(f"[*] Menjalankan perintah remote di Cika:\n{remote_cmd}\n\n")
            log_f.flush()

            res = subprocess.run(
                ["ssh", "-o", "BatchMode=yes", CIKA_HOST, remote_cmd],
                stdout=log_f, stderr=subprocess.STDOUT, text=True, timeout=300
            )

            if res.returncode == 0:
                log_f.write("\n[*] Eksekusi Cika selesai dengan sukses. Mengunduh hasil kembali ke NAS...\n")
                log_f.flush()
                # 4. Tarik seluruh artefak (.vtk, .dat, .out, .json) kembali ke NAS
                subprocess.run(
                    f"scp -o BatchMode=yes {CIKA_HOST}:{remote_job_dir}/* {job_dir}/",
                    shell=True, stdout=log_f, stderr=subprocess.STDOUT, timeout=45
                )

                # 5. Bersihkan direktori temporary di Cika
                subprocess.run(
                    ["ssh", "-o", "BatchMode=yes", CIKA_HOST, f"rm -rf {remote_job_dir}"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15
                )

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
            log_f.write(f"\n[ERROR] Exception occurred: {exc}\n")


@router.get("/cika-status")
def cika_status():
    """Status koneksi dan kesiapan ResIPy Cika."""
    return check_cika_readiness()


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
        "node": "Ubuntu Cika (100.91.228.122)",
        "resipy_source": f"{CIKA_SRC}/resipy"
    }

    background_tasks.add_task(run_inversion_task, job_id, req.dict())

    return {
        "success": True,
        "job_id": job_id,
        "status": "queued",
        "node": "Ubuntu Cika (100.91.228.122)",
        "resipy_source": f"{CIKA_SRC}/resipy",
        "message": f"Job inversi 2D {job_id} berhasil dijadwalkan ke simpul Cika.",
        "params": req.dict()
    }


@router.get("/status/{job_id}")
async def get_inversion_status(job_id: str):
    if job_id not in JOBS_REGISTRY:
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
