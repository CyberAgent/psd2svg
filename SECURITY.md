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
