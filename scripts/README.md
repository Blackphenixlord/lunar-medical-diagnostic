# scripts

`push_to_github.ps1` — creates the local git history if there is none, then
pushes the repo to GitHub. Safe to run more than once.

```powershell
powershell -ExecutionPolicy Bypass -File scripts\push_to_github.ps1
```

It will do the whole thing by itself if the GitHub CLI is installed; otherwise
it prints the two clicks you need to make first. See the comments at the top of
the file.
