#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Andrey Zheltukhin
# SPDX-License-Identifier: MIT
"""Check the FORM of an agent report against templates/report.md. Form only: truth is checked by re-running
the witnesses (reexec_claims.py) and the gate.

usage: check_report.py REPORT.md|REPORT.json [--template PATH] [--min-witnesses 1] [--numbers error|warn|off]

Keys come from the template (top-level `KEY: value` lines, sub-fields indented 2 spaces, list items `- `).
Without a template the built-in schema is used: BASE, TREE, GATE{line, log}, WITNESSES[{cmd, expected, fact}],
VERDICT, NOT_CHECKED. Aliases: VERDICT == EXIT, BASE == SHA.
Checks:
  - every template key is present and filled; no `{{...}}` placeholder left;
  - verdict in the closed vocabulary DONE | BLOCKED(reason) | SPEC_CONFLICT(test, source) | IMPOSSIBLE |
    NOT_REPRODUCED;
  - HYPOTHESIS starts with confirmed | refuted | not_tested;
  - TREE is a 40/64-hex tree hash (scripts/tree_hash.sh), BASE/SHA is 7-64 hex;
  - a block (GATE, PARENT_RED, ...) has its template sub-fields, or one line `n/a — reason`;
  - every witness has cmd (one command in backticks) and fact (+ the template's other sub-fields);
  - criteria lines carry PASS | FAIL | NOT_PROVEN and a command in backticks;
  - a number claim (`12 passed`, `75%`, `3/5`) outside a block with cmd or log and without a command
    in backticks on its line is flagged: a number without the command that produced it is an opinion.
    Free-text keys are exempt (ROOT, HYPOTHESIS, OPEN_RISKS, DEVIATIONS, NOT_CHECKED): they explain, they
    do not report results. Criteria, witness and other result lines keep the rule.
JSON reports use the same keys: blocks are objects, WITNESSES/CRITERIA are lists.
Exit: 0 form OK, 1 form problems (listed), 2 report not readable or has no keys at all.
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ddlib  # noqa: E402

DEFAULT_TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "templates", "report.md")
BUILTIN = {"keys": ["BASE", "TREE", "GATE", "WITNESSES", "VERDICT", "NOT_CHECKED"],
           "sub": {"GATE": ["line", "log"], "WITNESSES": ["cmd", "expected", "fact"]}, "lists": ["WITNESSES"]}
ALIASES = {"EXIT": "VERDICT", "SHA": "BASE"}
VERDICT_RE = re.compile(r"^(DONE|IMPOSSIBLE|NOT_REPRODUCED|BLOCKED\s*\(\s*\S.*\)|SPEC_CONFLICT\s*\(\s*\S.*\))$")
HYPOTHESIS_RE = re.compile(r"^(confirmed|refuted|not_tested)\b")
FREE_TEXT = ("ROOT", "HYPOTHESIS", "OPEN_RISKS", "DEVIATIONS", "NOT_CHECKED")
CRITERION_RE = re.compile(r"\b(PASS|FAIL|NOT_PROVEN)\b")
KEY_RE = re.compile(r"^([A-Z][A-Z0-9_]+):[ \t]*(.*)$")
SUB_RE = re.compile(r"^[ \t]{2,}([a-z_]+):[ \t]*(.*)$")
ITEM_RE = re.compile(r"^-[ \t]+(.*)$")
NA_RE = re.compile(r"^n/a\s*[—–:-]\s*\S")
CMD_RE = re.compile(r"`[^`]+`")
COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
PLACEHOLDER_RE = re.compile(r"\{\{.*?\}\}|^<[^<>]+>$")
NUMBER_CLAIM = re.compile(r"(?<![\w.:/#@-])(\d+(?:[.,]\d+)?\s?%|\d+/\d+\b|\d+(?:[.,]\d+)?\s+[^\W\d_]{3,})")
BOUND_SUBS = ("cmd", "log")  # a block with one of these binds its numbers to a command or a log


def canon(key):
    return ALIASES.get(key, key)


def parse_md(text):
    """{KEY: {"value", "sub": {}, "items": [{"_head", ...sub}]}} plus parse errors."""
    secs, errors, key, item = {}, [], None, None
    for line in COMMENT_RE.sub("", text).splitlines():
        if line.startswith("```") or line.startswith("#"):
            continue
        m = KEY_RE.match(line)
        if m:
            key, item = canon(m.group(1)), None
            if key in secs:
                errors.append("%s: key appears twice" % key)
            secs[key] = {"value": m.group(2).strip(), "sub": {}, "items": []}
            continue
        if key is None:
            continue
        m = ITEM_RE.match(line)
        if m:
            head = m.group(1).strip()
            item = {"_head": head}
            sm = re.match(r"^([a-z_]+):[ \t]*(.*)$", head)
            if sm:  # "- cmd: `x`" starts an item with its first sub-field
                item[sm.group(1)] = sm.group(2).strip()
            secs[key]["items"].append(item)
            continue
        m = SUB_RE.match(line)
        if m:
            (item if item is not None else secs[key]["sub"])[m.group(1)] = m.group(2).strip()
    return secs, errors


def _json_fields(d):
    """Lower-case string fields; a JSON cmd needs no backticks (the value itself is the command)."""
    out = {str(a).lower(): "" if b is None else str(b) for a, b in d.items()}
    if out.get("cmd") and not CMD_RE.search(out["cmd"]):
        out["cmd"] = "`%s`" % out["cmd"]
    return out


def parse_json(obj):
    secs = {}
    for k, v in obj.items():
        key = canon(str(k).upper())
        s = {"value": "", "sub": {}, "items": []}
        if isinstance(v, dict):
            s["sub"] = _json_fields(v)
        elif isinstance(v, list):
            for i, it in enumerate(v):
                if isinstance(it, dict):
                    d = _json_fields(it)
                    d["_head"] = d.get("id") or d.get("name") or "#%d" % (i + 1)
                    if "verdict" in d or "status" in d:
                        d["_head"] += ": %s %s" % (d.get("verdict") or d.get("status"), d.get("cmd", ""))
                else:
                    d = {"_head": str(it)}
                s["items"].append(d)
        else:
            s["value"] = "" if v is None else str(v)
        secs[key] = s
    return secs, []


def load_schema(path):
    if not path or not os.path.exists(path):
        return dict(BUILTIN, source="builtin")
    with open(path, encoding="utf-8") as f:
        secs, _ = parse_md(f.read())
    sub = {}
    for k, s in secs.items():
        fields = list(s["sub"]) or [f for f in (s["items"][0] if s["items"] else {}) if f != "_head"]
        if fields:
            sub[k] = fields
    lists = [k for k, s in secs.items() if s["items"]]
    return {"keys": list(secs), "sub": sub, "lists": lists, "source": os.path.abspath(path)}


def check(secs, schema, min_wit, numbers):
    probs, warns = [], []
    for k in schema["keys"]:
        s = secs.get(k)
        if s is None:
            probs.append("missing key %s" % k)
        elif not (s["value"] or s["sub"] or s["items"]):
            probs.append("%s: empty" % k)
    for k, s in secs.items():
        texts = [s["value"]] + list(s["sub"].values()) + [v for it in s["items"] for v in it.values()]
        if any(PLACEHOLDER_RE.search(t.strip()) for t in texts if t):
            probs.append("%s: unfilled placeholder" % k)
    v = secs.get("VERDICT", {}).get("value", "")
    if v and not VERDICT_RE.match(v):
        probs.append("VERDICT/EXIT %r not in DONE | BLOCKED(reason) | SPEC_CONFLICT(test, source) | IMPOSSIBLE"
                     " | NOT_REPRODUCED" % v)
    hyp = secs.get("HYPOTHESIS", {}).get("value", "")
    if "HYPOTHESIS" in secs and not HYPOTHESIS_RE.match(hyp):
        probs.append("HYPOTHESIS %r: must start with confirmed | refuted | not_tested" % hyp[:60])
    tree = secs.get("TREE", {}).get("value", "")
    if tree and not re.match(r"^([0-9a-f]{40}|[0-9a-f]{64})$", tree) and not NA_RE.match(tree):
        probs.append("TREE: 40/64 hex from tree_hash.sh at gate time")
    base = secs.get("BASE", {}).get("value", "")
    if base and not re.match(r"^[0-9a-f]{7,64}$", base):
        probs.append("BASE/SHA: 7-64 hex commit")
    for k, fields in schema["sub"].items():
        s = secs.get(k)
        if s is None or k in schema["lists"]:
            continue
        if s["value"]:
            if not NA_RE.match(s["value"]):
                probs.append("%s: either sub-fields %s or one line `n/a — reason`" % (k, ", ".join(fields)))
            continue
        probs += ["%s: no %s" % (k, f) for f in fields if not s["sub"].get(f)]
        if s["sub"].get("cmd") and not CMD_RE.search(s["sub"]["cmd"]):
            probs.append("%s.cmd: one command in backticks" % k)
    wit = secs.get("WITNESSES")
    if wit is not None:
        fields = list(dict.fromkeys(["cmd", "fact"] + schema["sub"].get("WITNESSES", [])))
        if len(wit["items"]) < min_wit:
            probs.append("WITNESSES: %d, need >= %d" % (len(wit["items"]), min_wit))
        for i, it in enumerate(wit["items"]):
            name = it["_head"].split(":")[0] or "#%d" % (i + 1)
            probs += ["WITNESSES.%s: no %s" % (name, f) for f in fields if not it.get(f)]
            if it.get("cmd") and not CMD_RE.search(it["cmd"]):
                probs.append("WITNESSES.%s: cmd is one command in backticks" % name)
    crit = secs.get("CRITERIA")
    for it in (crit or {}).get("items", []):
        line = it["_head"]
        if not CRITERION_RE.search(line):
            probs.append("CRITERIA %r: no PASS | FAIL | NOT_PROVEN" % line[:60])
        elif not CMD_RE.search(line):
            probs.append("CRITERIA %r: no command in backticks" % line[:60])
    if numbers != "off":
        for k, s in secs.items():
            if k in ("TREE", "BASE", "VERDICT") + FREE_TEXT or any(s["sub"].get(b) for b in BOUND_SUBS):
                continue
            lines = [s["value"]] + [it["_head"] for it in s["items"] if not any(it.get(b) for b in BOUND_SUBS)]
            for line in lines:
                m = NUMBER_CLAIM.search(line or "")
                if m and not CMD_RE.search(line):
                    (probs if numbers == "error" else warns).append(
                        "%s: number %r without a command on its line" % (k, m.group(0).strip()))
    return probs, warns


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("report")
    ap.add_argument("--template", default=DEFAULT_TEMPLATE)
    ap.add_argument("--min-witnesses", type=int, default=1)
    ap.add_argument("--numbers", choices=("error", "warn", "off"), default="error")
    a = ap.parse_args()
    try:
        with open(a.report, encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        ddlib.emit({"status": "NOT_PROVEN", "error": "cannot read report: %s" % e}, 2)
    if a.report.endswith(".json") or text.lstrip().startswith("{"):
        try:
            obj = json.loads(text)
        except ValueError as e:
            ddlib.emit({"status": "NOT_PROVEN", "error": "invalid JSON: %s" % e}, 2)
        if not isinstance(obj, dict):
            ddlib.emit({"status": "NOT_PROVEN", "error": "JSON report must be an object"}, 2)
        secs, errors = parse_json(obj)
    else:
        secs, errors = parse_md(text)
    if not secs:
        ddlib.emit({"status": "NOT_PROVEN", "error": "no `KEY: value` lines found"}, 2)
    schema = load_schema(a.template)
    probs, warns = check(secs, schema, a.min_witnesses, a.numbers)
    probs = errors + probs
    ddlib.emit({"status": "FAIL" if probs else "PASS", "schema": schema["source"], "problems": probs,
                "warnings": warns, "note": "form only; truth = re-run the witnesses"}, 1 if probs else 0)


if __name__ == "__main__":
    ddlib.guarded_main(main)
