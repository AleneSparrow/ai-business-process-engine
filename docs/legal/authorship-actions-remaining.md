# Authorship actions that still need Alena’s accounts

This repository can record the claim. It cannot log into GitHub, copyright.gov, a registrar, or a notary as you. Do these on your Mac, in your name. Do not back-date anything.

## 1. One legal name

Use **Alena Kulish** / **Алена Кулиш** and `alenesparrowvn@gmail.com` on GitHub, Lemon Squeezy, the future domain, and any company papers.

On your Mac, for this repo only:

```bash
git config user.name "Alena Kulish"
git config user.email "alenesparrowvn@gmail.com"
```

`.mailmap` already maps the old git names onto that identity. Do not `git rebase` or `filter-repo` the Claude/Cursor commits.

## 2. GitHub profile (you click this)

GitHub → Settings → Public profile:

- Name: `Alena Kulish`
- Bio: `Founder of Flywheel. I design the business process; neural networks are the workforce that drafts the software.`
- URL: the domain once you have it, otherwise this repository
- Social: LinkedIn when it exists

Then this repository → About (gear icon):

- Description: `Flywheel — a deterministic lead-to-sale engine. Founder-directed; AI coding assistants used as tools.`
- Website: same as profile URL
- Topics: `saas`, `business-process`, `lead-to-sale`, `ai-tools`

## 3. License and copyright files

Already in this repository: `LICENSE`, `COPYRIGHT`, `AUTHORS`, `NOTICE`, `AUTHORSHIP.md`. All rights reserved — this is not open source.

## 4. Signed tag and GitHub Release (you run this)

After this branch is on `main`, on your Mac (your GPG key, not a cloud VM key):

```bash
git checkout main
git pull
gpg --full-generate-key   # if you do not already have a key for Alena Kulish
git tag -s v0.1.0-source -m "Dated source snapshot and authorship claim, 2026-09-03. Not a product launch."
git push origin v0.1.0-source
```

Then GitHub → Releases → Draft a release from `v0.1.0-source`. Title: `v0.1.0-source — authorship snapshot`. Body: this is a dated source snapshot, not a launch. Author: Alena Kulish. Method: founder-directed implementation with AI coding assistants as tools.

An unsigned annotated tag may already exist from the working branch. Replace it with your signed tag on `main` if the two point at different commits. Prefer **your** signed tag.

## 5. Archive.org / archive.today (no account required)

Open these in your browser and wait until a snapshot URL appears:

Already captured (independent timestamp):

- https://web.archive.org/web/20260903051913/https://github.com/AleneSparrow/ai-business-process-engine

After this branch is on `main`, save again so `AUTHORSHIP.md` is in the snapshot:

- https://web.archive.org/save/https://github.com/AleneSparrow/ai-business-process-engine
- https://web.archive.org/save/https://github.com/AleneSparrow/ai-business-process-engine/blob/main/AUTHORSHIP.md
- https://archive.ph/?run=1&url=https://github.com/AleneSparrow/ai-business-process-engine

Repeat for the live product URL and your LinkedIn when they exist. Save the resulting snapshot URLs in a private folder.

## 6. Notary

Print `docs/legal/inventorship-declaration-for-notary.md`. Sign the English block. Notary date = the day you sign. Scan the sealed original to private storage. Do not commit the scan here.

## 7. U.S. Copyright Office

Follow `docs/legal/us-copyright-registration.md`. Create the copyright.gov account yourself. Run `bash scripts/export_copyright_deposit.sh` for the upload zip.

## 8. Domain

Register **in your name** (or in the Vietnam company you already control — not a friend’s account, not a privacy proxy you cannot prove). See the shortlist in `docs/legal/entity-jurisdiction-comparison.md`. Turn on registry lock and keep the invoice PDF.

## 9. Keep personal legal strategy off this public repo

Copyright, AUTHORS, and LICENSE belong here. Visa plans, passport scans, notary PDFs, and payment receipts do not.
