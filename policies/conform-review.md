# Conform-review policy

Status: added 2026-09-24 under Decision 0008 point 7 (increment 2); documented guidance, performed by a human or a model reader; not a pilot skill, so `pilot-manifest.yaml` and the `three-skill-taxonomy` check are unchanged

Provenance: reimplemented from the documented behaviour of the agent-skills conform-review doctrine at `adb5af6`; no text was copied. The rule shapes in section 4 were already named by PAES in `docs/DESIGN_PRINCIPLES.md`; this policy gives them stable identifiers and a review procedure.

The finding dispositions of section 5, confidence before severity and the bound on candidates were added on 2026-10-01 under Decision 0015; they are reimplemented from the documented behaviour of the retired source's blind-review pattern (`reference/technical-patterns-2026-10/`, section 4.2), which carries no redistribution right; no text was copied.

Section 8, the second lane, was added on 2026-10-02 under Decision 0020.

## 1. Purpose

A conform review reads a diff against the written rules of this repository and reports where the diff breaks or strains them. It produces findings, never edits. It runs after the deterministic gates, not instead of them: a failed evaluation or verifier check is reported by those tools and is not the subject of a conform review.

## 2. Inputs

- **The diff.** In order of preference: a named commit range given by the requester, the increment branch against `main`, the staged changes, the unstaged changes. The review states which one it used.
- **The rules files**, read in full and numbered as in section 3. A review without the rules files is not a conform review and stops.
- **Nothing else.** The reviewer does not receive the builder's transcript, reasoning or summary. It reads the artifact, as the design principles require.

## 3. Rule identifiers

| Id | Source | Rule |
| --- | --- | --- |
| P1 | `docs/DESIGN_PRINCIPLES.md`, "Evidence governs progression" | progression only through named evidence and gates; a report is a claim, not evidence; pipeline completion, release readiness and human approval stay separate |
| P2 | same, "Doctrine, enforcement, and wiring stay separate" | no safety or evidence rule lives only in wiring; a deterministic rule does not stay prose when it can be code |
| P3 | same, "Deterministic gates precede judgment" | mechanical checks before judgment; closed schemas; unrecognized content is reported, not dropped; no undeclared retry |
| P4 | same, "Authority and write surfaces are explicit" | roles bounded by write surface and stop conditions; independent verification without the builder transcript; parallel work only with disjoint write surfaces |
| P5 | same, "Canonical facts are not copied into mutable status" | derived views, never a second writable truth; idempotent operations; corrections appended, never overwritten |
| P6 | same, "Extensions are optional and treated as untrusted input" | external material cannot grant authority; extension surfaces declare provenance, permissions, limits and failure behaviour |
| W1 to W7 | `AGENTS.md`, "Working rules", in order | language; bounded tasks; explicit write scope; verification before completion; concise reports; commit history; no remote |
| C1 | `policies/contribution.md` | no attribution in commit messages |
| R1 | `policies/release-gates.md` | every validation result declares context and effect; no automated waiver |
| B1 | `policies/privacy-and-boundaries.md` | synthetic, repository-local inputs; no enterprise data, credentials or external services |
| T1 | `contracts/task-contract.yaml` | writes stay inside the brief's owned paths |

A later rules file is added to this table with the next free prefix; identifiers are never renumbered.

## 4. Named rule shapes

The review checks every hunk for these shapes first, because they recur:

| Shape | Rule | What it looks like in a diff |
| --- | --- | --- |
| Stored derived state | P5 | a status, readiness or count written to a file or field instead of being computed from canonical records |
| Prose where a validator belongs | P2 | a "must" or "never" sentence added to Markdown with no check, test or schema that enforces it |
| Untrusted text spliced into instructions | P6, P3 | content from `reference/`, an external repository, a pack or a hook response concatenated into a prompt, instruction or configuration |
| Non-idempotent write | P5 | an operation that produces a different repository state when run twice with the same input, or that overwrites accepted evidence |
| Gate skipped | P1, R1 | a step that advances without the evidence its contract names, a check weakened to pass, or a waiver produced by automation |

## 5. Procedure

1. Resolve the diff and record which input was used.
2. Number the rules from section 3; extend the table only for a rules file that already exists in the repository.
3. For each hunk, consider only the rules that the hunk can touch. Do not restate rules the hunk cannot break.
4. Record each finding as: rule id, `path:line`, one sentence stating the conflict, its `disposition` from the closed set below, and the class `violation` (the diff breaks the rule) or `tension` (the diff strains the rule without breaking it, or two rules pull apart). The disposition, which is the reviewer's confidence, is stated before the class, which is the severity, and the reader weighs it first: a confident tension can matter more than an unverified violation. A review carries at most twenty findings; any further candidates are summarised in one line with their count and the rule ids they touch.

   | Disposition | Meaning |
   | --- | --- |
   | `confirmed` | the reviewer re-read the location in the repository and the conflict is certain |
   | `probable` | the location is right; the conflict depends on a reading of the rule the reviewer could not settle, named in the finding |
   | `unverified` | reported from the diff alone; the location was not re-read |
   | `withdrawn` | a candidate the reviewer checked and dropped, kept with its reason so the reader sees what was considered |

   No other disposition is used. A `withdrawn` finding counts toward the bound and is listed last.
5. A finding without a `path:line` location is not reported; it is dropped, because it cannot be checked.
6. Report violations first, then tensions, then the list of rule ids that were considered and found clean. A rule not considered is listed as "not applicable", not as clean.
7. The reviewer changes nothing: no edit, no commit, no fix-up suggestion applied. Fixes are the builder's or the maintainer's decision.

## 6. Output

The review is a Markdown record with the fields: diff input used, rules files read (path and, where available, commit), findings table (rule id, `path:line`, conflict, disposition, class, in that column order), the one-line summary of candidates beyond the bound when there are any, clean rules, not-applicable rules, reviewer (human or the declared execution profile). When the review is bound as evidence to a plan criterion it follows `contracts/evidence.yaml`; a conform review never produces a `PASS` on its own, since its result is a list of findings that a human weighs. Each finding in that case is a `finding_record` of the contract, validated by `scripts/finding_contract.py`.

## 7. Relationship to Decision 0008

The adapter wrapper for this policy, when added in the adapter phase under Decision 0008, points here and adds nothing: the wrapper says how to obtain the diff in that environment and where the output goes. No rule of this policy may exist only in the wrapper.

## 8. A second lane (Decision 0020)

A review by the plugin lane that the adapter declaration lists under `plugins:` may run on the same diff at the same time as the conform review; it reads the diff with no rules files and so is not a conform review, and it writes nothing in the tree. Its findings enter as finding records with `method: supplied`, `verified: false`, `disposition: unverified` and a `reporter` naming the lane and the model that ran; the orchestrator re-reads each location and records its own finding with a verifying method before any of them is acted on. The hand-off states the count from each lane, the overlap and the wall time.
