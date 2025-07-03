#!/usr/bin/env python3
import psycopg2
from psycopg2.extras import RealDictCursor
import os
import sys
import argparse
from datetime import datetime, timedelta
from termgraph import termgraph as tg
from collections import defaultdict

# PostgreSQL configuration
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = os.environ.get("DB_PORT", "15432")
DB_NAME = "github_traffic_data"
DB_USER = os.environ.get("DB_USER", "pguser")
DB_PASS = os.environ.get("DB_PASS", "pgpass")

def get_db_connection():
    """Create database connection"""
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASS,
        cursor_factory=RealDictCursor
    )

def get_usage_summary():
    """Get overall usage summary statistics"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Get totals
    cur.execute("""
        SELECT 
            COUNT(DISTINCT repo_full_name) as total_repos,
            COUNT(DISTINCT CASE WHEN is_active THEN repo_full_name END) as active_repos,
            COUNT(DISTINCT CASE WHEN NOT is_active THEN repo_full_name END) as inactive_repos,
            COUNT(*) as total_workflows,
            COUNT(CASE WHEN is_active THEN 1 END) as active_workflows,
            SUM(CASE WHEN is_active THEN stars ELSE 0 END) as total_stars
        FROM flox_action_usage
    """)
    
    result = cur.fetchone()
    cur.close()
    conn.close()
    
    return result

def get_version_distribution():
    """Get distribution of action versions"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT 
            COALESCE(action_version, 'unknown') as version,
            COUNT(DISTINCT repo_full_name) as repo_count,
            SUM(stars) as total_stars
        FROM flox_action_usage
        WHERE is_active = TRUE
        GROUP BY action_version
        ORDER BY repo_count DESC
    """)
    
    results = cur.fetchall()
    cur.close()
    conn.close()
    
    return results

def get_language_distribution():
    """Get distribution of programming languages"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT 
            COALESCE(language, 'Unknown') as language,
            COUNT(DISTINCT repo_full_name) as repo_count,
            SUM(stars) as total_stars
        FROM flox_action_usage
        WHERE is_active = TRUE
        GROUP BY language
        ORDER BY repo_count DESC
        LIMIT 15
    """)
    
    results = cur.fetchall()
    cur.close()
    conn.close()
    
    return results

def get_top_repositories(limit=20, include_inactive=False):
    """Get top repositories by stars"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    active_filter = "WHERE is_active = TRUE" if not include_inactive else ""
    
    cur.execute(f"""
        SELECT 
            repo_full_name,
            MAX(stars) as stars,
            MAX(language) as language,
            MAX(description) as description,
            BOOL_OR(is_active) as is_active,
            COUNT(*) as workflow_count,
            MIN(first_seen) as first_seen,
            MAX(last_seen) as last_seen
        FROM flox_action_usage
        {active_filter}
        GROUP BY repo_full_name
        ORDER BY stars DESC
        LIMIT %s
    """, (limit,))
    
    results = cur.fetchall()
    cur.close()
    conn.close()
    
    return results

def get_adoption_timeline(days=30):
    """Get adoption timeline data"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=days)
    
    cur.execute("""
        SELECT 
            date,
            active_repos,
            new_repos,
            removed_repos,
            total_repos
        FROM flox_action_history
        WHERE date >= %s AND date <= %s
        ORDER BY date
    """, (start_date, end_date))
    
    results = cur.fetchall()
    cur.close()
    conn.close()
    
    return results

def get_recent_activity(days=7):
    """Get recent adoption and churn"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    cutoff_date = datetime.now().date() - timedelta(days=days)
    
    # New adopters
    cur.execute("""
        SELECT DISTINCT
            repo_full_name,
            stars,
            language,
            first_seen
        FROM flox_action_usage
        WHERE first_seen >= %s
        ORDER BY first_seen DESC, stars DESC
    """, (cutoff_date,))
    
    new_repos = cur.fetchall()
    
    # Recently churned
    cur.execute("""
        SELECT DISTINCT
            repo_full_name,
            stars,
            language,
            last_seen,
            first_seen
        FROM flox_action_usage
        WHERE is_active = FALSE 
          AND last_seen >= %s
        ORDER BY last_seen DESC, stars DESC
    """, (cutoff_date,))
    
    churned_repos = cur.fetchall()
    
    cur.close()
    conn.close()
    
    return new_repos, churned_repos

def display_usage_summary():
    """Display overall usage summary"""
    summary = get_usage_summary()
    
    if not summary:
        print("No flox action usage data found.")
        return
    
    retention_rate = (summary['active_repos'] / summary['total_repos'] * 100) if summary['total_repos'] > 0 else 0
    
    print("\nFlox Action Usage Summary:")
    print(f"  Total repositories tracked: {summary['total_repos']}")
    print(f"  Currently active: {summary['active_repos']}")
    print(f"  No longer using: {summary['inactive_repos']}")
    print(f"  Retention rate: {retention_rate:.1f}%")
    print(f"  Total workflows: {summary['total_workflows']}")
    print(f"  Active workflows: {summary['active_workflows']}")
    print(f"  Combined stars (active repos): {summary['total_stars']:,}")

def display_version_distribution():
    """Display version distribution"""
    versions = get_version_distribution()
    
    if not versions:
        print("\nNo version data available.")
        return
    
    print("\nAction Version Distribution (Active Repos):")
    
    # Prepare data for chart
    labels = []
    values = []
    
    for v in versions[:10]:  # Top 10 versions
        version_str = v['version']
        if len(version_str) > 20:
            version_str = version_str[:17] + "..."
        labels.append(f"{version_str} ({v['repo_count']} repos)")
        values.append([float(v['repo_count'])])
    
    chart_args = {
        'stacked': False,
        'width': 50,
        'no_labels': False,
        'format': '{:.0f}',
        'suffix': '',
        'no_values': False,
        'vertical': False,
        'histogram': False,
        'different_scale': False
    }
    
    tg.chart(colors=[], data=values, args=chart_args, labels=labels)
    
    # Detailed table
    print("\nDetailed Version Breakdown:")
    print(f"{'Version':<30} {'Repos':<10} {'Stars':<10}")
    print("-" * 50)
    for v in versions:
        version_str = v['version'][:28] if len(v['version']) > 28 else v['version']
        print(f"{version_str:<30} {v['repo_count']:<10} {v['total_stars']:<10}")

def display_language_distribution():
    """Display language distribution"""
    languages = get_language_distribution()
    
    if not languages:
        print("\nNo language data available.")
        return
    
    print("\nProgramming Language Distribution (Active Repos):")
    
    # Prepare data for chart
    labels = []
    values = []
    
    for lang in languages[:10]:  # Top 10 languages
        labels.append(f"{lang['language']} ({lang['repo_count']})")
        values.append([float(lang['repo_count'])])
    
    chart_args = {
        'stacked': False,
        'width': 50,
        'no_labels': False,
        'format': '{:.0f}',
        'suffix': '',
        'no_values': False,
        'vertical': False,
        'histogram': False,
        'different_scale': False
    }
    
    tg.chart(colors=[], data=values, args=chart_args, labels=labels)

def display_top_repositories(limit=20, include_inactive=False):
    """Display top repositories"""
    repos = get_top_repositories(limit, include_inactive)
    
    if not repos:
        print("\nNo repository data available.")
        return
    
    status = "All" if include_inactive else "Active"
    print(f"\nTop {len(repos)} {status} Repositories by Stars:")
    print(f"{'Repository':<40} {'Stars':<8} {'Language':<15} {'Workflows':<10} {'Status':<10}")
    print("-" * 83)
    
    for repo in repos:
        repo_name = repo['repo_full_name']
        if len(repo_name) > 38:
            repo_name = repo_name[:35] + "..."
        lang = (repo['language'] or 'Unknown')[:13]
        status = "Active" if repo['is_active'] else "Inactive"
        print(f"{repo_name:<40} {repo['stars']:<8} {lang:<15} {repo['workflow_count']:<10} {status:<10}")

def display_adoption_timeline(days=30):
    """Display adoption timeline"""
    timeline = get_adoption_timeline(days)
    
    if not timeline:
        print(f"\nNo timeline data available for the past {days} days.")
        return
    
    print(f"\nAdoption Timeline (Past {days} Days):")
    
    # Calculate growth
    if len(timeline) >= 2:
        start_repos = timeline[0]['active_repos']
        end_repos = timeline[-1]['active_repos']
        growth = end_repos - start_repos
        growth_pct = (growth / start_repos * 100) if start_repos > 0 else 0
        
        print(f"  Starting active repos: {start_repos}")
        print(f"  Current active repos: {end_repos}")
        print(f"  Net growth: {growth:+d} ({growth_pct:+.1f}%)")
        
        total_new = sum(row['new_repos'] for row in timeline)
        total_removed = sum(row['removed_repos'] for row in timeline)
        print(f"  Total new adopters: {total_new}")
        print(f"  Total churned: {total_removed}")
    
    # Chart of active repos over time
    print("\nActive Repositories Over Time:")
    
    labels = []
    values = []
    
    # Sample data points for readability
    sample_interval = max(1, len(timeline) // 20)
    
    for i in range(0, len(timeline), sample_interval):
        row = timeline[i]
        date_str = row['date'].strftime('%m/%d')
        labels.append(date_str)
        values.append([float(row['active_repos'])])
    
    chart_args = {
        'stacked': False,
        'width': 60,
        'no_labels': False,
        'format': '{:.0f}',
        'suffix': '',
        'no_values': False,
        'vertical': False,
        'histogram': False,
        'different_scale': False
    }
    
    tg.chart(colors=[], data=values, args=chart_args, labels=labels)

def display_recent_activity(days=7):
    """Display recent adoption and churn"""
    new_repos, churned_repos = get_recent_activity(days)
    
    print(f"\nRecent Activity (Past {days} Days):")
    
    if new_repos:
        print(f"\nNew Adopters ({len(new_repos)} repositories):")
        print(f"{'Repository':<40} {'Stars':<8} {'Language':<15} {'Date':<12}")
        print("-" * 75)
        
        for repo in new_repos[:10]:  # Show top 10
            repo_name = repo['repo_full_name']
            if len(repo_name) > 38:
                repo_name = repo_name[:35] + "..."
            lang = (repo['language'] or 'Unknown')[:13]
            date_str = repo['first_seen'].strftime('%Y-%m-%d')
            print(f"{repo_name:<40} {repo['stars']:<8} {lang:<15} {date_str:<12}")
        
        if len(new_repos) > 10:
            print(f"  ... and {len(new_repos) - 10} more")
    else:
        print("\nNo new adopters in this period.")
    
    if churned_repos:
        print(f"\nRepositories That Stopped Using Flox ({len(churned_repos)} repositories):")
        print(f"{'Repository':<40} {'Stars':<8} {'Days Used':<12} {'Last Seen':<12}")
        print("-" * 72)
        
        for repo in churned_repos[:10]:  # Show top 10
            repo_name = repo['repo_full_name']
            if len(repo_name) > 38:
                repo_name = repo_name[:35] + "..."
            days_used = (repo['last_seen'] - repo['first_seen']).days
            date_str = repo['last_seen'].strftime('%Y-%m-%d')
            print(f"{repo_name:<40} {repo['stars']:<8} {days_used:<12} {date_str:<12}")
        
        if len(churned_repos) > 10:
            print(f"  ... and {len(churned_repos) - 10} more")
    else:
        print("\nNo repositories stopped using flox in this period.")

def export_report(filename, days=30):
    """Export comprehensive analysis report"""
    with open(filename, 'w') as f:
        # Header
        f.write("Flox Action Usage Analysis Report\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Analysis Period: Past {days} days\n")
        f.write("=" * 80 + "\n\n")
        
        # Summary
        summary = get_usage_summary()
        if summary:
            retention_rate = (summary['active_repos'] / summary['total_repos'] * 100) if summary['total_repos'] > 0 else 0
            
            f.write("USAGE SUMMARY\n")
            f.write("-" * 40 + "\n")
            f.write(f"Total repositories tracked: {summary['total_repos']}\n")
            f.write(f"Currently active: {summary['active_repos']}\n")
            f.write(f"No longer using: {summary['inactive_repos']}\n")
            f.write(f"Retention rate: {retention_rate:.1f}%\n")
            f.write(f"Total workflows: {summary['total_workflows']}\n")
            f.write(f"Combined stars (active repos): {summary['total_stars']:,}\n\n")
        
        # Version distribution
        versions = get_version_distribution()
        if versions:
            f.write("VERSION DISTRIBUTION\n")
            f.write("-" * 40 + "\n")
            f.write(f"{'Version':<30} {'Repos':<10} {'Stars':<10}\n")
            for v in versions:
                version_str = v['version'][:28] if len(v['version']) > 28 else v['version']
                f.write(f"{version_str:<30} {v['repo_count']:<10} {v['total_stars']:<10}\n")
            f.write("\n")
        
        # Language distribution
        languages = get_language_distribution()
        if languages:
            f.write("LANGUAGE DISTRIBUTION\n")
            f.write("-" * 40 + "\n")
            f.write(f"{'Language':<20} {'Repos':<10} {'Stars':<10}\n")
            for lang in languages:
                f.write(f"{lang['language']:<20} {lang['repo_count']:<10} {lang['total_stars']:<10}\n")
            f.write("\n")
        
        # Top repositories
        repos = get_top_repositories(50, include_inactive=True)
        if repos:
            f.write("TOP 50 REPOSITORIES BY STARS\n")
            f.write("-" * 40 + "\n")
            f.write(f"{'Repository':<50} {'Stars':<8} {'Language':<15} {'Status':<10}\n")
            for repo in repos:
                status = "Active" if repo['is_active'] else "Inactive"
                lang = (repo['language'] or 'Unknown')[:13]
                f.write(f"{repo['repo_full_name']:<50} {repo['stars']:<8} {lang:<15} {status:<10}\n")
            f.write("\n")
        
        # Recent activity
        new_repos, churned_repos = get_recent_activity(days)
        
        if new_repos:
            f.write(f"NEW ADOPTERS (Past {days} Days)\n")
            f.write("-" * 40 + "\n")
            f.write(f"{'Repository':<50} {'Stars':<8} {'Language':<15} {'Date':<12}\n")
            for repo in new_repos:
                lang = (repo['language'] or 'Unknown')[:13]
                date_str = repo['first_seen'].strftime('%Y-%m-%d')
                f.write(f"{repo['repo_full_name']:<50} {repo['stars']:<8} {lang:<15} {date_str:<12}\n")
            f.write("\n")
        
        if churned_repos:
            f.write(f"CHURNED REPOSITORIES (Past {days} Days)\n")
            f.write("-" * 40 + "\n")
            f.write(f"{'Repository':<50} {'Days Used':<12} {'Last Seen':<12}\n")
            for repo in churned_repos:
                days_used = (repo['last_seen'] - repo['first_seen']).days
                date_str = repo['last_seen'].strftime('%Y-%m-%d')
                f.write(f"{repo['repo_full_name']:<50} {days_used:<12} {date_str:<12}\n")
    
    print(f"\nReport exported to: {filename}")

def main():
    parser = argparse.ArgumentParser(description='Analyze flox action usage data with visualizations')
    parser.add_argument('--summary', action='store_true', help='Show usage summary')
    parser.add_argument('--versions', action='store_true', help='Show version distribution')
    parser.add_argument('--languages', action='store_true', help='Show language distribution')
    parser.add_argument('--top', type=int, nargs='?', const=20, help='Show top N repositories by stars (default: 20)')
    parser.add_argument('--timeline', action='store_true', help='Show adoption timeline')
    parser.add_argument('--recent', action='store_true', help='Show recent activity')
    parser.add_argument('--days', type=int, default=30, help='Number of days for timeline/recent analysis (default: 30)')
    parser.add_argument('--all', action='store_true', help='Show all analyses')
    parser.add_argument('--export', help='Export comprehensive report to file')
    parser.add_argument('--include-inactive', action='store_true', help='Include inactive repos in top repositories')
    
    args = parser.parse_args()
    
    # Export report if requested
    if args.export:
        export_report(args.export, args.days)
        return
    
    # Determine what to show
    show_all = args.all or not any([args.summary, args.versions, args.languages, args.top, args.timeline, args.recent])
    
    if show_all or args.summary:
        display_usage_summary()
    
    if show_all or args.versions:
        display_version_distribution()
    
    if show_all or args.languages:
        display_language_distribution()
    
    if show_all or args.top is not None:
        limit = args.top if args.top is not None else 20
        display_top_repositories(limit, args.include_inactive)
    
    if show_all or args.timeline:
        display_adoption_timeline(args.days)
    
    if show_all or args.recent:
        display_recent_activity(args.days if args.recent else 7)

if __name__ == "__main__":
    main()