# Raid on ticket 0043: archive path from DATASETS_DIR (2026-10-31)

- Context: `/raid 43`, a single ticket. One coder ran hunt inline and wrote `src/archive_path.py`. `DATASETS_DIR` was unset in this Claude Code session, so the code falls back to reading `~/.config/environment.d/50-datasets.conf`.
- Event: the agent `gh` token (`~/.config/gh-agent/hosts.yml`) returned HTTP 401, and `git push` failed with it. Work stopped on a local branch until the author re-authenticated (`GH_CONFIG_DIR=~/.config/gh-agent gh auth login -h github.com`).
- Event: gaze had reviewed the branch as `branch:t0043-datasets-dir-archive` before PR 64 existed. The first verify-gate call refused for lack of a review: no round was spent. Recording the writer lines with `attribution_record.py --record-writer … --unit pr:64` opened the PR review, which adopted the branch review. The second call returned APPROVED in round 1.
- Outcome: PR 64 merged as f93211e. `make check-fast` on main with `DATASETS_DIR` unset gives 251 passed.
- Event: the attribution capture for pr:64 wrote nothing. The gaze answer carried `attribution: []`, and the helper reported `not derivable: reviewers`.
