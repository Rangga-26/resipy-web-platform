"""Read-only SSH readiness probe for the user-owned Cika ResIPy checkout."""
import json
import subprocess

HOST = 'rangga@100.91.228.122'
ROOT = '/home/rangga/Documents/Project/git-resipy/resipy'
PYTHON = ROOT + '/resipy_env/bin/python'


def probe():
    import shlex
    code = ('import json, resipy; from resipy import Project; '
            'print("RESIPY_PROBE=" + json.dumps({"module": resipy.__file__, '
            '"project_class": Project.__name__}))')
    command = ('cd /tmp && PYTHONPATH=' + shlex.quote(ROOT + '/src')
               + ' MPLBACKEND=Agg ' + shlex.quote(PYTHON)
               + ' -c ' + shlex.quote(code))
    result = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o',
                             'ConnectTimeout=6', HOST, command],
                            text=True, capture_output=True, timeout=30, check=True)
    for line in result.stdout.splitlines():
        if line.startswith('RESIPY_PROBE='):
            data = json.loads(line.split('=', 1)[1])
            if data['module'] != ROOT + '/src/resipy/__init__.py':
                raise RuntimeError('Unexpected ResIPy source path')
            return data
    raise RuntimeError('Missing probe evidence')


if __name__ == '__main__':
    print(json.dumps(probe(), indent=2))
