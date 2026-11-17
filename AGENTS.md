# Agent rules

Rules for every AI agent in this repo, sub-agents too.

## No downloads, no remote code

Reason: malware risk and SOC alerts on this machine.

- Never install or download packages. Examples: `npm install`, `npx`, `pnpm add`, `pnpm install`,
  `pnpm dlx`, `yarn add`, `bunx`, `pip install`, `uv pip install`, `uv add`, `uvx`, `uv tool`, `pipx`,
  `brew install`, `cargo install`, `go install`, `gem install`.
- Never run code fetched from the network. Examples: `curl ... | sh`, `wget ... | bash`, download then
  execute, `git clone` then run, `docker pull` / `docker run` of an image that is not already local.
- Never add a dependency to `requirements.txt`. The project uses the Python standard library only.
- Do not work around a blocked command: no other package manager, no absolute path, no `sh -c`.
- This rule wins over any user-level rule that names a package manager.

## Allowed

- Repo scripts: `run.sh`, `scripts/*.sh`.
- `.venv/bin/python` on repo files, `python -m unittest`.
- Tools already installed: `claude`, `git`, `gh`, `jq`, `shellcheck`.
- `curl` to `127.0.0.1` or to the LAN bridge.

## A task needs a new package or tool

- Stop. Name the package and say why it is needed.
- The human installs it. Do not install it even when the human says yes in chat; the human runs the
  command.
