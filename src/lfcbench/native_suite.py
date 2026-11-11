"""CLI bridge to source-pinned native API drivers in an editable project."""
import os, subprocess, sys
from pathlib import Path

SCRIPTS={'native-build':'build_native.py','native-run':'run_nyx.py','native-plot':'plot_nyx.py',
 'native-build-typed':'build_typed.py','native-inventory':'inventory_sdrbench.py',
 'native-suite':'run_sdrbench.py','native-suite-plot':'plot_sdrbench.py','native-suite-audit':'audit_sdrbench.py',
 'native-suite-progress':'progress_sdrbench.py'}
def dispatch(command,argv):
 root=Path(os.environ.get('LFCBENCH_NATIVE_ROOT',Path(__file__).resolve().parents[2]))
 path=root/'scripts'/SCRIPTS[command]
 if not path.is_file():
  raise SystemExit('Native suite needs its source checkout; set LFCBENCH_NATIVE_ROOT to the project root.')
 return subprocess.run([sys.executable,str(path),*argv],cwd=root).returncode
