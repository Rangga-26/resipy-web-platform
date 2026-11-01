"""Bounded review requests to four actual Hermes installations/profiles."""
import concurrent.futures
import datetime
import json
import os
from pathlib import Path
import subprocess
import base64
import shlex

OUT = Path('/home/localai/projects/resipy-web-platform/reviews/resipy-handshake')
OUT.mkdir(parents=True, exist_ok=True)
TASK = 'RESIPY-REVIEW-01'
COMMON = ('Phiseis meminta handshake atas perintah Rangga. Task RESIPY-REVIEW-01. '
          'Balas ACK dengan identitas dan host Anda, lalu 3 rekomendasi dan risiko berbasis inspeksi read-only. '
          'Jangan edit kode, konfigurasi, memori, jadwal, atau mengirim Discord. Bahasa Indonesia. '
          'Jangan menjalankan solver berat. Bedakan fakta terverifikasi dan usulan. '
          'NAS /home/localai/resipy adalah salinan source (tanpa tiga venv) dari Cika '
          '/home/rangga/Documents/Project/git-resipy/resipy. Local smoke R2 menghasilkan VTK 410749 byte. '
          'NAS root 88%, API bridge /home/localai/projects/resipy-web-platform/pipeline_2d/router.py. ')

def command(name):
    if name in ('Nissa', 'Healtrack'):
        env = os.environ.copy()
        env['HERMES_HOME'] = '/home/localai/.hermes/profiles/' + ('nisa' if name == 'Nissa' else 'healtrack')
        role = 'Audit storage, antrean, failover.' if name == 'Nissa' else 'Audit provenance data, QC, dan monitoring ilmiah; jangan akses data kesehatan.'
        return ['/home/localai/.local/bin/hermes','chat','--oneshot','-Q','--max-turns','8','--run-budget','180','-q',COMMON+role], env
    if name == 'Cika':
        q = COMMON + 'Periksa source repo Anda dan usulkan isolasi Project(dirname), validasi format dan filter reciprocal.'
        remote = '/home/rangga/.local/bin/hermes chat --oneshot -Q --max-turns 8 --run-budget 180 -q ' + shlex.quote(q)
        return ['ssh','-o','BatchMode=yes','-o','ConnectTimeout=6','rangga@100.91.228.122',remote], None
    q = COMMON + 'Audit kesiapan handoff output VTK ke pemodelan 3D Windah; jangan klaim Surfer berjalan tanpa bukti.'
    ps = r'& "$env:LOCALAPPDATA\hermes\bin\hermes.cmd" chat --oneshot -Q --max-turns 8 --run-budget 180 -q ' + "'" + q.replace("'", "''") + "'"
    encoded = base64.b64encode(ps.encode('utf-16le')).decode()
    return ['ssh','-i','/home/localai/.ssh/id_ed25519','-o','BatchMode=yes','-o','ConnectTimeout=6','winhermes@100.96.249.7','cmd /c powershell -NoProfile -EncodedCommand '+encoded], None

def run(name):
    cmd, env = command(name)
    started = datetime.datetime.now(datetime.timezone.utc).isoformat()
    try:
        r = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=230)
        (OUT/(name+'.txt')).write_text(r.stdout+'\nSTDERR:\n'+r.stderr)
        item = {'agent': name, 'task': TASK, 'started': started, 'exit_code': r.returncode, 'response_file': str(OUT/(name+'.txt')), 'state':'response_received_unreviewed' if r.returncode == 0 else 'failed'}
    except Exception as exc:
        item = {'agent': name, 'task': TASK, 'started': started, 'state':'failed', 'error':str(exc)}
    (OUT/(name+'.json')).write_text(json.dumps(item,indent=2))
    return item

import sys
names = sys.argv[1:] or ['Nissa','Healtrack','Cika','Windah']
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
    results = list(pool.map(run, names))
(OUT/('manifest.json' if len(names) == 4 else 'retry-manifest.json')).write_text(json.dumps(results,indent=2))
print(json.dumps(results,indent=2))
