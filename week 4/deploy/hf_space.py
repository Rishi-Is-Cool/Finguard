"""
deploy/hf_space.py — create or update the FinGuard Hugging Face Docker Space.

Uploads only what the image needs (allow-list, so .env can never ship), writes
the Space's README front-matter, and prints the URL. Free CPU Spaces give
16 GB RAM, enough for the embedding + reranker models.

Prereq:  hf auth login          (a token with write access)
Usage:   python deploy/hf_space.py                       # <you>/finguard-ai
         python deploy/hf_space.py --space you/name --private
         python deploy/hf_space.py --set-secrets          # also copy GROQ_API_KEY /
                                                          # TYPESAFE_API_KEY from .env
"""
import argparse
import os
from pathlib import Path

from dotenv import dotenv_values
from huggingface_hub import HfApi

ROOT = Path(__file__).resolve().parent.parent

INCLUDE = [
    "Dockerfile", ".dockerignore",
    "backend/*.py", "backend/requirements.txt",
    "frontend/index.html", "frontend/package.json", "frontend/package-lock.json",
    "frontend/*.config.js", "frontend/src/**",
    "data/transactions.csv",
]

SPACE_README = """---
title: FinGuard AI
emoji: 🛡️
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
license: mit
short_description: Multi-agent fraud triage with an auditable review trail
---

# FinGuard AI

Upload a transaction CSV (or click **Try it with sample data**). Five agents run
rules, model screening, corrective RAG and report writing; every decision lands
in a hash-chained audit trail you can review and export.

Source and docs: {repo}
"""

SECRETS = ["GROQ_API_KEY", "TYPESAFE_API_KEY", "LANGCHAIN_API_KEY"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--space", help="owner/name (default: <you>/finguard-ai)")
    ap.add_argument("--private", action="store_true")
    ap.add_argument("--set-secrets", action="store_true",
                    help="copy API keys from week 4/.env into the Space's secrets")
    ap.add_argument("--repo-url", default="https://github.com/Rishi-Is-Cool/Finguard")
    args = ap.parse_args()

    api = HfApi()
    space = args.space or f"{api.whoami()['name']}/finguard-ai"

    api.create_repo(space, repo_type="space", space_sdk="docker", private=args.private, exist_ok=True)
    api.upload_folder(folder_path=ROOT, repo_id=space, repo_type="space",
                      allow_patterns=INCLUDE, ignore_patterns=["**/__pycache__/**"],
                      commit_message="Deploy FinGuard AI")
    api.upload_file(path_or_fileobj=SPACE_README.format(repo=args.repo_url).encode(),
                    path_in_repo="README.md", repo_id=space, repo_type="space",
                    commit_message="Space README")

    if args.set_secrets:
        env = {**dotenv_values(ROOT / ".env"), **os.environ}
        for key in SECRETS:
            if env.get(key):
                api.add_space_secret(space, key, env[key])
                print(f"  secret set: {key}")

    owner, name = space.split("/")
    print(f"\nSpace:  https://huggingface.co/spaces/{space}")
    print(f"App:    https://{owner}-{name}.hf.space".lower().replace("_", "-"))
    if not args.set_secrets:
        print("\nAdd GROQ_API_KEY (and optionally TYPESAFE_API_KEY) under Settings → "
              "Variables and secrets, or re-run with --set-secrets.")
    print("First build takes ~8-10 minutes; watch the Logs tab.")


if __name__ == "__main__":
    main()
