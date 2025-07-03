#!/usr/bin/env python3
import psycopg2
from psycopg2.extras import RealDictCursor
import os
import sys
import argparse
from datetime import datetime, timedelta
from termgraph import termgraph as tg

# PostgreSQL configuration (same as github_traffic_grabber.py)
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = os.environ.get("DB_PORT", "15432")
DB_NAME = "github_traffic_data"
DB_USER = os.environ.get("DB_USER", "pguser")
DB_PASS = os.environ.get("DB_PASS", "pgpass")

def get_referrers(repo, days=14, filter_pattern=None, top_n=10, start_date=None, end_date=None):
    """Get referrer data for the specified period"""
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASS,
            cursor_factory=RealDictCursor
        )
        
        cur = conn.cursor()
        
        # Use provided dates or calculate from days
        if not end_date:
            end_date = datetime.now().date()
        if not start_date:
            start_date = end_date - timedelta(days=days)
        
        # Build query based on filter
        if filter_pattern:
            query = """
                SELECT referrer, SUM(count) as total_views, SUM(uniques) as total_uniques
                FROM referrers
                WHERE repo = %s 
                  AND date >= %s
                  AND date <= %s
                  AND referrer ILIKE %s
                GROUP BY referrer
                ORDER BY total_views DESC
                LIMIT %s
            """
            cur.execute(query, (repo, start_date, end_date, f'%{filter_pattern}%', top_n))
        else:
            query = """
                SELECT referrer, SUM(count) as total_views, SUM(uniques) as total_uniques
                FROM referrers
                WHERE repo = %s 
                  AND date >= %s
                  AND date <= %s
                GROUP BY referrer
                ORDER BY total_views DESC
                LIMIT %s
            """
            cur.execute(query, (repo, start_date, end_date, top_n))
        
        referrer_totals = cur.fetchall()
        
        # Get daily breakdown for time series
        if filter_pattern:
            query = """
                SELECT date, SUM(count) as daily_views, SUM(uniques) as daily_uniques
                FROM referrers
                WHERE repo = %s 
                  AND date >= %s
                  AND date <= %s
                  AND referrer ILIKE %s
                GROUP BY date
                ORDER BY date
            """
            cur.execute(query, (repo, start_date, end_date, f'%{filter_pattern}%'))
        else:
            query = """
                SELECT date, SUM(count) as daily_views, SUM(uniques) as daily_uniques
                FROM referrers
                WHERE repo = %s 
                  AND date >= %s
                  AND date <= %s
                GROUP BY date
                ORDER BY date
            """
            cur.execute(query, (repo, start_date, end_date))
        
        daily_data = cur.fetchall()
        
        cur.close()
        conn.close()
        
        return referrer_totals, daily_data
        
    except psycopg2.Error as e:
        print(f"Database error: {e}")
        sys.exit(1)

def format_bar_chart_data(data):
    """Format data for horizontal bar chart"""
    if not data:
        return [], []
    
    labels = []
    values = []
    
    for row in data:
        # Truncate long referrer names
        referrer = row['referrer']
        if len(referrer) > 30:
            referrer = referrer[:27] + "..."
        labels.append(referrer)
        values.append([float(row['total_views'])])
    
    return labels, values

def format_time_series_data(data):
    """Format data for time series chart"""
    if not data:
        return [], []
    
    labels = []
    values = []
    
    for row in data:
        # Format date as MM/DD
        date_str = row['date'].strftime('%m/%d')
        labels.append(date_str)
        values.append([float(row['daily_views'])])
    
    return labels, values

def main():
    parser = argparse.ArgumentParser(description='Analyze GitHub repository referrer traffic')
    parser.add_argument('repo', help='Repository in format owner/repo')
    parser.add_argument('--days', type=int, default=30, help='Number of days to analyze (default: 30)')
    parser.add_argument('--filter', help='Filter referrers by pattern (e.g., "reddit", "google", "twitter")')
    parser.add_argument('--top', type=int, default=10, help='Show top N referrers (default: 10)')
    parser.add_argument('--from', dest='from_date', help='Start date (YYYY-MM-DD)')
    parser.add_argument('--to', dest='to_date', help='End date (YYYY-MM-DD)')
    parser.add_argument('--no-chart', action='store_true', help='Skip the historical chart')
    
    args = parser.parse_args()
    
    # Parse dates if provided
    start_date = None
    end_date = None
    if args.from_date:
        try:
            start_date = datetime.strptime(args.from_date, '%Y-%m-%d').date()
        except ValueError:
            print(f"Invalid start date format: {args.from_date}. Use YYYY-MM-DD")
            sys.exit(1)
    if args.to_date:
        try:
            end_date = datetime.strptime(args.to_date, '%Y-%m-%d').date()
        except ValueError:
            print(f"Invalid end date format: {args.to_date}. Use YYYY-MM-DD")
            sys.exit(1)
    
    print(f"\nReferrer Analytics for {args.repo}")
    print("=" * 60)
    
    # Get data
    referrer_totals, daily_data = get_referrers(
        args.repo, 
        days=args.days, 
        filter_pattern=args.filter,
        top_n=args.top,
        start_date=start_date,
        end_date=end_date
    )
    
    if not referrer_totals and not daily_data:
        date_range = f"{start_date} to {end_date}" if start_date and end_date else f"past {args.days} days"
        print(f"No referrer data found for this repository in the {date_range}.")
        if args.filter:
            print(f"Filter applied: '{args.filter}'")
        print("\nPossible reasons:")
        print("- No external traffic to the repository")
        print("- Repository data hasn't been collected yet")
        print("- Repository name is incorrect")
        sys.exit(0)
    
    # Display date range
    if start_date and end_date:
        print(f"\nDate range: {start_date} to {end_date}")
    else:
        print(f"\nShowing data for the past {args.days} days")
    
    # Display summary
    if referrer_totals:
        total_views = sum(row['total_views'] for row in referrer_totals)
        total_uniques = sum(row['total_uniques'] for row in referrer_totals)
        
        filter_text = f" matching '{args.filter}'" if args.filter else ""
        print(f"\nTotal referrals{filter_text}:")
        print(f"  Views: {total_views}")
        print(f"  Unique visitors: {total_uniques}")
    
    # Show daily time series by default (unless --no-chart is used)
    if not args.no_chart and daily_data:
        filter_text = f" matching '{args.filter}'" if args.filter else ""
        print(f"\nDaily referral traffic{filter_text}:")
        labels, values = format_time_series_data(daily_data)
        
        args_dict = {
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
        
        tg.chart(colors=[], labels=labels, data=values, args=args_dict)
    
    # Show top referrers bar chart
    if referrer_totals:
        print(f"\nTop {len(referrer_totals)} referrers by views:")
        labels, values = format_bar_chart_data(referrer_totals)
        
        args_dict = {
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
        
        tg.chart(colors=[], labels=labels, data=values, args=args_dict)
        
        # Show detailed table
        print("\nDetailed breakdown:")
        print(f"{'Referrer':<35} {'Views':<10} {'Unique':<10}")
        print("-" * 55)
        for row in referrer_totals:
            referrer = row['referrer']
            if len(referrer) > 33:
                referrer = referrer[:30] + "..."
            print(f"{referrer:<35} {row['total_views']:<10} {row['total_uniques']:<10}")

if __name__ == "__main__":
    main()