# Schedule

Every scheduled GitHub Actions job in this repo. Times are Central (America/Chicago): each
`schedule:` entry carries `timezone: America/Chicago`, which GitHub Actions honours, so the clock
change in March and November no longer moves a job. Rebalanced 1 Nov 2026 (owner-approved weekly
schedule); see the notes below for what moved.

| Job | Workflow | When | Cron |
|---|---|---|---|
| Authority Network Post-Publish Distribution | `authority-post-publish-distribution.yml` | every day 10:37 CT | `37 10 * * *` |
| Authority Network V4.2 Autopilot + Social Auto-Post | `authority-v4-autopilot.yml` | every day 09:22 CT | `22 9 * * *` |
| Entity backlink watch | `entity-backlink-watch.yml` | Sun 08:30 CT | `30 8 * * 0` |
| Journalist Query Scan | `journalist-query-scan.yml` | Mon–Fri 07:00 CT | `0 7 * * 1-5` |
| Journalist Query Scan | `journalist-query-scan.yml` | Mon–Fri 13:15 CT | `15 13 * * 1-5` |
| Post-Deploy Live Check | `post-deploy-live-check.yml` | every day 11:41 CT | `41 11 * * *` |
| Bounded Self-Healing | `self-heal.yml` | Wed 11:34 CT | `34 11 * * 3` |
| Social Auto-Post Only | `social-autopost.yml` | every day 08:23 CT | `23 8 * * *` |
| Social Auto-Post Only | `social-autopost.yml` | every day 11:17 CT | `17 11 * * *` |
| Social Auto-Post Only | `social-autopost.yml` | every day 14:41 CT | `41 14 * * *` |
| Social Auto-Post Only | `social-autopost.yml` | every day 17:09 CT | `9 17 * * *` |
| USCIS Form and Fee Changelog | `uscis-changelog.yml` | Tue 08:11 CT | `11 8 * * 2` |

## Weekly windows

- **Saturday 04:00–08:00 CT is the weekly-upkeep window for every Spry Labs side business**
  (owner ruling, 1 Nov 2026): weekly maintenance, refresh and metrics jobs run there, staggered
  at least 15 minutes apart, never two in the same slot. Publishing, link checks and
  self-healing are not upkeep and keep their own days.

## Notes
- Nothing moved day on 1 Nov 2026; every job keeps the Central time it ran at all summer, now pinned.
