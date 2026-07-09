# Plan: complete the full CooperBench dataset locally as linux/amd64

## Goal
Have **all 30 task images** of the CooperBench dataset available locally on this
amd64 host, each tagged exactly as the Docker backend expects
(`akhatua/cooperbench-<slug>:task<id>`), so `cooperbench run --backend docker`
and `cooperbench eval` work end-to-end with **no arch failures and no emulation**.

## Why two strategies (pull vs rebuild)
The published images on Docker Hub (`akhatua/...`) are inconsistently multi-arch.
Checked every one of the 30 dataset task IDs against the registry:

- **16 have a native `amd64` manifest** → just **pull** (Docker selects amd64).
- **14 are `arm64`-only** → **rebuild from source** for amd64 using each task's
  local `dataset/<repo>/<task>/Dockerfile` (a true native build — you cannot
  convert arm64 binaries to amd64).

Both produce an image under the identical tag, so the local Docker backend
(`src/cooperbench/eval/backends/docker.py` → `containers.run(image=...)`) uses the
local copy and never re-pulls. Full breakdown is in `manifest.tsv`.

## Scope facts (verified)
- `dataset/` in the repo IS the full dataset: 30 task dirs == 30 `per_task`
  entries in `dataset/gold_conflict_report.json`. `cooperbench prepare` only
  mirrors the same HF repo into `./dataset`, so no extra tasks appear.
- Every task ships a complete build context (`Dockerfile`, `runner.sh`, patches).
- This local-image work helps the **Docker backend only**. Modal/GCP pull from
  the registry on their own (amd64) VMs and hit the same arm64-only gap there.

## The 14 rebuilds (action=build)
All build natively on amd64. Bases:
- 11 are `python:3.x-slim` (fast): dottxt-ai-outlines task1655/1706, dspy
  task8394/8587/8635, huggingface-datasets task3997/6252, llama-index task18813,
  pallets-click task2800, pallets-jinja task1559/1621.
- **Heavy** (give them CPU/RAM/time):
  - `openai-tiktoken:task0` — installs Rust via rustup (compiles a native ext).
  - `go-chi:task27` — `golang:1.21-alpine`.
  - `typst:task6554` — `rust:1.80-slim`, large Rust build.

## Steps
1. **Preconditions**: Docker daemon running (`docker info`); host is `x86_64`
   (confirmed); network access (builds `git clone` + `pip/cargo install`); enough
   disk (full repo clones + deps; tens of GB across all 30).
2. **(optional) Refresh dataset**: `uv run cooperbench prepare` — already present,
   safe to skip.
3. **Pull the 16 amd64 images**: `./sync_local_dataset.sh --only pull`
4. **Rebuild the 14 arm64-only images**: `./sync_local_dataset.sh --only build`
   (or do both at once with no `--only`). Each is built with
   `docker build --platform linux/amd64 -t <tag> dataset/<repo>/<task>/`.
5. **Verify**: the script asserts every resulting image is `linux/amd64` and
   prints a built/failed summary + `docker image ls 'akhatua/cooperbench-*'`.
   Per-image logs land in `scripts/local_images/logs/`.
6. **Oracle smoke-test a rebuild** (recommended, catches fresh-dep breakage —
   Dockerfiles pin the repo commit but not dependency versions):
   ```bash
   docker run --rm \
     -v "$PWD/dataset/llama_index_task/task18813:/patches" \
     akhatua/cooperbench-llama-index:task18813 \
     feature1/tests.patch feature1/feature.patch     # gold patch -> tests pass
   ```
   Or run a full oracle pass via `cooperbench eval`.
7. **(optional) Portable on-disk copy**: `./sync_local_dataset.sh --save` writes
   `docker save` tarballs to `scripts/local_images/images/` for offline reuse.

## Deliverables (in scripts/local_images/)
- `manifest.tsv` — all 30 tasks: tag, registry archs, action (pull|build), base.
- `sync_local_dataset.sh` — orchestrates pull/build, verifies arch, logs, summary.
- `logs/` — per-image pull/build logs.
- `images/` — optional `docker save` tarballs (with `--save`).

## Risks / notes
- **Unpinned deps**: a rebuild may resolve newer dependency versions than the
  original arm64 image. Usually fine (target repo commit is pinned); the oracle
  step (6) is how we confirm.
- **Tag overwrite**: building over a previously-pulled arm64 tag repoints it to
  the amd64 build locally — intended.
- **typst rebuild** is the long pole (Rust). Expect the longest single build.
- Re-running is idempotent: pulls are cached, builds reuse Docker layer cache.
