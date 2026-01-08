#!/usr/bin/env python3
"""
diff-fls-matches - Show human-readable diff for a single guideline.

This tool displays a detailed comparison between the mapping file and decision
for a specific guideline, including FLS content for added/removed sections.

Usage:
    uv run diff-fls-matches --standard misra-c --guideline "Rule 10.1" --batch 1
"""

import argparse
import sys
from pathlib import Path

from fls_tools.shared import VALID_STANDARDS, normalize_standard, get_project_root

from .shared import (
    load_comparison_data,
    load_fls_content,
    get_active_flags,
    normalize_applicability,
)


def print_match(match: dict, indent: str = "    ", root: Path | None = None) -> None:
    """Print a single match with optional FLS content."""
    fls_id = match.get("fls_id", "?")
    title = match.get("fls_title", match.get("title", "?"))
    score = match.get("score", 0)
    reason = match.get("reason", "")
    
    print(f"{indent}{fls_id}: {title} (score: {score:.2f})")
    if reason:
        # Wrap reason text
        lines = reason.split(". ")
        for line in lines[:3]:
            print(f"{indent}  {line.strip()}.")
        if len(lines) > 3:
            print(f"{indent}  ...")


def print_fls_section(fls_id: str, root: Path | None = None) -> None:
    """Print FLS section content."""
    content = load_fls_content(fls_id, root)
    if not content:
        print(f"      (FLS content not found)")
        return
    
    title = content.get("title", "")
    text = content.get("content", "")
    
    print(f"      Title: {title}")
    if text:
        # Show first 300 chars
        preview = text[:300].strip()
        if len(text) > 300:
            preview += "..."
        lines = preview.split("\n")
        for line in lines[:5]:
            print(f"      {line}")
        if len(lines) > 5:
            print(f"      ...")
    
    # Show rubric summary
    rubrics = content.get("rubrics", {})
    if rubrics:
        rubric_names = {
            "-1": "general",
            "-2": "legality_rules",
            "-3": "dynamic_semantics",
            "-4": "undefined_behavior",
        }
        parts = [f"{rubric_names.get(k, k)}:{len(v)}" for k, v in rubrics.items() if v]
        if parts:
            print(f"      Rubrics: {', '.join(parts)}")


def main():
    parser = argparse.ArgumentParser(
        description="Show detailed diff for a guideline's FLS matches."
    )
    parser.add_argument(
        "--standard",
        required=True,
        choices=VALID_STANDARDS,
        help="Standard to process (e.g., misra-c)",
    )
    parser.add_argument(
        "--guideline",
        required=True,
        help="Guideline ID (e.g., 'Rule 10.1')",
    )
    parser.add_argument(
        "--batch",
        required=True,
        type=int,
        help="Batch number",
    )
    parser.add_argument(
        "--show-content",
        action="store_true",
        help="Show FLS content for added/removed sections",
    )
    parser.add_argument(
        "--context",
        choices=["all_rust", "safe_rust", "both"],
        default="both",
        help="Which context to show (default: both)",
    )
    
    args = parser.parse_args()
    
    standard = normalize_standard(args.standard)
    root = get_project_root()
    
    # Load comparison data
    data = load_comparison_data(args.guideline, args.batch, root)
    if not data:
        print(f"ERROR: No comparison data found for {args.guideline} in batch {args.batch}", file=sys.stderr)
        sys.exit(1)
    
    print(f"=" * 80)
    print(f"GUIDELINE: {args.guideline} (Batch {args.batch})")
    print(f"=" * 80)
    print()
    
    # ADD-6 reference
    add6 = data.get("add6", {})
    print("ADD-6 Reference:")
    print(f"  all_rust: {add6.get('applicability_all_rust')} → {add6.get('adjusted_category')}")
    print(f"  safe_rust: {add6.get('applicability_safe_rust')} → {add6.get('adjusted_category')}")
    print(f"  Rationale codes: {', '.join(add6.get('rationale_codes', []))}")
    if add6.get("comment"):
        print(f"  Comment: {add6['comment']}")
    print()
    
    # Flags
    flags = data.get("flags", {})
    active = get_active_flags(flags)
    print(f"Flags ({len(active)}): {', '.join(active)}")
    print()
    
    contexts = ["all_rust", "safe_rust"] if args.context == "both" else [args.context]
    
    for ctx in contexts:
        print(f"-" * 40)
        print(f"CONTEXT: {ctx}")
        print(f"-" * 40)
        
        mapping = data.get("mapping", {}).get(ctx, {})
        decision = data.get("decision", {}).get(ctx, {})
        comparison = data.get("comparison", {}).get(ctx, {})
        
        # Categorization
        print()
        print("Categorization:")
        print(f"  Mapping:  applicability={mapping.get('applicability')}, "
              f"category={mapping.get('adjusted_category')}, "
              f"rationale={mapping.get('rationale_type')}")
        print(f"  Decision: applicability={decision.get('applicability')}, "
              f"category={decision.get('adjusted_category')}, "
              f"rationale={decision.get('rationale_type')}")
        
        if comparison.get("applicability_changed"):
            print(f"  ⚠ Applicability changed: {comparison['applicability_mapping_to_decision']}")
        if comparison.get("adjusted_category_changed"):
            print(f"  ⚠ Category changed: {comparison['adjusted_category_mapping_to_decision']}")
        if comparison.get("rationale_type_changed"):
            print(f"  ⚠ Rationale changed: {comparison['rationale_type_mapping_to_decision']}")
        
        # ADD-6 comparison
        if comparison.get("applicability_differs_from_add6"):
            add6_app = add6.get(f"applicability_{ctx}")
            dec_app = decision.get("applicability")
            print(f"  ⚠ Differs from ADD-6: decision={dec_app}, ADD-6={add6_app}")
        
        # FLS changes
        print()
        print(f"FLS Changes (mapping: {comparison.get('match_count_mapping', 0)} → "
              f"decision: {comparison.get('match_count_decision', 0)}, "
              f"net: {comparison.get('net_fls_change', 0):+d}):")
        
        added = comparison.get("fls_added", [])
        removed = comparison.get("fls_removed", [])
        retained = comparison.get("fls_retained", [])
        
        if removed:
            print()
            print(f"  REMOVED ({len(removed)}):")
            for fls_id in removed:
                # Find match in mapping
                match = next(
                    (m for m in mapping.get("accepted_matches", []) if m.get("fls_id") == fls_id),
                    {"fls_id": fls_id}
                )
                print(f"    - {fls_id}: {match.get('fls_title', '?')}")
                if args.show_content:
                    print_fls_section(fls_id, root)
        
        if added:
            print()
            print(f"  ADDED ({len(added)}):")
            for fls_id in added:
                # Find match in decision
                match = next(
                    (m for m in decision.get("accepted_matches", []) if m.get("fls_id") == fls_id),
                    {"fls_id": fls_id}
                )
                print(f"    + {fls_id}: {match.get('fls_title', '?')} (score: {match.get('score', 0):.2f})")
                if match.get("reason"):
                    reason = match["reason"][:200]
                    if len(match["reason"]) > 200:
                        reason += "..."
                    print(f"      Reason: {reason}")
                if args.show_content:
                    print_fls_section(fls_id, root)
        
        if retained:
            print()
            print(f"  RETAINED ({len(retained)}):")
            for fls_id in retained:
                match = next(
                    (m for m in decision.get("accepted_matches", []) if m.get("fls_id") == fls_id),
                    {"fls_id": fls_id}
                )
                print(f"    = {fls_id}: {match.get('fls_title', '?')}")
        
        print()
    
    # Notes from decision
    for ctx in contexts:
        decision = data.get("decision", {}).get(ctx, {})
        if decision.get("notes"):
            print(f"Decision notes ({ctx}):")
            print(f"  {decision['notes'][:500]}")
            print()


if __name__ == "__main__":
    main()
