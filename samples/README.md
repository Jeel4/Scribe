# Sample transcripts — SYNTHETIC DEMO DATA

Every file in this folder was **written by hand for demonstrating Scribe**.
They are not recordings or transcripts of real meetings, and the people,
companies and dates in them are invented.

| File | Format | Reference summary |
|---|---|---|
| `synthetic_platform_migration.txt` | `Name: text` turns | yes — `synthetic_platform_migration.reference.txt` (hand-written, for exercising the ROUGE code path only) |
| `synthetic_remote_control_design.txt` | AMI-style `[A] text` turns | no |
| `synthetic_weekly_standup.txt` | `Name: text` turns | no |

The reference summary was written by the same author as the transcript, so
ROUGE scores computed against it only show that the evaluation pipeline
works. **They are not evidence of summarisation quality.** For a real
evaluation, import AMI meetings with `backend/scripts/import_ami.py`.

Load them from the app (Dashboard → "Load a synthetic sample") or upload
the .txt files like any other transcript.
