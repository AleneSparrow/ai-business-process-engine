# U.S. Copyright Office — registration packet

This is a checklist for Alena Kulish to file **herself** at [copyright.gov](https://www.copyright.gov/). Nobody else should create that account. This is not legal advice; the Copyright Office circulars control.

The repository is already **published** (public GitHub on 11 August 2026). Register it as a published computer program, not as an unpublished work.

## Why this filing exists

A registration certificate is an independent U.S. government timestamp of the claim: author Alena Kulish, first publication 11 August 2026, title below. It also lets you sue in U.S. federal court and seek statutory damages if someone copies the engine after the effective date.

U.S. Copyright Office policy on AI: a work with AI-generated material can be registered when a human conceived it, directed the tools, and selected what was kept. Describe the AI use honestly on the form (see the “Limitation of claim” / AI material notes in current practice). Do not say the code was written entirely by hand. Do not say the work has no human author.

## Form fields to copy

Use **Standard Application**, type of work: **Literary Work** (computer programs are registered in this class).

| Field | Value |
| --- | --- |
| Title | Flywheel (AI Business Process Engine) |
| Name of author | Alena Kulish |
| Citizenship / domicile | as on your passport (do not invent a U.S. domicile) |
| Work made for hire | No |
| Year of completion | 2026 |
| Date of first publication | 11 August 2026 |
| Nation of first publication | United States (GitHub is a U.S. publication of the source) |
| Copyright claimant | Alena Kulish |
| Author’s contribution | text of computer program; compilation and selection of code |
| Limitation / AI disclosure | Computer program drafted in part by AI coding assistants under the author’s direction and review. Author conceived the work, specified behavior, and selected all deposited material. |
| Deposit | identifying material produced by `scripts/export_copyright_deposit.sh` (below), or the public GitHub URL plus a zip of the tagged snapshot |

Fee is the Office’s current Standard Application fee (check the site on the day you file; it changes). Pay with your own card.

## Deposit (what to upload)

1. On your machine, after this branch is on `main`:
   ```bash
   git checkout main
   bash scripts/export_copyright_deposit.sh
   ```
2. Upload the zip the script prints. It excludes `.env`, secrets, `.git`, and `node_modules`.
3. In the application, also write the public URL:
   `https://github.com/AleneSparrow/ai-business-process-engine`
   and the tag name you create (see `docs/legal/authorship-actions-remaining.md`).

If the Office asks for “first 25 and last 25 pages” instead of a full deposit, export a PDF of concatenated source from that zip. The script’s file list is enough to recreate that.

## After you file

Save the email confirmation, the case number, and later the certificate PDF in a private folder. Do not commit payment receipts or ID scans to this public repository.
