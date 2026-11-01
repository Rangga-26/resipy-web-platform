"""Illustrative synthetic peat ERT; not field data or calibrated peat properties."""
import os, sys, json, re, hashlib
from pathlib import Path
os.environ['MPLBACKEND']='Agg'
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.tri as tri
from matplotlib.colors import LogNorm
from resipy import Project
root=Path(sys.argv[1]).resolve(); root.mkdir(parents=True,exist_ok=True)
np.random.seed(42)
p=Project(dirname=str(root/'work'),typ='R2')
elec=np.column_stack([np.arange(24)*2.,np.zeros(24),np.zeros(24)])
p.setElec(elec)
p.createSequence(params=[('wenner',1,6)])
p.createMesh(typ='trian',cl=1.0,fmd=12)
c=p.mesh.elmCentre
# Illustrative electrical layers, not a unique geological mapping.
rho=np.where(c[:,2]>-3,150.,25.)
rho[(c[:,2]>-3)&(c[:,0]>18)&(c[:,0]<30)]=40.
p.mesh.df['res0']=rho
p.mesh.df['phase0']=0.
truth_c=c.copy(); truth_rho=rho.copy()
p.forward(noise=2.,iplot=False)
p.surveys[0].df.to_csv(root/'synthetic_measurements.csv',index=False)
p.elec.to_csv(root/'electrodes.csv',index=False)
# Reset prior so inverse does not start from the true model.
p.mesh.df['res0']=np.full(len(rho),70.)
p.invert(param={'max_iter':6,'a_wgt':0.001,'b_wgt':0.03})
assert p.meshResults, 'No inversion mesh returned'
from resipy import meshTools as mt
m=mt.vtk_import(str(Path(p.dirname)/'f001_res.vtk'))
# Read solver VTK explicitly: forward workflows may retain a true-model cache.
print('RESULT_COLUMNS',m.df.columns.tolist(),flush=True)
key=next(k for k in ['Resistivity(ohm.m)','Magnitude(ohm.m)'] if k in m.df)
res=m.df[key].to_numpy(); centres=m.elmCentre
np.savetxt(root/'inverted_cells.csv',np.column_stack([centres[:,0],centres[:,2],res]),delimiter=',',header='x_m,z_m,model_resistivity_ohm_m',comments='')
# Plot centroid interpolation: display only, not additional inversion.
fig,axs=plt.subplots(2,1,figsize=(11,7),constrained_layout=True)
for ax,cc,rr,title in [(axs[0],truth_c,truth_rho,'A. Model listrik sintetis: lapisan atas 150, zona basah ilustratif 40, substrat 25 Ohm.m'),(axs[1],centres,res,'B. Hasil inversi ResIPy R2 (bukan data lapangan)')]:
 t=tri.Triangulation(cc[:,0],cc[:,2]); vals=np.clip(rr,10,300)
 im=ax.tripcolor(t,vals,shading='gouraud',norm=LogNorm(10,300),cmap='viridis')
 ax.set(xlim=(0,46),ylim=(-10,0.6),xlabel='Jarak (m)',ylabel='Elevasi relatif (m)',title=title)
 ax.scatter(elec[:,0],elec[:,2],s=9,c='black'); ax.axhline(-3,ls='--',c='white',lw=.8)
 fig.colorbar(im,ax=ax,label='Resistivitas model (Ohm.m)')
fig.suptitle('CONTOH SINTETIS ERT LAHAN GAMBUT — bukan validasi litologi/muka air',fontsize=12)
fig.savefig(root/'peat_resipy_section.png',dpi=160); plt.close(fig)
text=(Path(p.dirname)/'R2.out').read_text(errors='replace')
rms=re.findall(r'Final RMS Misfit:\s*([\d.]+)',text)
summary={'dataset_type':'synthetic illustrative peat electrical model, not field observations','source':__import__('resipy').__file__,'electrodes':24,'spacing_m':2,'line_length_m':46,'array':'Wenner','data_count':len(p.surveys[0].df),'forward_noise_percent':2,'seed':42,'assumed_layers_ohm_m':{'upper_0_to_3m':150,'wet_patch_x18_to30m':40,'substrate':25},'final_RMS_misfit':float(rms[-1]) if rms else None,'model_cells':len(res),'model_min_ohm_m':float(np.min(res)),'model_max_ohm_m':float(np.max(res)),'warning':'Electrical contrasts are assumed, not calibrated peat lithology or water-table thresholds. Same mesh forward/inverse makes recovery optimistic.'}
(root/'summary.json').write_text(json.dumps(summary,indent=2))
(root/'R2.out').write_text(text)
files={str(f.relative_to(root)):hashlib.sha256(f.read_bytes()).hexdigest() for f in root.iterdir() if f.is_file()}
(root/'sha256.json').write_text(json.dumps(files,indent=2))
print(json.dumps(summary,indent=2),flush=True)
