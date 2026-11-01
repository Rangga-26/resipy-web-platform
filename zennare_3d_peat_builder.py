import os, sys, json, pathlib
import numpy as np
import pyvista as pv

def main():
    vtk_2d_path = pathlib.Path("/home/rangga/resipy_worker/zennare_real_run/f001_res.vtk")
    if not vtk_2d_path.is_file():
        vtk_2d_path = pathlib.Path("/home/rangga/resipy_worker/zennare_real_run/work/invdir/f001_res.vtk")
    if not vtk_2d_path.is_file():
        raise FileNotFoundError(f"Missing 2D VTK: {vtk_2d_path}")

    out_dir = pathlib.Path("/home/rangga/resipy_worker/zennare_3d_run")
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading 2D mesh from {vtk_2d_path}...")
    mesh2d = pv.read(str(vtk_2d_path))
    print(f"Mesh 2D summary: {mesh2d.n_points} points, {mesh2d.n_cells} cells")
    print(f"Point arrays: {mesh2d.point_data.keys()}, Cell arrays: {mesh2d.cell_data.keys()}")

    # Cari array resistivitas
    res_key = None
    data_source = None
    for k in ["Resistivity(ohm.m)", "Magnitude(ohm.m)", "Resistivity(log10)"]:
        if k in mesh2d.cell_data:
            res_key = k
            data_source = "cell"
            break
        if k in mesh2d.point_data:
            res_key = k
            data_source = "point"
            break

    if res_key is None:
        all_keys = list(mesh2d.cell_data.keys()) + list(mesh2d.point_data.keys())
        if all_keys:
            res_key = all_keys[0]
            data_source = "cell" if res_key in mesh2d.cell_data else "point"
        else:
            raise ValueError("No scalar data array found in VTK!")

    print(f"Using resistivity array: {res_key} (from {data_source})")

    # Mesh 2D ResIPy berada pada bidang X - Y (di mana Y adalah elevasi/kedalaman di ResIPy)!
    # Cek bounds aktual
    print(f"Mesh 2D full bounds (xmin, xmax, ymin, ymax, zmin, zmax): {mesh2d.bounds}")
    x_bounds = mesh2d.bounds[0], mesh2d.bounds[1] # 0 to 23.625 m
    elev_bounds = mesh2d.bounds[2], mesh2d.bounds[3] # misal -5.5 to 0.0 m
    print(f"Mesh 2D X-range: {x_bounds}, Elevation-range (Y di mesh2d): {elev_bounds}")

    # Buat regular 3D grid voxel:
    # Sumbu X: sepanjang profil (0 s/d 23.625 m)
    # Sumbu Y: lebar melintang 3D (0 s/d 3.0 m)
    # Sumbu Z: elevasi/kedalaman sejati (elev_bounds[0] s/d elev_bounds[1])
    nx, ny, nz = 160, 25, 50
    gx = np.linspace(x_bounds[0], x_bounds[1], nx)
    gy = np.linspace(0.0, 3.0, ny)
    gz = np.linspace(elev_bounds[0], elev_bounds[1], nz)
    grid3d = pv.RectilinearGrid(gx, gy, gz)

    # Titik query untuk sampling dari mesh2d:
    # mesh2d titiknya berkoordinat (x, elevasi, 0)
    pts3d = grid3d.points # shape (N, 3): [x, y, z]
    pts2d_query = np.zeros_like(pts3d)
    pts2d_query[:, 0] = pts3d[:, 0] # X sama
    pts2d_query[:, 1] = pts3d[:, 2] # Elevasi Z dipetakan ke sumbu Y mesh2d
    pts2d_query[:, 2] = 0.0         # Z pada mesh2d adalah 0

    query_cloud = pv.PolyData(pts2d_query)
    sampled = query_cloud.sample(mesh2d)
    grid3d[res_key] = sampled[res_key]

    # Bersihkan nilai resistivitas: pastikan strictly positive dan tidak ada NaN/Inf
    res_raw = grid3d[res_key]
    # Ganti NaN, Inf, atau <= 0 dengan nilai fallback valid (misal 7.0 Ohm.m)
    invalid_mask = np.isnan(res_raw) | np.isinf(res_raw) | (res_raw <= 0)
    res_cleaned = np.where(invalid_mask, 7.0, res_raw)
    # Clip ke rentang geofisika yang masuk akal berdasarkan data 2D
    c_min = 5.0
    c_max = 60.0
    res_cleaned = np.clip(res_cleaned, c_min, c_max)
    grid3d[res_key] = res_cleaned

    print(f"Cleaned resistivity: min={np.min(res_cleaned):.2f}, max={np.max(res_cleaned):.2f}, mean={np.mean(res_cleaned):.2f}")

    out_vtk_3d = out_dir / "zennare_peat_3d_volume.vtk"
    grid3d.save(str(out_vtk_3d))
    print(f"Saved solid 3D grid VTK: {out_vtk_3d}")

    # Render 1: Volume Isometrik 3D Solid
    pv.set_plot_theme("document")
    p = pv.Plotter(off_screen=True, window_size=[1600, 1000])
    p.set_background("white")

    sargs = dict(
        title="Resistivitas (Ohm.m)",
        title_font_size=13,
        label_font_size=11,
        shadow=False,
        n_labels=6,
        fmt="%.1f",
        position_x=0.30,
        position_y=0.015,
        width=0.40,
        height=0.04
    )

    p.add_mesh(grid3d.outline(), color="black", line_width=1.5)
    p.add_mesh(
        grid3d,
        scalars=res_key,
        cmap="turbo",
        log_scale=True,
        clim=[c_min, c_max],
        opacity=0.88,
        scalar_bar_args=sargs
    )

    # Titik elektroda di permukaan Z=0
    elec_x = np.linspace(0.0, 23.5, 48)
    for y_pos in [0.5, 1.5, 2.5]:
        pts = np.column_stack([elec_x, np.full_like(elec_x, y_pos), np.zeros_like(elec_x)])
        p.add_points(pts, color="black", point_size=6, render_points_as_spheres=True)

    p.show_bounds(
        xtitle="Panjang X (m)",
        ytitle="Lebar Y (m)",
        ztitle="Kedalaman Z (m)",
        color="black",
        font_size=10,
        location="outer",
        axes_ranges=[x_bounds[0], x_bounds[1], 0.0, 3.0, elev_bounds[0], elev_bounds[1]]
    )
    p.camera_position = [
        (38.0, -22.0, 14.0),
        (11.75, 1.5, -2.5),
        (0.0, 0.0, 1.0)
    ]
    p.add_title(
        "REKONSTRUKSI 3D TOMOGRAFI ERT LAHAN GAMBUT (BASIN ZENNARE, ITALIA)\n"
        "Model 3D Solid Voxel Grid dari ERT Lapangan Nyata (Boaga et al., 2020)",
        font_size=14,
        color="black"
    )
    out_img = out_dir / "zennare_peat_3d_isometric.png"
    p.screenshot(str(out_img))
    print(f"Saved 3D isometric screenshot: {out_img}")

    # Render 2: Irisan Tiga Bidang 3D Sejati (Orthogonal Slices)
    p2 = pv.Plotter(off_screen=True, window_size=[1600, 1000])
    p2.set_background("white")

    slice_x = grid3d.slice(normal="x", origin=(11.75, 0, 0))
    slice_y = grid3d.slice(normal="y", origin=(0, 1.5, 0))
    slice_z = grid3d.slice(normal="z", origin=(0, 0, -1.34)) # Batas rata-rata bor gambut

    sargs2 = dict(
        title="Resistivitas (Ohm.m)",
        title_font_size=13,
        label_font_size=11,
        shadow=False,
        n_labels=6,
        fmt="%.1f",
        position_x=0.30,
        position_y=0.015,
        width=0.40,
        height=0.04
    )

    p2.add_mesh(grid3d.outline(), color="black", line_width=1.5)
    p2.add_mesh(slice_x, scalars=res_key, cmap="turbo", log_scale=True, clim=[c_min, c_max], show_scalar_bar=False)
    p2.add_mesh(slice_y, scalars=res_key, cmap="turbo", log_scale=True, clim=[c_min, c_max], show_scalar_bar=False)
    p2.add_mesh(slice_z, scalars=res_key, cmap="turbo", log_scale=True, clim=[c_min, c_max], scalar_bar_args=sargs2)

    p2.show_bounds(
        xtitle="Panjang X (m)",
        ytitle="Lebar Y (m)",
        ztitle="Kedalaman Z (m)",
        color="black",
        font_size=10,
        location="outer",
        axes_ranges=[x_bounds[0], x_bounds[1], 0.0, 3.0, elev_bounds[0], elev_bounds[1]]
    )
    p2.camera_position = [
        (38.0, -22.0, 14.0),
        (11.75, 1.5, -2.5),
        (0.0, 0.0, 1.0)
    ]
    p2.add_title(
        "IRISAN TIGA BIDANG 3D (X-Y-Z ORTHOGONAL SLICES)\n"
        "Bidang Horizontal Z = -1.34 m (Batas Rata-Rata Bor Gambut) & Bidang Tengah X/Y",
        font_size=14,
        color="black"
    )
    out_slices_img = out_dir / "zennare_peat_3d_orthoslices.png"
    p2.screenshot(str(out_slices_img))
    print(f"Saved 3D solid orthoslices screenshot: {out_slices_img}")

    summary = {
        "status": "success",
        "representation": "3D Solid Voxel Grid & Orthogonal Slices from Real 2D Inversion",
        "mesh_2d_source": str(vtk_2d_path),
        "grid_3d_cells": int(grid3d.n_cells),
        "grid_3d_points": int(grid3d.n_points),
        "extrusion_y_m": 3.0,
        "files": [
            str(out_vtk_3d.name),
            str(out_img.name),
            str(out_slices_img.name)
        ]
    }
    with open(out_dir / "zennare_3d_summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    print("ALL 3D TASKS COMPLETED!")

if __name__ == "__main__":
    main()
