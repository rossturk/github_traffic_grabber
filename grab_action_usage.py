#!/usr/bin/env python3
import requests
import json
import os
from datetime import datetime, timedelta
import sys
import argparse
import psycopg2
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager
import time
import base64
import re

# GitHub API configuration
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")

# PostgreSQL configuration
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = os.environ.get("DB_PORT", "15432")
DB_NAME = "github_traffic_data"
DB_USER = os.environ.get("DB_USER", "pguser")
DB_PASS = os.environ.get("DB_PASS", "pgpass")

@contextmanager
def get_db():
    """Context manager for database connections"""
    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASS,
        cursor_factory=RealDictCursor
    )
    try:
        yield conn
    finally:
        conn.close()

def init_database():
    """Initialize database schema for GitHub action tracking"""
    with get_db() as conn:
        cur = conn.cursor()
        
        # Create table for tracking repositories using GitHub actions
        cur.execute("""
            CREATE TABLE IF NOT EXISTS action_usage (
                id SERIAL PRIMARY KEY,
                action_name TEXT NOT NULL,  -- e.g., 'flox/install-flox-action', 'actions/checkout'
                repo_full_name TEXT NOT NULL,
                repo_owner TEXT NOT NULL,
                repo_name TEXT NOT NULL,
                action_version TEXT,
                workflow_file TEXT,
                workflow_path TEXT,
                first_seen DATE NOT NULL,
                last_seen DATE NOT NULL,
                is_active BOOLEAN DEFAULT TRUE,
                stars INTEGER DEFAULT 0,
                is_fork BOOLEAN DEFAULT FALSE,
                is_private BOOLEAN DEFAULT FALSE,
                default_branch TEXT,
                language TEXT,
                description TEXT,
                created_at TIMESTAMP,
                updated_at TIMESTAMP,
                UNIQUE(action_name, repo_full_name, workflow_path)
            );
            
            CREATE INDEX IF NOT EXISTS idx_action_usage_action 
                ON action_usage(action_name);
            CREATE INDEX IF NOT EXISTS idx_action_usage_repo 
                ON action_usage(repo_full_name);
            CREATE INDEX IF NOT EXISTS idx_action_usage_active 
                ON action_usage(is_active);
            CREATE INDEX IF NOT EXISTS idx_action_usage_dates 
                ON action_usage(first_seen, last_seen);
        """)
        
        # Create history table for tracking changes
        cur.execute("""
            CREATE TABLE IF NOT EXISTS action_usage_history (
                id SERIAL PRIMARY KEY,
                action_name TEXT NOT NULL,
                date DATE NOT NULL,
                total_repos INTEGER NOT NULL,
                new_repos INTEGER NOT NULL,
                removed_repos INTEGER NOT NULL,
                active_repos INTEGER NOT NULL,
                timestamp TIMESTAMP NOT NULL
            );
            
            CREATE INDEX IF NOT EXISTS idx_action_usage_history_action 
                ON action_usage_history(action_name);
            CREATE INDEX IF NOT EXISTS idx_action_usage_history_date 
                ON action_usage_history(date);
        """)
        
        conn.commit()
        cur.close()

def search_github_code(query, page=1, per_page=100):
    """Search GitHub code for specific content"""
    if not GITHUB_TOKEN:
        print("Error: GITHUB_TOKEN environment variable not set")
        sys.exit(1)
    
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    params = {
        "q": query,
        "per_page": per_page,
        "page": page,
        "sort": "indexed"  # Get most recently indexed first
    }
    
    url = "https://api.github.com/search/code"
    
    try:
        response = requests.get(url, headers=headers, params=params)
        
        # Handle rate limiting
        if response.status_code == 403:
            if 'X-RateLimit-Remaining' in response.headers and response.headers['X-RateLimit-Remaining'] == '0':
                reset_time = int(response.headers.get('X-RateLimit-Reset', 0))
                wait_time = reset_time - int(time.time()) + 1
                if wait_time > 0:
                    print(f"Rate limit hit. Waiting {wait_time} seconds...")
                    time.sleep(wait_time)
                    return search_github_code(query, page, per_page)
            else:
                print("Access denied. Make sure your token has the necessary scopes.")
                sys.exit(1)
        
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error searching GitHub: {e}")
        return None

def get_file_content(repo_full_name, file_path):
    """Get the content of a file from GitHub API"""
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    url = f"https://api.github.com/repos/{repo_full_name}/contents/{file_path}"
    
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            data = response.json()
            if 'content' in data:
                return base64.b64decode(data['content']).decode('utf-8')
        return None
    except:
        return None

def extract_action_version(content, action_name):
    """Extract version from workflow content for a specific action"""
    if not content:
        return None
    
    # Pattern to match: uses: action_name@version
    pattern = rf'uses:\s*["\']?{re.escape(action_name)}@([^"\'\s]+)'
    matches = re.findall(pattern, content)
    return matches[0] if matches else None

def get_repo_details(repo_full_name):
    """Get additional repository details"""
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    url = f"https://api.github.com/repos/{repo_full_name}"
    
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return response.json()
        return None
    except:
        return None

def find_action_users(action_name):
    """Find all repositories using a specific GitHub action"""
    print(f"Searching for repositories using action: {action_name}")
    
    # Generate search queries for the action
    queries = [
        f'uses: "{action_name}@" path:.github/workflows',
        f'uses: {action_name} path:.github/workflows',
        f'uses: "{action_name}" path:.github/workflows'
    ]
    
    all_results = {}
    
    for query in queries:
        print(f"  Query: {query}")
        page = 1
        
        while True:
            results = search_github_code(query, page=page)
            if not results or 'items' not in results:
                break
            
            if not results['items']:
                break
            
            for item in results['items']:
                repo_full_name = item['repository']['full_name']
                workflow_path = item['path']
                
                # Store unique combination of repo and workflow
                key = f"{repo_full_name}:{workflow_path}"
                if key not in all_results:
                    all_results[key] = {
                        'action_name': action_name,
                        'repo_full_name': repo_full_name,
                        'repo_owner': item['repository']['owner']['login'],
                        'repo_name': item['repository']['name'],
                        'workflow_path': workflow_path,
                        'workflow_file': os.path.basename(workflow_path)
                    }
            
            # Check if there are more pages
            if len(results['items']) < 100:  # Default per_page
                break
            
            page += 1
            # Be nice to the API
            time.sleep(1)
    
    return list(all_results.values())

def update_repository_data(conn, repos_data, action_name):
    """Update repository data in the database"""
    cur = conn.cursor()
    today = datetime.now().date()
    timestamp = datetime.now()
    
    # Track statistics
    new_repos = 0
    updated_repos = 0
    
    # Get all currently active repos for this action
    cur.execute("""
        SELECT repo_full_name, workflow_path 
        FROM action_usage 
        WHERE action_name = %s AND is_active = TRUE
    """, (action_name,))
    currently_active = {(row['repo_full_name'], row['workflow_path']) for row in cur.fetchall()}
    
    # Process found repositories
    found_repos = set()
    for repo in repos_data:
        repo_full_name = repo['repo_full_name']
        workflow_path = repo['workflow_path']
        found_repos.add((repo_full_name, workflow_path))
        
        # Get action version from workflow file
        content = get_file_content(repo_full_name, workflow_path)
        version = extract_action_version(content, action_name)
        
        # Get additional repo details
        repo_details = get_repo_details(repo_full_name)
        
        # Check if repo exists
        cur.execute("""
            SELECT id, first_seen FROM action_usage 
            WHERE action_name = %s AND repo_full_name = %s AND workflow_path = %s
        """, (action_name, repo_full_name, workflow_path))
        existing = cur.fetchone()
        
        if existing:
            # Update existing repo
            cur.execute("""
                UPDATE action_usage 
                SET last_seen = %s, 
                    is_active = TRUE,
                    action_version = %s,
                    stars = %s,
                    is_fork = %s,
                    is_private = %s,
                    default_branch = %s,
                    language = %s,
                    description = %s,
                    updated_at = %s
                WHERE action_name = %s AND repo_full_name = %s AND workflow_path = %s
            """, (
                today, version,
                repo_details.get('stargazers_count', 0) if repo_details else 0,
                repo_details.get('fork', False) if repo_details else False,
                repo_details.get('private', False) if repo_details else False,
                repo_details.get('default_branch') if repo_details else None,
                repo_details.get('language') if repo_details else None,
                repo_details.get('description', '')[:500] if repo_details and repo_details.get('description') else None,
                timestamp, action_name, repo_full_name, workflow_path
            ))
            updated_repos += 1
        else:
            # Insert new repo
            cur.execute("""
                INSERT INTO action_usage (
                    action_name, repo_full_name, repo_owner, repo_name, action_version,
                    workflow_file, workflow_path, first_seen, last_seen,
                    is_active, stars, is_fork, is_private, default_branch,
                    language, description, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                action_name, repo_full_name, repo['repo_owner'], repo['repo_name'],
                version, repo['workflow_file'], workflow_path, today, today, True,
                repo_details.get('stargazers_count', 0) if repo_details else 0,
                repo_details.get('fork', False) if repo_details else False,
                repo_details.get('private', False) if repo_details else False,
                repo_details.get('default_branch') if repo_details else None,
                repo_details.get('language') if repo_details else None,
                (repo_details.get('description') or '')[:500] if repo_details else None,
                timestamp, timestamp
            ))
            new_repos += 1
        
        # Be nice to the API when fetching details
        if repo_details:
            time.sleep(0.5)
    
    # Mark repos as inactive if they weren't found today
    removed_repos = currently_active - found_repos
    for repo_full_name, workflow_path in removed_repos:
        cur.execute("""
            UPDATE action_usage 
            SET is_active = FALSE, last_seen = %s 
            WHERE action_name = %s AND repo_full_name = %s AND workflow_path = %s
        """, (today, action_name, repo_full_name, workflow_path))
    
    # Update history
    cur.execute("""
        INSERT INTO action_usage_history (action_name, date, total_repos, new_repos, removed_repos, active_repos, timestamp)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (
        action_name, today, len(found_repos), new_repos, len(removed_repos), len(found_repos), timestamp
    ))
    
    cur.close()
    
    return {
        'total': len(found_repos),
        'new': new_repos,
        'updated': updated_repos,
        'removed': len(removed_repos)
    }

def display_summary(conn, action_name=None):
    """Display summary of action usage"""
    cur = conn.cursor()
    
    # Build WHERE clause
    where_clause = ""
    params = []
    if action_name:
        where_clause = "WHERE action_name = %s"
        params = [action_name]
    
    # Get current stats
    cur.execute(f"""
        SELECT action_name,
               COUNT(*) as total, 
               COUNT(CASE WHEN is_active THEN 1 END) as active,
               COUNT(CASE WHEN NOT is_active THEN 1 END) as inactive
        FROM action_usage
        {where_clause}
        GROUP BY action_name
        ORDER BY active DESC, action_name
    """, params)
    stats = cur.fetchall()
    
    print(f"\nGitHub Action Usage Summary:")
    print("=" * 80)
    
    for stat in stats:
        print(f"\nAction: {stat['action_name']}")
        print(f"  Total repositories tracked: {stat['total']}")
        print(f"  Currently active: {stat['active']}")
        print(f"  No longer using: {stat['inactive']}")
        
        # Get version distribution
        cur.execute("""
            SELECT action_version, COUNT(*) as count 
            FROM action_usage 
            WHERE action_name = %s AND is_active = TRUE AND action_version IS NOT NULL
            GROUP BY action_version 
            ORDER BY count DESC
        """, (stat['action_name'],))
        versions = cur.fetchall()
        
        if versions:
            print(f"  Versions in use:")
            for v in versions:
                print(f"    {v['action_version']}: {v['count']} repos")
        
        # Get top repos by stars
        cur.execute("""
            SELECT repo_full_name, stars, language 
            FROM action_usage 
            WHERE action_name = %s AND is_active = TRUE 
            ORDER BY stars DESC 
            LIMIT 5
        """, (stat['action_name'],))
        top_repos = cur.fetchall()
        
        if top_repos:
            print(f"  Top repositories by stars:")
            for repo in top_repos:
                lang = f" ({repo['language']})" if repo['language'] else ""
                print(f"    {repo['repo_full_name']}: {repo['stars']} stars{lang}")
    
    cur.close()

def export_report(conn, output_file, action_name=None):
    """Export detailed report of all repositories"""
    cur = conn.cursor()
    
    # Build WHERE clause
    where_clause = ""
    params = []
    if action_name:
        where_clause = "WHERE action_name = %s"
        params = [action_name]
    
    # Get all repositories
    cur.execute(f"""
        SELECT * FROM action_usage 
        {where_clause}
        ORDER BY action_name, is_active DESC, stars DESC
    """, params)
    repos = cur.fetchall()
    
    with open(output_file, 'w') as f:
        f.write("GitHub Action Usage Report\n")
        f.write(f"Generated: {datetime.now()}\n")
        f.write("=" * 80 + "\n\n")
        
        # Group by action
        current_action = None
        for repo in repos:
            if repo['action_name'] != current_action:
                f.write(f"\nAction: {repo['action_name']}\n")
                f.write("-" * 80 + "\n")
                current_action = repo['action_name']
            
            status = "ACTIVE" if repo['is_active'] else "INACTIVE"
            f.write(f"\n  Repository: {repo['repo_full_name']} [{status}]\n")
            f.write(f"    Workflow: {repo['workflow_path']}\n")
            f.write(f"    Version: {repo['action_version'] or 'unknown'}\n")
            f.write(f"    Stars: {repo['stars']}\n")
            f.write(f"    Language: {repo['language'] or 'unknown'}\n")
            f.write(f"    First seen: {repo['first_seen']}\n")
            f.write(f"    Last seen: {repo['last_seen']}\n")
            if repo['description']:
                f.write(f"    Description: {repo['description']}\n")
    
    cur.close()
    print(f"\nReport exported to: {output_file}")

def list_tracked_actions(conn):
    """List all currently tracked actions"""
    cur = conn.cursor()
    
    cur.execute("""
        SELECT action_name, 
               COUNT(*) as total_repos,
               COUNT(CASE WHEN is_active THEN 1 END) as active_repos,
               MAX(last_seen) as last_updated
        FROM action_usage
        GROUP BY action_name
        ORDER BY active_repos DESC, action_name
    """)
    
    actions = cur.fetchall()
    
    if actions:
        print(f"\nCurrently tracked actions:")
        print("-" * 80)
        for action in actions:
            print(f"{action['action_name']}: {action['active_repos']} active repos (last updated: {action['last_updated']})")
    else:
        print("No actions currently tracked.")
    
    cur.close()

def main():
    parser = argparse.ArgumentParser(description='Track GitHub repositories using any GitHub action')
    parser.add_argument('action', nargs='?', help='GitHub action to track (e.g., "flox/install-flox-action", "actions/checkout")')
    parser.add_argument('--update', action='store_true', help='Update repository data for the specified action')
    parser.add_argument('--summary', action='store_true', help='Show usage summary')
    parser.add_argument('--export', help='Export detailed report to file')
    parser.add_argument('--list', choices=['active', 'inactive', 'all'], help='List repositories using the action')
    parser.add_argument('--list-actions', action='store_true', help='List all tracked actions')
    
    args = parser.parse_args()
    
    if not GITHUB_TOKEN:
        print("Error: GITHUB_TOKEN environment variable not set")
        print("Please set your GitHub personal access token:")
        print("export GITHUB_TOKEN='your_token_here'")
        sys.exit(1)
    
    # Initialize database
    init_database()
    
    # List tracked actions
    if args.list_actions:
        with get_db() as conn:
            list_tracked_actions(conn)
        return
    
    # Require action name for most operations
    if not args.action and not args.summary:
        print("Error: Please specify an action to track or use --summary to see all actions")
        print("Examples:")
        print("  python3 action_tracker.py flox/install-flox-action --update")
        print("  python3 action_tracker.py actions/checkout --summary")
        print("  python3 action_tracker.py --list-actions")
        sys.exit(1)
    
    # Update data if requested
    if args.update:
        if not args.action:
            print("Error: --update requires an action name")
            sys.exit(1)
            
        print(f"Searching for repositories using action: {args.action}")
        repos = find_action_users(args.action)
        
        print(f"Found {len(repos)} workflow files using {args.action}")
        
        with get_db() as conn:
            stats = update_repository_data(conn, repos, args.action)
            conn.commit()
            
            print(f"\nUpdate complete for {args.action}:")
            print(f"  Total active: {stats['total']}")
            print(f"  New repos: {stats['new']}")
            print(f"  Updated repos: {stats['updated']}")
            print(f"  Removed repos: {stats['removed']}")
    
    # Show summary
    if args.summary:
        with get_db() as conn:
            display_summary(conn, args.action)
    
    # Export report
    if args.export:
        with get_db() as conn:
            export_report(conn, args.export, args.action)
    
    # List repositories
    if args.list:
        if not args.action:
            print("Error: --list requires an action name")
            sys.exit(1)
            
        with get_db() as conn:
            cur = conn.cursor()
            
            if args.list == 'active':
                cur.execute("""
                    SELECT repo_full_name, action_version, stars, first_seen, last_seen 
                    FROM action_usage 
                    WHERE action_name = %s AND is_active = TRUE 
                    ORDER BY stars DESC
                """, (args.action,))
            elif args.list == 'inactive':
                cur.execute("""
                    SELECT repo_full_name, first_seen, last_seen 
                    FROM action_usage 
                    WHERE action_name = %s AND is_active = FALSE 
                    ORDER BY last_seen DESC
                """, (args.action,))
            else:  # all
                cur.execute("""
                    SELECT repo_full_name, is_active, stars, first_seen, last_seen 
                    FROM action_usage 
                    WHERE action_name = %s
                    ORDER BY is_active DESC, stars DESC
                """, (args.action,))
            
            results = cur.fetchall()
            
            if results:
                print(f"\n{args.list.capitalize()} repositories using {args.action}:")
                for repo in results:
                    status = "ACTIVE" if repo.get('is_active', True) else "INACTIVE"
                    stars = f" ({repo['stars']} stars)" if 'stars' in repo else ""
                    print(f"  {repo['repo_full_name']}{stars} - {status}")
                    print(f"    First seen: {repo['first_seen']}, Last seen: {repo['last_seen']}")
            else:
                print(f"No {args.list} repositories found for {args.action}")
            
            cur.close()

if __name__ == "__main__":
    main()