#!/usr/bin/env python3
import psycopg2
from psycopg2.extras import RealDictCursor
import os
import sys
import argparse
from datetime import datetime, timedelta
from termgraph import termgraph as tg
from collections import defaultdict

# PostgreSQL configuration (same as github_traffic_grabber.py)
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

def get_daily_views(repo, days=14):
    """Get daily views data for the past N days"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=days)
    
    cur.execute("""
        SELECT date, count as views, uniques
        FROM daily_views
        WHERE repo = %s 
          AND date >= %s
          AND date <= %s
        ORDER BY date
    """, (repo, start_date, end_date))
    
    results = cur.fetchall()
    cur.close()
    conn.close()
    
    return results

def get_popular_paths(repo, days=14, top_n=10):
    """Get popular paths data"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=days)
    
    cur.execute("""
        SELECT path, title, SUM(count) as total_views, SUM(uniques) as total_uniques
        FROM popular_paths
        WHERE repo = %s 
          AND date >= %s
          AND date <= %s
        GROUP BY path, title
        ORDER BY total_views DESC
        LIMIT %s
    """, (repo, start_date, end_date, top_n))
    
    results = cur.fetchall()
    cur.close()
    conn.close()
    
    return results

def get_referrers_summary(repo, days=14, top_n=10):
    """Get referrers summary"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=days)
    
    cur.execute("""
        SELECT referrer, SUM(count) as total_views, SUM(uniques) as total_uniques
        FROM referrers
        WHERE repo = %s 
          AND date >= %s
          AND date <= %s
        GROUP BY referrer
        ORDER BY total_views DESC
        LIMIT %s
    """, (repo, start_date, end_date, top_n))
    
    results = cur.fetchall()
    cur.close()
    conn.close()
    
    return results

def get_current_totals(repo):
    """Get current total views and uniques"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT count, uniques, timestamp
        FROM current_totals
        WHERE repo = %s
    """, (repo,))
    
    result = cur.fetchone()
    cur.close()
    conn.close()
    
    return result

def get_repos_list():
    """Get list of all repositories in the database"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT DISTINCT repo, MAX(timestamp) as last_update
        FROM current_totals
        GROUP BY repo
        ORDER BY repo
    """)
    
    results = cur.fetchall()
    cur.close()
    conn.close()
    
    return results

def format_line_chart_data(data, value_field='views'):
    """Format data for line chart"""
    if not data:
        return [], []
    
    labels = []
    values = []
    
    for row in data:
        date_str = row['date'].strftime('%m/%d')
        labels.append(date_str)
        values.append([float(row[value_field])])
    
    return labels, values

def format_bar_chart_data(data, label_field, value_field='total_views', max_label_length=40):
    """Format data for horizontal bar chart"""
    if not data:
        return [], []
    
    labels = []
    values = []
    
    for row in data:
        label = str(row[label_field])
        if len(label) > max_label_length:
            label = label[:max_label_length-3] + "..."
        labels.append(label)
        values.append([float(row[value_field])])
    
    return labels, values

def display_daily_traffic(repo, days):
    """Display daily traffic visualization"""
    daily_data = get_daily_views(repo, days)
    
    if not daily_data:
        print(f"No daily traffic data found for {repo}")
        return
    
    # Calculate totals
    total_views = sum(row['views'] for row in daily_data)
    total_uniques = sum(row['uniques'] for row in daily_data)
    avg_views = total_views / len(daily_data) if daily_data else 0
    avg_uniques = total_uniques / len(daily_data) if daily_data else 0
    
    print(f"\nDaily Traffic Summary (past {days} days):")
    print(f"  Total views: {total_views}")
    print(f"  Total unique visitors: {total_uniques}")
    print(f"  Average daily views: {avg_views:.1f}")
    print(f"  Average daily uniques: {avg_uniques:.1f}")
    
    # Views chart
    print("\nDaily Views:")
    labels, values = format_line_chart_data(daily_data, 'views')
    
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
    
    # Unique visitors chart
    print("\nDaily Unique Visitors:")
    labels, values = format_line_chart_data(daily_data, 'uniques')
    tg.chart(colors=[], data=values, args=chart_args, labels=labels)

def display_popular_paths(repo, days, top_n):
    """Display popular paths visualization"""
    paths_data = get_popular_paths(repo, days, top_n)
    
    if not paths_data:
        print(f"\nNo popular paths data found for {repo}")
        return
    
    print(f"\nTop {len(paths_data)} Popular Paths (past {days} days):")
    
    # Format paths for display
    labels, values = format_bar_chart_data(paths_data, 'path', 'total_views')
    
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
    print("\nDetailed Path Breakdown:")
    print(f"{'Path':<45} {'Views':<10} {'Unique':<10}")
    print("-" * 65)
    for row in paths_data:
        path = row['path']
        if len(path) > 43:
            path = path[:40] + "..."
        print(f"{path:<45} {row['total_views']:<10} {row['total_uniques']:<10}")

def display_referrers(repo, days, top_n):
    """Display referrers visualization"""
    referrers_data = get_referrers_summary(repo, days, top_n)
    
    if not referrers_data:
        print(f"\nNo referrer data found for {repo}")
        return
    
    print(f"\nTop {len(referrers_data)} Referrers (past {days} days):")
    
    labels, values = format_bar_chart_data(referrers_data, 'referrer', 'total_views')
    
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

def display_repo_comparison(repos):
    """Display comparison between multiple repositories"""
    print("\nRepository Comparison:")
    print(f"{'Repository':<30} {'Total Views':<12} {'Uniques':<12} {'Last Update':<20}")
    print("-" * 74)
    
    repo_data = []
    for repo in repos:
        totals = get_current_totals(repo)
        if totals:
            repo_data.append({
                'repo': repo,
                'views': totals['count'],
                'uniques': totals['uniques'],
                'timestamp': totals['timestamp']
            })
    
    # Sort by views
    repo_data.sort(key=lambda x: x['views'], reverse=True)
    
    for data in repo_data:
        repo_name = data['repo']
        if len(repo_name) > 28:
            repo_name = repo_name[:25] + "..."
        timestamp_str = data['timestamp'].strftime('%Y-%m-%d %H:%M')
        print(f"{repo_name:<30} {data['views']:<12} {data['uniques']:<12} {timestamp_str:<20}")
    
    if len(repo_data) > 1:
        # Bar chart comparison
        print("\nViews Comparison:")
        labels = []
        values = []
        for data in repo_data[:10]:  # Top 10 only
            repo_name = data['repo']
            if len(repo_name) > 30:
                repo_name = repo_name[:27] + "..."
            labels.append(repo_name)
            values.append([float(data['views'])])
        
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

def export_report(repo, days, filename):
    """Export analysis report to a file"""
    with open(filename, 'w') as f:
        # Header
        f.write(f"GitHub Traffic Analysis Report\n")
        f.write(f"Repository: {repo}\n")
        f.write(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Period: Past {days} days\n")
        f.write("=" * 60 + "\n\n")
        
        # Current totals
        totals = get_current_totals(repo)
        if totals:
            f.write(f"Current Totals:\n")
            f.write(f"  Total Views: {totals['count']}\n")
            f.write(f"  Unique Visitors: {totals['uniques']}\n")
            f.write(f"  Last Updated: {totals['timestamp']}\n\n")
        
        # Daily data
        daily_data = get_daily_views(repo, days)
        if daily_data:
            f.write("Daily Traffic:\n")
            f.write(f"{'Date':<12} {'Views':<10} {'Uniques':<10}\n")
            f.write("-" * 32 + "\n")
            for row in daily_data:
                f.write(f"{row['date']:<12} {row['views']:<10} {row['uniques']:<10}\n")
            f.write("\n")
        
        # Popular paths
        paths_data = get_popular_paths(repo, days, 20)
        if paths_data:
            f.write("Top 20 Popular Paths:\n")
            f.write(f"{'Path':<50} {'Views':<10} {'Uniques':<10}\n")
            f.write("-" * 70 + "\n")
            for row in paths_data:
                path = row['path'][:48] if len(row['path']) > 48 else row['path']
                f.write(f"{path:<50} {row['total_views']:<10} {row['total_uniques']:<10}\n")
            f.write("\n")
        
        # Referrers
        referrers_data = get_referrers_summary(repo, days, 20)
        if referrers_data:
            f.write("Top 20 Referrers:\n")
            f.write(f"{'Referrer':<40} {'Views':<10} {'Uniques':<10}\n")
            f.write("-" * 60 + "\n")
            for row in referrers_data:
                referrer = row['referrer'][:38] if len(row['referrer']) > 38 else row['referrer']
                f.write(f"{referrer:<40} {row['total_views']:<10} {row['total_uniques']:<10}\n")
    
    print(f"\nReport exported to: {filename}")

def main():
    parser = argparse.ArgumentParser(description='Analyze GitHub repository traffic data with visualizations')
    parser.add_argument('repo', nargs='?', help='Repository in format owner/repo')
    parser.add_argument('--days', type=int, default=14, help='Number of days to analyze (default: 14)')
    parser.add_argument('--top', type=int, default=10, help='Show top N items (default: 10)')
    parser.add_argument('--daily', action='store_true', help='Show daily traffic charts')
    parser.add_argument('--paths', action='store_true', help='Show popular paths analysis')
    parser.add_argument('--referrers', action='store_true', help='Show referrers analysis')
    parser.add_argument('--all', action='store_true', help='Show all analyses')
    parser.add_argument('--list', action='store_true', help='List all repositories in database')
    parser.add_argument('--compare', nargs='+', help='Compare multiple repositories')
    parser.add_argument('--export', help='Export report to file')
    
    args = parser.parse_args()
    
    # List repositories
    if args.list:
        repos = get_repos_list()
        if repos:
            print("\nRepositories in database:")
            for repo in repos:
                last_update = repo['last_update'].strftime('%Y-%m-%d %H:%M')
                print(f"  - {repo['repo']} (last updated: {last_update})")
        else:
            print("No repositories found in database.")
        return
    
    # Compare repositories
    if args.compare:
        display_repo_comparison(args.compare)
        return
    
    # Single repo analysis
    if not args.repo:
        print("Error: Please specify a repository or use --list to see available repos")
        print("Usage: python3 traffic_analyzer.py owner/repo [options]")
        sys.exit(1)
    
    # Current totals
    totals = get_current_totals(args.repo)
    if totals:
        print(f"\n{args.repo} - Current Totals:")
        print(f"  Total Views: {totals['count']}")
        print(f"  Unique Visitors: {totals['uniques']}")
        print(f"  Last Updated: {totals['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}")
    else:
        print(f"\nNo data found for repository: {args.repo}")
        print("Make sure you've run the traffic grabber for this repository first.")
        sys.exit(1)
    
    # Export report if requested
    if args.export:
        export_report(args.repo, args.days, args.export)
    
    # Show requested analyses
    show_all = args.all or (not args.daily and not args.paths and not args.referrers)
    
    if show_all or args.daily:
        display_daily_traffic(args.repo, args.days)
    
    if show_all or args.paths:
        display_popular_paths(args.repo, args.days, args.top)
    
    if show_all or args.referrers:
        display_referrers(args.repo, args.days, args.top)

if __name__ == "__main__":
    main()