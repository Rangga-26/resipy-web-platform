"""Illustrative synthetic peat ERT under wet vs dry surface scenario.
Demonstration artifact: assumed electrical layers coupled with PeatFR demonstration context.
NOT field measurements or calibrated peat properties.
"""
import os, sys, json, re, hashlib
from pathlib import Path
os.environ['MPLBACKEND'] = 'Agg'
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.tri as tri
from matplotlib.colors import LogNorm
from resipy import Project
from resipy import meshTools as mt

root = Path(sys.argv[1]).resolve()
root.mkdir(parents=True, exist_ok=True)
np.random.seed(42)

# 1. Inspect PeatFR demonstration dataset metadata & representative dates
peatfr_csv = Path('/home/localai/projects/peatfr/data/international_demo_sabangau_2023/peatfr_international_sources_demo_2023.csv')
if not peatfr_csv.exists():
    # If executed remotely where localai path is absent, fallback to local path in worker
    peatfr_csv = Path(sys.argv[2])

df_peat = pd.read_csv(peatfr_csv)
# Pick two representative days from the 192-day demo:
# Wet candidate: 2023-04-20 (ERA5 rainfall 43.6 mm, top SM 0.327 m3/m3)
# Dry candidate: 2023-08-15 (ERA5 rainfall 0.0 mm, top SM 0.118 m3/m3)
wet_row = df_peat.loc[df_peat['open_meteo_precipitation_sum_mm'].idxmax()]
dry_row = df_peat.loc[df_peat['open_meteo_soil_moisture_0_7cm_mean_m3_m3'].idxmin()]

scenarios = {
    'wet': {
        'date': str(wet_row['date_utc']),
        'rain_mm': float(wet_row['open_meteo_precipitation_sum_mm']),
        'sm_top': float(wet_row['open_meteo_soil_moisture_0_7cm_mean_m3_m3']),
        'sm_sub': float(wet_row['open_meteo_soil_moisture_28_100cm_mean_m3_m3']),
        # Assumed electrical resistivities for synthetic forward demonstration:
        # Wet upper layer more conductive due to higher moisture
        'rho_upper': 60.0,
        'rho_wet_zone': 25.0,
        'rho_substrate': 20.0
    },
    'dry': {
        'date': str(dry_row['date_utc']),
        'rain_mm': float(dry_row['open_meteo_precipitation_sum_mm']),
        'sm_top': float(dry_row['open_meteo_soil_moisture_0_7cm_mean_m3_m3']),
        'sm_sub': float(dry_row['open_meteo_soil_moisture_28_100cm_mean_m3_m3']),
        # Dry upper layer more resistive due to desiccation
        'rho_upper': 250.0,
        'rho_wet_zone': 70.0,
        'rho_substrate': 25.0
    }
}

results = {}

for sc_name, sc_info in scenarios.items():
    sc_dir = root / sc_name
    sc_dir.mkdir(parents=True, exist_ok=True)
    work_dir = sc_dir / 'work'
    
    p = Project(dirname=str(work_dir), typ='R2')
    elec = np.column_stack([np.arange(24) * 2.0, np.zeros(24), np.zeros(24)])
    p.setElec(elec)
    p.createSequence(params=[('wenner', 1, 6)])
    p.createMesh(typ='trian', cl=1.0, fmd=12)
    
    c = p.mesh.elmCentre
    # Synthetic assignment: upper layer (0 to -3m) vs substrate (<-3m)
    rho = np.where(c[:, 2] > -3.0, sc_info['rho_upper'], sc_info['rho_substrate'])
    # Central feature (x between 18 and 30m)
    rho[(c[:, 2] > -3.0) & (c[:, 0] > 18.0) & (c[:, 0] < 30.0)] = sc_info['rho_wet_zone']
    p.mesh.df['res0'] = rho
    p.mesh.df['phase0'] = 0.0
    
    truth_c = c.copy()
    truth_rho = rho.copy()
    
    # Forward simulation with 2% Gaussian noise
    p.forward(noise=2.0, iplot=False)
    p.surveys[0].df.to_csv(sc_dir / 'synthetic_measurements.csv', index=False)
    p.elec.to_csv(sc_dir / 'electrodes.csv', index=False)
    
    # Inversion: starting model reset to 100 Ohm.m
    p.mesh.df['res0'] = np.full(len(rho), 100.0)
    p.invert(param={'max_iter': 6, 'a_wgt': 0.001, 'b_wgt': 0.03})
    
    # Load actual solver VTK
    vtk_path = work_dir / 'invdir' / 'f001_res.vtk'
    if not vtk_path.exists():
        vtk_path = work_dir / 'f001_res.vtk'
    
    m = mt.vtk_import(str(vtk_path))
    key = next(k for k in ['Resistivity(ohm.m)', 'Magnitude(ohm.m)'] if k in m.df)
    res = m.df[key].to_numpy()
    centres = m.elmCentre
    
    np.savetxt(sc_dir / 'inverted_cells.csv',
               np.column_stack([centres[:, 0], centres[:, 2], res]),
               delimiter=',',
               header='x_m,z_m,model_resistivity_ohm_m',
               comments='')
    
    # Parse final RMS from R2.out
    out_file = work_dir / 'R2.out'
    if not out_file.exists():
        out_file = work_dir / 'invdir' / 'R2.out'
    r2_text = out_file.read_text(errors='replace')
    rms_matches = re.findall(r'Final RMS Misfit:\s*([\d.]+)', r2_text)
    final_rms = float(rms_matches[-1]) if rms_matches else None
    
    results[sc_name] = {
        'scenario': sc_name,
        'reference_peatfr_date': sc_info['date'],
        'open_meteo_rain_mm': sc_info['rain_mm'],
        'open_meteo_sm_top_m3_m3': sc_info['sm_top'],
        'open_meteo_sm_sub_m3_m3': sc_info['sm_sub'],
        'assumed_rho_upper': sc_info['rho_upper'],
        'assumed_rho_wet_zone': sc_info['rho_wet_zone'],
        'assumed_rho_substrate': sc_info['rho_substrate'],
        'final_RMS_misfit': final_rms,
        'model_cells': len(res),
        'model_min_ohm_m': float(np.min(res)),
        'model_max_ohm_m': float(np.max(res)),
        'truth_c': truth_c,
        'truth_rho': truth_rho,
        'centres': centres,
        'res': res,
        'elec': elec
    }

# 2. Generate Combined Multi-Panel Figure
# 4 panels:
# Top Left: Skenario Basah (Model Asumsi)
# Top Right: Skenario Basah (Inversi ResIPy R2)
# Bottom Left: Skenario Kering (Model Asumsi)
# Bottom Right: Skenario Kering (Inversi ResIPy R2)
fig, axs = plt.subplots(2, 2, figsize=(15, 9), constrained_layout=True)

norm = LogNorm(10.0, 350.0)

# Wet Model True
t_w_t = tri.Triangulation(results['wet']['truth_c'][:, 0], results['wet']['truth_c'][:, 2])
im1 = axs[0, 0].tripcolor(t_w_t, np.clip(results['wet']['truth_rho'], 10, 350), shading='gouraud', norm=norm, cmap='viridis')
axs[0, 0].set_title(f"A1. Model Sintetis Basah (Ref PeatFR: {results['wet']['reference_peatfr_date']}, Hujan={results['wet']['open_meteo_rain_mm']} mm)", fontsize=10)
axs[0, 0].scatter(results['wet']['elec'][:, 0], results['wet']['elec'][:, 2], s=6, c='black')
axs[0, 0].axhline(-3, ls='--', c='white', lw=0.8)
axs[0, 0].set(xlim=(0, 46), ylim=(-10, 0.6), ylabel='Elevasi relatif (m)')

# Wet Inversion
t_w_i = tri.Triangulation(results['wet']['centres'][:, 0], results['wet']['centres'][:, 2])
axs[0, 1].tripcolor(t_w_i, np.clip(results['wet']['res'], 10, 350), shading='gouraud', norm=norm, cmap='viridis')
axs[0, 1].set_title(f"A2. Inversi R2 Basah (RMS Misfit={results['wet']['final_RMS_misfit']})", fontsize=10)
axs[0, 1].scatter(results['wet']['elec'][:, 0], results['wet']['elec'][:, 2], s=6, c='black')
axs[0, 1].axhline(-3, ls='--', c='white', lw=0.8)
axs[0, 1].set(xlim=(0, 46), ylim=(-10, 0.6))

# Dry Model True
t_d_t = tri.Triangulation(results['dry']['truth_c'][:, 0], results['dry']['truth_c'][:, 2])
axs[1, 0].tripcolor(t_d_t, np.clip(results['dry']['truth_rho'], 10, 350), shading='gouraud', norm=norm, cmap='viridis')
axs[1, 0].set_title(f"B1. Model Sintetis Kering (Ref PeatFR: {results['dry']['reference_peatfr_date']}, Hujan={results['dry']['open_meteo_rain_mm']} mm)", fontsize=10)
axs[1, 0].scatter(results['dry']['elec'][:, 0], results['dry']['elec'][:, 2], s=6, c='black')
axs[1, 0].axhline(-3, ls='--', c='white', lw=0.8)
axs[1, 0].set(xlim=(0, 46), ylim=(-10, 0.6), xlabel='Jarak elektroda (m)', ylabel='Elevasi relatif (m)')

# Dry Inversion
t_d_i = tri.Triangulation(results['dry']['centres'][:, 0], results['dry']['centres'][:, 2])
im4 = axs[1, 1].tripcolor(t_d_i, np.clip(results['dry']['res'], 10, 350), shading='gouraud', norm=norm, cmap='viridis')
axs[1, 1].set_title(f"B2. Inversi R2 Kering (RMS Misfit={results['dry']['final_RMS_misfit']})", fontsize=10)
axs[1, 1].scatter(results['dry']['elec'][:, 0], results['dry']['elec'][:, 2], s=6, c='black')
axs[1, 1].axhline(-3, ls='--', c='white', lw=0.8)
axs[1, 1].set(xlim=(0, 46), ylim=(-10, 0.6), xlabel='Jarak elektroda (m)')

cbar = fig.colorbar(im4, ax=axs, orientation='horizontal', fraction=0.045, pad=0.08)
cbar.set_label('Resistivitas Model (Ohm.m) [Skala Logaritmik: 10 - 350]')

fig.suptitle('SIMULASI GABUNGAN PEATFR & RESIPY 2D: SKENARIO KONTRASTIF BASAH VS KERING\n(Demonstrasi Sintetis Pembelajaran - Bukan Pengukuran Lapangan BRGM/BMKG Terkalibrasi)', fontsize=12, weight='bold')

plot_png = root / 'peatfr_resipy_dual_scenario.png'
fig.savefig(plot_png, dpi=160)
plt.close(fig)

# Clean serialization without numpy arrays
clean_summary = {
    'demonstration_name': 'Integrasi PeatFR (Sabangau 2023) & ResIPy 2D Forward-Inverse',
    'status': 'synthetic demonstration completed',
    'source_resipy': str(__import__('resipy').__file__),
    'scientific_caveat': 'Parameter listrik merupakan nilai asumsi ilustratif untuk mendemonstrasikan kontras basah-kering. Ini bukan kalibrasi muka air tanah (WT) atau litologi gambut bersertifikasi lapangan.',
    'scenarios': {
        'wet': {k: v for k, v in results['wet'].items() if not isinstance(v, (np.ndarray, list))},
        'dry': {k: v for k, v in results['dry'].items() if not isinstance(v, (np.ndarray, list))}
    }
}

(root / 'summary_dual_scenario.json').write_text(json.dumps(clean_summary, indent=2))

# Checksum file manifest
manifest = {}
for p_f in root.rglob('*'):
    if p_f.is_file():
        manifest[str(p_f.relative_to(root))] = hashlib.sha256(p_f.read_bytes()).hexdigest()

(root / 'sha256.json').write_text(json.dumps(manifest, indent=2))
print("EXECUTION_COMPLETED_SUCCESSFULLY")
