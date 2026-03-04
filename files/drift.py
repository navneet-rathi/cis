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

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def sha256(file_path):
    if os.path.islink(file_path):
        return None
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
        if not os.path.isdir(target_dir):
            continue
        for root, _, files in os.walk(target_dir):
            for name in files:
                path = os.path.join(root, name)
                if path in EXCLUDED:
                    continue
                file_hash = sha256(path)
                if file_hash:
                    data[path] = file_hash
    return data

def write_metric(changed):
    try:
        # Write to a temp file first then rename to prevent Prometheus from reading a partial file
        temp_file = METRIC_FILE + ".tmp"
        with open(temp_file, "w") as f:
            f.write("# HELP etc_file_changes_detected 1 if changes detected\n")
            f.write("# TYPE etc_file_changes_detected gauge\n")
            f.write(f"etc_file_changes_detected {1 if changed else 0}\n")
        os.replace(temp_file, METRIC_FILE)
    except IOError as e:
        logging.error(f"Error writing metric: {e}")

def run_fim(directories):
    logging.info("Starting FIM scan...")
    current = scan(directories)
    
    # Load baseline
    baseline = {}
    if os.path.exists(BASELINE_FILE):
        try:
            with open(BASELINE_FILE, "r") as f:
                baseline = json.load(f)
        except:
            pass

    changed = current != baseline

    if changed:
        logging.warning("Changes detected in monitored directories!")
        with open(BASELINE_FILE, "w") as f:
            json.dump(current, f)
    
    write_metric(changed)
    logging.info(f"Scan complete. Status: {'Changed' if changed else 'No Change'}")

def main():
    parser = argparse.ArgumentParser(description="Continuous FIM Script")
    parser.add_argument('--dirs', nargs='+', default=[], help='Additional directories to scan')
    parser.add_argument('--interval', type=int, default=60, help='Seconds between scans')
    args = parser.parse_args()

    logging.info(f"FIM Monitor started. Interval: {args.interval}s")
    
    try:
        while True:
            run_fim(args.dirs)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        logging.info("Monitor stopped by user.")

if __name__ == "__main__":
    main()