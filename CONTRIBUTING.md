# Contributing to arequest

Thank you for your interest in contributing to arequest! This document provides guidelines and instructions for contributing.

## Development Setup

1. **Fork and Clone the Repository**

```bash
git clone https://github.com/abhrajyoti-01/arequest.git
cd arequest
```

2. **Create a Virtual Environment**

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install Development Dependencies**

```bash
pip install -e .[dev,all]
```

## Development Workflow

1. **Create a Feature Branch**

```bash
git checkout -b feature/your-feature-name
```

2. **Make Your Changes**

- Write clean, readable code
- Follow existing code style
- Add type hints
- Update documentation as needed

3. **Run Tests**

```bash
pytest
```

4. **Run Linting**

```bash
ruff check src/
```

5. **Format Code**

```bash
ruff format src/
```

6. **Commit Your Changes**

```bash
git add .
git commit -m "Add feature: description of your feature"
```

7. **Push and Create Pull Request**

```bash
git push origin feature/your-feature-name
```

Then create a pull request on GitHub.

## Code Style Guidelines

- Follow PEP 8 with a line length of 100 characters
- Use type hints for all function signatures
- Write docstrings for public APIs
- Keep functions focused and concise
- Use meaningful variable names

## Testing Guidelines

- Write tests for new features
- Ensure all tests pass before submitting PR
- Aim for high code coverage
- Test edge cases and error conditions

## Documentation

- Update README.md if adding new features
- Update API documentation in docs/
- Add examples for new functionality
- Keep documentation clear and concise

## Reporting Issues

When reporting issues, please include:

- Python version
- Operating system
- Minimal code to reproduce the issue
- Expected vs actual behavior
- Error messages and stack traces

## Questions?

Feel free to open an issue for questions or discussions!

Thank you for contributing to arequest! 🚀
