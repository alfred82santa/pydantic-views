# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

from importlib import metadata

project = "Pydantic Views"
copyright = "2025–2026, Alfred Santacatalina"
author = "Alfred Santacatalina"
release = metadata.version("pydantic-views")
language = "en"

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.doctest",
    "sphinx.ext.intersphinx",
    "sphinxcontrib.autodoc_pydantic",
]

templates_path = ["_templates"]
exclude_patterns = []


# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = "alabaster"
html_static_path = ["_static"]
html_css_files = ["custom.css"]
html_title = "Pydantic Views — Typed schemas from one model"
html_logo = "_static/pydantic-views-logo-192.png"
html_favicon = "_static/favicon.ico"

html_theme_options = {
    "page_width": "1100px",
    "sidebar_width": "260px",
    "github_user": "alfred82santa",
    "github_repo": "pydantic-views",
    "github_banner": True,
    "description": "One domain model. Purpose-built schemas for every operation.",
}

# -- Autodoc config -----------------------------------------------

# autodoc_typehints = "description"

autodoc_member_order = "bysource"

add_module_names = True

set_type_checking_flag = True

python_use_unqualified_type_names = True
python_maximum_signature_line_length = 80
python_display_short_literal_types = True

autoclass_content = "both"

autodoc_default_options = {
    "members": "",
    "member-order": "bysource",
    "undoc-members": True,
    "show-inheritance": True,
    "autoclass_content": "class",
}


# -- Intersphinx config -----------------------------------------------

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "pydantic": ("https://docs.pydantic.dev/latest", None),
}


# -- github config -------------------------------------------

github_username = "alfred82santa"
github_repository = "pydantic-views"


# -- Latex ------------------------------

latex_elements = {
    "maxlistdepth": "9",
}
