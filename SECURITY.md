# Security policy

Clone is an agent meant to represent its owner without being able to impersonate them. Security reports are welcome and taken seriously.

## Reporting a vulnerability

Please **do not open a public issue** for a security problem.

Report it privately through GitHub: open the repository's **Security** tab and choose **Report a vulnerability**. Include what you found, how to reproduce it, and what an attacker could do with it.

This is a personal open source project, maintained on a best-effort basis. You should get a first answer within a week. There is no bug bounty. Once a fix is available, you will be credited in the release notes if you wish.

## Supported versions

The project is pre-release. Only the latest commit on `main` is supported.

## What counts as a vulnerability

In particular:

- anything that makes the clone send, release or write to the outbox a message the owner did not approve, or that the policy forbids;
- a way for the model, a note or a contact entry to change a policy decision or a recipient's category;
- personal data from `data/` or `state/`, or a secret, ending up in an image, a log entry it should not be in, or the repository;
- a way to alter the action log that `clone log verify` does not detect, beyond the limits below;
- a container configuration that weakens the hardening described in the README (non-root user, read-only filesystem, no capabilities, no published port).

## Known limits (not vulnerabilities)

These are documented design limits, planned for later phases:

- Deleting the last entries of the action log is not detectable by the hash chain alone. `clone log verify` shows the head hash so the owner can note it; signing comes with the owner's key (ADR-008).
- Matching pending proposals against the log protects against mistakes and simple tampering, not against someone able to rewrite `state/` and recompute the chain.
- The outgoing channel is simulated: nothing is really sent yet.

Reports that show one of these limits is worse than documented are welcome.
