import os
import hashlib
import json
import argparse
import time
import logging
import signal
import fnmatch

# Configuration
BASELINE_FILE = "/var/lib/etc_baseline.json"
METRIC_FILE = "/var/lib/node_exporter/textfile_collector/etc_changes.prom"

# New: Add patterns here. 
# Use '*' for wildcards. e.g., "*/insights/*" ignores everything in an insights folder.
IGNORE_PATTERNS = {
    "/etc/os-release", 
    "/etc/redhat-release", 
    "/etc/insights/*"

}

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

RENEW_BASELINE_REQUESTED = False

def handle_reload(signum, frame):
    global RENEW_BASELINE_REQUESTED
    logging.info("SIGHUP received. Force renewing baseline...")
    RENEW_BASELINE_REQUESTED = True

signal.signal(signal.SIGHUP, handle_reload)

def is_ignored(path):
    """Checks if a path matches any of the ignore patterns."""
    for pattern in IGNORE_PATTERNS:
        if fnmatch.fnmatch(path, pattern):
            return True
    return False

def sha256(file_path):
    if os.path.islink(file_path): return None
    try:
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    except (PermissionError, OSError):
        return None

def scan(directories):
    data = {}
    paths_to_scan = set(directories)
    paths_to_scan.add("/etc")
    for target_dir in paths_to_scan:
        if not os.path.isdir(target_dir): continue
        for root, _, files in os.walk(target_dir):
            for name in files:
                path = os.path.join(root, name)
                
                # Check against the new pattern matcher
                if is_ignored(path):
                    continue
                    
                h = sha256(path)
                if h: data[path] = h
    return data

def write_metrics(diffs):
    try:
        temp_file = METRIC_FILE + ".tmp"
        with open(temp_file, "w") as f:
            f.write("# HELP etc_file_deviation Details of changed files\n")
            f.write("# TYPE etc_file_deviation gauge\n")
            if not diffs:
                f.write('etc_file_deviation{file="none",action="none"} 0\n')
            else:
                for file_path, action in diffs.items():
                    safe_path = file_path.replace("\\", "\\\\").replace('"', '\\"')
                    f.write(f'etc_file_deviation{{file="{safe_path}",action="{action}"}} 1\n')
        os.replace(temp_file, METRIC_FILE)
    except IOError as e:
        logging.error(f"Error writing metric: {e}")

def run_fim(directories):
    global RENEW_BASELINE_REQUESTED
    current = scan(directories)
    
    if RENEW_BASELINE_REQUESTED:
        if os.path.exists(BASELINE_FILE):
            os.remove(BASELINE_FILE)
        RENEW_BASELINE_REQUESTED = False

    if not os.path.exists(BASELINE_FILE):
        logging.info("Generating new baseline...")
        with open(BASELINE_FILE, "w") as f:
            json.dump(current, f, indent=4)
        write_metrics({})
        return

    try:
        with open(BASELINE_FILE, "r") as f:
            baseline = json.load(f)
    except Exception as e:
        logging.error(f"Failed to read baseline: {e}")
        return

    diffs = {}
    for path, h in current.items():
        if path not in baseline: diffs[path] = "added"
        elif baseline[path] != h: diffs[path] = "modified"
    for path in baseline:
        if path not in current: diffs[path] = "deleted"

    write_metrics(diffs)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dirs', nargs='+', default=[])
    parser.add_argument('--interval', type=int, default=120)
    args = parser.parse_args()

    while True:
        run_fim(args.dirs)
        time.sleep(args.interval)

if __name__ == "__main__":
    main()