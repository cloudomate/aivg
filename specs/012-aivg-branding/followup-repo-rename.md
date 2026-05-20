# Follow-up: rename the repo directory `hermes-voice/` → `aivg/`

**Source**: feature 012 spec Assumptions + task T044.
**Status**: deferred — explicit non-goal of feature 012. Tracked here.

The AIVG rebrand intentionally **does not** rename the repo directory
itself. Doing so triggers external coordination that's separate from
the in-repo product rename:

## What renaming the repo dir affects

| Surface | Impact |
|---|---|
| GitHub remote URL | `cloudomate/hermes-voice` → `cloudomate/aivg` (or similar). GitHub auto-redirects for some clients but not all. |
| Existing developer clones | Every clone needs `git remote set-url origin <new-url>` (or a fresh clone). |
| README badges and docs links | Anything that pins to the GitHub raw URL or branch URL needs updating. |
| External deploy scripts | Anything that hard-codes the repo dirname (e.g. `cd ~/coderepo/hermes-voice && …`) needs updating. |
| CI integrations | Webhooks, branch-protection rules, status-check IDs — verified after the rename. |
| Pinned dependencies pointing at the GitHub URL | Any downstream `pip install git+https://github.com/cloudomate/hermes-voice` style entry. |

## What it does NOT affect

- Anything in-repo (already renamed in feature 012).
- The Python package names (`aivg_core` / `aivg_cli`) — already done.
- The CLI binary `aivg` — already done.
- The data dir `~/.aivg/` — already done.

## Recommended sequence

1. Coordinate with anyone with an active clone — give them at least one
   week of notice (or close out the active branches first).
2. Rename on GitHub: Settings → General → Repository name.
3. Update README badges / clone-URL examples / CI status-check
   references.
4. Update any external deployment scripts that hard-code the dir name.
5. Add the redirect to a one-line note in CHANGELOG.

## Constitution check

The repo-dir rename does not change any Principle. No amendment needed.
