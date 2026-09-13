# Setup

## One-time: the workflow token

The daily workflow commits to two repositories and must do so with a personal
access token, not the default `GITHUB_TOKEN`. Commits made with `GITHUB_TOKEN`
do not count as repository activity, and GitHub disables scheduled workflows
after 60 days without activity.

1. GitHub → Settings → Developer settings → Fine-grained personal access tokens → Generate new token.
   - Name: `cy-grocery-index collector`
   - Expiration: 1 year (put the renewal date in your calendar; an expired token stops the series silently apart from a failed-run email)
   - Repository access: *Only select repositories* → `cy-grocery-index` and `cy-grocery-index-data`
   - Permissions → Repository permissions → **Contents: Read and write**. Nothing else.
2. Store it as a repository secret on the public repo:

       gh secret set DATA_REPO_TOKEN --repo George649451/cy-grocery-index

   (paste the token when prompted; it is never written to disk).
3. Trigger the first run and watch it:

       gh workflow run collect --repo George649451/cy-grocery-index
       gh run watch --repo George649451/cy-grocery-index

## Monitoring

- GitHub emails the repository owner when a scheduled workflow fails. Keep those notifications on.
- `runs.csv` in the private data repo has one row per run with `ok`, `coverage` and `error`. A run with coverage below 0.97 writes nothing and fails.
- Check once a week for the first month that the `collect` workflow has a run for every day.

## Local run

    python3 collector/collect.py --data-dir ../cy-grocery-index-data --public-dir data --dry-run
