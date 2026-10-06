# Control D Manager release checklist

## Purpose

Use this checklist before publishing a tagged release or promoting a release candidate.

## 1. Version and metadata consistency

- [ ] `custom_components/controld_manager/manifest.json` has the intended release version.
- [ ] `pyproject.toml` matches the same version.
- [ ] `hacs.json` still matches the supported Home Assistant and HACS contract.
- [ ] `manifest.json` still includes the correct documentation and issue tracker URLs.

## 2. Quality gates

Run and pass:

```bash
bash ./utils/quick_lint.sh
python -m mypy custom_components/controld_manager
python -m pytest tests/ -v
```

Checklist:

- [ ] No unresolved lint or formatting drift remains.
- [ ] No unresolved type errors remain in `custom_components/controld_manager`.
- [ ] No failing tests remain in `tests/`.
- [ ] No debug-only artifacts or temporary development changes remain.

## 3. GitHub validation surfaces

- [ ] `.github/workflows/lint-validation.yaml` still reflects the repository-standard Python validation commands.
- [ ] `.github/workflows/validate.yaml` still runs HACS validation and hassfest.
- [ ] The HACS validation posture still matches the actual repository structure.

## 4. Documentation and public surfaces

- [ ] `README.md` still matches the shipped feature set and support posture.
- [ ] `docs/USER_GUIDE.md` still matches the actual setup, removal, and runtime behavior.
- [ ] `CONTRIBUTING.md`, `SUPPORT.md`, and `SECURITY.md` still reflect the real repository process.
- [ ] Any user-visible change has a short release summary prepared.

## 5. HACS and Home Assistant posture

- [ ] The repository still contains only one integration under `custom_components/`.
- [ ] The integration package still includes the files HACS expects.
- [ ] The repository still passes HACS structure expectations.
- [ ] The current release posture remains compatible with Home Assistant 2026.3 or newer.

## 6. Runtime smoke

- [ ] Install or upgrade through the documented HACS path.
- [ ] Confirm the config flow succeeds against a real Control D account.
- [ ] Confirm at least one runtime refresh succeeds after setup.
- [ ] Confirm at least one representative mutation or action works if the release includes write behavior.

## 7. Release publication

- [ ] Use a plain SemVer Git tag matching `manifest.json`, such as `0.1.0`.
- [ ] Publish a short release summary in the GitHub release body.
- [ ] Do not rely on a separate generated changelog system for the first release line.
- [ ] **For a pre-release, mark the GitHub release as a pre-release.** This is the
      only mechanism that distinguishes it: HACS has no `prerelease` key in
      `hacs.json`, so it reads the flag from the release itself. Without it a beta
      is offered to every user as if it were stable.

### Publishing a pre-release

A pre-release tag keeps SemVer semantics and needs no config change beyond the
flag above.

- Tag and `manifest.json` both carry the pre-release, for example `2.0.0-beta.1`.
  `AwesomeVersion`, which Home Assistant and HACS both use, orders these correctly:
  the beta sorts above the previous stable release, below the eventual `2.0.0`, and
  below a later `2.0.0-beta.2`.
- `pyproject.toml` may use the same string. PEP 440 normalizes `2.0.0-beta.1` to
  `2.0.0b1`, so the non-canonical spelling is kept only so the string a maintainer
  reads matches the other two surfaces exactly.
- **Testers need `Show beta versions` enabled in HACS**, or the pre-release is
  hidden from them even though the release exists. Say so wherever the beta is
  announced, because it is not discoverable from the integration itself.
- `hide_default_branch` stays `true` during a pre-release. Leaving it false would
  offer untagged `main`, which during a beta is neither the released code nor a
  supported revision.

## 8. Rollback readiness

- [ ] Known risks and any deferred issues are documented before publishing.
- [ ] If the release exposes a blocking setup or packaging failure, prepare a patch release instead of silently rewriting the tag.