FROM python:3.12-slim

# apply.py shells out to `git` (worktree/commit/push) and `gh` (draft PR
# creation) when AGENT_GIT_APPLY_ENABLED=1 — both must be present in the
# image or every real apply attempt fails with "command not found" even
# after auth + AGENT_GIT_REPO are correctly configured. Both stay inert
# (never invoked) while the apply path is disabled, which is the default.
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    ca-certificates \
    && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
       -o /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
       > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update && apt-get install -y --no-install-recommends gh \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# graph.py loads the system prompt one directory above the module
# (os.path.join(dirname(__file__), "..", "SYSTEM_PROMPT.md")), which
# resolves to /SYSTEM_PROMPT.md once WORKDIR is /app. The build context
# must be the kovanica-agent repo root (see compose build.context).
COPY SYSTEM_PROMPT.md /SYSTEM_PROMPT.md

COPY agent/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY agent/ .

EXPOSE 8080
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
