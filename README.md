# GitHub Traffic Grabber

A Python script to track and store GitHub repository traffic statistics using PostgreSQL.

## Features

- Track daily view counts and unique visitors
- Store popular content paths
- Track referring sites
- Historical data preservation
- PostgreSQL database for efficient querying and analysis
- Automatic database and schema creation
- Idempotent operation (safe to run multiple times)

## Prerequisites

- GitHub personal access token with `repo` scope
- Flox environment (includes Python, PostgreSQL, psycopg2, and requests)

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

3. Activate the Flox environment with PostgreSQL services:
   ```bash
   flox activate --start-services
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

The script automatically creates a PostgreSQL database (`github_traffic_data`) with the following tables:

- `daily_views`: Historical daily view counts (with DATE and TIMESTAMP types)
- `current_totals`: Latest cumulative totals
- `popular_paths`: Popular content paths by date
- `referrers`: Referring sites by date

## Database Configuration

The script uses the following default PostgreSQL connection settings:
- Host: `localhost`
- Port: `15432` (matches flox/postgres configuration)
- Database: `github_traffic_data`
- User: `pguser`
- Password: `pgpass`

These can be overridden using environment variables:
- `DB_HOST`
- `DB_PORT` 
- `DB_USER`
- `DB_PASS`


## Notes

- GitHub's traffic API only provides the last 14 days of data
- The script preserves all historical data collected
- Running multiple times per day updates the current day's data