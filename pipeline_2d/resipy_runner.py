#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Module: pipeline_2d.resipy_runner
Engine headless inversi 2D ResIPy (cR2/R2) dengan dukungan parsing ResInv .dat,
reciprocal error filtering, automated triangular meshing, dan ekspor grid JSON & VTK.
"""

from __future__ import annotations
import os
import sys
import json
import time
import shutil
import pathlib
import traceback
from datetime import datetime, timezone
from typing import Dict, Any, Optional

import numpy as np
import pandas as pd


class ResIPy2DRunner:
    """Runner untuk pipeline inversi 2D ResIPy headless."""

    def __init__(self, typ: str = "cR2"):
        self.typ = typ
        self.project = None
        self.output_dir = None
        self.run_metadata: Dict[str, Any] = {}

    def run(
        self,
        input_dat_path: str,
        output_dir: str,
        recip_filter_pct: float = 20.0,
        mesh_typ: str = "trian",
        b_wgt: float = 0.4,
        rho_min: float = 1.0,
        max_iter: int = 15,
        target_decrease: float = 0.05,
    ) -> Dict[str, Any]:
        """
        Menjalankan pipeline inversi 2D lengkap:
        1. Parse file survey Loke Res2dInv format (.dat)
        2. Filter reciprocal error & bad datum
        3. Create 2D finite element mesh (triangular/quad)
        4. Eksekusi solver inversi (cR2/R2)
        5. Ekstraksi hasil model (f001_res.vtk, .dat) dan generate grid JSON
        """
        import resipy as rs

        start_time = time.time()
        self.output_dir = pathlib.Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        input_path = pathlib.Path(input_dat_path).resolve()
        if not input_path.is_file():
            raise FileNotFoundError(f"File data survey tidak ditemukan: {input_path}")

        print(f"[INFO] Inisialisasi ResIPy Project (typ={self.typ})...")
        self.project = rs.Project(typ=self.typ)

        # 1. Parsing & Validasi
        print(f"[INFO] Parsing data survei: {input_path} (ftype=ResInv)...")
        self.project.createSurvey(str(input_path), ftype="ResInv")
        if not self.project.surveys:
            raise ValueError("Gagal membaca survei geolistrik dari file input.")

        survey = self.project.surveys[0]
        n_elec = len(survey.elec)
        n_data_raw = len(survey.df)
        print(f"[INFO] Survei dimuat: {n_elec} elektroda, {n_data_raw} quadrupoles data mentah.")

        # 2. Reciprocal error & filtering
        print(f"[INFO] Menjalankan filter reciprocal error (threshold={recip_filter_pct}%)...")
        if "recipError" in survey.df.columns and not survey.df["recipError"].isna().all():
            try:
                self.project.filterRecip(percent=recip_filter_pct)
            except Exception as e:
                print(f"[WARN] filterRecip info: {e}")
        else:
            print("[INFO] Tidak ada data reciprocal pairs dalam survei, melewati filter reciprocal.")

        # Filter nilai resistivitas semu negatif/anomali
        try:
            self.project.filterNegative()
        except Exception as e:
            print(f"[WARN] filterNegative info: {e}")

        n_data_filtered = len(survey.df)
        print(f"[INFO] Data siap inversi: {n_data_filtered} quadrupoles.")

        # 3. Create mesh
        print(f"[INFO] Menghasilkan 2D mesh (typ={mesh_typ})...")
        self.project.createMesh(typ=mesh_typ)
        n_elements = int(self.project.mesh.numel)
        n_nodes = int(self.project.mesh.numnp)
        print(f"[INFO] Mesh berhasil dibangun: {n_elements} elemen, {n_nodes} nodes.")

        # 4. Parameterisasi & Eksekusi Solver Headless (cR2)
        param = {
            "b_wgt": float(b_wgt),
            "rho_min": float(rho_min),
            "max_iter": int(max_iter),
            "target_decrease": float(target_decrease),
        }
        print(f"[INFO] Menjalankan solver headless {self.typ} dengan param: {param}...")
        self.project.invert(param=param)

        # 5. Ekstraksi Hasil Inversi
        invdir = pathlib.Path(self.project.dirname)
        print(f"[INFO] Inversi selesai. Mengumpulkan output dari {invdir}...")

        # Salin file penting ke output_dir
        exported_files = []
        for fname in ["cR2.out", "cR2.in", "mesh.dat", "res0.dat", "protocol.dat", "electrodes.dat", "f001_res.dat", "f001_res.vtk"]:
            src_f = invdir / fname
            if src_f.is_file():
                dest_f = self.output_dir / fname
                shutil.copy2(src_f, dest_f)
                exported_files.append(fname)

        # Parse summary hasil & RMS
        final_rms = None
        iterations_run = 0
        converged = False

        cR2_out = self.output_dir / "cR2.out"
        if cR2_out.is_file():
            with open(cR2_out, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if "Final RMS Misfit:" in line:
                        try:
                            final_rms = float(line.split()[-1])
                        except Exception:
                            pass
                    if "Iteration" in line:
                        iterations_run += 1
                    if "Convergence of inverse solution" in line or (final_rms is not None and final_rms < 5.0):
                        converged = True

        # Generate Grid JSON untuk render web frontend
        grid_json_path = self.output_dir / "model_grid_2d.json"
        grid_data = self._export_grid_json(grid_json_path)
        if grid_json_path.is_file():
            exported_files.append("model_grid_2d.json")

        elapsed_sec = round(time.time() - start_time, 2)
        summary = {
            "status": "success",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "elapsed_seconds": elapsed_sec,
            "engine": self.typ,
            "input_file": str(input_path),
            "output_directory": str(self.output_dir.resolve()),
            "parameters": param,
            "survey": {
                "electrodes_count": n_elec,
                "data_points_raw": n_data_raw,
                "data_points_filtered": n_data_filtered,
            },
            "mesh": {
                "type": mesh_typ,
                "elements_count": n_elements,
                "nodes_count": n_nodes,
            },
            "inversion_result": {
                "iterations_run": iterations_run,
                "final_rms": final_rms,
                "converged": bool(converged),
            },
            "exported_files": exported_files,
            "grid_summary": {
                "cell_count": len(grid_data.get("cells", [])),
                "res_min": grid_data.get("res_min"),
                "res_max": grid_data.get("res_max"),
                "depth_max": grid_data.get("depth_max"),
            }
        }

        summary_file = self.output_dir / "inversion_summary.json"
        with open(summary_file, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        exported_files.append("inversion_summary.json")

        return summary

    def _export_grid_json(self, output_path: pathlib.Path) -> Dict[str, Any]:
        """Ekspor data elemen finite element (X, Z, Resistivitas, Phase) ke JSON grid untuk render UI."""
        if self.output_dir is None:
            return {}
        vtk_path = self.output_dir / "f001_res.vtk"
        if not vtk_path.is_file():
            return {}

        import resipy.meshTools as mt
        try:
            m = mt.vtk_import(str(vtk_path), order_nodes=False)
            df = m.df
            
            # Ambil centroid elemen atau koordinat X, Z dan resistivitas
            x = df["X"].values.tolist() if "X" in df.columns else []
            z = df["Z"].values.tolist() if "Z" in df.columns else []
            res = df["Magnitude(ohm.m)"].values.tolist() if "Magnitude(ohm.m)" in df.columns else []
            phase = df["Phase(mrad)"].values.tolist() if "Phase(mrad)" in df.columns else []

            cells = []
            for i in range(len(res)):
                cells.append({
                    "id": i + 1,
                    "x": round(float(x[i]), 2) if i < len(x) else 0.0,
                    "z": round(float(z[i]), 2) if i < len(z) else 0.0,
                    "res": round(float(res[i]), 2),
                    "phase": round(float(phase[i]), 2) if i < len(phase) else 0.0
                })

            valid_res = [c["res"] for c in cells if c["res"] > 0]
            valid_z = [c["z"] for c in cells]

            payload = {
                "total_cells": len(cells),
                "res_min": float(min(valid_res)) if valid_res else 0.0,
                "res_max": float(max(valid_res)) if valid_res else 0.0,
                "depth_max": float(abs(min(valid_z))) if valid_z else 0.0,
                "cells": cells
            }

            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)

            return payload
        except Exception as e:
            print(f"[WARN] Gagal mengekspor grid JSON: {e}")
            return {}


def main():
    import argparse
    parser = argparse.ArgumentParser(description="ResIPy 2D Inversion Engine (CLI)")
    parser.add_argument("--data", "-d", required=True, help="Path ke file data .dat")
    parser.add_argument("--out", "-o", default="./inversion_output", help="Direktori output")
    parser.add_argument("--typ", default="cR2", choices=["cR2", "R2"], help="Engine solver")
    parser.add_argument("--b-wgt", type=float, default=0.4, help="Data weight b_wgt")
    parser.add_argument("--rho-min", type=float, default=1.0, help="Minimum resistivity")
    parser.add_argument("--max-iter", type=int, default=15, help="Maksimal iterasi")
    parser.add_argument("--recip-pct", type=float, default=20.0, help="Reciprocal error filter percent")
    parser.add_argument("--mesh", default="trian", choices=["trian", "quad"], help="Tipe mesh")

    args = parser.parse_args()

    runner = ResIPy2DRunner(typ=args.typ)
    result = runner.run(
        input_dat_path=args.data,
        output_dir=args.out,
        recip_filter_pct=args.recip_pct,
        mesh_typ=args.mesh,
        b_wgt=args.b_wgt,
        rho_min=args.rho_min,
        max_iter=args.max_iter,
    )

    print("\n" + "=" * 60)
    print("HASIL INVERSI 2D (JSON SUMMARY):")
    print(json.dumps(result, indent=2))
    print("=" * 60)


if __name__ == "__main__":
    main()
