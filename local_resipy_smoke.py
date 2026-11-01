"""Bounded local source/solver acceptance test; uses only bundled example data."""
import json
import os
from pathlib import Path
os.environ['MPLBACKEND'] = 'Agg'
import sys
sys.path.insert(0, '/home/localai/resipy/src')
from resipy import Project
import resipy
out = Path('/home/localai/projects/resipy-web-platform/runs/local_source_smoke')
out.mkdir(parents=True, exist_ok=True)
p = Project(dirname=str(out), typ='R2')
p.createSurvey('/home/localai/resipy/src/examples/dc-2d/syscal.csv', ftype='Syscal')
p.createMesh(typ='trian')
p.invert(param={'max_iter': 2})
vtk = Path(p.dirname) / 'f001_res.vtk'
if not vtk.is_file() or vtk.stat().st_size == 0:
    raise RuntimeError('Solver did not produce nonempty VTK')
result = {'source': resipy.__file__, 'vtk': str(vtk), 'bytes': vtk.stat().st_size, 'test': 'local solver smoke, not scientific validation'}
(out / 'local_acceptance.json').write_text(json.dumps(result, indent=2))
print(json.dumps(result, indent=2))
