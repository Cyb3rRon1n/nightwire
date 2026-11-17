"""Run a phototest script with a gentler GPU: cool at 74C -> 62C and rest 45 s after every job."""
import asyncio, runpy, sys
sys.path.insert(0, ".")
import narrator.comfyui_backend as cb
assert hasattr(cb, "GPU_COOL_C"), cb.__file__
cb.GPU_HOT_C, cb.GPU_COOL_C = 74, 62
_run = cb.ComfyUIBackend.run_workflow
async def run(self, *a, **k):
    out = await _run(self, *a, **k)
    await asyncio.sleep(45)
    return out
cb.ComfyUIBackend.run_workflow = run
script = sys.argv.pop(1)
sys.argv[0] = script
runpy.run_path(script, run_name="__main__")
