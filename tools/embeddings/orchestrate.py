#!/usr/bin/env python3
"""
Orchestrator for the MISRA-FLS semantic similarity pipeline.

This script runs all steps of the embedding pipeline in sequence:
1. Extract MISRA text from PDF (if not already done)
2. Extract FLS content from RST files (if not already done)
3. Generate embeddings for MISRA, FLS sections, and FLS paragraphs
4. Compute similarity matrices at section and paragraph levels

Usage:
    uv run python tools/embeddings/orchestrate.py [--force] [--skip-extract]

Options:
    --force         Force regeneration of all artifacts
    --skip-extract  Skip extraction steps (use existing extracted data)
    --model MODEL   Embedding model (default: all-mpnet-base-v2)
    --top-n N       Number of top section matches per guideline (default: 20)
    --para-top-n N  Number of top paragraph matches per guideline (default: 30)
"""

import argparse
import subprocess
import sys
from pathlib import Path


def get_project_root() -> Path:
    """Get the project root directory."""
    return Path(__file__).parent.parent.parent


def run_step(name: str, script: str, args: list[str] | None = None, 
             skip_condition: Path | None = None, force: bool = False) -> bool:
    """
    Run a pipeline step.
    
    Args:
        name: Human-readable step name
        script: Path to script relative to tools/embeddings/
        args: Additional arguments to pass to script
        skip_condition: If this path exists and force=False, skip the step
        force: Force running even if skip_condition is met
    
    Returns:
        True if step succeeded, False otherwise
    """
    if skip_condition and skip_condition.exists() and not force:
        print(f"\n{'='*60}")
        print(f"Step: {name}")
        print(f"{'='*60}")
        print(f"Skipping: {skip_condition} already exists")
        print("Use --force to regenerate")
        return True
    
    print(f"\n{'='*60}")
    print(f"Step: {name}")
    print(f"{'='*60}")
    
    # Build command
    cmd = ["uv", "run", "python", f"embeddings/{script}"]
    if args:
        cmd.extend(args)
    
    # Run from tools directory
    tools_dir = get_project_root() / "tools"
    
    try:
        result = subprocess.run(
            cmd,
            cwd=tools_dir,
            check=True
        )
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error: Step failed with exit code {e.returncode}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description='Run MISRA-FLS semantic similarity pipeline'
    )
    parser.add_argument('--force', action='store_true',
                       help='Force regeneration of all artifacts')
    parser.add_argument('--skip-extract', action='store_true',
                       help='Skip extraction steps')
    parser.add_argument('--model', default='all-mpnet-base-v2',
                       help='Embedding model name')
    parser.add_argument('--top-n', type=int, default=20,
                       help='Number of top section matches per guideline')
    parser.add_argument('--para-top-n', type=int, default=30,
                       help='Number of top paragraph matches per guideline')
    args = parser.parse_args()
    
    project_root = get_project_root()
    
    print("="*60)
    print("MISRA-FLS Semantic Similarity Pipeline")
    print("="*60)
    
    steps_completed = 0
    steps_failed = 0
    
    # Step 1: Extract MISRA text
    if not args.skip_extract:
        success = run_step(
            name="Extract MISRA C:2025 text from PDF",
            script="extract_misra_text.py",
            skip_condition=project_root / "cache" / "misra_c_extracted_text.json",
            force=args.force
        )
        if success:
            steps_completed += 1
        else:
            steps_failed += 1
            print("\nPipeline stopped due to extraction failure")
            return 1
    
    # Step 2: Extract FLS content
    if not args.skip_extract:
        success = run_step(
            name="Extract FLS content from RST files",
            script="extract_fls_content.py",
            skip_condition=project_root / "embeddings" / "fls" / "index.json",
            force=args.force
        )
        if success:
            steps_completed += 1
        else:
            steps_failed += 1
            print("\nPipeline stopped due to extraction failure")
            return 1
    
    # Step 3: Generate embeddings (sections + paragraphs)
    # Skip only if both section and paragraph embeddings exist
    section_emb = project_root / "embeddings" / "fls" / "embeddings.pkl"
    para_emb = project_root / "embeddings" / "fls" / "paragraph_embeddings.pkl"
    skip_embeddings = section_emb.exists() and para_emb.exists() and not args.force
    
    success = run_step(
        name="Generate vector embeddings (sections + paragraphs)",
        script="generate_embeddings.py",
        args=["--model", args.model],
        skip_condition=para_emb if skip_embeddings else None,
        force=args.force
    )
    if success:
        steps_completed += 1
    else:
        steps_failed += 1
        print("\nPipeline stopped due to embedding failure")
        return 1
    
    # Step 4: Compute similarity (sections + paragraphs)
    success = run_step(
        name="Compute similarity matrices (sections + paragraphs)",
        script="compute_similarity.py",
        args=["--top-n", str(args.top_n), "--para-top-n", str(args.para_top_n)],
        skip_condition=None,  # Always run similarity computation
        force=True  # Always regenerate similarity
    )
    if success:
        steps_completed += 1
    else:
        steps_failed += 1
    
    # Summary
    print("\n" + "="*60)
    print("Pipeline Complete")
    print("="*60)
    print(f"Steps completed: {steps_completed}")
    print(f"Steps failed: {steps_failed}")
    
    if steps_failed > 0:
        return 1
    
    # Show output locations
    print("\nOutput files:")
    outputs = [
        ("MISRA extracted text", "cache/misra_c_extracted_text.json", "(gitignored)"),
        ("FLS index", "embeddings/fls/index.json", ""),
        ("FLS chapters", "embeddings/fls/chapter_*.json", "(22 files)"),
        ("MISRA embeddings", "embeddings/misra_c/embeddings.pkl", ""),
        ("FLS section embeddings", "embeddings/fls/embeddings.pkl", ""),
        ("FLS paragraph embeddings", "embeddings/fls/paragraph_embeddings.pkl", ""),
        ("Similarity results", "embeddings/similarity/misra_c_to_fls.json", ""),
    ]
    for name, path, note in outputs:
        full_path = project_root / path
        # Handle glob patterns specially
        if '*' in path:
            import glob as glob_module
            matches = list(glob_module.glob(str(project_root / path)))
            if matches:
                total_size = sum(Path(m).stat().st_size for m in matches) / 1024
                unit = "KB"
                if total_size > 1024:
                    total_size /= 1024
                    unit = "MB"
                print(f"  {name}: {path} ({total_size:.1f} {unit}, {len(matches)} files) {note}")
            else:
                print(f"  {name}: {path} (not found)")
        elif full_path.exists():
            size = full_path.stat().st_size / 1024
            unit = "KB"
            if size > 1024:
                size /= 1024
                unit = "MB"
            print(f"  {name}: {path} ({size:.1f} {unit}) {note}")
        else:
            print(f"  {name}: {path} (not found)")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
