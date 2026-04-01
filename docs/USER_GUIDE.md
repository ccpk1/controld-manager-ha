# Control D Manager user guide

## Current state

This repository currently ships a scaffold and planning baseline only.

The production Control D integration behavior has not been implemented yet.

## What exists today

- repository structure for a Home Assistant custom integration
- validation tooling and GitHub workflows
- architecture and engineering standards
- planning notes for the future implementation

## What does not exist yet

- working account authentication
- profile selection against the live Control D API
- entities, services, diagnostics, and runtime polling behavior
- published setup instructions for a real user workflow

## Intended future scope

The expected direction is a cloud DNS management integration with profile-aware setup and a restrained set of high-value entities and services.

See `plans/in-process/CONTROLD_MANAGER_BASELINE_RECOMMENDATIONS_IN-PROCESS.md` for the current recommendations.