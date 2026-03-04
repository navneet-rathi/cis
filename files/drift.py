import os
import hashlib
import json
import argparse
import time
import logging

# Configuration
BASELINE_FILE = "/var/lib/etc_baseline.json"
METRIC_FILE = "/var/lib/node_exporter/textfile_collector/etc_changes.prom"
EXCLUDED = {"/etc/os-release", "/etc/redhat-release", "/etc/system-release"}

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

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
                if path in EXCLUDED: continue
                h = sha256(path)
                if h: data[path] = h
    return data

def write_metrics(diffs):
    """Writes detailed metrics with file labels."""
    try:
        temp_file = METRIC_FILE + ".tmp"
        with open(temp_file, "w") as f:
            f.write("# HELP etc_file_deviation Details of changed files\n")
            f.write("# TYPE etc_file_deviation gauge\n")
            
            if not diffs:
                # If no changes, ensure the metric exists but is set to 0
                f.write("etc_file_deviation{file=\"none\",action=\"none\"} 0\n")
            else:
                for file_path, action in diffs.items():
                    # Prometheus labels use double quotes; we escape path backslashes
                    safe_path = file_path.replace("\\", "\\\\")
                    f.write(f'etc_file_deviation{{file="{safe_path}",action="{action}"}} 1\n')
        
        os.replace(temp_file, METRIC_FILE)
    except IOError as e:
        logging.error(f"Error writing metric: {e}")

def run_fim(directories):
    current = scan(directories)
    baseline = {}
    
    if os.path.exists(BASELINE_FILE):
        try:
            with open(BASELINE_FILE, "r") as f:
                baseline = json.load(f)
        except: pass

    # Identify specific deviations
    diffs = {}
    
    # Check for modifications or additions
    for path, h in current.items():
        if path not in baseline:
            diffs[path] = "added"
        elif baseline[path] != h:
            diffs[path] = "modified"
            
    # Check for deletions
    for path in baseline:
        if path not in current:
            diffs[path] = "deleted"

    if diffs:
        logging.warning(f"Deviations found: {len(diffs)} files")
        with open(BASELINE_FILE, "w") as f:
            json.dump(current, f)
    
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