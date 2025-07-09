# File: discover_features.py
# Directory: scripts
# Purpose: # Purpose: Extract and identify routes and documentation strings from project files for API documentation generation.
#
# Upstream:
#   - ENV: —
#   - Imports: os, re
#
# Downstream:
#   - —
#
# Contents:
#   - find_routes_and_docs()







#!/usr/bin/env python3
import os
import re

def find_routes_and_docs(root_dir):
    route_pattern = re.compile(r"@app\.(get|post|put|delete)\(['\"](.+?)['\"]")
    docstring_pattern = re.compile(r"\"\"\"([\s\S]*?)\"\"\"", re.MULTILINE)
    features = []

    for subdir, _, files in os.walk(root_dir):
        for filename in files:
            if filename.endswith('.py'):
                path = os.path.join(subdir, filename)
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
                for match in route_pattern.finditer(content):
                    method, route = match.groups()
                    doc_match = docstring_pattern.search(content, match.end())
                    doc = doc_match.group(1).strip() if doc_match else ''
                    features.append({'file': path, 'method': method.upper(), 'route': route, 'doc': doc})
    return features

if __name__ == '__main__':
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    routes = find_routes_and_docs(root)
    for r in routes:
        print(f"{r['method']} {r['route']} — {r['file']}\n  {r['doc']}\n")