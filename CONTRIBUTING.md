# Contributing to Neuro-Pipeline

Thank you for your interest in contributing to Neuro-Pipeline! This document provides guidelines and workflows for contributing.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Development Setup](#development-setup)
- [Branch Strategy](#branch-strategy)
- [Commit Guidelines](#commit-guidelines)
- [Pull Request Process](#pull-request-process)
- [Testing Requirements](#testing-requirements)
- [Code Style](#code-style)

## Code of Conduct

- Be respectful and inclusive
- Focus on constructive feedback
- Help others learn and grow

## Development Setup

### Prerequisites

- **macOS**: Xcode Command Line Tools, Homebrew
- **RK3588**: Cross-compilation Docker environment

### Quick Start

```bash
# Clone with submodules
git clone --recursive https://github.com/your-org/neuro-pipeline.git
cd neuro-pipeline

# Initialize submodules (if already cloned)
git submodule update --init --depth 1

# Python setup
cd mac-central
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt

# C++ setup (native macOS with mock HAL)
cd ../rk3588-edge
mkdir build && cd build
cmake .. -DUSE_MOCK_HAL=ON -DBUILD_TESTING=ON
make -j$(sysctl -n hw.ncpu)
```

### IDE Configuration

**clangd (Recommended for C++):**
```bash
cd rk3588-edge/build
cmake ..  # Generates compile_commands.json
ln -sf build/compile_commands.json .
```

**VSCode:**
- Install C/C++ extension, Python extension
- Use workspace at repo root

## Branch Strategy

```
main        ← Stable releases only (tagged)
  ↑
milestone/* ← Release candidates
  ↑
dev         ← Active development (default branch)
  ↑
feature/*   ← Individual features
```

### Branch Naming

- `feature/<name>` - New features
- `fix/<name>` - Bug fixes
- `refactor/<name>` - Code refactoring
- `docs/<name>` - Documentation updates
- `test/<name>` - Test improvements

## Commit Guidelines

### Commit Message Format

```
<type>(<scope>): <subject>

<body>

<footer>
```

### Types

- `feat`: New feature
- `fix`: Bug fix
- `refactor`: Code refactoring
- `docs`: Documentation
- `test`: Tests
- `chore`: Build, CI, dependencies

### Examples

```
feat(edge): add multi-model hot-swap support

Implement MultiModelManager to load YOLOv5s/v5m/v8s on separate NPU cores.
Support gRPC SWITCH_MODEL_VARIANT command for runtime model switching.

Closes #123
```

```
fix(central): handle empty detection list in BehaviorAnalyzer

Return empty result instead of raising IndexError when no detections
are provided to analyze() method.
```

## Pull Request Process

### Before Submitting

1. **Update from dev:**
   ```bash
   git checkout dev
   git pull origin dev
   git checkout your-branch
   git rebase dev
   ```

2. **Run all tests:**
   ```bash
   # Python tests
   cd mac-central
   source .venv/bin/activate
   pytest tests/ -v --tb=short -o "addopts="

   # C++ tests (if applicable)
   cd rk3588-edge/build
   ctest --output-on-failure
   ```

3. **Check code style:**
   ```bash
   # Python
   ruff check mac-central/src/
   mypy mac-central/src/

   # C++ (via clang-tidy)
   clang-tidy rk3588-edge/src/**/*.cpp
   ```

### PR Checklist

- [ ] Branch is up-to-date with `dev`
- [ ] All tests pass
- [ ] New code has test coverage
- [ ] Documentation updated (if applicable)
- [ ] Commit messages follow guidelines
- [ ] PR description explains the change

### PR Template

```markdown
## Summary
Brief description of changes.

## Type of Change
- [ ] Feature
- [ ] Bug fix
- [ ] Refactor
- [ ] Documentation
- [ ] Test

## Testing
How was this tested?

## Checklist
- [ ] Tests pass
- [ ] Documentation updated
```

### Review Process

1. At least one approval required
2. CI must pass
3. Resolve all review comments
4. Squash and merge to `dev`

## Testing Requirements

### Coverage Targets

- **Python**: 80%+ coverage for new code
- **C++**: Unit tests for all public APIs

### Running Tests

```bash
# Python unit tests
cd mac-central
pytest tests/unit_tests/ -v --cov=src --cov-report=html -o "addopts="

# Python integration tests
pytest tests/integration_tests/ -v -o "addopts="

# C++ tests
cd rk3588-edge/build
cmake .. -DUSE_MOCK_HAL=ON -DBUILD_TESTING=ON
make -j$(nproc)
ctest --output-on-failure

# C++ with coverage
cmake .. -DUSE_MOCK_HAL=ON -DBUILD_TESTING=ON -DENABLE_COVERAGE=ON
make -j$(nproc)
ctest
gcovr -r .. --html-details coverage.html
```

### Writing Tests

**Python (pytest):**
```python
import pytest

class TestMyFeature:
    def test_basic_case(self):
        result = my_function("input")
        assert result == "expected"

    @pytest.mark.asyncio
    async def test_async_case(self):
        result = await my_async_function()
        assert result is not None
```

**C++ (GoogleTest):**
```cpp
#include <gtest/gtest.h>

TEST(MyFeatureTest, BasicCase) {
    auto result = MyFunction("input");
    EXPECT_EQ(result, "expected");
}
```

## Code Style

### Python

- Follow PEP 8
- Use type hints
- Use dataclasses for data structures
- Prefer `asyncio` for I/O operations

**Formatting:**
```bash
ruff format mac-central/src/
```

### C++

- Follow C++17 standard
- Use `neuro::` namespace
- Use smart pointers (no raw `new`/`delete`)
- RAII for resource management

**Naming:**
- Classes: `PascalCase`
- Functions: `snake_case()`
- Constants: `kCamelCase`
- Members: `snake_case_` (trailing underscore)

### Documentation

- Update README.md for user-facing changes
- Update CLAUDE.md for AI assistant context
- Add inline comments for complex logic
- Update VERSION_HISTORY.md for releases

---

## Questions?

- Open an issue for bugs or feature requests
- Check existing documentation in `docs/`
- Review closed PRs for examples
