# Integration

After running `erg init`, follow these two steps to integrate git-erg
with your project.

## 1. Pre-commit hook

Append the following to `.git/hooks/pre-commit` (create the file and
`chmod +x` it if it does not exist):

```sh
# Reject tickets/erg commit on non-main branches
# CI rebuilds the binary after merge; feature PRs must not include it.
if git diff --cached --name-only | grep -q '^tickets/erg$'; then
    branch=$(git branch --show-current)
    if [ "$branch" != "main" ]; then
        echo "pre-commit: do not commit tickets/erg in feature branches." >&2
        echo " CI rebuilds the binary after merge. Use 'make build' and test" >&2
        echo " with build/erg. To override: git commit --no-verify" >&2
        exit 1
    fi
fi

# Validate .erg files (if any are staged)
erg_files=$(git diff --cached --name-only | grep '\.erg$' || true)
if [ -n "$erg_files" ]; then
    erg_bin="tickets/erg"
    if [ -x "$erg_bin" ]; then
        # shellcheck disable=SC2086
        if ! $erg_bin validate $erg_files; then
            echo "ERROR: Ticket validation failed. Fix errors above." >&2
            exit 1
        fi
        if ! $erg_bin check tickets/; then
            echo "ERROR: Ticket corpus check failed. Fix errors above." >&2
            exit 1
        fi
    else
        echo "ERROR: erg binary not found. Run 'make build' first." >&2
        exit 1
    fi
fi
```

## 2. Agent instructions

Add this line to your `AGENTS.md` (or equivalent agent-visible file):

```
git-erg local tickets: see tickets/AGENTS.md
```

## Optional: .gitignore

Add `tickets/erg` to `.gitignore` if you do not want to commit the
bootstrap binary. If you *do* commit it (recommended for offline
environments), skip this step.
