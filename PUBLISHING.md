# Publishing arequest to PyPI

This guide explains how to build and publish the arequest package to PyPI.

## Prerequisites

1. **Install Build Tools**

```bash
pip install --upgrade build twine
```

2. **Create PyPI Account**

- Register at https://pypi.org/account/register/
- Register at https://test.pypi.org/account/register/ (for testing)

3. **Setup API Tokens**

- Go to https://pypi.org/manage/account/token/
- Create a new API token
- Save it securely (you'll need it for uploading)

## Build the Package

1. **Clean Previous Builds**

```bash
# Windows PowerShell
Remove-Item -Recurse -Force dist, build, *.egg-info -ErrorAction SilentlyContinue

# Linux/macOS
rm -rf dist/ build/ *.egg-info
```

2. **Build Distribution Files**

```bash
python -m build
```

This creates two files in `dist/`:
- `arequest-0.2.0.tar.gz` (source distribution)
- `arequest-0.2.0-py3-none-any.whl` (wheel distribution)

3. **Verify the Build**

```bash
# Check package contents
tar -tzf dist/arequest-0.2.0.tar.gz

# Install locally to test
pip install dist/arequest-0.2.0-py3-none-any.whl
```

## Test on TestPyPI First (Recommended)

1. **Upload to TestPyPI**

```bash
python -m twine upload --repository testpypi dist/*
```

Enter your TestPyPI username and API token when prompted.

2. **Test Installation from TestPyPI**

```bash
pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ arequest
```

3. **Test the Installed Package**

```bash
python -c "import arequest; print(arequest.__version__)"
python example_basic.py
```

## Publish to PyPI (Production)

1. **Upload to PyPI**

```bash
python -m twine upload dist/*
```

Enter your PyPI username and API token when prompted.

2. **Verify Installation**

```bash
pip install arequest
```

3. **Test the Package**

```bash
python -c "import arequest; print(arequest.__version__)"
```

## Using API Tokens (Recommended)

Create a `.pypirc` file in your home directory:

**Windows:** `C:\Users\YourUsername\.pypirc`
**Linux/macOS:** `~/.pypirc`

```ini
[distutils]
index-servers =
    pypi
    testpypi

[pypi]
username = __token__
password = pypi-YourActualAPITokenHere

[testpypi]
username = __token__
password = pypi-YourTestAPITokenHere
```

Then you can upload without entering credentials:

```bash
# Test upload
python -m twine upload --repository testpypi dist/*

# Production upload
python -m twine upload dist/*
```

## Complete Release Workflow

```bash
# 1. Update version in pyproject.toml
# Edit: version = "0.2.0" to "0.3.0"

# 2. Update CHANGELOG (if you have one)

# 3. Commit version bump
git add pyproject.toml
git commit -m "Bump version to 0.3.0"
git tag v0.3.0
git push origin main --tags

# 4. Clean old builds
Remove-Item -Recurse -Force dist, build, *.egg-info -ErrorAction SilentlyContinue

# 5. Build new distribution
python -m build

# 6. Upload to TestPyPI
python -m twine upload --repository testpypi dist/*

# 7. Test installation
pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ arequest==0.3.0

# 8. Upload to PyPI
python -m twine upload dist/*

# 9. Verify on PyPI
# Visit: https://pypi.org/project/arequest/

# 10. Test final installation
pip install --upgrade arequest
```

## Automated Publishing with GitHub Actions (Optional)

Create `.github/workflows/publish.yml`:

```yaml
name: Publish to PyPI

on:
  release:
    types: [published]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.11'
    
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install build twine
    
    - name: Build package
      run: python -m build
    
    - name: Publish to PyPI
      env:
        TWINE_USERNAME: __token__
        TWINE_PASSWORD: ${{ secrets.PYPI_API_TOKEN }}
      run: twine upload dist/*
```

Add your PyPI API token as a GitHub secret named `PYPI_API_TOKEN`.

## Troubleshooting

### "File already exists" Error

This means the version already exists on PyPI. Update the version in `pyproject.toml` and rebuild.

### Authentication Failed

- Verify your API token is correct
- Make sure you're using `__token__` as username
- Check `.pypirc` file permissions (should be readable only by you)

### Import Errors After Installation

- Verify package structure is correct
- Check that `src/arequest/__init__.py` exists and imports correctly
- Test locally with `pip install -e .`

### Missing Files in Distribution

- Check `MANIFEST.in` includes all necessary files
- Verify `pyproject.toml` has correct package configuration
- Use `tar -tzf dist/arequest-*.tar.gz` to inspect contents

## Current Status

✅ Package structure ready
✅ `pyproject.toml` configured
✅ `MANIFEST.in` created
✅ Documentation complete
✅ Examples included
✅ Ready for PyPI upload

## Quick Commands Reference

```bash
# Build package
python -m build

# Upload to TestPyPI
python -m twine upload --repository testpypi dist/*

# Upload to PyPI
python -m twine upload dist/*

# Install from TestPyPI
pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ arequest

# Install from PyPI
pip install arequest

# Install with extras
pip install arequest[fast]
pip install arequest[all]
```

## After Publishing

1. **Announce the Release**
   - Update GitHub release notes
   - Share on social media
   - Update documentation site

2. **Monitor Issues**
   - Watch for bug reports
   - Respond to questions
   - Plan next release

3. **Keep Package Updated**
   - Regular maintenance releases
   - Security updates
   - Performance improvements

---

**Ready to publish? Good luck! 🚀**

Your package will be available at:
- PyPI: https://pypi.org/project/arequest/
- GitHub: https://github.com/abhrajyoti-01/arequest
