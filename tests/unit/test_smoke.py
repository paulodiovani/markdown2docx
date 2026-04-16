"""Sanity test that verifies the test infrastructure is wired up correctly."""


def test_lib_modules_importable():
    import lib.alerts  # noqa: F401
    import lib.config  # noqa: F401
    import lib.confluence  # noqa: F401
    import lib.mermaid  # noqa: F401
    import lib.parser  # noqa: F401


def test_cli_modules_importable():
    import markdown2confluence  # noqa: F401
    import markdown2docx  # noqa: F401
