// docker-bake.hcl — netcup-api-filter release image build.
// =============================================================================
// Phase 1 of naf's cmru adoption (nyxloom-trove/CMRU-RELEASE-PLAN-2026-07-21.md):
// one target, "py311" and "py314" — the self-hosting containers, grouped as "release".
//
// This file is used by BOTH tools, unmodified:
//   ciu  (local dev/inspect): docker buildx bake -f docker-bake.hcl release --load
//   cmru (publish to ghcr):   docker buildx bake -f docker-bake.hcl release --push
// cmru's built-in OCI handler (SPEC S14, cmru/handlers.py cmd_oci_image_push)
// sets REGISTRY / GITHUB_USERNAME / GITHUB_PUSH_PAT from cmru.toml's [targets]/
// [github] and runs `docker login` before invoking bake --push — mirrors
// modern-debian-tools-python-debug's docker-bake.hcl variable naming so that
// wiring works unmodified.
// =============================================================================

// Registry to push to. Empty (the default) keeps local `--load` builds
// portable; cmru sets this from [targets].registry (S11) when publishing.
variable "REGISTRY" {
  default = ""
}

// GHCR owner/namespace. cmru sets this from [github].owner when publishing.
variable "GITHUB_USERNAME" {
  default = ""
}

// Local-only image namespace (used when REGISTRY is empty), matching
// ciu.global.defaults.toml.j2's [deploy.registry].namespace for this repo.
variable "NAMESPACE" {
  default = "netcup-api-filter"
}

// Floating tag. cmru's oci-image profile does not git-tag (S-REL.4 — OCI
// images aren't semver-tagged), so this stays "latest" unless a caller (e.g.
// a future CI step) overrides it with a build-date or digest-derived value.
variable "IMAGE_TAG" {
  default = "latest"
}

// NOTE: no HCL `variable` named PYTHON_VERSION — deliberately. `docker buildx bake`
// auto-overrides an HCL variable from a same-named shell env var, and the devcontainer
// shell may export one; the interpreter is fixed per target via `args` below instead.

// Per-interpreter tags; the floating IMAGE_TAG (latest) goes on py314 only, so two
// targets never fight over one tag.
function "release_tags" {
  params = [name, py, floating]
  result = concat(
    REGISTRY != "" ? ["${REGISTRY}/${GITHUB_USERNAME}/${name}:${py}"] : ["${NAMESPACE}/${name}:${py}"],
    floating ? (REGISTRY != "" ? ["${REGISTRY}/${GITHUB_USERNAME}/${name}:${IMAGE_TAG}"] : ["${NAMESPACE}/${name}:${IMAGE_TAG}"]) : []
  )
}

// The self-hosting release images — see Dockerfile.release. One per shipped
// interpreter: py311 mirrors the Passenger runtime, py314 is the default.
# Exact age-windowed patch tags from versions/oci-images.json (cmru targets
# oci.python311 / oci.python314); keep them equal to the corresponding
# `build.python_base_image*` facts.
target "py311" {
  dockerfile = "Dockerfile.release"
  context    = "."
  args       = { PYTHON_VERSION = "3.11", PYTHON_BASE_IMAGE = "python:3.11.17-slim-trixie" }
  tags       = release_tags("app", "py311", false)
}

target "py314" {
  dockerfile = "Dockerfile.release"
  context    = "."
  args       = { PYTHON_VERSION = "3.14", PYTHON_BASE_IMAGE = "python:3.14.9-slim-trixie" }
  tags       = release_tags("app", "py314", true)
}

// What cmru pushes (cmru.toml [project.naf.oci].target = "release").
group "release" {
  targets = ["py311", "py314"]
}

group "default" {
  targets = ["release"]
}
