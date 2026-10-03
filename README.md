# Engineering Team Claude Plugins

A shared marketplace of Claude Code plugins and skills. Install once and they work in every project, in the terminal and in the VS Code / JetBrains extensions.

## Available plugins

| Plugin | What it does |
|---|---|
| `react-architecture` | Folder structure, import boundaries, swappable design-system layer and coding standards for React + TypeScript + Vite apps |

## Install (one time per developer)

From a terminal:

```bash
claude plugin marketplace add sosingh-gd/team-claude-plugins
claude plugin install react-architecture@engineering-team
```

Or inside a Claude Code session (including the VS Code extension):

```
/plugin marketplace add sosingh-gd/team-claude-plugins
/plugin install react-architecture@engineering-team
```

Restart the session (or run `/reload-plugins`). Check with `claude plugin list`.

The skill triggers automatically on React work. To be explicit, ask Claude to "use the react-architecture skill".

Optional: copy `plugins/react-architecture/CLAUDE.example.md` to `~/.claude/CLAUDE.md` so Claude detects React projects and applies the skill consistently.

## Get updates

```bash
claude plugin marketplace update engineering-team
```

## Auto-enable for a project's team

Add this to a project's `.claude/settings.json` so anyone opening the repo is prompted to install it:

```json
{
  "extraKnownMarketplaces": {
    "engineering-team": {
      "source": { "source": "github", "repo": "sosingh-gd/team-claude-plugins" }
    }
  },
  "enabledPlugins": {
    "react-architecture@engineering-team": true
  }
}
```

## Repository layout

```
.claude-plugin/marketplace.json          # catalog of all plugins
plugins/
└── react-architecture/
    ├── .claude-plugin/plugin.json       # plugin manifest (name must match the catalog entry)
    ├── CLAUDE.example.md                # optional global CLAUDE.md
    └── skills/
        └── react-architecture/
            ├── SKILL.md
            ├── references/
            └── assets/templates/
```

## Contributing

1. Create a branch and edit the skill files (usually `SKILL.md` or `references/*.md`).
2. Bump `version` in the plugin's `plugin.json` (semver: patch = wording fixes, minor = new rules, major = changed conventions). Users only receive updates when the version changes.
3. Test locally:
   ```bash
   claude plugin validate .
   claude plugin marketplace add ./      # from your clone
   claude plugin install react-architecture@engineering-team
   ```
4. Open a pull request. A code owner reviews before merge.

### Adding a new plugin

1. Create `plugins/<name>/.claude-plugin/plugin.json` and `plugins/<name>/skills/<skill-name>/SKILL.md`.
2. Add an entry to `.claude-plugin/marketplace.json` with the same `name`.
3. Run `claude plugin validate .` and open a PR.

Rules: plugin names have no spaces; `source` paths are relative to the repo root and must not use `..`.
