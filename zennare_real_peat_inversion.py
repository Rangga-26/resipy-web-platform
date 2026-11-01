"""Field Peatland ERT Inversion Runner.
Dataset: Zennare Basin Peatland, Venice Coastland, Italy.
Reference: Boaga et al. (2020), STOTEN / Zenodo DOI: 10.5281/zenodo.3786404.
Hardware: Syscal Pro 48 electrodes, 0.5 m spacing (total length 23.5 m).
"""
import os
import sys
import json
import time
import shutil
import pathlib
import hashlib
os.environ['MPLBACKEND'] = 'Agg'
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

def main():
    start_time = time.time()
    work_dir = pathlib.Path("/home/rangga/resipy_worker/zennare_real_run/work")
    out_dir = pathlib.Path("/home/rangga/resipy_worker/zennare_real_run")
    if work_dir.exists():
        shutil.rmtree(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    protocol_file = pathlib.Path("/home/rangga/resipy_worker/zennare_protocol.dat")
    if not protocol_file.is_file():
        raise FileNotFoundError(f"Missing {protocol_file}")

    input_sha256 = hashlib.sha256(protocol_file.read_bytes()).hexdigest()

    import resipy as rs
    from resipy import meshTools as mt

    p = rs.Project(dirname=str(work_dir), typ="R2")
    p.createSurvey(str(protocol_file), ftype="ProtocolDC")
    survey = p.surveys[0]

    raw_data_count = len(survey.df)
    elec = survey.elec.copy()
    elec["x"] = np.arange(len(elec)) * 0.5
    elec["y"] = 0.0
    elec["z"] = 0.0
    p.setElec(elec)

    p.createMesh(typ="trian", cl=0.25, fmd=8.0)
    mesh_elements = int(p.mesh.numel)
    mesh_nodes = int(p.mesh.numnp)

    # Inversi parameter R2 teratur
    param = {
        "max_iter": 6,
        "a_wgt": 0.001,
        "b_wgt": 0.03,
        "target_decrease": 0.05
    }
    p.invert(param=param)

    # Muat f001_res.vtk dari invdir di dalam work directory
    inv_dir = work_dir / "invdir"
    vtk_path = inv_dir / "f001_res.vtk"
    if not vtk_path.is_file():
        raise FileNotFoundError(f"Missing inverted vtk {vtk_path}")

    m = mt.vtk_import(str(vtk_path))
    res_col = next(c for c in ["Resistivity(ohm.m)", "Magnitude(ohm.m)"] if c in m.df.columns)
    model_res = m.df[res_col].to_numpy()
    centres = m.elmCentre

    r2_out = inv_dir / "R2.out"
    final_rms = None
    if r2_out.is_file():
        out_txt = r2_out.read_text(encoding="utf-8", errors="ignore")
        rms_matches = [float(x) for x in re.findall(r"Final RMS Misfit:\s+([0-9.]+)", out_txt)]
        if rms_matches:
            final_rms = rms_matches[-1]

    # Ekspor plot penampang resistivitas real
    fig, ax = plt.subplots(figsize=(12, 5.5), dpi=150)
    sc = ax.scatter(
        centres[:, 0], centres[:, 2],
        c=model_res,
        cmap="turbo",
        norm=matplotlib.colors.LogNorm(vmin=1.0, vmax=50.0),
        s=32, edgecolors="none"
    )
    ax.scatter(elec["x"], elec["z"], c="black", s=18, label="Elektroda (48 titik, spasi 0.5 m)", zorder=4)
    # Garis ketebalan rata-rata gambut Boaga et al. 2020 (1.34 m)
    ax.axhline(y=-1.34, color="white", linestyle="--", linewidth=1.5, label="Rata-rata ketebalan gambut bor (1.34 m)")
    
    cb = plt.colorbar(sc, ax=ax, orientation="horizontal", pad=0.18, fraction=0.045)
    cb.set_label("Resistivitas Model Lapisan Nyata (Ohm.m)")
    
    ax.set_title(
        "HASIL INVERSI ERT LAPANGAN REAL: LAHAN GAMBUT BASIN ZENNARE (ITALIA)\n"
        f"Data Riil Syscal Pro 48 Elektroda (Boaga et al. 2020, STOTEN / Zenodo 10.5281/zenodo.3786404) | Final RMS = {final_rms}",
        fontsize=10.5, fontweight="bold", pad=10
    )
    ax.set_xlabel("Jarak Sepanjang Lintasan (m)", fontsize=9.5)
    ax.set_ylabel("Elevasi Relatif (m)", fontsize=9.5)
    ax.set_xlim(-0.5, 24.0)
    ax.set_ylim(-5.5, 0.5)
    ax.grid(True, linestyle=":", alpha=0.5)
    ax.legend(loc="lower left", fontsize=8.5)
    fig.tight_layout()

    plot_file = out_dir / "zennare_real_peat_inversion.png"
    fig.savefig(str(plot_file))
    plt.close(fig)

    summary = {
        "status": "success",
        "dataset_name": "Zennare Basin Peatland ERT Survey (Real Field Data)",
        "citation": "Boaga et al. (2020), STOTEN; Zenodo DOI: 10.5281/zenodo.3786404",
        "instrument": "Syscal Pro Switch 48 (Iris Instruments)",
        "survey_geometry": {
            "electrodes": 48,
            "spacing_m": 0.5,
            "total_length_m": 23.5,
            "dipole_dipole_points": raw_data_count
        },
        "input_sha256": input_sha256,
        "mesh": {
            "type": "triangular",
            "elements": mesh_elements,
            "nodes": mesh_nodes
        },
        "solver": {
            "engine": "R2 v4.10",
            "final_rms_misfit": final_rms,
            "elapsed_seconds": round(time.time() - start_time, 2)
        },
        "model_statistics": {
            "cells_count": int(len(model_res)),
            "min_ohm_m": float(np.min(model_res)),
            "max_ohm_m": float(np.max(model_res)),
            "median_ohm_m": float(np.median(model_res))
        },
        "geological_context": "Lahan gambut pesisir Venesia di atas lapisan lempung/air asin intrusi; gambut tipis (~1.34 m) memiliki resistivitas relatif lebih tinggi dibanding substrat salin lempung."
    }

    summary_file = out_dir / "zennare_summary.json"
    summary_file.write_text(json.dumps(summary, indent=2))

    # Salin artefak penting
    shutil.copy2(vtk_path, out_dir / "f001_res.vtk")
    if r2_out.is_file():
        shutil.copy2(r2_out, out_dir / "R2.out")
    print(json.dumps(summary, indent=2))

if __name__ == "__main__":
    import re
    import matplotlib
    main()
