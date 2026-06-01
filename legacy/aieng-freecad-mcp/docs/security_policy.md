# Security Policy

## Core Rule

The MCP is a local execution surface and must be treated as security-sensitive.

## Prohibited Capabilities

Do not implement tools that allow:

- arbitrary shell command execution
- arbitrary Python execution
- unrestricted file reads
- unrestricted file writes
- network access by default
- hidden background execution
- silent mutation of source packages
- automatic trust in generated files

## Path Safety

All file paths must be resolved and checked.

Tools may only read or write within approved roots:

- package root
- job workspace
- explicitly configured artifact output directory

Do not follow paths that escape approved roots.

## Input Validation

Every tool must validate input against a schema.

Reject unknown or unsupported operations explicitly.

## Execution Safety

Use approved scripts or modules only.

Do not pass unsanitized values into shell commands.

Prefer subprocess argument arrays over shell strings.

## Mutation Safety

All mutating operations must:

- validate input
- operate inside a controlled workspace
- log tool versions
- log operation name
- record exit status
- record produced artifacts
- record warnings and failures
- preserve source artifact immutability
- default to `claims_advanced: false`
