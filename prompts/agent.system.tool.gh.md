### gh:
This is a GitHub CLI-style tool implemented with GitHub REST API (no `gh` binary required).

For write operations, set `GH_TOKEN` or `GITHUB_TOKEN`.

#### Methods
1. `gh:repo_view`
- Shows repository metadata.
- Args: `owner` + `repo`, or `repo` as `owner/name`.

2. `gh:issue_list`
- Lists issues.
- Args: `owner` + `repo` (or `repo=owner/name`), `state` (`open|closed|all`, optional), `limit` (optional, max 100).

3. `gh:issue_create`
- Creates an issue.
- Args: repo args above, `title` (required), `body` (optional), `labels` (optional list).

4. `gh:pr_list`
- Lists pull requests.
- Args: repo args above, `state` (`open|closed|all`, optional), `limit` (optional).

5. `gh:pr_view`
- Shows one pull request.
- Args: repo args above, `number` (required int).

6. `gh:pr_create`
- Creates a pull request.
- Args: repo args above, `title` (required), `head` (required), `base` (optional, default `main`), `body` (optional).

If repo args are omitted, the tool tries to infer `owner/repo` from `git remote origin`.

#### Usage example
```json
{
  "thoughts": ["I need to open a PR from my branch."],
  "tool_name": "gh:pr_create",
  "tool_args": {
    "owner": "acme",
    "repo": "agentzero-governed",
    "title": "Add Slack + gh tools",
    "head": "feature/slack-gh-tools",
    "base": "main",
    "body": "Adds Python-native Slack and GitHub integration tools."
  }
}
```
