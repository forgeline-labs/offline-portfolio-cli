#!/usr/bin/env python3
"""offline-portfolio-cli 0.1.0.

Non-interactive terminal portfolio backed by a local JSON file.
Standard library only; no network, no embedded personal data.
"""

import json
import re
import sys

PRODUCT = "offline-portfolio-cli"
VERSION = "0.1.0"

MAX_FILE_BYTES = 1024 * 1024
MAX_PROJECTS = 100
MAX_SKILLS = 100
MAX_QUERY_CHARS = 120
SECTIONS = ("profile", "projects", "skills")
SLUG_RE = re.compile(r"[a-z][a-z0-9-]{0,31}\Z")

HELP = """usage: app show FILE [--section profile|projects|skills]
       app find FILE QUERY
       app --version
       app --help

Non-interactive offline portfolio CLI. Reads a local JSON file and prints
portfolio data as JSON on stdout.

commands:
  show FILE                     print the validated portfolio object
  show FILE --section profile   print only the profile object
  show FILE --section projects  print only the projects array
  show FILE --section skills    print only the skills array
  find FILE QUERY               print projects whose title or description
                                contains QUERY (Unicode casefold)

options:
  --section VALUE               select profile, projects or skills
  --version                     print the product version and exit
  --help                        print this help and exit

FILE must be a UTF-8 JSON object of at most 1048576 bytes.
"""


class ValidationError(Exception):
    """Input rejected by the schema rules (exit code 2)."""


class IoFailure(Exception):
    """The input file could not be opened or read (exit code 3)."""


def _emit_json(value):
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    sys.stdout.buffer.write(payload.encode("utf-8") + b"\n")
    sys.stdout.buffer.flush()


def _emit_text(text):
    sys.stdout.buffer.write(text.encode("utf-8"))
    sys.stdout.buffer.flush()


def _fail(message, code):
    sys.stderr.write("error: " + message + "\n")
    sys.stderr.flush()
    return code


def _check_text(value, field, min_length, max_length):
    if not isinstance(value, str):
        raise ValidationError(field + " must be a string")
    if not min_length <= len(value) <= max_length:
        raise ValidationError(field + " length is out of range")
    for char in value:
        point = ord(char)
        if point < 0x20 or point == 0x7F:
            raise ValidationError(field + " contains a control character")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise ValidationError(field + " is not valid Unicode text") from None


def _object_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValidationError("duplicate object key")
        result[key] = value
    return result


def _reject_constant(_token):
    raise ValidationError("NaN and Infinity are not valid JSON values")


def _parse_json(text):
    try:
        return json.loads(
            text,
            object_pairs_hook=_object_pairs,
            parse_constant=_reject_constant,
        )
    except ValidationError:
        raise
    except (ValueError, RecursionError):
        raise ValidationError("invalid JSON") from None


def _validate_project(project):
    if not isinstance(project, dict):
        raise ValidationError("each project must be an object")
    if set(project) != {"slug", "title", "description"}:
        raise ValidationError("project keys must be exactly slug, title, description")
    slug = project["slug"]
    if not isinstance(slug, str) or SLUG_RE.fullmatch(slug) is None:
        raise ValidationError("project slug is invalid")
    _check_text(project["title"], "project title", 1, 120)
    _check_text(project["description"], "project description", 0, 2000)
    return {
        "slug": slug,
        "title": project["title"],
        "description": project["description"],
    }


def validate_portfolio(document):
    """Validate the whole document and return a normalized copy."""
    if not isinstance(document, dict):
        raise ValidationError("top-level JSON value must be an object")
    if set(document) != {"profile", "projects", "skills"}:
        raise ValidationError("top-level keys must be exactly profile, projects, skills")

    profile = document["profile"]
    if not isinstance(profile, dict):
        raise ValidationError("profile must be an object")
    if set(profile) != {"name", "bio"}:
        raise ValidationError("profile keys must be exactly name, bio")
    _check_text(profile["name"], "profile name", 1, 80)
    _check_text(profile["bio"], "profile bio", 0, 2000)

    projects = document["projects"]
    if not isinstance(projects, list):
        raise ValidationError("projects must be an array")
    if len(projects) > MAX_PROJECTS:
        raise ValidationError("too many projects")
    normalized_projects = []
    slugs = set()
    for project in projects:
        normalized = _validate_project(project)
        if normalized["slug"] in slugs:
            raise ValidationError("duplicate project slug")
        slugs.add(normalized["slug"])
        normalized_projects.append(normalized)

    skills = document["skills"]
    if not isinstance(skills, list):
        raise ValidationError("skills must be an array")
    if len(skills) > MAX_SKILLS:
        raise ValidationError("too many skills")
    seen_skills = set()
    normalized_skills = []
    for skill in skills:
        _check_text(skill, "skill", 1, 80)
        if skill in seen_skills:
            raise ValidationError("duplicate skill")
        seen_skills.add(skill)
        normalized_skills.append(skill)

    return {
        "profile": {"name": profile["name"], "bio": profile["bio"]},
        "projects": sorted(normalized_projects, key=lambda item: item["slug"]),
        "skills": sorted(normalized_skills),
    }


def load_portfolio(path):
    try:
        with open(path, "rb") as handle:
            raw = handle.read(MAX_FILE_BYTES + 1)
    except OSError:
        raise IoFailure() from None
    if len(raw) > MAX_FILE_BYTES:
        raise ValidationError("file exceeds 1048576 bytes")
    if raw.startswith(b"\xef\xbb\xbf"):
        raise ValidationError("UTF-8 BOM is not allowed")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise ValidationError("file is not valid UTF-8") from None
    return validate_portfolio(_parse_json(text))


def _validate_query(query):
    if not isinstance(query, str):
        raise ValidationError("QUERY must be a string")
    if not 1 <= len(query) <= MAX_QUERY_CHARS:
        raise ValidationError("QUERY length is out of range")
    for char in query:
        point = ord(char)
        if point < 0x20 or point == 0x7F:
            raise ValidationError("QUERY contains a control character")


def _command_show(args):
    if not args:
        return _fail("show requires FILE", 2)
    path = args[0]
    rest = args[1:]
    section = None
    if rest:
        if rest[0] != "--section":
            return _fail("unknown argument", 2)
        if len(rest) < 2:
            return _fail("--section requires a value", 2)
        if len(rest) > 2:
            return _fail("unknown argument", 2)
        section = rest[1]
        if section not in SECTIONS:
            return _fail("--section must be profile, projects or skills", 2)

    portfolio = load_portfolio(path)
    if section is None:
        _emit_json(portfolio)
    elif section == "profile":
        _emit_json(portfolio["profile"])
    else:
        _emit_json(portfolio[section])
    return 0


def _command_find(args):
    if len(args) < 2:
        return _fail("find requires FILE and QUERY", 2)
    if len(args) > 2:
        return _fail("unknown argument", 2)
    path, query = args[0], args[1]
    _validate_query(query)
    portfolio = load_portfolio(path)
    needle = query.casefold()
    matches = [
        project
        for project in portfolio["projects"]
        if needle in project["title"].casefold()
        or needle in project["description"].casefold()
    ]
    _emit_json(matches)
    return 0


def main(argv):
    if argv == ["--version"]:
        _emit_text(PRODUCT + " " + VERSION + "\n")
        return 0
    if argv == ["--help"]:
        _emit_text(HELP)
        return 0
    if not argv:
        return _fail("missing command", 2)
    command = argv[0]
    if command == "show":
        return _command_show(argv[1:])
    if command == "find":
        return _command_find(argv[1:])
    return _fail("unknown argument", 2)


def run(argv):
    try:
        return main(argv)
    except ValidationError as error:
        return _fail(str(error), 2)
    except IoFailure:
        return _fail("cannot read FILE", 3)
    except OSError:
        return _fail("i/o failure", 3)


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:]))
