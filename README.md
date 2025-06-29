# GitHub Traffic Grabber

A Python script to track and store GitHub repository traffic statistics using SQLite.

## Features

- Track daily view counts and unique visitors
- Store popular content paths
- Track referring sites
- Historical data preservation
- SQLite database for efficient querying
- Idempotent operation (safe to run multiple times)

## Prerequisites

- GitHub personal access token with `repo` scope
- Flox environment (includes Python, SQLite, and requests)

## Setup

1. Create a GitHub personal access token:
   - Go to https://github.com/settings/tokens
   - Click "Generate new token (classic)"
   - Select the `repo` scope
   - Generate the token

2. Store your token in a `.token` file:
   ```bash
   echo 'your_token_here' > .token
   ```
   
   The Flox environment automatically loads the token from `.token` when activated.

3. Activate the Flox environment:
   ```bash
   flox activate
   ```

## Usage

Track a specific repository:
```bash
python3 github_traffic_grabber.py owner/repo
```

List all accessible repositories:
```bash
python3 github_traffic_grabber.py --list-repos
```

## Database Schema

The script creates an SQLite database (`github_traffic.db`) with the following tables:

- `daily_views`: Historical daily view counts
- `current_totals`: Latest cumulative totals
- `popular_paths`: Popular content paths by date
- `referrers`: Referring sites by date


## Notes

- GitHub's traffic API only provides the last 14 days of data
- The script preserves all historical data collected
- Running multiple times per day updates the current day's data