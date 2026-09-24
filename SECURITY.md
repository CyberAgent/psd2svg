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

psd2svg is an open project: anyone may open an issue or a pull request, and
first-time contributors are welcome. Trust in a *change*, however, is never
inherited from trust in a *contributor*.

The realistic supply-chain attack on a project this size is not a single hostile
pull request that a reviewer catches. It is a contributor who builds a genuine
track record over months and then submits one change that trades on it. The
controls below are designed so that accrued goodwill never converts into the
ability to land an unreviewed change - and so that no contributor has to be
judged as a person for the project to stay safe.

### Contribution trust model

- **Merged-PR count confers nothing.** Contribution history is not evidence of
  trustworthiness; it is precisely what an attacker would farm. Repository
  access is granted on organizational need, never as a reward for volume.
- **Repository access is managed through teams.** The `psd2svg`,
  `psd2svg-maintainer` and `psd2svg-admin` teams carry write, maintain and admin
  permission respectively. External contributors work from forks. CyberAgent
  organization owners additionally hold inherited admin on this repository, as
  they do on every repository in the organization.
- **Every change reaches `main` through a pull request.** A repository ruleset
  makes this mandatory for everyone, maintainers included - there are no bypass
  actors - and the full test matrix must pass before merge. Reviewing every
  change, including one-line ones, is project convention; what the ruleset
  enforces is the pull request and the checks, not the review itself.
- **Review effort scales with blast radius, not diff size.** CI configuration,
  dependency manifests, release tooling, filesystem and subprocess code, and
  binary files get detailed review regardless of author.

### Repository controls

- **Fork pull requests require maintainer approval before CI runs.** This
  applies to every outside contributor, not only first-time ones - GitHub offers
  the relaxed setting and we decline it, because "has merged before" is
  precisely the status an attacker farms.
- **Binary test fixtures** (`tests/fixtures/**/*.psd`) are accepted from any
  authoring tool, and files from non-Adobe applications are wanted for coverage.
  They are bounded by a documented size cap and reviewed by a person; there is
  no automated integrity check, for the reasons in "Why fixtures are not mechanically
  verified" below. See [CONTRIBUTING.md](CONTRIBUTING.md#test-fixtures).
- **Releases publish to PyPI via Trusted Publishing** (OIDC), so no long-lived
  PyPI token exists in repository secrets. The `release` deployment environment
  requires reviewer approval and accepts deployments only from `v*` tags, and
  creating, moving or deleting a `v*` tag is restricted to the maintainer and
  admin teams. Pushing a tag is therefore not sufficient to ship a release - a
  human has to approve the deployment. With a single maintainer that approver
  may be the person who pushed the tag, so this is a deliberate-action gate
  rather than a separation of duties.
- **Commits must carry a DCO sign-off**, giving a per-commit record of who
  asserted the right to submit the code. This is a documented requirement
  checked at review today; mechanical enforcement in CI is being added
  separately.
- **Workflow tokens are read-only by default**, and GitHub Actions cannot
  approve pull requests. Workflows that need to write declare it explicitly in
  their own `permissions:` block.

### Why fixtures are not mechanically verified

We looked for an automated check that a contributed PSD contains only what it
claims to contain, and did not find one worth shipping. The negative result is
recorded here so it is not re-litigated:

- **Round-trip byte accounting** - re-serialize the parsed file and compare to
  the file size. Exact for Photoshop output, but not for other writers, because
  psd-tools normalizes padding. Measured against the psd-tools test corpus,
  which unlike ours contains non-Adobe output: its `cactus_top`,
  `transparentbg-gimp` and `broken-groups` files came back 4, 2 and 6 bytes
  short, while every Photoshop file tested round-tripped exactly. As a gate it
  would have rejected third-party fixtures and nothing else - precisely the
  contributions we want.
- **Declared-length tiling** - walk the section lengths in the raw bytes, with
  no parser involved. Writer-independent, but toothless: the image data section
  carries no declared length, so 3 KB appended to a valid PSD passes the check
  and parses identically to the original.
- **Detecting that reliably** would mean decoding the image data stream to find
  its true end: reimplementing part of the codec to defend a file that is
  parsed, never executed, and therefore has no path to running a payload.

What remains is a size cap and human review. That is a weaker guarantee than a
green check mark would imply, which is the honest position - and a reason to
keep weight on the controls above that do not depend on inspecting a binary.

### What these controls are not

DCO sign-off and contribution history are provenance records, not security
guarantees. A determined attacker will sign off truthfully and contribute
genuinely useful code for as long as it takes. The controls that carry weight are
the ones that do not depend on judging a person: team-scoped access, a mandatory
pull request, blast-radius-weighted scrutiny, a release path that a tag push
alone cannot trigger, and CI that an outside fork cannot run without approval.

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
