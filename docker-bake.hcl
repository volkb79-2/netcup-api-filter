// docker-bake.hcl — netcup-api-filter release image build.
// =============================================================================
// Phase 1 of naf's cmru adoption (nyxloom-trove/CMRU-RELEASE-PLAN-2026-07-21.md):
// one target, "py314" — the py3.14 self-hosting container. Tarball/bundle
// (per-interpreter Passenger webhosting artifacts) are Phase 2, not here.
//
// This file is used by BOTH tools, unmodified:
//   ciu  (local dev/inspect): docker buildx bake -f docker-bake.hcl py314 --load
//   cmru (publish to ghcr):   docker buildx bake -f docker-bake.hcl py314 --push
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

// NOTE: no "PYTHON_VERSION" bake variable — deliberately. `docker buildx bake`
// auto-overrides an HCL `variable` from a same-named shell env var, and this
// repo's tooling/test-runner/runner.env EXPORTS "PYTHON_VERSION" for the
// unrelated gate-matrix purpose (3.9/3.11/3.14 test-runner images); the
// devcontainer shell exports it too. A same-named bake variable here would
// silently pick up whichever value happened to be in the invoking shell and
// build the wrong interpreter under the "py314" target's name. Dockerfile.release
// pins its own ARG PYTHON_VERSION=3.14 default instead, unparameterized here.

function "release_tags" {
  params = [name]
  result = REGISTRY != "" ? [
    "${REGISTRY}/${GITHUB_USERNAME}/${name}:${IMAGE_TAG}",
    "${REGISTRY}/${GITHUB_USERNAME}/${name}:py314",
  ] : [
    "${NAMESPACE}/${name}:${IMAGE_TAG}",
    "${NAMESPACE}/${name}:py314",
  ]
}

// The py3.14 self-hosting release image — see Dockerfile.release for the
// full rationale (entrypoint, layout, what config is/isn't baked in).
target "py314" {
  dockerfile = "Dockerfile.release"
  context    = "."
  tags       = release_tags("app")
}

group "default" {
  targets = ["py314"]
}
