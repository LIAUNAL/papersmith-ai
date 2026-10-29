### `nextStep: "convert"` — port the implementation to PyTorch

`backend` reports which files still compute with numpy. **[GATE]** ask, then convert
the modules under `src/<Package>/` **and their tests together**. `mixed` is the state
to avoid, not a milestone: modules that train while the tests still assert over numpy
give a passing suite that measures something the trained model never touched.

The mathematics does not change — this is a change of backend, not of method — so
`verify --revision <latest>` must still report `fidelity` clean afterwards, and every
invariant test must still hold. Re-run the audit: a remedy established over the numpy
sweep has not been established over the converted one.

**Declare the backend once converted.** By default `backend` is inferred from
imports, and any file importing only numpy reads as `mixed`, including a test
helper that only seeds a generator. State the backend in
`src/<Package>/__init__.py` instead:

```python
__backend__ = "torch"   # or "numpy", "jax", "tensorflow"; None = infer from imports
```

Then the stated value decides (`backend.source: "declared"`, `backend.declared`):
`tensor` (trainable) when some file under `src/<Package>/` imports it,
`declared-unmet` when none does, `numpy` for `"numpy"`, and
`unrecognized-backend` (with `declarationError`) for any other value, which
fails closed and is never trainable. `numpyFiles`/`tensorFiles` are still
reported. The kit's `tests/conftest.py` and `tests/sweep.py` import no array
library (they seed a `random.Random` and expose `SEED`/`configuration_seed`),
so they never decide the backend; a target scaffolded before 0.14.0 keeps its
numpy-importing copies, which is exactly the case the declaration settles.

**Torch in the target venv.** PyPI's plain `torch` is the CUDA build on Linux.
`env --torch cpu` appends `--extra-index-url https://download.pytorch.org/whl/cpu
torch==<X>+cpu` to `nextCommand`, with `<X>` from `--torch-version` or the one
exact `torch==X` pin in the target's manifests (no exact release refuses
`TORCH_VERSION_REQUIRED`); `env --torch gpu` appends `torch` (or `torch==<X>`)
from the default index. Without `--torch`, `env` installs no torch.
