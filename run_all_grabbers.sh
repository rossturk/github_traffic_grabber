#!/bin/bash

# run_all_grabbers.sh - Run all data grabbers for flox-related projects
# This script collects traffic data and action usage for flox repositories

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

print_error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

# Check if we're in the right directory
if [ ! -f "grab_github_traffic.py" ] || [ ! -f "grab_action_usage.py" ]; then
    print_error "Error: Required scripts not found. Please run from the grab-activity directory."
    exit 1
fi

# Check if GITHUB_TOKEN is set
if [ -z "$GITHUB_TOKEN" ]; then
    print_error "Error: GITHUB_TOKEN environment variable not set"
    echo "Please set your GitHub personal access token:"
    echo "export GITHUB_TOKEN='your_token_here'"
    exit 1
fi

print_status "Starting flox data collection..."

# Array of flox repositories to track traffic for
FLOX_REPOS=(
    "flox/flox"
    "flox/floxdocs"
    "flox/floxenvs"
)

# Array of flox GitHub actions to track
FLOX_ACTIONS=(
    "flox/install-flox-action"
    "flox/activate-action"
)

# Function to run traffic grabber for a repository
run_traffic_grabber() {
    local repo=$1
    print_status "Collecting traffic data for $repo..."
    
    if python3 grab_github_traffic.py "$repo"; then
        print_success "Traffic data collected for $repo"
    else
        print_error "Failed to collect traffic data for $repo"
        return 1
    fi
}

# Function to run action tracker for a GitHub action
run_action_tracker() {
    local action=$1
    print_status "Collecting usage data for action $action..."
    
    if python3 grab_action_usage.py "$action" --update; then
        print_success "Usage data collected for action $action"
    else
        print_error "Failed to collect usage data for action $action"
        return 1
    fi
}

# Main execution
main() {
    local start_time=$(date +%s)
    local failed_repos=()
    local failed_actions=()
    
    print_status "=========================================="
    print_status "Starting flox data collection suite"
    print_status "=========================================="
    
    # Collect traffic data for flox repositories
    print_status "Phase 1: Collecting traffic data for flox repositories..."
    for repo in "${FLOX_REPOS[@]}"; do
        if ! run_traffic_grabber "$repo"; then
            failed_repos+=("$repo")
        fi
        # Add a small delay between API calls
        sleep 2
    done
    
    print_status "Phase 1 complete. Traffic data collection finished."
    echo
    
    # Collect action usage data
    print_status "Phase 2: Collecting GitHub action usage data..."
    for action in "${FLOX_ACTIONS[@]}"; do
        if ! run_action_tracker "$action"; then
            failed_actions+=("$action")
        fi
        # Add a small delay between searches
        sleep 5
    done
    
    print_status "Phase 2 complete. Action usage data collection finished."
    echo
    
    # Generate summary reports
    print_status "Phase 3: Generating summary reports..."
    
    # Traffic analysis summary
    print_status "Traffic Analysis Summary:"
    echo "----------------------------------------"
    for repo in "${FLOX_REPOS[@]}"; do
        if python3 traffic_analyzer.py "$repo" --days 7 2>/dev/null; then
            echo
        else
            print_warning "Could not generate traffic summary for $repo"
        fi
    done
    
    # Action usage summary
    print_status "Action Usage Summary:"
    echo "----------------------------------------"
    if python3 action_tracker.py --summary; then
        echo
    else
        print_warning "Could not generate action usage summary"
    fi
    
    # Calculate runtime
    local end_time=$(date +%s)
    local runtime=$((end_time - start_time))
    
    print_status "=========================================="
    print_status "Data collection complete!"
    print_status "Total runtime: ${runtime} seconds"
    print_status "=========================================="
    
    # Report any failures
    if [ ${#failed_repos[@]} -gt 0 ] || [ ${#failed_actions[@]} -gt 0 ]; then
        print_warning "Some operations failed:"
        
        if [ ${#failed_repos[@]} -gt 0 ]; then
            print_warning "Failed repository traffic collection:"
            for repo in "${failed_repos[@]}"; do
                print_warning "  - $repo"
            done
        fi
        
        if [ ${#failed_actions[@]} -gt 0 ]; then
            print_warning "Failed action usage collection:"
            for action in "${failed_actions[@]}"; do
                print_warning "  - $action"
            done
        fi
        
        exit 1
    else
        print_success "All data collection completed successfully!"
    fi
}

# Function to show usage information
show_usage() {
    echo "Usage: $0 [OPTIONS]"
    echo
    echo "Run all flox data grabbers to collect traffic and usage statistics."
    echo
    echo "OPTIONS:"
    echo "  -h, --help     Show this help message"
    echo "  --dry-run      Show what would be executed without running"
    echo "  --traffic-only Only collect traffic data (skip action tracking)"
    echo "  --actions-only Only collect action usage data (skip traffic)"
    echo
    echo "Environment Variables:"
    echo "  GITHUB_TOKEN   GitHub personal access token (required)"
    echo
    echo "Examples:"
    echo "  $0                    # Run all grabbers"
    echo "  $0 --traffic-only     # Only collect traffic data"
    echo "  $0 --actions-only     # Only collect action usage data"
    echo "  $0 --dry-run          # Show what would be executed"
}

# Function to show dry run information
show_dry_run() {
    echo "DRY RUN MODE - The following commands would be executed:"
    echo
    echo "Traffic data collection:"
    for repo in "${FLOX_REPOS[@]}"; do
        echo "  python3 github_traffic_grabber.py $repo"
    done
    echo
    echo "Action usage data collection:"
    for action in "${FLOX_ACTIONS[@]}"; do
        echo "  python3 action_tracker.py $action --update"
    done
    echo
    echo "Summary reports:"
    echo "  python3 action_tracker.py --summary"
    for repo in "${FLOX_REPOS[@]}"; do
        echo "  python3 traffic_analyzer.py $repo --days 7"
    done
}

# Parse command line arguments
TRAFFIC_ONLY=false
ACTIONS_ONLY=false
DRY_RUN=false

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_usage
            exit 0
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --traffic-only)
            TRAFFIC_ONLY=true
            shift
            ;;
        --actions-only)
            ACTIONS_ONLY=true
            shift
            ;;
        *)
            print_error "Unknown option: $1"
            show_usage
            exit 1
            ;;
    esac
done

# Handle dry run
if [ "$DRY_RUN" = true ]; then
    show_dry_run
    exit 0
fi

# Handle traffic-only mode
if [ "$TRAFFIC_ONLY" = true ]; then
    print_status "Running in traffic-only mode..."
    for repo in "${FLOX_REPOS[@]}"; do
        run_traffic_grabber "$repo"
        sleep 2
    done
    print_success "Traffic data collection complete!"
    exit 0
fi

# Handle actions-only mode
if [ "$ACTIONS_ONLY" = true ]; then
    print_status "Running in actions-only mode..."
    for action in "${FLOX_ACTIONS[@]}"; do
        run_action_tracker "$action"
        sleep 5
    done
    print_success "Action usage data collection complete!"
    exit 0
fi

# Run main function
main
