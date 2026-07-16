"""Tiny HTML rendering helpers — the whole "template engine".

Views are Python functions building escaped f-strings. Each view fragment is
wrapped in a declarative shadow root (<template shadowrootmode="open">), so
its <style> tag is scoped by the browser itself — with or without JS.
"""

from html import escape


def esc(value) -> str:
    return escape(str(value), quote=True)


def view(style: str, body: str) -> str:
    """A fragment: scoped styles + content inside a declarative shadow root.

    The same bytes serve three places: alone (fragment requests), inside the
    page chrome (full pages), and re-parsed by the SPA loader's setHTMLUnsafe
    (which understands declarative shadow DOM).
    """
    return (
        "<gf-view>"
        f'<template shadowrootmode="open"><style>{style}</style>{body}</template>'
        "</gf-view>"
    )


def page(title: str, fragment: str) -> str:
    """The site chrome around a view fragment."""
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)} · gitflower</title>
<link rel="stylesheet" href="/static/gitflower.css">
<script type="module" src="/static/components.js"></script>
</head>
<body>
<nav class="gf-nav">
  <a class="gf-brand" href="/">❀ gitflower</a>
  <a href="/repos/">Repositories</a>
  <a href="/docs/">Documentation</a>
</nav>
<main id="gf-main">{fragment}</main>
</body>
</html>"""
