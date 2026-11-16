# Changelog

All notable changes to this project are documented here.

## [0.1.0] - 2026-11-16

### Added

- `app` CLI (`python app` / `./app`) and `app.cmd` Windows launcher.
- `show FILE` with optional `--section profile|projects|skills`.
- `find FILE QUERY` with Unicode `casefold()` matching over titles and
  descriptions.
- Strict UTF-8 JSON validation: exact schema, unique slugs and skills,
  prohibition of control characters, BOM, duplicate keys and NaN/Infinity,
  and the 1048576-byte size limit.
- Black-box pytest suite traceable to acceptance criteria AC-1..AC-12.
- GitHub Actions CI on Ubuntu and Windows with Python 3.12.
