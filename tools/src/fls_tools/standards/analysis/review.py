#!/usr/bin/env python3
"""
review-outliers - Interactive human review tool for outlier analysis.

This tool allows humans to review and make decisions on outlier analysis,
recording per-aspect and per-FLS-ID decisions (per-context) in the outlier files.

Modes:
    --interactive  Interactive prompts for each decision (batch or single)
    --show         Display LLM analysis without making decisions
    CLI flags      Direct accept/reject via command line

Usage:
    # Interactive mode for a batch (prompts for each guideline)
    uv run review-outliers --standard misra-c --batch 1

    # Interactive mode for all batches
    uv run review-outliers --standard misra-c --all

    # Resume from a specific guideline
    uv run review-outliers --standard misra-c --batch 1 --start-from "Rule 10.5"

    # Show LLM analysis for a guideline
    uv run review-outliers --standard misra-c --guideline "Rule 10.1" --show

    # Accept all aspects for a guideline
    uv run review-outliers --standard misra-c --guideline "Rule 10.1" --accept-all

    # Accept FLS removal for specific context
    uv run review-outliers --standard misra-c --guideline "Rule 10.1" \\
        --accept-removal fls_xyz123 --context all_rust --reason "Over-matched"

    # Bulk accept a systematic removal across all guidelines for a context
    uv run review-outliers --standard misra-c --bulk-accept-removal fls_xyz123 \\
        --context all_rust --reason "Over-matched in initial mapping"
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

from fls_tools.shared import VALID_STANDARDS, normalize_standard, get_project_root

from .shared import (
    get_outlier_analysis_dir,
    load_outlier_analysis,
    save_outlier_analysis,
    load_review_state,
    save_review_state,
    recompute_review_summary,
    get_active_flags,
    filename_to_guideline,
    BATCH_EXPECTED_PATTERNS,
)


VALID_CONTEXTS = ["all_rust", "safe_rust", "both"]


def create_human_review_section() -> dict:
    """Create initial human_review section structure."""
    return {
        "overall_status": "pending",
        "reviewed_at": None,
        "categorization": None,
        "fls_removals": {},  # {fls_id: {contexts: [...], decisions: {ctx: {decision, reason}}}}
        "fls_additions": {},
        "add6_divergence": None,
        "specificity": None,
        "notes": None,
    }


def compute_overall_status(human_review: dict, flags: dict, llm_analysis: dict) -> str:
    """
    Compute overall review status based on individual decisions.
    
    Returns 'fully_reviewed', 'partial', or 'pending'.
    """
    pending_aspects = 0
    total_aspects = 0
    
    # Check categorization if relevant flags set
    if flags.get("rationale_type_changed") or flags.get("batch_pattern_outlier"):
        total_aspects += 1
        if not human_review.get("categorization"):
            pending_aspects += 1
    
    # Check FLS removals - need per-context decisions
    for fls_id, item in human_review.get("fls_removals", {}).items():
        contexts = item.get("contexts", [])
        decisions = item.get("decisions", {})
        for ctx in contexts:
            total_aspects += 1
            if not decisions.get(ctx, {}).get("decision"):
                pending_aspects += 1
    
    # Check FLS additions - need per-context decisions
    for fls_id, item in human_review.get("fls_additions", {}).items():
        contexts = item.get("contexts", [])
        decisions = item.get("decisions", {})
        for ctx in contexts:
            total_aspects += 1
            if not decisions.get(ctx, {}).get("decision"):
                pending_aspects += 1
    
    # Check ADD-6 divergence
    if flags.get("applicability_differs_from_add6") or flags.get("adjusted_category_differs_from_add6"):
        total_aspects += 1
        if not human_review.get("add6_divergence"):
            pending_aspects += 1
    
    # Check specificity if flag set
    if flags.get("specificity_decreased"):
        total_aspects += 1
        if not human_review.get("specificity"):
            pending_aspects += 1
    
    if total_aspects == 0:
        return "fully_reviewed"
    if pending_aspects == 0:
        return "fully_reviewed"
    if pending_aspects < total_aspects:
        return "partial"
    return "pending"


def display_llm_analysis(analysis: dict) -> None:
    """Display LLM analysis in a readable format."""
    llm = analysis.get("llm_analysis", {})
    if not llm:
        print("  No LLM analysis recorded.")
        return
    
    print(f"\n{'='*60}")
    print(f"LLM ANALYSIS: {analysis.get('guideline_id')}")
    print(f"{'='*60}")
    
    print(f"\nOverall Recommendation: {llm.get('overall_recommendation', 'N/A')}")
    print(f"\nSummary:\n  {llm.get('summary', 'N/A')}")
    
    # Categorization
    cat = llm.get("categorization")
    if cat:
        print(f"\n--- Categorization ---")
        print(f"  Verdict: {cat.get('verdict')}")
        print(f"  Reasoning: {cat.get('reasoning')}")
    
    # FLS Removals
    removals = llm.get("fls_removals")
    if removals:
        print(f"\n--- FLS Removals ---")
        print(f"  Verdict: {removals.get('verdict')}")
        print(f"  Reasoning: {removals.get('reasoning')}")
        per_id = removals.get("per_id", {})
        if per_id:
            print(f"  Per-ID:")
            for fls_id, info in per_id.items():
                contexts = info.get("contexts", [])
                print(f"    {fls_id} (contexts: {', '.join(contexts)}):")
                print(f"      Title: {info.get('title')}")
                print(f"      Category: {info.get('category')}")
                orig = info.get('original_reason', 'N/A') or 'N/A'
                print(f"      Original reason: {orig[:100]}...")
                decisions = info.get("removal_decisions", {})
                for ctx, justification in decisions.items():
                    print(f"      LLM justification ({ctx}): {justification}")
    
    # FLS Additions
    additions = llm.get("fls_additions")
    if additions:
        print(f"\n--- FLS Additions ---")
        print(f"  Verdict: {additions.get('verdict')}")
        print(f"  Reasoning: {additions.get('reasoning')}")
        per_id = additions.get("per_id", {})
        if per_id:
            print(f"  Per-ID:")
            for fls_id, info in per_id.items():
                contexts = info.get("contexts", [])
                print(f"    {fls_id} (contexts: {', '.join(contexts)}):")
                print(f"      Title: {info.get('title')}")
                print(f"      Category: {info.get('category')}")
                new_reason = info.get('new_reason', 'N/A') or 'N/A'
                print(f"      New reason: {new_reason[:100]}...")
                decisions = info.get("addition_decisions", {})
                for ctx, justification in decisions.items():
                    print(f"      LLM justification ({ctx}): {justification}")
    
    # ADD-6 Divergence
    add6 = llm.get("add6_divergence")
    if add6:
        print(f"\n--- ADD-6 Divergence ---")
        print(f"  Verdict: {add6.get('verdict')}")
        print(f"  Reasoning: {add6.get('reasoning')}")
    
    # Specificity
    spec = llm.get("specificity")
    if spec:
        print(f"\n--- Specificity ---")
        print(f"  Verdict: {spec.get('verdict')}")
        print(f"  Reasoning: {spec.get('reasoning')}")
        lost = spec.get("lost_paragraphs", [])
        if lost:
            print(f"  Lost paragraphs:")
            for p in lost[:5]:  # Limit display
                print(f"    - {p.get('fls_id')} ({p.get('fls_title')})")
    
    # Routine pattern
    if llm.get("routine_pattern"):
        print(f"\nRoutine Pattern: {llm.get('routine_pattern')}")
    
    # Notes
    if llm.get("notes"):
        print(f"\nNotes: {llm.get('notes')}")
    
    print(f"\n{'='*60}")


def display_pending_decisions(analysis: dict) -> None:
    """Display what decisions still need to be made."""
    human_review = analysis.get("human_review")
    if not human_review:
        print("  No human review started yet.")
        return
    
    flags = analysis.get("flags", {})
    active = get_active_flags(flags)
    
    print(f"\nActive flags: {', '.join(active) if active else 'None'}")
    print(f"Overall status: {human_review.get('overall_status')}")
    
    pending = []
    
    # Check categorization
    if (flags.get("rationale_type_changed") or flags.get("batch_pattern_outlier")) and not human_review.get("categorization"):
        pending.append("categorization")
    
    # Check FLS removals
    for fls_id, item in human_review.get("fls_removals", {}).items():
        contexts = item.get("contexts", [])
        decisions = item.get("decisions", {})
        for ctx in contexts:
            if not decisions.get(ctx, {}).get("decision"):
                pending.append(f"fls_removal:{fls_id}:{ctx}")
    
    # Check FLS additions
    for fls_id, item in human_review.get("fls_additions", {}).items():
        contexts = item.get("contexts", [])
        decisions = item.get("decisions", {})
        for ctx in contexts:
            if not decisions.get(ctx, {}).get("decision"):
                pending.append(f"fls_addition:{fls_id}:{ctx}")
    
    # Check ADD-6 divergence
    if (flags.get("applicability_differs_from_add6") or flags.get("adjusted_category_differs_from_add6")) and not human_review.get("add6_divergence"):
        pending.append("add6_divergence")
    
    # Check specificity
    if flags.get("specificity_decreased") and not human_review.get("specificity"):
        pending.append("specificity")
    
    if pending:
        print(f"\nPending decisions ({len(pending)}):")
        for p in pending:
            print(f"  - {p}")
    else:
        print("\nAll decisions complete!")


def initialize_fls_structures(human_review: dict, llm_analysis: dict, comparison: dict) -> None:
    """
    Initialize FLS removal/addition structures from LLM analysis or comparison data.
    
    Uses per-context structure: {fls_id: {contexts: [...], decisions: {ctx: {decision, reason}}}}
    """
    # Initialize from LLM analysis per_id (if available)
    llm_removals = llm_analysis.get("fls_removals", {}).get("per_id", {})
    llm_additions = llm_analysis.get("fls_additions", {}).get("per_id", {})
    
    # FLS Removals
    for fls_id, info in llm_removals.items():
        if fls_id not in human_review["fls_removals"]:
            human_review["fls_removals"][fls_id] = {
                "contexts": info.get("contexts", []),
                "title": info.get("title"),
                "category": info.get("category"),
                "decisions": {},
            }
    
    # Also check comparison data for any missing
    for ctx in ["all_rust", "safe_rust"]:
        ctx_comp = comparison.get(ctx, {})
        for fls_id in ctx_comp.get("fls_removed", []):
            if fls_id not in human_review["fls_removals"]:
                human_review["fls_removals"][fls_id] = {
                    "contexts": [ctx],
                    "title": None,
                    "category": None,
                    "decisions": {},
                }
            elif ctx not in human_review["fls_removals"][fls_id]["contexts"]:
                human_review["fls_removals"][fls_id]["contexts"].append(ctx)
    
    # FLS Additions
    for fls_id, info in llm_additions.items():
        if fls_id not in human_review["fls_additions"]:
            human_review["fls_additions"][fls_id] = {
                "contexts": info.get("contexts", []),
                "title": info.get("title"),
                "category": info.get("category"),
                "decisions": {},
            }
    
    # Also check comparison data
    for ctx in ["all_rust", "safe_rust"]:
        ctx_comp = comparison.get(ctx, {})
        for fls_id in ctx_comp.get("fls_added", []):
            if fls_id not in human_review["fls_additions"]:
                human_review["fls_additions"][fls_id] = {
                    "contexts": [ctx],
                    "title": None,
                    "category": None,
                    "decisions": {},
                }
            elif ctx not in human_review["fls_additions"][fls_id]["contexts"]:
                human_review["fls_additions"][fls_id]["contexts"].append(ctx)


def apply_fls_decision(
    human_review: dict,
    fls_dict: dict,
    fls_id: str,
    context: str,
    decision: str,
    reason: str | None,
) -> bool:
    """
    Apply a decision to an FLS ID for a specific context.
    
    Returns True if successful, False if FLS ID or context not found.
    """
    if fls_id not in fls_dict:
        return False
    
    item = fls_dict[fls_id]
    contexts = item.get("contexts", [])
    
    if context == "both":
        # Apply to all contexts where this FLS ID appears
        for ctx in contexts:
            if "decisions" not in item:
                item["decisions"] = {}
            item["decisions"][ctx] = {"decision": decision, "reason": reason}
        return True
    elif context in contexts:
        if "decisions" not in item:
            item["decisions"] = {}
        item["decisions"][context] = {"decision": decision, "reason": reason}
        return True
    else:
        return False


# =============================================================================
# Interactive Mode Functions
# =============================================================================

def get_guidelines_for_batch(batch: int, root: Path) -> list[str]:
    """Get all guideline IDs in a specific batch, sorted."""
    outlier_dir = get_outlier_analysis_dir(root)
    guidelines = []
    
    import json
    for path in outlier_dir.glob("*.json"):
        try:
            with open(path) as f:
                data = json.load(f)
            if data.get("batch") == batch:
                guidelines.append(data.get("guideline_id"))
        except (json.JSONDecodeError, KeyError):
            continue
    
    return sorted(guidelines)


def get_all_guidelines(root: Path) -> list[tuple[int, str]]:
    """Get all (batch, guideline_id) pairs, sorted by batch then guideline."""
    outlier_dir = get_outlier_analysis_dir(root)
    guidelines = []
    
    import json
    for path in outlier_dir.glob("*.json"):
        try:
            with open(path) as f:
                data = json.load(f)
            batch = data.get("batch", 0)
            guideline_id = data.get("guideline_id")
            if guideline_id:
                guidelines.append((batch, guideline_id))
        except (json.JSONDecodeError, KeyError):
            continue
    
    return sorted(guidelines)


def get_pending_guidelines(root: Path, batch: int | None = None) -> list[str]:
    """Get guidelines that haven't been fully reviewed yet."""
    outlier_dir = get_outlier_analysis_dir(root)
    pending = []
    
    import json
    for path in outlier_dir.glob("*.json"):
        try:
            with open(path) as f:
                data = json.load(f)
            if batch is not None and data.get("batch") != batch:
                continue
            human_review = data.get("human_review")
            if human_review is None or human_review.get("overall_status") != "fully_reviewed":
                pending.append(data.get("guideline_id"))
        except (json.JSONDecodeError, KeyError):
            continue
    
    return sorted(pending)


def prompt_yes_no_skip_quit(prompt: str) -> str:
    """
    Prompt user for y/n/s/q response.
    
    Returns: 'yes', 'no', 'skip', or 'quit'
    """
    while True:
        try:
            response = input(f"{prompt} [y]es | [n]o | [s]kip | [q]uit > ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n")
            return "quit"
        
        if response in ("y", "yes"):
            return "yes"
        elif response in ("n", "no"):
            return "no"
        elif response in ("s", "skip"):
            return "skip"
        elif response in ("q", "quit"):
            return "quit"
        else:
            print("  Invalid input. Please enter y, n, s, or q.")


def prompt_yes_no_na(prompt: str, allow_na: bool = True) -> str:
    """
    Prompt user for y/n/n_a response.
    
    Returns: 'yes', 'no', 'n_a', or 'quit'
    """
    options = "[y]es | [n]o | [n/a]" if allow_na else "[y]es | [n]o"
    while True:
        try:
            response = input(f"{prompt} {options} > ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n")
            return "quit"
        
        if response in ("y", "yes"):
            return "yes"
        elif response in ("n", "no"):
            return "no"
        elif allow_na and response in ("na", "n/a", "n_a"):
            return "n_a"
        elif response in ("q", "quit"):
            return "quit"
        else:
            valid = "y, n, n/a, or q" if allow_na else "y, n, or q"
            print(f"  Invalid input. Please enter {valid}.")


def prompt_accept_all(prompt: str) -> str:
    """
    Prompt user for accept-all option.
    
    Returns: 'yes', 'no', 'all', or 'quit'
    """
    while True:
        try:
            response = input(f"{prompt} [y]es | [n]o | [a]ll | [q]uit > ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n")
            return "quit"
        
        if response in ("y", "yes"):
            return "yes"
        elif response in ("n", "no"):
            return "no"
        elif response in ("a", "all"):
            return "all"
        elif response in ("q", "quit"):
            return "quit"
        else:
            print("  Invalid input. Please enter y, n, a, or q.")


def display_header(guideline_id: str, batch: int, current: int, total: int) -> None:
    """Display the header for a guideline review."""
    batch_name = BATCH_EXPECTED_PATTERNS.get(batch, {}).get("name", "Unknown")
    print()
    print("╔" + "═" * 78 + "╗")
    print(f"║  Outlier Review: {guideline_id:<40} ({current}/{total})".ljust(79) + "║")
    print(f"║  Batch: {batch} ({batch_name})".ljust(79) + "║")
    print("╚" + "═" * 78 + "╝")


def display_quick_reference(analysis: dict) -> None:
    """Display quick reference info for the guideline."""
    add6 = analysis.get("add6", {})
    comparison = analysis.get("comparison", {})
    flags = analysis.get("flags", {})
    active_flags = get_active_flags(flags)
    
    print(f"\nFlags: {', '.join(active_flags) if active_flags else 'None'}")
    print(f"\nQuick Reference:")
    print(f"  ADD-6: applicability_all_rust={add6.get('applicability_all_rust', 'N/A')}, "
          f"applicability_safe_rust={add6.get('applicability_safe_rust', 'N/A')}")
    
    # Show decision summary from comparison
    for ctx in ["all_rust", "safe_rust"]:
        ctx_comp = comparison.get(ctx, {})
        app_changed = ctx_comp.get("applicability_changed", False)
        rat_changed = ctx_comp.get("rationale_type_changed", False)
        app_trans = ctx_comp.get("applicability_mapping_to_decision") or "no change"
        rat_trans = ctx_comp.get("rationale_type_mapping_to_decision") or "no change"
        print(f"  Decision ({ctx}): applicability {app_trans}, rationale {rat_trans}")


def interactive_review_guideline(
    guideline_id: str,
    root: Path,
    current: int,
    total: int,
    dry_run: bool = False,
) -> str:
    """
    Interactively review a single guideline.
    
    Returns: 'continue', 'skip', or 'quit'
    """
    analysis = load_outlier_analysis(guideline_id, root)
    if not analysis:
        print(f"  WARNING: No analysis found for {guideline_id}, skipping")
        return "continue"
    
    batch = analysis.get("batch", 0)
    flags = analysis.get("flags", {})
    llm_analysis = analysis.get("llm_analysis", {})
    comparison = analysis.get("comparison", {})
    
    # Display header
    display_header(guideline_id, batch, current, total)
    display_quick_reference(analysis)
    
    # Initialize human_review if needed
    if analysis.get("human_review") is None:
        analysis["human_review"] = create_human_review_section()
    
    human_review = analysis["human_review"]
    initialize_fls_structures(human_review, llm_analysis, comparison)
    
    # Check if already fully reviewed
    current_status = compute_overall_status(human_review, flags, llm_analysis)
    if current_status == "fully_reviewed":
        print(f"\n✓ Already fully reviewed")
        response = prompt_yes_no_skip_quit("Re-review this guideline?")
        if response == "quit":
            return "quit"
        elif response in ("no", "skip"):
            return "continue"
        # Otherwise continue to re-review
    
    # Offer accept-all option first
    llm_recommendation = llm_analysis.get("overall_recommendation", "N/A")
    print(f"\nLLM Recommendation: {llm_recommendation}")
    print(f"Summary: {llm_analysis.get('summary', 'N/A')}")
    
    response = prompt_accept_all("\nAccept all LLM recommendations?")
    if response == "quit":
        return "quit"
    elif response == "all":
        # Accept everything
        _accept_all(human_review, flags, llm_analysis)
        human_review["overall_status"] = "fully_reviewed"
        human_review["reviewed_at"] = datetime.utcnow().isoformat() + "Z"
        if not dry_run:
            save_outlier_analysis(guideline_id, analysis, root)
        print(f"\n✓ {guideline_id}: Accepted all")
        _wait_for_enter()
        return "continue"
    elif response == "skip":
        return "continue"
    
    # Detailed review
    quit_requested = False
    
    # 1. Categorization
    if flags.get("rationale_type_changed") or flags.get("batch_pattern_outlier"):
        quit_requested = _review_categorization(human_review, llm_analysis, comparison, flags)
        if quit_requested:
            return "quit"
    
    # 2. FLS Removals
    if flags.get("fls_removed"):
        quit_requested = _review_fls_removals(human_review, llm_analysis, comparison)
        if quit_requested:
            return "quit"
    
    # 3. FLS Additions
    if flags.get("fls_added"):
        quit_requested = _review_fls_additions(human_review, llm_analysis, comparison)
        if quit_requested:
            return "quit"
    
    # 4. Specificity
    if flags.get("specificity_decreased"):
        quit_requested = _review_specificity(human_review, llm_analysis)
        if quit_requested:
            return "quit"
    
    # 5. ADD-6 Divergence
    if flags.get("applicability_differs_from_add6") or flags.get("adjusted_category_differs_from_add6"):
        quit_requested = _review_add6_divergence(human_review, llm_analysis, analysis.get("add6", {}))
        if quit_requested:
            return "quit"
    
    # Update status and save
    human_review["overall_status"] = compute_overall_status(human_review, flags, llm_analysis)
    human_review["reviewed_at"] = datetime.utcnow().isoformat() + "Z"
    
    if not dry_run:
        save_outlier_analysis(guideline_id, analysis, root)
    
    # Show summary
    _display_review_summary(guideline_id, human_review, flags)
    _wait_for_enter()
    
    return "continue"


def _accept_all(human_review: dict, flags: dict, llm_analysis: dict) -> None:
    """Accept all aspects based on LLM recommendations."""
    # Categorization
    if flags.get("rationale_type_changed") or flags.get("batch_pattern_outlier"):
        human_review["categorization"] = {
            "decision": "accept",
            "reason": "Accepted per LLM recommendation",
        }
    
    # FLS Removals
    for fls_id, item in human_review.get("fls_removals", {}).items():
        for ctx in item.get("contexts", []):
            if "decisions" not in item:
                item["decisions"] = {}
            item["decisions"][ctx] = {
                "decision": "accept",
                "reason": "Accepted per LLM recommendation",
            }
    
    # FLS Additions
    for fls_id, item in human_review.get("fls_additions", {}).items():
        for ctx in item.get("contexts", []):
            if "decisions" not in item:
                item["decisions"] = {}
            item["decisions"][ctx] = {
                "decision": "accept",
                "reason": "Accepted per LLM recommendation",
            }
    
    # Specificity
    if flags.get("specificity_decreased"):
        human_review["specificity"] = {
            "decision": "accept",
            "reason": "Accepted per LLM recommendation",
        }
    
    # ADD-6 Divergence
    if flags.get("applicability_differs_from_add6") or flags.get("adjusted_category_differs_from_add6"):
        human_review["add6_divergence"] = {
            "decision": "accept",
            "reason": "Accepted per LLM recommendation",
        }


def _review_categorization(human_review: dict, llm_analysis: dict, comparison: dict, flags: dict) -> bool:
    """Review categorization changes. Returns True if quit requested."""
    print()
    print("═" * 78)
    print("CATEGORIZATION CHANGE")
    print("═" * 78)
    
    cat = llm_analysis.get("categorization", {})
    print(f"LLM Verdict: {cat.get('verdict', 'N/A')}")
    print(f"LLM Reasoning: {cat.get('reasoning', 'N/A')}")
    
    # Show changes per context
    for ctx in ["all_rust", "safe_rust"]:
        ctx_comp = comparison.get(ctx, {})
        app_trans = ctx_comp.get("applicability_mapping_to_decision") or "no change"
        rat_trans = ctx_comp.get("rationale_type_mapping_to_decision") or "no change"
        print(f"\n  {ctx}: applicability {app_trans}, rationale {rat_trans}")
    
    response = prompt_yes_no_skip_quit("\nAccept categorization?")
    if response == "quit":
        return True
    elif response == "skip":
        pass  # Leave as-is
    elif response == "yes":
        human_review["categorization"] = {"decision": "accept", "reason": None}
    elif response == "no":
        human_review["categorization"] = {"decision": "reject", "reason": None}
    
    return False


def _review_fls_removals(human_review: dict, llm_analysis: dict, comparison: dict) -> bool:
    """Review FLS removals. Returns True if quit requested."""
    removals = llm_analysis.get("fls_removals", {})
    per_id = removals.get("per_id", {})
    
    if not human_review.get("fls_removals"):
        return False
    
    removal_count = sum(len(item.get("contexts", [])) for item in human_review["fls_removals"].values())
    if removal_count == 0:
        return False
    
    print()
    print("═" * 78)
    print(f"FLS REMOVALS ({removal_count} context decisions)")
    print("═" * 78)
    print(f"LLM Verdict: {removals.get('verdict', 'N/A')}")
    print(f"LLM Reasoning: {removals.get('reasoning', 'N/A')}")
    
    idx = 0
    for fls_id, item in human_review["fls_removals"].items():
        contexts = item.get("contexts", [])
        llm_info = per_id.get(fls_id, {})
        
        for ctx in contexts:
            idx += 1
            print(f"\n  [{idx}] {fls_id}: {item.get('title', 'Unknown')} (category: {item.get('category')})")
            print(f"      Context: {ctx}")
            
            # Get LLM justification for this context
            removal_decisions = llm_info.get("removal_decisions", {})
            justification = removal_decisions.get(ctx, "No justification provided")
            print(f"      LLM justification: {justification}")
            
            # Check if already decided
            existing = item.get("decisions", {}).get(ctx, {}).get("decision")
            if existing:
                print(f"      [Already decided: {existing}]")
                response = prompt_yes_no_skip_quit(f"      Change decision for {ctx}?")
                if response == "quit":
                    return True
                elif response in ("no", "skip"):
                    continue
            
            response = prompt_yes_no_na(f"      Accept removal for {ctx}?", allow_na=(ctx not in contexts))
            if response == "quit":
                return True
            elif response == "n_a":
                continue
            else:
                if "decisions" not in item:
                    item["decisions"] = {}
                item["decisions"][ctx] = {
                    "decision": "accept" if response == "yes" else "reject",
                    "reason": None,
                }
    
    return False


def _review_fls_additions(human_review: dict, llm_analysis: dict, comparison: dict) -> bool:
    """Review FLS additions. Returns True if quit requested."""
    additions = llm_analysis.get("fls_additions", {})
    per_id = additions.get("per_id", {})
    
    if not human_review.get("fls_additions"):
        return False
    
    addition_count = sum(len(item.get("contexts", [])) for item in human_review["fls_additions"].values())
    if addition_count == 0:
        return False
    
    print()
    print("═" * 78)
    print(f"FLS ADDITIONS ({addition_count} context decisions)")
    print("═" * 78)
    print(f"LLM Verdict: {additions.get('verdict', 'N/A')}")
    print(f"LLM Reasoning: {additions.get('reasoning', 'N/A')}")
    
    idx = 0
    for fls_id, item in human_review["fls_additions"].items():
        contexts = item.get("contexts", [])
        llm_info = per_id.get(fls_id, {})
        
        for ctx in contexts:
            idx += 1
            print(f"\n  [{idx}] {fls_id}: {item.get('title', 'Unknown')} (category: {item.get('category')})")
            print(f"      Context: {ctx}")
            
            # Get LLM justification
            addition_decisions = llm_info.get("addition_decisions", {})
            justification = addition_decisions.get(ctx, "No justification provided")
            print(f"      LLM justification: {justification}")
            
            # Check if already decided
            existing = item.get("decisions", {}).get(ctx, {}).get("decision")
            if existing:
                print(f"      [Already decided: {existing}]")
                response = prompt_yes_no_skip_quit(f"      Change decision for {ctx}?")
                if response == "quit":
                    return True
                elif response in ("no", "skip"):
                    continue
            
            response = prompt_yes_no_na(f"      Accept addition for {ctx}?", allow_na=(ctx not in contexts))
            if response == "quit":
                return True
            elif response == "n_a":
                continue
            else:
                if "decisions" not in item:
                    item["decisions"] = {}
                item["decisions"][ctx] = {
                    "decision": "accept" if response == "yes" else "reject",
                    "reason": None,
                }
    
    return False


def _review_specificity(human_review: dict, llm_analysis: dict) -> bool:
    """Review specificity loss. Returns True if quit requested."""
    spec = llm_analysis.get("specificity", {})
    
    print()
    print("═" * 78)
    print("SPECIFICITY CHANGE")
    print("═" * 78)
    print(f"LLM Verdict: {spec.get('verdict', 'N/A')}")
    print(f"LLM Reasoning: {spec.get('reasoning', 'N/A')}")
    
    lost = spec.get("lost_paragraphs", [])
    if lost:
        print(f"\nLost paragraphs:")
        for p in lost[:10]:
            print(f"  - {p.get('fls_id')} (category {p.get('category')}): {p.get('fls_title')}")
    
    response = prompt_yes_no_skip_quit("\nAccept specificity loss?")
    if response == "quit":
        return True
    elif response == "skip":
        pass
    elif response == "yes":
        human_review["specificity"] = {"decision": "accept", "reason": None}
    elif response == "no":
        human_review["specificity"] = {"decision": "reject", "reason": None}
    
    return False


def _review_add6_divergence(human_review: dict, llm_analysis: dict, add6: dict) -> bool:
    """Review ADD-6 divergence. Returns True if quit requested."""
    div = llm_analysis.get("add6_divergence", {})
    
    print()
    print("═" * 78)
    print("ADD-6 DIVERGENCE")
    print("═" * 78)
    print(f"LLM Verdict: {div.get('verdict', 'N/A')}")
    print(f"LLM Reasoning: {div.get('reasoning', 'N/A')}")
    
    print(f"\nADD-6 Reference:")
    print(f"  applicability_all_rust: {add6.get('applicability_all_rust', 'N/A')}")
    print(f"  applicability_safe_rust: {add6.get('applicability_safe_rust', 'N/A')}")
    print(f"  adjusted_category: {add6.get('adjusted_category', 'N/A')}")
    
    response = prompt_yes_no_skip_quit("\nAccept divergence from ADD-6?")
    if response == "quit":
        return True
    elif response == "skip":
        pass
    elif response == "yes":
        human_review["add6_divergence"] = {"decision": "accept", "reason": None}
    elif response == "no":
        human_review["add6_divergence"] = {"decision": "reject", "reason": None}
    
    return False


def _display_review_summary(guideline_id: str, human_review: dict, flags: dict) -> None:
    """Display summary of review decisions."""
    print()
    print("═" * 78)
    print(f"✓ {guideline_id} review complete")
    print(f"  Overall status: {human_review.get('overall_status')}")
    
    if human_review.get("categorization"):
        print(f"  Categorization: {human_review['categorization'].get('decision')}")
    
    removal_decisions = []
    for fls_id, item in human_review.get("fls_removals", {}).items():
        for ctx, dec in item.get("decisions", {}).items():
            removal_decisions.append(f"{fls_id}:{ctx}={dec.get('decision')}")
    if removal_decisions:
        print(f"  FLS Removals: {', '.join(removal_decisions[:5])}" + 
              (f" (+{len(removal_decisions)-5} more)" if len(removal_decisions) > 5 else ""))
    
    addition_decisions = []
    for fls_id, item in human_review.get("fls_additions", {}).items():
        for ctx, dec in item.get("decisions", {}).items():
            addition_decisions.append(f"{fls_id}:{ctx}={dec.get('decision')}")
    if addition_decisions:
        print(f"  FLS Additions: {', '.join(addition_decisions[:5])}" + 
              (f" (+{len(addition_decisions)-5} more)" if len(addition_decisions) > 5 else ""))
    
    if human_review.get("specificity"):
        print(f"  Specificity: {human_review['specificity'].get('decision')}")
    
    if human_review.get("add6_divergence"):
        print(f"  ADD-6 Divergence: {human_review['add6_divergence'].get('decision')}")


def _wait_for_enter() -> None:
    """Wait for user to press Enter to continue."""
    try:
        input("\nPress Enter to continue to next outlier...")
    except (EOFError, KeyboardInterrupt):
        pass


def run_interactive_mode(
    root: Path,
    batch: int | None,
    start_from: str | None,
    pending_only: bool,
    dry_run: bool,
) -> None:
    """Run interactive review mode for a batch or all guidelines."""
    # Get guidelines to review
    if batch is not None:
        guidelines = get_guidelines_for_batch(batch, root)
        scope = f"batch {batch}"
    else:
        all_pairs = get_all_guidelines(root)
        guidelines = [g for _, g in all_pairs]
        scope = "all batches"
    
    if pending_only:
        pending = get_pending_guidelines(root, batch)
        guidelines = [g for g in guidelines if g in pending]
        scope = f"{scope} (pending only)"
    
    if not guidelines:
        print(f"No guidelines to review for {scope}")
        return
    
    # Find start index
    start_idx = 0
    if start_from:
        try:
            start_idx = guidelines.index(start_from)
        except ValueError:
            print(f"WARNING: Guideline '{start_from}' not found in {scope}, starting from beginning")
    
    total = len(guidelines)
    reviewed_count = 0
    
    print(f"\n{'='*60}")
    print(f"Interactive Review: {scope}")
    print(f"{'='*60}")
    print(f"Guidelines: {total}")
    if start_idx > 0:
        print(f"Starting from: {guidelines[start_idx]} ({start_idx + 1}/{total})")
    if dry_run:
        print("DRY RUN: Changes will not be saved")
    print()
    
    for i, guideline_id in enumerate(guidelines[start_idx:], start=start_idx + 1):
        result = interactive_review_guideline(guideline_id, root, i, total, dry_run)
        
        if result == "quit":
            print(f"\nExiting. Reviewed {reviewed_count} guidelines.")
            print(f"Resume with: --start-from \"{guideline_id}\"")
            break
        elif result == "continue":
            reviewed_count += 1
    else:
        print(f"\n{'='*60}")
        print(f"Review complete! Reviewed {reviewed_count} guidelines.")
        print(f"{'='*60}")
    
    # Update review state summary
    if not dry_run:
        review_state = load_review_state(root)
        review_state["summary"] = recompute_review_summary(root)
        save_review_state(review_state, root)


def main():
    parser = argparse.ArgumentParser(
        description="Interactive human review for outlier analysis."
    )
    parser.add_argument(
        "--standard",
        required=True,
        choices=VALID_STANDARDS,
        help="Standard to process (e.g., misra-c)",
    )
    
    # Scope selection
    scope_group = parser.add_mutually_exclusive_group()
    scope_group.add_argument(
        "--guideline",
        help="Review a single guideline (e.g., 'Rule 10.1')",
    )
    scope_group.add_argument(
        "--batch",
        type=int,
        help="Review all guidelines in a specific batch",
    )
    scope_group.add_argument(
        "--all",
        action="store_true",
        help="Review all guidelines across all batches",
    )
    
    # Interactive mode options
    parser.add_argument(
        "--start-from",
        metavar="GUIDELINE",
        help="Start/resume from a specific guideline (for --batch or --all)",
    )
    parser.add_argument(
        "--pending-only",
        action="store_true",
        help="Only review guidelines that aren't fully reviewed yet",
    )
    
    # Display modes
    parser.add_argument(
        "--show",
        action="store_true",
        help="Display LLM analysis without making decisions (single guideline only)",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Interactive mode with prompts (default for --batch/--all)",
    )
    
    # Context for FLS operations
    parser.add_argument(
        "--context",
        choices=VALID_CONTEXTS,
        help="Context for FLS accept/reject operations (all_rust, safe_rust, both)",
    )
    
    # Accept/reject actions (single guideline mode)
    parser.add_argument(
        "--accept-all",
        action="store_true",
        help="Accept all aspects of the outlier decision",
    )
    parser.add_argument(
        "--accept-categorization",
        action="store_true",
        help="Accept categorization changes",
    )
    parser.add_argument(
        "--reject-categorization",
        action="store_true",
        help="Reject categorization changes",
    )
    parser.add_argument(
        "--accept-removal",
        metavar="FLS_ID",
        action="append",
        default=[],
        help="Accept a specific FLS removal (requires --context)",
    )
    parser.add_argument(
        "--reject-removal",
        metavar="FLS_ID",
        action="append",
        default=[],
        help="Reject a specific FLS removal (requires --context)",
    )
    parser.add_argument(
        "--accept-addition",
        metavar="FLS_ID",
        action="append",
        default=[],
        help="Accept a specific FLS addition (requires --context)",
    )
    parser.add_argument(
        "--reject-addition",
        metavar="FLS_ID",
        action="append",
        default=[],
        help="Reject a specific FLS addition (requires --context)",
    )
    parser.add_argument(
        "--accept-add6-divergence",
        action="store_true",
        help="Accept divergence from ADD-6",
    )
    parser.add_argument(
        "--reject-add6-divergence",
        action="store_true",
        help="Reject divergence from ADD-6",
    )
    parser.add_argument(
        "--accept-specificity",
        action="store_true",
        help="Accept loss of specificity",
    )
    parser.add_argument(
        "--reject-specificity",
        action="store_true",
        help="Reject loss of specificity",
    )
    
    # Bulk operations
    parser.add_argument(
        "--bulk-accept-removal",
        metavar="FLS_ID",
        help="Accept this FLS removal across ALL outliers (requires --context)",
    )
    parser.add_argument(
        "--bulk-accept-addition",
        metavar="FLS_ID",
        help="Accept this FLS addition across ALL outliers (requires --context)",
    )
    
    # Common options
    parser.add_argument(
        "--reason",
        help="Reason for the decision",
    )
    parser.add_argument(
        "--notes",
        help="Additional notes",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be changed without saving",
    )
    
    args = parser.parse_args()
    
    standard = normalize_standard(args.standard)
    root = get_project_root()
    
    # Validate context requirement for FLS operations
    fls_operations = (
        args.accept_removal or args.reject_removal or
        args.accept_addition or args.reject_addition or
        args.bulk_accept_removal or args.bulk_accept_addition
    )
    if fls_operations and not args.context:
        print("ERROR: --context is required for FLS accept/reject operations", file=sys.stderr)
        print("  Valid contexts: all_rust, safe_rust, both", file=sys.stderr)
        sys.exit(1)
    
    # Handle bulk operations
    if args.bulk_accept_removal or args.bulk_accept_addition:
        review_state = load_review_state(root)
        
        if args.bulk_accept_removal:
            fls_id = args.bulk_accept_removal
            ctx = args.context
            bulk_rules = review_state.setdefault("bulk_rules", {})
            bulk_removals = bulk_rules.setdefault("accept_removals", {})
            
            if fls_id not in bulk_removals:
                bulk_removals[fls_id] = {"contexts": [], "reason": None}
            
            if ctx == "both":
                for c in ["all_rust", "safe_rust"]:
                    if c not in bulk_removals[fls_id]["contexts"]:
                        bulk_removals[fls_id]["contexts"].append(c)
            elif ctx not in bulk_removals[fls_id]["contexts"]:
                bulk_removals[fls_id]["contexts"].append(ctx)
            
            if args.reason:
                bulk_removals[fls_id]["reason"] = args.reason
            
            print(f"Added bulk rule: accept removal of {fls_id} for context(s): {', '.join(bulk_removals[fls_id]['contexts'])}")
        
        if args.bulk_accept_addition:
            fls_id = args.bulk_accept_addition
            ctx = args.context
            bulk_rules = review_state.setdefault("bulk_rules", {})
            bulk_additions = bulk_rules.setdefault("accept_additions", {})
            
            if fls_id not in bulk_additions:
                bulk_additions[fls_id] = {"contexts": [], "reason": None}
            
            if ctx == "both":
                for c in ["all_rust", "safe_rust"]:
                    if c not in bulk_additions[fls_id]["contexts"]:
                        bulk_additions[fls_id]["contexts"].append(c)
            elif ctx not in bulk_additions[fls_id]["contexts"]:
                bulk_additions[fls_id]["contexts"].append(ctx)
            
            if args.reason:
                bulk_additions[fls_id]["reason"] = args.reason
            
            print(f"Added bulk rule: accept addition of {fls_id} for context(s): {', '.join(bulk_additions[fls_id]['contexts'])}")
        
        if not args.dry_run:
            save_review_state(review_state, root)
            print("Saved bulk rules to review_state.json")
        else:
            print("[DRY RUN] Would save bulk rules")
        
        return
    
    # Interactive batch mode
    if args.batch is not None or args.all:
        batch = args.batch if args.batch is not None else None
        run_interactive_mode(
            root=root,
            batch=batch,
            start_from=args.start_from,
            pending_only=args.pending_only,
            dry_run=args.dry_run,
        )
        return
    
    # Single guideline operations
    if not args.guideline:
        print("ERROR: --guideline, --batch, or --all is required", file=sys.stderr)
        print("\nUsage examples:", file=sys.stderr)
        print("  Interactive batch mode:  uv run review-outliers --standard misra-c --batch 1", file=sys.stderr)
        print("  Single guideline show:   uv run review-outliers --standard misra-c --guideline \"Rule 10.1\" --show", file=sys.stderr)
        print("  Accept all for one:      uv run review-outliers --standard misra-c --guideline \"Rule 10.1\" --accept-all", file=sys.stderr)
        sys.exit(1)
    
    # Load outlier analysis
    analysis = load_outlier_analysis(args.guideline, root)
    if not analysis:
        print(f"ERROR: No outlier analysis found for {args.guideline}", file=sys.stderr)
        sys.exit(1)
    
    # Show mode - display and exit
    if args.show:
        display_llm_analysis(analysis)
        display_pending_decisions(analysis)
        return
    
    # Interactive mode for single guideline
    if args.interactive:
        result = interactive_review_guideline(args.guideline, root, 1, 1, args.dry_run)
        return
    
    # CLI-flag mode for single guideline
    if analysis.get("human_review") is None:
        analysis["human_review"] = create_human_review_section()
    
    human_review = analysis["human_review"]
    flags = analysis.get("flags", {})
    comparison = analysis.get("comparison", {})
    llm_analysis = analysis.get("llm_analysis", {})
    
    initialize_fls_structures(human_review, llm_analysis, comparison)
    
    changes_made = False
    
    # Process accept-all
    if args.accept_all:
        _accept_all(human_review, flags, llm_analysis)
        changes_made = True
        print(f"Accepted all aspects for {args.guideline}")
    
    # Process categorization
    if args.accept_categorization:
        human_review["categorization"] = {"decision": "accept", "reason": args.reason}
        changes_made = True
        print(f"Accepted categorization for {args.guideline}")
    
    if args.reject_categorization:
        human_review["categorization"] = {"decision": "reject", "reason": args.reason}
        changes_made = True
        print(f"Rejected categorization for {args.guideline}")
    
    # Process FLS removals
    for fls_id in args.accept_removal:
        if apply_fls_decision(human_review, human_review["fls_removals"], fls_id, args.context, "accept", args.reason):
            changes_made = True
            print(f"Accepted removal of {fls_id} ({args.context}) for {args.guideline}")
        else:
            print(f"WARNING: {fls_id} not in removals list for context {args.context}")
    
    for fls_id in args.reject_removal:
        if apply_fls_decision(human_review, human_review["fls_removals"], fls_id, args.context, "reject", args.reason):
            changes_made = True
            print(f"Rejected removal of {fls_id} ({args.context}) for {args.guideline}")
        else:
            print(f"WARNING: {fls_id} not in removals list for context {args.context}")
    
    # Process FLS additions
    for fls_id in args.accept_addition:
        if apply_fls_decision(human_review, human_review["fls_additions"], fls_id, args.context, "accept", args.reason):
            changes_made = True
            print(f"Accepted addition of {fls_id} ({args.context}) for {args.guideline}")
        else:
            print(f"WARNING: {fls_id} not in additions list for context {args.context}")
    
    for fls_id in args.reject_addition:
        if apply_fls_decision(human_review, human_review["fls_additions"], fls_id, args.context, "reject", args.reason):
            changes_made = True
            print(f"Rejected addition of {fls_id} ({args.context}) for {args.guideline}")
        else:
            print(f"WARNING: {fls_id} not in additions list for context {args.context}")
    
    # Process ADD-6 divergence
    if args.accept_add6_divergence:
        human_review["add6_divergence"] = {"decision": "accept", "reason": args.reason}
        changes_made = True
        print(f"Accepted ADD-6 divergence for {args.guideline}")
    
    if args.reject_add6_divergence:
        human_review["add6_divergence"] = {"decision": "reject", "reason": args.reason}
        changes_made = True
        print(f"Rejected ADD-6 divergence for {args.guideline}")
    
    # Process specificity
    if args.accept_specificity:
        human_review["specificity"] = {"decision": "accept", "reason": args.reason}
        changes_made = True
        print(f"Accepted specificity loss for {args.guideline}")
    
    if args.reject_specificity:
        human_review["specificity"] = {"decision": "reject", "reason": args.reason}
        changes_made = True
        print(f"Rejected specificity loss for {args.guideline}")
    
    # Add notes
    if args.notes:
        human_review["notes"] = args.notes
        changes_made = True
    
    if not changes_made:
        print("No changes specified. Use --show to view analysis, or --accept-all, etc.")
        print("\nFor FLS operations, --context is required. Example:")
        print("  --accept-removal fls_xyz123 --context all_rust")
        sys.exit(1)
    
    # Update status
    human_review["overall_status"] = compute_overall_status(human_review, flags, llm_analysis)
    human_review["reviewed_at"] = datetime.utcnow().isoformat() + "Z"
    analysis["human_review"] = human_review
    
    if args.dry_run:
        import json
        print("\n[DRY RUN] Would update human_review:")
        print(json.dumps(human_review, indent=2))
        return
    
    save_outlier_analysis(args.guideline, analysis, root)
    print(f"\nSaved review to outlier analysis file")
    print(f"Overall status: {human_review['overall_status']}")
    
    review_state = load_review_state(root)
    review_state["summary"] = recompute_review_summary(root)
    save_review_state(review_state, root)


if __name__ == "__main__":
    main()
