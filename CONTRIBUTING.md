# Contributing to psd2svg

Thank you for your interest in contributing to psd2svg! This guide explains how to report issues, suggest features, and submit code contributions.

## Code of Conduct

This project adheres to the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code.

## How to Contribute

### Reporting Bugs

Before creating a bug report, check the [existing issues](https://github.com/CyberAgent/psd2svg/issues) and review the [Known Limitations](https://psd2svg.readthedocs.io/en/latest/limitations.html).

Use the [Bug Report template](.github/ISSUE_TEMPLATE/bug_report.yml) which will guide you through providing:

- psd2svg and Python versions
- Operating system
- Reproduction steps
- Expected vs. actual behavior
- Sample PSD file (if possible)

### Suggesting Features

Use the [Feature Request template](.github/ISSUE_TEMPLATE/feature_request.yml) to suggest new features or enhancements.

Please describe:

- The use case and why it's valuable
- Your proposed solution
- Alternative approaches you've considered

### Security Vulnerabilities

**Do not open public issues for security vulnerabilities.** Follow the process in [SECURITY.md](SECURITY.md) to report security issues privately.

## Development Setup

Quick setup:

```bash
# Clone and install dependencies
git clone https://github.com/CyberAgent/psd2svg.git
cd psd2svg
uv sync

# Optional: Install browser support for testing
uv sync --extra browser
uv run playwright install chromium
```

For detailed setup instructions, architecture overview, and debugging tips, see the [Development Guide](https://psd2svg.readthedocs.io/en/latest/development.html).

## Pull Request Workflow

**IMPORTANT**: This project uses a pull request workflow. Never commit directly to the main branch.

### Steps to Contribute

1. **Create a feature branch**:

   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes** following the code quality standards below

3. **Run the pre-commit checklist** (see below) - all checks must pass

4. **Commit and push**:

   ```bash
   git add .
   git commit -m "Description of changes"
   git push -u origin feature/your-feature-name
   ```

5. **Create a pull request** on GitHub targeting `main`

6. **Wait for CI checks to pass** - all checks must pass before merging

### Pre-Commit Checklist

Before pushing changes, **always run**:

```bash
uv run ruff format src/ tests/   # Format code
uv run ruff check src/ tests/    # Lint code
uv run mypy src/ tests/          # Type check
uv run pytest                    # Run tests
```

All checks must pass before your PR can be merged.

## Code Quality Standards

- **Type hints**: Full type annotation coverage required
- **Modern Python**: Target Python 3.10+ features (e.g., `list[str]` not `List[str]`)
- **Linting**: Use Ruff for linting and formatting
- **Style**: Follow existing code patterns, prefer module-level imports
- **Testing**: Add tests for new features, ensure all tests pass
- **Simplicity**: Keep changes focused, avoid over-engineering, delete unused code completely

For detailed standards, architecture information, and development practices, see:

- [Development Guide](https://psd2svg.readthedocs.io/en/latest/development.html) - Comprehensive development documentation
- [CLAUDE.md](CLAUDE.md) - Quick reference and AI-assisted development guidance

## What to Include in Your PR

- **Tests**: Add tests for new features or bug fixes
- **Documentation**: Update docs if changing public API or adding features
- **Type hints**: Ensure all new code has proper type annotations
- **No warnings**: Code should not generate new warnings

## Getting Help

- **Documentation**: [psd2svg.readthedocs.io](https://psd2svg.readthedocs.io/)
- **Issues**: [GitHub Issues](https://github.com/CyberAgent/psd2svg/issues)
- **Questions**: Open an issue with the "question" label

## License

By contributing to psd2svg, you agree that your contributions will be licensed under the [MIT License](LICENSE).
