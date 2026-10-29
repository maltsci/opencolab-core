# TODOS

## Adaptive Training

### Evaluate built-in offline model distribution

**What:** Evaluate whether OpenColab should package, download, verify, and manage a supported offline model instead of requiring administrators to deploy an OpenAI-compatible endpoint.

**Why:** A built-in path could reduce onboarding friction if the Training Foundation Pilot shows that administrator-managed model deployment materially blocks adoption.

**Context:** Adaptive Training v1 deliberately supports an administrator-deployed local or controlled-LAN OpenAI-compatible endpoint and does not distribute model weights. Revisit this only with Pilot evidence. The evaluation must cover model licensing, artifact provenance and checksum verification, image and download size, resumable downloads, CPU/GPU and memory detection, air-gapped installation media, model upgrades and rollback, hardware-specific performance profiles, and long-term support ownership. Benefits include a more predictable offline setup and a clearer supported baseline. Costs include substantial supply-chain, licensing, packaging, hardware-compatibility, storage, and operations scope. Start from the approved `OfflineModelHardwareProfile` contract and compare adoption/support data for administrator-managed endpoints before proposing implementation.

**Effort:** XL
**Priority:** P3
**Depends on:** Training Foundation Pilot completion and evidence that administrator-managed local model deployment is a material adoption blocker

### Evaluate tamper-evident audit for regulated training

**What:** Evaluate a legally defensible, administrator-resistant audit architecture for Training facts if OpenColab enters regulated, statutory, or externally certified training scenarios.

**Why:** The current append-only domain model protects normal application paths but does not detect or prevent direct database-administrator tampering and must not be represented as legal-grade evidence.

**Context:** The Training Foundation Pilot is an internal onboarding tool, not an examination, statutory certification, or compliance-record system. A future evaluation should begin only after a documented product or regulatory requirement exists. It must cover canonical event serialization, per-aggregate or global hash chains, digital signatures, trusted timestamps, key generation and rotation, hardware-backed key custody, separation of duties, independent/WORM storage, verification and export tooling, backup/restore continuity, redaction and privacy-retention conflicts, incident response, jurisdiction-specific evidentiary requirements, external security review, and operational ownership. Benefits include detectable tampering and stronger third-party assurance. Costs include significant cryptography, key-management, disaster-recovery, compliance, and long-term operations complexity.

**Effort:** XL
**Priority:** P4
**Depends on:** A documented regulated or external-certification use case, legal/compliance review, and an approved threat model

## Completed
