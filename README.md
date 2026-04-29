# claude-skills

Collection of custom skills for [Claude Code](https://claude.com/claude-code), distributed as a plugin marketplace.

## Install

In Claude Code, add the marketplace and install the plugin:

```
/plugin marketplace add fivol/claude-skills
/plugin install main@fivol-skills
```

After install, skills become available with the `main:` prefix, e.g. `main:skill-name`.

## Repo structure

```
claude-skills/
├── .claude-plugin/
│   └── marketplace.json        # marketplace catalog
└── plugins/
    └── main/
        ├── .claude-plugin/
        │   └── plugin.json     # plugin manifest
        └── skills/             # add SKILL.md files here
            └── <skill-name>/
                └── SKILL.md
```

## Adding a skill

1. Create `plugins/main/skills/<skill-name>/SKILL.md` with frontmatter:
   ```markdown
   ---
   name: skill-name
   description: When to use this skill (precise triggers)
   ---

   Skill body…
   ```
2. Commit and push. Users update with `/plugin update main@fivol-skills`.

## Updating

```
/plugin marketplace update fivol-skills
/plugin update main@fivol-skills
```
