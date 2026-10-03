# Engineering Team Claude Plugins

A shared marketplace of Claude Code plugins and skills. Install once and they work in every project, in the terminal and in the VS Code / JetBrains extensions.

## Available skills

One plugin, `python-react-fullstack`, contains all the skills:

| Skill | What it does |
|---|---|
| `react-architecture` | Folder structure, import boundaries, swappable design-system layer and coding standards for React + TypeScript + Vite apps |
| `python-architecture` | uv + Makefile + pyproject standards and a project scaffolder for FastAPI services, libraries and CLIs |
| `python-react-fullstack` | FastAPI ↔ React contract: generated TypeScript types from OpenAPI, typed client, TanStack Query, errors, auth, SSE streaming |

## Install

There are two ways to install. Pick one; you do **not** need a `.claude/settings.json` file unless you want a repo to prompt teammates to install.

| | Personal (user scope, default) | Team repo (project scope) |
|---|---|---|
| Where it's recorded | your `~/.claude/settings.json` | the repo's `.claude/settings.json` (committed) |
| Applies to | every project on your machine | anyone who opens that repo |
| Best for | trying it out, or always having it available | team repos where everyone should follow the same standards |

### Option 1: Personal install (one time per developer)

From a terminal, in any folder:

```bash
claude plugin marketplace add sosingh-gd/team-claude-plugins
claude plugin install python-react-fullstack@engineering-team
```

Or inside a Claude Code session (including the VS Code extension):

```
/plugin marketplace add sosingh-gd/team-claude-plugins
/plugin install python-react-fullstack@engineering-team
```

No files are added to any repo.

### Option 2: Team repo install (writes `.claude/settings.json` for you)

From the project's root folder:

```bash
claude plugin marketplace add sosingh-gd/team-claude-plugins --scope project
claude plugin install python-react-fullstack@engineering-team --scope project
```

This creates (or updates) `.claude/settings.json` with the marketplace and the enabled plugin. Commit it. Anyone who clones the repo and opens it in Claude Code is prompted to install the plugin, with no commands to run. The generated file looks like this, so you can also write it by hand:

```json
{
  "extraKnownMarketplaces": {
    "engineering-team": {
      "source": { "source": "github", "repo": "sosingh-gd/team-claude-plugins" }
    }
  },
  "enabledPlugins": {
    "python-react-fullstack@engineering-team": true
  }
}
```

Use `--scope local` instead to enable it only for yourself in one repo (written to the gitignored `.claude/settings.local.json`).

### Verify

Restart the session (or run `/reload-plugins`), then type `/python-react-fullstack:` in Claude Code. You should see `react-architecture`, `python-architecture` and `python-react-fullstack`. From a terminal, `claude plugin list` shows the plugin as enabled.

## Usage

Each skill triggers automatically on matching work (React, Python, or full-stack FastAPI + React). To be explicit, ask Claude to "use the react-architecture skill", "use the python-architecture skill" or "use the python-react-fullstack skill", or call `/python-react-fullstack:<skill-name>`.

Optional: copy `plugins/python-react-fullstack/CLAUDE.example.md` to `~/.claude/CLAUDE.md` so Claude detects React projects and applies the skill consistently.

## Updating the plugin

### Get the latest version (users)

From a terminal:

```bash
claude plugin marketplace update engineering-team                 # fetch the latest catalog from GitHub
claude plugin update python-react-fullstack@engineering-team      # install the new version
```

If you installed with `--scope project` (or `local`), pass the same scope to the update:

```bash
claude plugin update python-react-fullstack@engineering-team --scope project
```

Then restart Claude Code (or run `/reload-plugins` in an open session). Updates don't apply to sessions that are already running.

Check which version you have:

```bash
claude plugin list        # shows python-react-fullstack@engineering-team with its Version
```

Compare it with `version` in [`plugins/python-react-fullstack/.claude-plugin/plugin.json`](plugins/python-react-fullstack/.claude-plugin/plugin.json) on `main`.

**Not getting the new changes?**

- The update only happens when `version` in `plugin.json` changes. A push without a version bump is not picked up.
- Run `claude plugin marketplace update engineering-team` first. `plugin update` only sees versions the local catalog knows about.
- Still stuck: `claude plugin uninstall python-react-fullstack@engineering-team`, then install again.

### Publish an update (maintainers)

1. Edit the skill files and bump `version` in `plugins/python-react-fullstack/.claude-plugin/plugin.json` (see [Contributing](#contributing) for semver).
2. Run `claude plugin validate .`, then merge to `main`.
3. Tell the team to run the two update commands above. The `.claude/settings.json` in team repos doesn't need to change, because it enables the plugin by name, not by version.

## Uninstall

```bash
claude plugin uninstall python-react-fullstack@engineering-team
```

## Repository layout

```
.claude-plugin/marketplace.json          # catalog of all plugins
plugins/
└── python-react-fullstack/
    ├── .claude-plugin/plugin.json       # plugin manifest (name must match the catalog entry)
    ├── README.md
    ├── CLAUDE.example.md                # optional global CLAUDE.md
    └── skills/
        ├── react-architecture/
        │   ├── SKILL.md
        │   ├── references/
        │   └── assets/templates/
        ├── python-architecture/
        │   ├── SKILL.md
        │   ├── references/                  # tooling, fastapi, project-types
        │   ├── assets/templates/            # pyproject, Makefile, Dockerfile, CI, pre-commit
        │   ├── assets/skeletons/            # fastapi-modular, fastapi-layered, library, cli
        │   └── scripts/scaffold.py          # stdlib-only project generator
        └── python-react-fullstack/
            ├── SKILL.md
            ├── references/                  # api-contract, auth, streaming, backend-structure, dev-setup, other-patterns
            └── assets/templates/            # backend/, frontend/, project/ ({{placeholder}} templates)
```

## Contributing

1. Create a branch and edit the skill files (usually `SKILL.md` or `references/*.md`).
2. Bump `version` in `plugins/python-react-fullstack/.claude-plugin/plugin.json` (semver: patch = wording fixes, minor = new rules, major = changed conventions). Users only receive updates when the version changes.
3. Test locally:
   ```bash
   claude plugin validate .
   claude plugin marketplace add ./      # from your clone
   claude plugin install python-react-fullstack@engineering-team
   ```
4. Open a pull request. A code owner reviews before merge.

### Adding a new skill

Create `plugins/python-react-fullstack/skills/<skill-name>/SKILL.md`; it is picked up automatically. Bump the plugin version.

### Adding a new plugin

1. Create `plugins/<name>/.claude-plugin/plugin.json` and `plugins/<name>/skills/<skill-name>/SKILL.md`.
2. Add an entry to `.claude-plugin/marketplace.json` with the same `name`.
3. Run `claude plugin validate .` and open a PR.

Rules: plugin names have no spaces; `source` paths are relative to the repo root and must not use `..`.
