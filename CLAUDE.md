# GitHub Traffic Grabber - System Architecture & Data Loading Guide

## Overview
This is a GitHub traffic analytics system that fetches and stores repository traffic data using the GitHub API and PostgreSQL database.

## Core Components

### 1. github_traffic_grabber.py
Main data collection script that:
- Fetches traffic data from GitHub API (views, popular paths, referrers)
- Stores data in PostgreSQL database
- Maintains historical records

### 2. Database Schema (PostgreSQL)
- **Database**: `github_traffic_data`
- **Connection**: localhost:15432, user: pguser, pass: pgpass
- **Tables**:
  - `daily_views`: Historical daily view counts (repo, date, count, uniques, timestamp)
  - `current_totals`: Latest cumulative totals per repo
  - `popular_paths`: Popular content paths by date
  - `referrers`: Referring sites by date

### 3. Analytics Tools
- **traffic_analyzer.py**: General traffic analysis and visualization
- **referrer_analytics.py**: Specialized referrer analysis

## Authentication
- Requires GitHub personal access token with `repo` scope
- Token stored in `.token` file or via `GITHUB_TOKEN` env var
- Token is automatically loaded from `.token` when flox environment is activated

## Data Loading Process

### Step 1: GitHub API Data Fetching
The script fetches three types of data:
1. **Traffic views** (`/repos/{owner}/{repo}/traffic/views`): 14-day rolling window
2. **Popular paths** (`/repos/{owner}/{repo}/traffic/popular/paths`): Current popular content
3. **Referrers** (`/repos/{owner}/{repo}/traffic/popular/referrers`): Traffic sources

### Step 2: Data Storage
- Uses UPSERT pattern for idempotent operation
- `daily_views`: Updates existing records for the same date
- `popular_paths` & `referrers`: Deletes today's data before inserting fresh data
- Preserves all historical data beyond GitHub's 14-day window

### Step 3: Running the Grabber
```bash
# Activate flox environment with PostgreSQL
flox activate --start-services

# Fetch data for a specific repo
python3 github_traffic_grabber.py owner/repo

# List accessible repos
python3 github_traffic_grabber.py --list-repos
```

## Adding New Data Grabbers

To add new data sources to this system:

1. **Create new table** in `init_database()`:
   ```python
   CREATE TABLE IF NOT EXISTS new_data_type (
       repo TEXT NOT NULL,
       date DATE NOT NULL,
       -- your fields here
       timestamp TIMESTAMP NOT NULL
   );
   ```

2. **Add API fetch function**:
   ```python
   def get_new_data(repo):
       headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
       url = f"https://api.github.com/repos/{repo}/your-endpoint"
       response = requests.get(url, headers=headers)
       response.raise_for_status()
       return response.json()
   ```

3. **Add save function**:
   ```python
   def save_new_data(conn, repo, data):
       cur = conn.cursor()
       # Implementation similar to save_referrers() or save_popular_paths()
       cur.close()
   ```

4. **Update main()** to call new functions:
   ```python
   new_data = get_new_data(args.repo)
   save_new_data(conn, args.repo, new_data)
   ```

## GitHub API Limitations
- Traffic API only provides last 14 days of data
- Requires push access to repository
- Rate limited to 5000 requests/hour (authenticated)

## Environment Setup
- Uses Flox environment with Python, PostgreSQL, psycopg2, requests
- PostgreSQL runs on port 15432 (configured in flox.toml)
- Database is automatically created if it doesn't exist

## Best Practices
1. Run daily to maintain complete historical record
2. Multiple runs per day update current day's data
3. Use analytics scripts to visualize trends
4. Export reports for long-term analysis

## Common Operations

### View traffic for a repo
```bash
python3 traffic_analyzer.py owner/repo --days 30
```

### Analyze referrers
```bash
python3 referrer_analytics.py owner/repo --filter "reddit" --days 90
```

### Export report
```bash
python3 traffic_analyzer.py owner/repo --export report.txt
```

### Compare multiple repos
```bash
python3 traffic_analyzer.py --compare repo1 repo2 repo3
```

## Flox Action Tracker

### Overview
`flox_action_tracker.py` tracks GitHub repositories using the `flox/install-flox-action` GitHub Action. It searches GitHub for workflow files containing this action and maintains a database of usage over time.

### Features
- Searches GitHub for repositories using `flox/install-flox-action`
- Tracks when repos start/stop using the action
- Records action versions, stars, languages, and descriptions
- Maintains historical data to track adoption trends
- Identifies active vs inactive usage

### Database Tables
- **flox_action_usage**: Tracks each repo/workflow combination
  - Includes repo details, action version, first/last seen dates
  - Marks repos as active/inactive based on current usage
- **flox_action_history**: Daily summary statistics
  - Total repos, new additions, removals

### Usage
```bash
# Update the database with current usage
python3 flox_action_tracker.py --update

# Show summary statistics
python3 flox_action_tracker.py --summary

# List repositories
python3 flox_action_tracker.py --list active    # Currently using
python3 flox_action_tracker.py --list inactive  # No longer using
python3 flox_action_tracker.py --list all       # All tracked

# Export detailed report
python3 flox_action_tracker.py --export flox_usage_report.txt
```

### Running Daily
To track adoption over time, run daily with cron:
```bash
0 9 * * * cd /path/to/grab-activity && python3 flox_action_tracker.py --update
```

This provides insights into:
- How many projects adopt flox actions
- Which versions are popular
- When projects stop using it
- Top projects by stars using flox