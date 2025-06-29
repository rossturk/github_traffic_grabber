#!/usr/bin/env python3
import requests
import json
import os
from datetime import datetime
import sys
import argparse
import psycopg2
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager

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

def ensure_database_exists():
    """Ensure the database exists, create if it doesn't"""
    # Connect to default postgres database to create our database
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            database="postgres",
            user=DB_USER,
            password=DB_PASS
        )
        conn.autocommit = True
        cur = conn.cursor()
        
        # Check if database exists
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (DB_NAME,))
        if not cur.fetchone():
            cur.execute(f"CREATE DATABASE {DB_NAME}")
            print(f"Created database: {DB_NAME}")
        
        cur.close()
        conn.close()
    except psycopg2.Error as e:
        print(f"Error ensuring database exists: {e}")
        sys.exit(1)

def init_database():
    """Initialize database schema"""
    ensure_database_exists()
    
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS daily_views (
                repo TEXT NOT NULL,
                date DATE NOT NULL,
                count INTEGER NOT NULL,
                uniques INTEGER NOT NULL,
                timestamp TIMESTAMP NOT NULL,
                PRIMARY KEY (repo, date)
            );
            
            CREATE TABLE IF NOT EXISTS current_totals (
                repo TEXT PRIMARY KEY,
                count INTEGER NOT NULL,
                uniques INTEGER NOT NULL,
                timestamp TIMESTAMP NOT NULL
            );
            
            CREATE TABLE IF NOT EXISTS popular_paths (
                id SERIAL PRIMARY KEY,
                repo TEXT NOT NULL,
                date DATE NOT NULL,
                path TEXT NOT NULL,
                title TEXT,
                count INTEGER NOT NULL,
                uniques INTEGER NOT NULL,
                timestamp TIMESTAMP NOT NULL
            );
            
            CREATE TABLE IF NOT EXISTS referrers (
                id SERIAL PRIMARY KEY,
                repo TEXT NOT NULL,
                date DATE NOT NULL,
                referrer TEXT NOT NULL,
                count INTEGER NOT NULL,
                uniques INTEGER NOT NULL,
                timestamp TIMESTAMP NOT NULL
            );
            
        """)
        
        # Create indexes
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_popular_paths_repo_date 
                ON popular_paths(repo, date);
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_referrers_repo_date 
                ON referrers(repo, date);
        """)
        
        conn.commit()
        cur.close()

def get_github_views(repo):
    """Fetch view statistics from GitHub API"""
    if not GITHUB_TOKEN:
        print("Error: GITHUB_TOKEN environment variable not set")
        print("Please set your GitHub personal access token:")
        print("export GITHUB_TOKEN='your_token_here'")
        sys.exit(1)
    
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    url = f"https://api.github.com/repos/{repo}/traffic/views"
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 403:
            print(f"Error: Access denied to repository '{repo}'")
            print("\nThis usually means one of two things:")
            print("1. You don't have push access to this repository")
            print("2. Your GitHub token doesn't have the 'repo' scope")
            print("\nTo fix this, create a new token with the 'repo' scope:")
            print("  1. Go to https://github.com/settings/tokens")
            print("  2. Click 'Generate new token (classic)'")
            print("  3. Check the 'repo' checkbox")
            print("  4. Generate and export the new token:")
            print("     export GITHUB_TOKEN='your_new_token'")
            sys.exit(1)
        else:
            print(f"Error fetching data from GitHub: {e}")
            sys.exit(1)
    except requests.exceptions.RequestException as e:
        print(f"Error fetching data from GitHub: {e}")
        sys.exit(1)

def get_popular_paths(repo):
    """Fetch popular content paths from GitHub API"""
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    url = f"https://api.github.com/repos/{repo}/traffic/popular/paths"
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Warning: Could not fetch popular paths: {e}")
        return []

def get_referrers(repo):
    """Fetch referring sites from GitHub API"""
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    url = f"https://api.github.com/repos/{repo}/traffic/popular/referrers"
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Warning: Could not fetch referrers: {e}")
        return []

def list_accessible_repos():
    """List repositories the user has push access to"""
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    repos_with_push_access = []
    page = 1
    
    while True:
        url = f"https://api.github.com/user/repos?page={page}&per_page=100&affiliation=owner,collaborator,organization_member"
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        repos = response.json()
        if not repos:
            break
            
        for repo in repos:
            if repo.get('permissions', {}).get('push', False):
                repos_with_push_access.append(repo['full_name'])
        
        page += 1
    
    return repos_with_push_access

def save_daily_views(conn, repo, views_data):
    """Save daily views data to database"""
    if "views" in views_data:
        cur = conn.cursor()
        for day_data in views_data["views"]:
            date = day_data["timestamp"][:10]  # Extract YYYY-MM-DD
            cur.execute("""
                INSERT INTO daily_views (repo, date, count, uniques, timestamp)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (repo, date) DO UPDATE
                SET count = EXCLUDED.count,
                    uniques = EXCLUDED.uniques,
                    timestamp = EXCLUDED.timestamp
            """, (repo, date, day_data["count"], day_data["uniques"], day_data["timestamp"]))
        cur.close()

def save_current_totals(conn, repo, views_data):
    """Save current totals to database"""
    current_timestamp = datetime.now()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO current_totals (repo, count, uniques, timestamp)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (repo) DO UPDATE
        SET count = EXCLUDED.count,
            uniques = EXCLUDED.uniques,
            timestamp = EXCLUDED.timestamp
    """, (repo, views_data.get("count", 0), views_data.get("uniques", 0), current_timestamp))
    cur.close()

def save_popular_paths(conn, repo, popular_paths):
    """Save popular paths to database"""
    if popular_paths:
        today = datetime.now().date()
        current_timestamp = datetime.now()
        
        cur = conn.cursor()
        # Delete existing entries for today
        cur.execute("DELETE FROM popular_paths WHERE repo = %s AND date = %s", (repo, today))
        
        # Insert new entries
        for path in popular_paths:
            cur.execute("""
                INSERT INTO popular_paths (repo, date, path, title, count, uniques, timestamp)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (repo, today, path['path'], path.get('title', ''), 
                  path['count'], path['uniques'], current_timestamp))
        cur.close()

def save_referrers(conn, repo, referrers):
    """Save referrers to database"""
    if referrers:
        today = datetime.now().date()
        current_timestamp = datetime.now()
        
        cur = conn.cursor()
        # Delete existing entries for today
        cur.execute("DELETE FROM referrers WHERE repo = %s AND date = %s", (repo, today))
        
        # Insert new entries
        for referrer in referrers:
            cur.execute("""
                INSERT INTO referrers (repo, date, referrer, count, uniques, timestamp)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (repo, today, referrer['referrer'], 
                  referrer['count'], referrer['uniques'], current_timestamp))
        cur.close()

def get_historical_views(conn, repo):
    """Get historical views from database"""
    cur = conn.cursor()
    cur.execute("""
        SELECT date, count, uniques 
        FROM daily_views 
        WHERE repo = %s 
        ORDER BY date DESC 
        LIMIT 14
    """, (repo,))
    results = cur.fetchall()
    cur.close()
    return results

def main():
    """Main function to fetch and store GitHub view data"""
    parser = argparse.ArgumentParser(description='Track GitHub repository view statistics')
    parser.add_argument('repo', nargs='?', help='Repository in format owner/repo (e.g., rossturk/myrepo)')
    parser.add_argument('--list-repos', action='store_true', help='List repositories you have access to')
    
    args = parser.parse_args()
    
    if not GITHUB_TOKEN:
        print("Error: GITHUB_TOKEN environment variable not set")
        print("Please set your GitHub personal access token:")
        print("export GITHUB_TOKEN='your_token_here'")
        sys.exit(1)
    
    # Initialize database
    init_database()
    
    if args.list_repos:
        print("Fetching your accessible repositories...")
        repos = list_accessible_repos()
        if repos:
            print("\nRepositories with traffic view access:")
            for repo in repos:
                print(f"  - {repo}")
        else:
            print("No repositories found with push access.")
        return
    
    if not args.repo:
        print("Error: Please specify a repository")
        print("Usage: python3 github_traffic_grabber.py owner/repo")
        print("   or: python3 github_traffic_grabber.py --list-repos")
        sys.exit(1)
    
    # Get current views with historical data
    views_data = get_github_views(args.repo)
    
    # Get popular paths and referrers
    popular_paths = get_popular_paths(args.repo)
    referrers = get_referrers(args.repo)
    
    # Save to database
    with get_db() as conn:
        save_daily_views(conn, args.repo, views_data)
        save_current_totals(conn, args.repo, views_data)
        save_popular_paths(conn, args.repo, popular_paths)
        save_referrers(conn, args.repo, referrers)
        conn.commit()
        
        # Display summary
        print(f"\nGitHub Traffic Data for {args.repo}:")
        print(f"Current Total Views: {views_data.get('count', 0)}")
        print(f"Current Unique Visitors: {views_data.get('uniques', 0)}")
        
        # Show historical data from database
        historical = get_historical_views(conn, args.repo)
        if historical:
            print(f"\nHistorical data (last {len(historical)} days):")
            for row in historical:
                print(f"  {row['date']}: {row['count']} views, {row['uniques']} unique visitors")
        
        if popular_paths:
            print(f"\nTop {min(5, len(popular_paths))} popular paths today:")
            for path in popular_paths[:5]:
                print(f"  {path['path']}: {path['count']} views, {path['uniques']} unique visitors")
        
        if referrers:
            print(f"\nTop {min(5, len(referrers))} referrers today:")
            for referrer in referrers[:5]:
                print(f"  {referrer['referrer']}: {referrer['count']} views, {referrer['uniques']} unique visitors")
        
        print(f"\nData saved to PostgreSQL database: {DB_NAME}")

if __name__ == "__main__":
    main()