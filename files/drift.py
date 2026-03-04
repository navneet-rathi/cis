import os
import hashlib
import json
import argparse

# Default Configuration
BASELINE_FILE = "/var/lib/etc_baseline.json"
METRIC_FILE = "/var/lib/node_exporter/textfile_collector/etc_changes.prom"
EXCLUDED = {"/etc/os-release", "/etc/redhat-release", "/etc/system-release"}

def sha256(file_path):
    """Calculates SHA256, skipping symlinks and unreadable files."""
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
    """Scans provided directories and generates hashes for files."""
    data = {}
    # Ensure /etc is always included and paths are unique
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

def load_baseline():
    if os.path.exists(BASELINE_FILE):
        try:
            with open(BASELINE_FILE, "r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}
    return {}

def save_baseline(data):
    with open(BASELINE_FILE, "w") as f:
        json.dump(data, f, indent=4)

def write_metric(changed):
    """Writes the gauge to the Prometheus textfile collector path."""
    try:
        with open(METRIC_FILE, "w") as f:
            f.write("# HELP etc_file_changes_detected 1 if changes detected\n")
            f.write("# TYPE etc_file_changes_detected gauge\n")
            f.write(f"etc_file_changes_detected {1 if changed else 0}\n")
    except IOError as e:
        print(f"Error writing metric: {e}")

def main():
    parser = argparse.ArgumentParser(description="FIM Script for Prometheus")
    parser.add_argument('--dirs', nargs='+', default=[], help='Additional directories to scan')
    args = parser.parse_args()

    current = scan(args.dirs)
    baseline = load_baseline()

    # Compare dictionaries
    changed = current != baseline

    if changed:
        save_baseline(current)

    write_metric(changed)

if __name__ == "__main__":
    main()
