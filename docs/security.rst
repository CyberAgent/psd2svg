====================
Security Considerations
====================

This guide covers security considerations when using psd2svg, especially when processing untrusted input files.

Overview
========

psd2svg processes PSD files which can contain:

- Complex layer structures
- Embedded images (potentially very large)
- Font references
- External resource references

When processing untrusted PSD files, you should be aware of potential security risks and implement appropriate mitigations.

Security Features
=================

Path Traversal Protection
-------------------------

The ``image_prefix`` parameter in ``save()`` and ``tostring()`` methods has built-in protections:

.. code-block:: python

    from psd2svg import SVGDocument

    document = SVGDocument.from_psd(psdimage)

    # ✓ Safe: Relative paths are allowed
    document.save("output.svg", image_prefix="images/output")

    # ✗ Blocked: Path traversal attempts are rejected
    try:
        document.save("output.svg", image_prefix="../../../etc/output")
    except ValueError as e:
        print(e)  # "image_prefix cannot contain '..' (path traversal not allowed)"

    # ✗ Blocked: Absolute paths without svg_filepath are rejected
    try:
        document.tostring(image_prefix="/tmp/output")
    except ValueError as e:
        print(e)  # "image_prefix must be relative when svg_filepath is not provided"

These protections prevent malicious or compromised code from writing files outside intended directories.

Font File Validation
--------------------

When extracting font files from SVG ``@font-face`` rules (used by ResvgRasterizer), psd2svg validates:

1. **File extensions**: Only valid font formats are accepted (``.ttf``, ``.otf``, ``.woff``, ``.woff2``, ``.ttc``)
2. **File existence**: Non-existent files are skipped with a warning

.. code-block:: python

    from psd2svg.rasterizer import ResvgRasterizer

    # Font files are automatically validated
    rasterizer = ResvgRasterizer()

    # Valid font files are used, invalid ones are skipped
    image = rasterizer.from_string(svg_content)

This prevents:

- Access to arbitrary file paths (e.g., ``/etc/passwd``)
- Log pollution from invalid paths
- Potential information disclosure

Security Best Practices
=======================

Processing Untrusted Files
--------------------------

When processing PSD files from untrusted sources, psd2svg provides built-in resource limits to prevent denial-of-service attacks.

Built-in Resource Limits
^^^^^^^^^^^^^^^^^^^^^^^^^

**New in version 0.4.0**: psd2svg includes automatic DoS prevention via the ``ResourceLimits`` class.

By default, resource limits are **automatically enabled** with sensible defaults:

.. code-block:: python

    from psd_tools import PSDImage
    from psd2svg import SVGDocument, convert

    # Option 1: Using convert() - limits applied automatically
    convert("input.psd", "output.svg")
    # Applies default limits: 2GB file size, 3 minute timeout,
    # 100 layer depth, 16K image dimension

    # Option 2: Using from_psd() - limits applied automatically
    psdimage = PSDImage.open("input.psd")
    document = SVGDocument.from_psd(psdimage)
    # Same default limits applied

**Important**: This is a breaking change from previous versions where no limits were enforced.

Customizing Resource Limits
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

For untrusted input, use stricter limits:

.. code-block:: python

    from psd2svg import ResourceLimits, convert

    # Define stricter limits for untrusted input
    limits = ResourceLimits(
        max_file_size=500 * 1024 * 1024,  # 500MB (vs 2GB default)
        timeout=60,                        # 1 minute (vs 3 minutes default)
        max_layer_depth=50,                # 50 levels (vs 100 default)
        max_image_dimension=8192           # 8K (vs 16K default)
    )

    # Use with convert()
    convert("untrusted.psd", "output.svg", resource_limits=limits)

    # Or with from_psd()
    psdimage = PSDImage.open("untrusted.psd")
    document = SVGDocument.from_psd(psdimage, resource_limits=limits)

Default Limits (Trusted Input)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The default limits are designed for professional PSD files from trusted sources:

.. code-block:: python

    from psd2svg import ResourceLimits

    # Explicitly use default limits (same as passing None)
    limits = ResourceLimits.default()
    # - max_file_size: 2GB (typical for professional PSDs)
    # - timeout: 180 seconds (3 minutes)
    # - max_layer_depth: 100 layers deep
    # - max_image_dimension: 16383 pixels (WebP hard limit)

Disabling Limits (Use with Caution)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

For fully trusted input where you need to process very large files:

.. code-block:: python

    from psd2svg import ResourceLimits, convert

    # WARNING: Only use for trusted input in controlled environments!
    limits = ResourceLimits.unlimited()

    convert("huge_trusted_file.psd", "output.svg", resource_limits=limits)

Environment Variable Configuration
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Resource limits can be configured via environment variables. See :doc:`configuration` for details on available environment variables and their usage.

Resource Limit Errors
^^^^^^^^^^^^^^^^^^^^^

When limits are exceeded, specific errors are raised:

.. code-block:: python

    from psd2svg import convert, ResourceLimits

    try:
        convert("large.psd", "output.svg")
    except ValueError as e:
        # File size limit exceeded:
        # "File size 3221225472 bytes exceeds limit 2147483648 bytes.
        #  To process: set PSD2SVG_MAX_FILE_SIZE=3326459872 environment variable,
        #  or use ResourceLimits(max_file_size=3326459872) in Python API."
        print(f"Limit exceeded: {e}")
    except TimeoutError as e:
        # Timeout exceeded:
        # "PSD conversion timed out after 180 seconds. File may be complex.
        #  To process: set PSD2SVG_TIMEOUT=360 environment variable,
        #  or use ResourceLimits(timeout=360) in Python API."
        print(f"Conversion took too long: {e}")

**Note on Timeout**: Cross-platform timeout is supported:

- **Unix/macOS**: Uses ``signal.SIGALRM`` for reliable timeout
- **Windows**: Uses threading-based timeout (may not interrupt native C code)

Sandboxing with Subprocess
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Run conversion in a separate process with resource limits:

.. code-block:: python

    import subprocess
    import json
    from pathlib import Path

    def convert_sandboxed(
        psd_path: str,
        output_path: str,
        timeout: int = 60,
        max_memory_mb: int = 512
    ) -> bool:
        """Convert PSD in sandboxed subprocess."""
        script = f"""
    from psd_tools import PSDImage
    from psd2svg import SVGDocument

    psdimage = PSDImage.open({psd_path!r})
    document = SVGDocument.from_psd(psdimage)
    document.save({output_path!r})
    """

        try:
            # Run in subprocess with timeout
            result = subprocess.run(
                ["python", "-c", script],
                timeout=timeout,
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                print(f"Conversion failed: {result.stderr}")
                return False

            return True

        except subprocess.TimeoutExpired:
            print(f"Conversion timed out after {timeout} seconds")
            return False
        except Exception as e:
            print(f"Conversion error: {e}")
            return False

Container Isolation
^^^^^^^^^^^^^^^^^^^^^^

For maximum isolation, run conversions in Docker containers:

.. code-block:: bash

    # Dockerfile
    FROM python:3.10-slim
    RUN pip install psd2svg
    WORKDIR /workspace

    # Run with resource limits
    docker run --rm \
        --memory=512m \
        --cpus=1 \
        --network=none \
        -v /path/to/input:/input:ro \
        -v /path/to/output:/output:rw \
        psd2svg-image \
        python -m psd2svg /input/file.psd /output/file.svg

Path Validation
---------------

Always validate user-provided paths:

.. code-block:: python

    import os
    from pathlib import Path

    def validate_path(path: str, base_dir: str) -> str:
        """Validate path is within base directory."""
        # Resolve to absolute path
        resolved = Path(path).resolve()
        base = Path(base_dir).resolve()

        # Check if path is within base directory
        try:
            resolved.relative_to(base)
        except ValueError:
            raise ValueError(f"Path {path} is outside base directory {base_dir}")

        return str(resolved)

    # Usage
    safe_output = validate_path(user_provided_path, "/safe/output/dir")

Font Security
-------------

When using custom fonts or font embedding:

.. code-block:: python

    from pathlib import Path

    # Define trusted font directories
    TRUSTED_FONT_DIRS = [
        "/usr/share/fonts",
        "/System/Library/Fonts",
        str(Path.home() / ".fonts"),
    ]

    def validate_font_path(font_path: str) -> bool:
        """Check if font comes from trusted directory."""
        resolved = Path(font_path).resolve()
        return any(
            str(resolved).startswith(trusted_dir)
            for trusted_dir in TRUSTED_FONT_DIRS
        )

    # Usage
    if not validate_font_path(font_file):
        raise ValueError("Untrusted font file")

Known Limitations
=================

Resource Consumption
--------------------

PSD processing can be resource-intensive:

- **Memory**: Large PSD files or many embedded images can consume significant memory
- **CPU**: Complex layer effects and deeply nested layers require substantial processing
- **Disk**: Output SVG files with embedded images can be very large

**Impact**: Can lead to denial of service if not properly limited.

**Mitigation** (New in version 0.4.0):

psd2svg now includes **built-in DoS prevention** via automatic resource limits:

- **File size limits**: 2GB default (customizable via ``ResourceLimits``)
- **Timeout protection**: 3 minutes default with cross-platform support
- **Layer depth limits**: 100 levels default to prevent stack overflow
- **Image dimension limits**: 16K pixels default (WebP hard limit)

See "Processing Untrusted Files" section above for configuration details.

For additional protection:

- Run in resource-constrained environments (containers, VMs)
- Monitor resource usage in production
- Use stricter limits for untrusted input (500MB, 60 seconds)

WebP Dimension Limits
---------------------

**Critical Limitation**: WebP format has a hard limit of **16383 pixels per dimension**.

This is a common issue with professional Photoshop files that contain:

- High-resolution print designs (e.g., 300 DPI posters)
- Large billboard or banner designs
- Detailed panoramic images
- Individual layers exceeding 16383 pixels on either width or height

**Impact**: Conversion will fail with a WebP encoding error when encountering oversized layers.

**Automatic Validation** (New in version 0.4.0):

psd2svg now **automatically validates** image dimensions before conversion:

.. code-block:: python

    from psd2svg import convert

    # Automatically rejects layers exceeding 16K dimension limit
    try:
        convert("large.psd", "output.svg")
    except ValueError as e:
        print(e)
        # "Layer 'Background' dimensions 20000x15000 exceed limit 16383x16383"

To customize the dimension limit or disable it:

.. code-block:: python

    from psd2svg import ResourceLimits, convert

    # Use a smaller limit (e.g., for untrusted input)
    limits = ResourceLimits(max_image_dimension=8192)
    convert("file.psd", "output.svg", resource_limits=limits)

    # Or disable validation (not recommended)
    limits = ResourceLimits(max_image_dimension=0)
    convert("file.psd", "output.svg", resource_limits=limits)

**Additional Mitigations**:

1. **Use alternative image formats** for large layers:

   .. code-block:: python

       # Save with PNG format for layers that might exceed WebP limits
       document.save("output.svg", image_format="PNG")

2. **Downscale large layers** before conversion (if quality loss is acceptable)
3. **Rasterize the entire PSD** instead of per-layer conversion for very large files

**Note**: This is a fundamental WebP format limitation, not a psd2svg limitation. PNG format supports up to 2^31-1 pixels per dimension and can be used as an alternative.

External Dependencies
---------------------

psd2svg depends on several libraries:

- ``psd-tools``: PSD file parsing
- ``fonttools``: Font handling
- ``pillow``: Image processing
- ``resvg-py``: SVG rasterization (default)
- ``playwright``: Browser-based rasterization (optional)

**Impact**: Vulnerabilities in dependencies could affect psd2svg.

**Mitigation**:

- Automated security scanning via Dependabot and GitHub Actions
- Regular dependency updates
- See ``SECURITY.md`` for vulnerability reporting

SVG Output Security
-------------------

Generated SVG files may contain:

- Embedded images (data URIs)
- Font data (data URIs)
- External resource references

**Impact**: SVG files rendered in browsers could potentially exploit browser vulnerabilities.

**Mitigation**:

- Sanitize SVG output before rendering in untrusted contexts
- Use Content Security Policy (CSP) when serving SVG files
- Consider server-side rendering for untrusted content

Security Checklist
==================

When deploying psd2svg in production:

.. list-table::
   :header-rows: 1
   :widths: 10 90

   * - Priority
     - Recommendation
   * - High
     - ✓ Implement file size limits for input files
   * - High
     - ✓ Implement timeout protection for conversions
   * - High
     - ✓ Validate all user-provided file paths
   * - High
     - ✓ Keep dependencies up to date
   * - Medium
     - ✓ Run conversions in sandboxed environments
   * - Medium
     - ✓ Monitor resource usage (CPU, memory, disk)
   * - Medium
     - ✓ Validate font file sources
   * - Medium
     - ✓ Implement rate limiting for conversion APIs
   * - Low
     - ✓ Use container isolation for maximum security
   * - Low
     - ✓ Sanitize SVG output for web rendering

Security Updates
================

Security features and fixes are documented in the changelog. Subscribe to:

- **GitHub Security Advisories**: https://github.com/CyberAgent/psd2svg/security/advisories
- **Release Notes**: https://github.com/CyberAgent/psd2svg/releases
- **Dependabot Alerts**: Enable for your repository

Reporting Security Issues
=========================

See ``SECURITY.md`` in the repository root for instructions on reporting security vulnerabilities.

Additional Resources
====================

- `SECURITY.md <https://github.com/CyberAgent/psd2svg/blob/main/SECURITY.md>`_ - Security policy
- `OWASP Secure Coding Practices <https://owasp.org/www-project-secure-coding-practices-quick-reference-guide/>`_
- `CWE Top 25 <https://cwe.mitre.org/top25/archive/2023/2023_top25_list.html>`_
