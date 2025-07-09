# File: tools/export_mermaid_graph.py
# Purpose: Generate a highly visual, accurate Mermaid graph of file relationships with smarter orphan detection and grouping

import json
from pathlib import Path
from collections import defaultdict

INPUT = Path("tools/metadata_with_reverse_downstream.json")
OUTPUT = Path("docs/graph_clean.mmd")

MERMAID_HEADER = """```mermaid
graph TD
"""
MERMAID_FOOTER = "```\n"

# File type groups based on directory
GROUPS = {
    "agent": "#bae6fd",
    "critic": "#fef9c3",
    "route": "#fde68a",
    "service": "#dcfce7",
    "tool": "#e0e7ff",
    "test": "#fcdcdc",
    "core": "#fef2f2",
    "script": "#fff3e0",
    "memory": "#ede9fe",
}


def get_node_style(file):
    if "critic_agent" in file or "critic" in file:
        return "critic"
    for name in GROUPS:
        if f"/{name}" in file or file.startswith(f"{name}_"):
            return name
    return "unknown"


def to_mermaid_id(name):
    return name.replace(".py", "").replace("/", "_").replace(".", "_")


def generate_graph(metadata):
    edges = set()
    styles = {}
    label_map = {}
    reverse_index = defaultdict(set)
    groups = defaultdict(list)

    for entry in metadata:
        src = to_mermaid_id(entry['file'])
        label_map[src] = entry['file']
        tag = get_node_style(entry['directory'] + "/" + entry['file'])
        groups[tag].append(src)
        styles[src] = f"fill:{GROUPS.get(tag, '#e5e7eb')}"

        downstream = entry.get("downstream", [])
        for dst in downstream:
            dst_node = to_mermaid_id(dst)
            edges.add((src, dst_node))
            reverse_index[dst_node].add(src)

    lines = []
    for a, b in sorted(edges):
        lines.append(f"  {a} --> {b}")

    for node, color in styles.items():
        lines.append(f"  style {node} {color}")

    # Mark truly orphaned nodes (not used, and use nothing)
    lines.append("\n%% Orphaned nodes")
    for node in label_map:
        if node not in reverse_index and all(node != a for a, _ in edges):
            lines.append(f"  class {node} orphan")

    lines.append("  classDef orphan stroke:#f87171,stroke-width:2px;")

    return lines, groups


def build_subgraphs(groups):
    lines = []
    for group, nodes in sorted(groups.items()):
        if not nodes:
            continue
        lines.append(f"  subgraph {group.title()}")
        for node in sorted(nodes):
            lines.append(f"    {node}")
        lines.append("  end")
    return lines


def main():
    with open(INPUT, "r") as f:
        metadata = json.load(f)

    edge_lines, groups = generate_graph(metadata)
    subgraph_lines = build_subgraphs(groups)

    with open(OUTPUT, "w") as f:
        f.write(MERMAID_HEADER)
        f.write("\n".join(edge_lines))
        f.write("\n")
        f.write("\n".join(subgraph_lines))
        f.write("\n" + MERMAID_FOOTER)

    print(f"✅ Clean Mermaid graph written to {OUTPUT}")

if __name__ == "__main__":
    main()
