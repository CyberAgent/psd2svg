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
   git commit -s -m "Description of changes"
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

## Sign Your Commits (DCO)

psd2svg uses the [Developer Certificate of Origin](https://developercertificate.org/).
Every commit must carry a `Signed-off-by` line:

```bash
git commit -s -m "Description of changes"
```

By signing off you certify that you wrote the patch, or otherwise have the right to
submit it under the MIT License. It is a one-line assertion, **not** a copyright
assignment - you keep the copyright in your contribution, and there is no CLA to
sign. The same requirement applies to maintainers and CyberAgent employees.

The sign-off must match the commit author's name and email. Forgot one?
`git commit --amend -s` fixes the last commit, and `git rebase --signoff main`
fixes a whole branch of your own commits - it signs off as the current
committer, so do not use it on commits authored by someone else.

## AI-Assisted Contributions

AI assistance is welcome - this project is developed with it (see [CLAUDE.md](CLAUDE.md)).
Two conditions:

- **Disclose it.** Say in the PR description which parts were AI-generated.
- **Stand behind it.** You must understand every line you submit and be able to
  explain why it is correct. Run the [Pre-Commit Checklist](#pre-commit-checklist)
  locally. "The model produced it" and "CI was green" are not review.

If you cannot explain your own diff, we will ask - and a PR that stays
unexplained will be closed, whether or not it works.

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

## Test Fixtures

Tests run against PSD files in `tests/fixtures/`. All 309 fixtures in the
repository today were authored in Adobe Photoshop, which leaves no coverage of
files written by other applications - and third-party writers are where
interesting parser edge cases live. **Fixtures from Clip Studio Paint, Affinity
Photo, Krita, GIMP, Photopea and similar tools are welcome.** A maintainer
cannot author those on your behalf, because the third-party writer's output *is*
the thing under test.

There is no mechanical way to verify that a PSD contains only what it claims to
contain - see [SECURITY.md](SECURITY.md#why-fixtures-are-not-mechanically-verified)
for what we tried. So what we ask for is the context that makes human review
possible:

- **Keep it minimal and original.** The smallest document that reproduces the
  issue, created by you for this purpose rather than cut from existing artwork.
  That keeps the file reviewable and keeps third-party artwork licensing out of
  the repository. If recreating the document loses the bug, a minimized copy of
  a file you own is fine - say so in the PR.
- **Name the authoring tool and version** in the PR description, e.g.
  `Clip Studio Paint 3.0.6 (Windows)`.
- **Keep it under 1 MB**, or say why it needs to be larger. Current fixtures run
  to a median of 40 KB, p90 of 104 KB, and a largest of 942 KB.
- **No linked smart objects** or other references to files outside the PSD,
  unless that reference is itself what the fixture tests - say so if it is.
- **Your DCO sign-off covers the fixture**, certifying you have the right to
  contribute that file under the MIT License. For binary artwork this matters
  more than it does for code.

A reviewer's first question is then: **is the bulk of this file explained by
what it is for?** 900 KB in a pattern-overlay fixture is explained by the pattern
data; 900 KB in a fixture for a one-line stroke bug is not. That question catches
an implausible file, not a small payload hidden in a plausible one - which is why
these rules lean on minimality and provenance rather than on inspection.

## How We Review

Review attention scales with what a change can affect - not with who wrote it, and
not with how large the diff is. These areas get slower, more detailed review from
everyone, maintainers included:

- `.github/workflows/**`, `pyproject.toml`, `uv.lock` - build, CI, and dependency surfaces
- Code that reads or writes files, spawns a process, or loads fonts from disk
- Binary files of any kind

A one-line change in one of those areas may take longer to merge than a
hundred-line change to a converter. That isn't distrust - it's the same standard
applied to every PR.

## Getting Help

- **Documentation**: [psd2svg.readthedocs.io](https://psd2svg.readthedocs.io/)
- **Issues**: [GitHub Issues](https://github.com/CyberAgent/psd2svg/issues)
- **Questions**: Open an issue with the "question" label

## License

By contributing to psd2svg, you agree that your contributions will be licensed
under the [MIT License](LICENSE). You keep the copyright in your contribution;
your DCO sign-off asserts that you have the right to submit it under that
license.
