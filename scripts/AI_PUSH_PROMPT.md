# Prompt for the AI in VS Code

Paste the block below into Copilot Chat or Claude in VS Code, with the `nasa`
folder open, in **agent mode** — it needs terminal access to run git.

---

```
Push this repo to GitHub. The folder is C:\Users\joshua\Desktop\nasa on Windows.
Use the integrated terminal (PowerShell). Do not edit any source files.

Context you need:
- This is VITALS, a NASA HUNCH project. Team TETHER.
- A local git repo ALREADY EXISTS here with 2 commits on branch `main`. Do not
  re-init it and do not delete .git.
- It has never been pushed anywhere. There is no `origin` remote yet.
- The repo was last written from a Linux mount, so two things are probably wrong:
  a stale `.git\index.lock` file, and every file showing as modified because of
  the executable bit. Both are fixed below.
- There is a `_to_delete\` folder (old `src\mdx`, a first broken `.git`, an old
  script). It is junk. Delete it before committing.

Do this:

1. cd to C:\Users\joshua\Desktop\nasa

2. Try the script that is already in the repo first:
       powershell -ExecutionPolicy Bypass -File scripts\push_to_github.ps1
   If it completes, you are done. If it fails, tell me the exact error and then
   do steps 3-7 by hand.

3. Clean up:
       Remove-Item -Recurse -Force _to_delete -ErrorAction SilentlyContinue
       Remove-Item -Force .git\index.lock -ErrorAction SilentlyContinue
       git config core.filemode false
       git config core.autocrlf false

4. Confirm `git status` is now sane - it should NOT list all 65 files as modified.
   If it does, stop and show me the output. Then:
       git add -A
       git commit -m "cleanup: remove device-bridge leftovers"
   (skip the commit if there is nothing staged)

5. Create the GitHub repo. Name it `vitals`, PRIVATE.
   If the GitHub CLI is available:
       gh repo create vitals --private --source=. --remote=origin --push
   If `gh` is not installed, install it first:
       winget install -e --id GitHub.cli
       gh auth login
   and then run the create command above.

6. If `gh` will not work at all, tell me and instead print the exact commands for
   me to run after I make an EMPTY repo at https://github.com/new (no README,
   no .gitignore, no license):
       git remote add origin https://github.com/<my-username>/vitals.git
       git branch -M main
       git push -u origin main

7. When it is pushed, run `pytest tests -q` (set $env:PYTHONPATH="src" first) and
   confirm all 111 tests pass. Then give me the repo URL.

Do not force-push. Do not rewrite history. Do not change .gitignore.
```

---

## After it works

Add Joaquin and Cruz as collaborators: repo page → Settings → Collaborators.

To make the repo public later (for judges to browse), either flip
`$Visibility` at the top of `push_to_github.ps1`, or:

```powershell
gh repo edit --visibility public --accept-visibility-change-consequences
```
