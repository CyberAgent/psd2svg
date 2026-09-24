# Security Policy

## Supported Versions

We release patches for security vulnerabilities in the following versions:

| Version | Supported          |
| ------- | ------------------ |
| Latest  | :white_check_mark: |
| < Latest| :x:                |

We recommend always using the latest version of psd2svg to ensure you have the latest security updates.

## Reporting a Vulnerability

We take the security of psd2svg seriously. If you discover a security vulnerability, please follow these steps:

### 1. Do Not Create a Public Issue

Please **do not** create a public GitHub issue for security vulnerabilities. Public disclosure before a fix is available can put users at risk.

### 2. Report Privately

Report security vulnerabilities by opening a [GitHub Security Advisory](https://github.com/CyberAgent/psd2svg/security/advisories/new).

Alternatively, you can email the maintainer directly. Check the repository for contact information.

### 3. Provide Details

When reporting a vulnerability, please include:

- **Description**: A clear description of the vulnerability
- **Impact**: What an attacker could do if they exploit this vulnerability
- **Steps to Reproduce**: Detailed steps to reproduce the vulnerability
- **Proof of Concept**: Code or files demonstrating the vulnerability (if applicable)
- **Suggested Fix**: If you have ideas for how to fix the issue (optional)
- **Your Information**: How we can contact you for follow-up questions

### 4. Response Timeline

- **Initial Response**: We aim to acknowledge your report within 48 hours
- **Status Updates**: We will provide status updates at least every 7 days
- **Fix Timeline**: We aim to release a fix within 30 days for critical vulnerabilities
- **Disclosure**: We will coordinate with you on the disclosure timeline

## Security Features and Best Practices

psd2svg includes built-in security features to protect against common vulnerabilities when processing untrusted PSD files:

- **Resource Limits**: Automatic DoS prevention with configurable limits (file size, timeout, layer depth, image dimensions)
- **Path Traversal Protection**: Built-in validation for `image_prefix` parameter
- **Font File Validation**: Automatic validation of font file extensions and paths

For comprehensive security documentation including:

- Detailed configuration examples
- Best practices for processing untrusted files
- Sandboxing and container isolation
- Production deployment checklist

**See the [Security Considerations](https://psd2svg.readthedocs.io/en/latest/security.html) documentation.**

## Supply Chain and Contribution Security

psd2svg is open to anyone: first-time contributors are welcome, and nothing here
restricts who may open a pull request. Trust in a *change*, however, is never
inherited from trust in a *contributor*. The attack this guards against is a
contributor who builds a real track record over months and then submits one
change that trades on it.

### Contribution trust model

- **Merged-PR count confers nothing.** Contribution history is precisely what an
  attacker farms, so it is never the reason to extend trust or access.
- **Repository access is managed through teams.** `psd2svg`,
  `psd2svg-maintainer` and `psd2svg-admin` carry write, maintain and admin
  permission. External contributors work from forks. CyberAgent organization
  owners hold inherited admin, as they do on every repository in the
  organization.
- **Review effort scales with blast radius, not with diff size or author.** CI
  configuration, dependency manifests, release tooling, filesystem and
  subprocess code, and binary files get detailed review regardless of who sent
  them.

### Repository controls

- **`main` requires a pull request** with the full test matrix green. The
  ruleset has no bypass actors, so it applies to maintainers too. Required
  approvals are zero: the pull request and the checks are enforced, the review
  is convention.
- **Fork pull requests require maintainer approval before CI runs** - for all
  outside contributors, not only first-time ones, since "has merged before" is
  the status an attacker farms.
- **Releases publish to PyPI via Trusted Publishing** (OIDC), so no long-lived
  token exists in repository secrets. The `release` environment requires
  reviewer approval and accepts deployments only from `v*` tags, and creating,
  moving or deleting a `v*` tag is restricted to the maintainer and admin teams.
- **Workflow tokens are read-only by default**, and GitHub Actions cannot
  approve pull requests. Workflows that need to write declare it in their own
  `permissions:` block.
- **Commits must carry a DCO sign-off** - see
  [CONTRIBUTING.md](CONTRIBUTING.md#sign-your-commits-dco).
- **Binary test fixtures** are accepted from any authoring tool, bounded by a
  size cap and reviewed by a person rather than by an automated integrity check.
  See [CONTRIBUTING.md](CONTRIBUTING.md#test-fixtures).

### What these controls do not do

They narrow what a single account can reach and how far a bad change spreads.
They do not catch a malicious change that passes an ordinary review, and this
repository has no independent reviewer: required approvals are zero, so whoever
can merge may merge their own work. Approving a fork's CI run grants execution,
not validation. Administrators can bypass the release environment, the release
approver may be the person who pushed the tag, and nothing checks that a tagged
commit reached `main` through a pull request.

DCO sign-off and contribution history are provenance records, not guarantees. A
determined attacker will sign off truthfully and contribute genuinely useful
code for as long as it takes.

## Automated Security Scanning

This project uses automated security scanning:

- **Dependabot**: Automatic dependency updates and vulnerability alerts
- **pip-audit**: Python-specific vulnerability scanning
- **Safety**: Dependency security checker
- **Trivy**: Comprehensive security scanner

Security scan results are available in the [Security tab](https://github.com/CyberAgent/psd2svg/security).

## Acknowledgments

We appreciate security researchers who responsibly disclose vulnerabilities. Contributors who report valid security issues may be acknowledged in release notes (with their permission).

## Questions?

If you have questions about this security policy, please open an issue in the [Issues tab](https://github.com/CyberAgent/psd2svg/issues) with the "question" label.
