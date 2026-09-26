# Running the scripts with `python -m`

Every `scripts/*.py` is a stdlib-only tool. `pyproject.toml` installs each one as a top-level module, so after installation it runs from any directory, like `python -m zipfile`, with no clone or file path:

```sh
# one-off: nothing cloned, uv caches the build
uv run --no-project --with "git+https://github.com/myon-bioinformatics/browser-test-kit" python -m check_png shot.png

# or install once, then use it anywhere (also from Python one-liners)
python -m pip install "git+https://github.com/myon-bioinformatics/browser-test-kit"
python -m check_png shot.png
python -c "import check_png; print(check_png.dimensions(open('shot.png', 'rb').read()))"

# inside a clone, without installing
PYTHONPATH=scripts python -S -m check_png shot.png
```

Module names are the file names (`check_png`, and each script added later), so install into an environment without other modules of the same names, such as a uv run or a virtualenv. `tests/python/test_python_m.py` runs `python -S -m NAME --help` for every script, and CI installs the repository and runs one module from outside the checkout.
