#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Andrey Zheltukhin
# SPDX-License-Identifier: MIT
# Git tree hash of the working tree as it is now: tracked changes + untracked non-ignored files.
# The real index is never touched: a copy goes into a temporary GIT_INDEX_FILE.
# usage: tree_hash.sh [DIR]      (DIR defaults to the current directory; any path inside the repo)
# Prints one 40/64-hex line = what `git add -A && git write-tree` would give, without staging anything.
# Take it right after the gate run and before writing the report, so the report is not in the judged tree.
# Two runs on the same content give the same hash; any edit, new file or deletion changes it.
# Exit: 0 hash printed, 2 not a git repository / git error.
set -u
dir="${1:-.}"
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE  # judge the named tree, not an inherited one
root=$(git -C "$dir" rev-parse --show-toplevel 2>/dev/null) || { echo "tree_hash: not a git repository: $dir" >&2; exit 2; }
real_idx=$(git -C "$root" rev-parse --path-format=absolute --git-path index 2>/dev/null) || exit 2
tmp=$(mktemp -d "${TMPDIR:-/tmp}/dd-tree.XXXXXX") || exit 2
trap 'rm -rf "$tmp"' EXIT
export GIT_INDEX_FILE="$tmp/index"
if [ -f "$real_idx" ]; then
  cp "$real_idx" "$GIT_INDEX_FILE" || exit 2   # copy keeps the stat cache: no rehash of unchanged files
elif git -C "$root" rev-parse -q --verify HEAD >/dev/null; then
  git -C "$root" read-tree HEAD || exit 2
fi
git -C "$root" add -A -- . >/dev/null 2>&1 || { echo "tree_hash: git add failed" >&2; exit 2; }
git -C "$root" write-tree || exit 2
