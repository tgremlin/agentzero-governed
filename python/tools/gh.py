import json
import os
import re
import subprocess
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from python.helpers.tool import Response, Tool


class GhTool(Tool):
    API_BASE = "https://api.github.com"

    async def execute(self, **kwargs):
        method = str(kwargs.get("method") or self.method or "").strip().lower()
        if not method:
            return Response(
                message="Missing method. Supported: repo_view, issue_list, issue_create, pr_list, pr_view, pr_create",
                break_loop=False,
            )

        try:
            if method == "repo_view":
                payload = self._repo_view(kwargs)
            elif method == "issue_list":
                payload = self._issue_list(kwargs)
            elif method == "issue_create":
                payload = self._issue_create(kwargs)
            elif method == "pr_list":
                payload = self._pr_list(kwargs)
            elif method == "pr_view":
                payload = self._pr_view(kwargs)
            elif method == "pr_create":
                payload = self._pr_create(kwargs)
            else:
                return Response(
                    message=f"Unknown method '{method}'. Supported: repo_view, issue_list, issue_create, pr_list, pr_view, pr_create",
                    break_loop=False,
                )
            return Response(message=json.dumps(payload, indent=2), break_loop=False)
        except Exception as exc:
            return Response(message=f"gh tool error: {exc}", break_loop=False)

    def _repo_view(self, args: dict[str, Any]) -> dict[str, Any]:
        owner, repo = self._resolve_repo(args)
        return self._api_request("GET", f"/repos/{owner}/{repo}")

    def _issue_list(self, args: dict[str, Any]) -> list[dict[str, Any]]:
        owner, repo = self._resolve_repo(args)
        state = str(args.get("state", "open")).strip().lower()
        per_page = max(1, min(int(args.get("limit", 20)), 100))
        data = self._api_request(
            "GET",
            f"/repos/{owner}/{repo}/issues",
            query={"state": state, "per_page": per_page},
        )
        if not isinstance(data, list):
            raise RuntimeError("GitHub returned unexpected issue list payload")
        return data

    def _issue_create(self, args: dict[str, Any]) -> dict[str, Any]:
        owner, repo = self._resolve_repo(args)
        title = str(args.get("title", "")).strip()
        body = str(args.get("body", "")).strip()
        labels = args.get("labels", [])
        if not title:
            raise ValueError("title is required for issue_create")
        if labels and not isinstance(labels, list):
            raise ValueError("labels must be a list of strings")
        return self._api_request(
            "POST",
            f"/repos/{owner}/{repo}/issues",
            body={"title": title, "body": body, "labels": labels or []},
            auth_required=True,
        )

    def _pr_list(self, args: dict[str, Any]) -> list[dict[str, Any]]:
        owner, repo = self._resolve_repo(args)
        state = str(args.get("state", "open")).strip().lower()
        per_page = max(1, min(int(args.get("limit", 20)), 100))
        data = self._api_request(
            "GET",
            f"/repos/{owner}/{repo}/pulls",
            query={"state": state, "per_page": per_page},
        )
        if not isinstance(data, list):
            raise RuntimeError("GitHub returned unexpected PR list payload")
        return data

    def _pr_view(self, args: dict[str, Any]) -> dict[str, Any]:
        owner, repo = self._resolve_repo(args)
        number = int(args.get("number", 0))
        if number <= 0:
            raise ValueError("number is required for pr_view")
        return self._api_request("GET", f"/repos/{owner}/{repo}/pulls/{number}")

    def _pr_create(self, args: dict[str, Any]) -> dict[str, Any]:
        owner, repo = self._resolve_repo(args)
        title = str(args.get("title", "")).strip()
        body = str(args.get("body", "")).strip()
        head = str(args.get("head", "")).strip()
        base = str(args.get("base", "main")).strip()
        if not title:
            raise ValueError("title is required for pr_create")
        if not head:
            raise ValueError("head is required for pr_create")
        return self._api_request(
            "POST",
            f"/repos/{owner}/{repo}/pulls",
            body={"title": title, "body": body, "head": head, "base": base},
            auth_required=True,
        )

    def _resolve_repo(self, args: dict[str, Any]) -> tuple[str, str]:
        owner = str(args.get("owner", "")).strip()
        repo = str(args.get("repo", "")).strip()
        if owner and repo:
            return owner, repo
        if repo and "/" in repo and not owner:
            parts = repo.split("/", 1)
            if len(parts) == 2 and parts[0].strip() and parts[1].strip():
                return parts[0].strip(), parts[1].strip()

        inferred = self._infer_repo_from_git_remote()
        if inferred:
            return inferred
        raise ValueError(
            "Unable to resolve repository. Provide owner+repo or repo='owner/name'."
        )

    def _infer_repo_from_git_remote(self) -> tuple[str, str] | None:
        try:
            proc = subprocess.run(
                ["git", "config", "--get", "remote.origin.url"],
                check=False,
                capture_output=True,
                text=True,
                timeout=5,
            )
        except Exception:
            return None
        if proc.returncode != 0:
            return None

        remote = proc.stdout.strip()
        if not remote:
            return None

        patterns = [
            r"^git@github\.com:(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?$",
            r"^https://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?$",
            r"^ssh://git@github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?$",
        ]
        for pat in patterns:
            match = re.match(pat, remote)
            if match:
                return match.group("owner"), match.group("repo")
        return None

    def _api_request(
        self,
        method: str,
        path: str,
        query: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        auth_required: bool = False,
    ) -> Any:
        token = str(os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN") or "").strip()
        if auth_required and not token:
            raise RuntimeError("Missing GH_TOKEN or GITHUB_TOKEN for write operation.")

        url = f"{self.API_BASE}{path}"
        if query:
            url = f"{url}?{urlencode(query)}"

        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "agentzero-gh-tool",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if body is not None:
            headers["Content-Type"] = "application/json; charset=utf-8"

        req = Request(url, data=data, method=method, headers=headers)
        try:
            with urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8")
        except HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"GitHub API HTTP {e.code}: {detail}") from e
        except URLError as e:
            raise RuntimeError(f"GitHub API network error: {e}") from e

        if not raw:
            return {}
        return json.loads(raw)
