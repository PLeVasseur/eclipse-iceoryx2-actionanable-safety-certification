# Coding Standards to FLS Mapping

This directory contains mappings from safety-critical coding standards (MISRA C, MISRA C++, CERT C, CERT C++) to the Ferrocene Language Specification (FLS) for Rust.

## Purpose

The Safety-Critical Rust Consortium needs to understand how existing C/C++ safety coding standards relate to Rust language constructs. This mapping enables:

1. **Prioritization**: Identify which FLS sections are most frequently referenced by safety standards
2. **Gap Analysis**: Find areas where Rust's design prevents C/C++ issues entirely
3. **Documentation**: Provide traceability from established standards to Rust equivalents
4. **Tool Development**: Support static analysis tools that need to map C/C++ rules to Rust

## Current Status (2025-12-31)

### MISRA C:2025 Mapping - Complete (Draft)

| Applicability | All Rust | Safe Rust |
|---------------|----------|-----------|
| direct | 117 | 58 |
| partial | 2 | 15 |
| not_applicable | 91 | 139 |
| rust_prevents | 2 | 0 |
| **Total** | **212** | **212** |

Key findings:
- **91 guidelines N/A**: C-specific features (preprocessor, bit-fields, etc.)
- **2 rust_prevents**: Rules 11.11 and 14.4 are enforced by the Rust compiler
- **61 guidelines differ**: Between all-Rust and safe-Rust applicability
- **All mappings have medium confidence**: Automated from MISRA ADD-6 data + keyword matching

### Other Standards - Scaffolds Only

CERT C, CERT C++, and MISRA C++ mapping files exist but need schema updates and population.

## Directory Structure

```
coding-standards-fls-mapping/
├── schema/
│   ├── coding_standard_rules.schema.json   # Schema for rule/directive listings
│   └── fls_mapping.schema.json             # Schema for FLS mappings
├── standards/                               # Extracted rule listings
│   ├── misra_c_2025.json                   # MISRA C:2025 rules & directives
│   ├── misra_cpp_2023.json                 # MISRA C++:2023 rules & directives
│   ├── cert_c.json                         # CERT C rules & recommendations
│   └── cert_cpp.json                       # CERT C++ rules
├── mappings/                                # FLS mappings (deliverables)
│   ├── misra_c_to_fls.json                 # MISRA C → FLS IDs ✅ COMPLETE
│   ├── misra_cpp_to_fls.json               # MISRA C++ → FLS IDs (needs update)
│   ├── cert_c_to_fls.json                  # CERT C → FLS IDs (needs update)
│   └── cert_cpp_to_fls.json                # CERT C++ → FLS IDs (needs update)
├── concept_to_fls.json                      # C concepts → FLS mappings
├── misra_rust_applicability.json            # MISRA ADD-6 Rust applicability data
└── README.md
```

## Standards Summary

| Standard | Version | Rules | Directives | Recommendations | Total |
|----------|---------|-------|------------|-----------------|-------|
| MISRA C | 2025 | 190 | 22 | - | 212 |
| MISRA C++ | 2023 | 168 | 4 | - | 172 |
| CERT C | 2016 Edition | 123 | - | 183 | 306 |
| CERT C++ | 2016 Edition | 143 | - | 0* | 143 |

*CERT C++ recommendations were removed from the wiki pending review.

## Dual Applicability Model

Each guideline has TWO applicability values:

| Field | Description |
|-------|-------------|
| `applicability_all_rust` | Applies to ALL Rust code, including unsafe |
| `applicability_safe_rust` | Applies to SAFE Rust code only |

This distinction is critical because many C/C++ safety issues:
- Are **prevented by safe Rust** (borrow checker, bounds checking, etc.)
- But **still apply in unsafe Rust** (raw pointers, union access, etc.)

### Applicability Values

| Value | Meaning | Example |
|-------|---------|---------|
| `direct` | Guideline maps directly to FLS concept(s) | Function declarations → FLS Chapter 9 |
| `partial` | Concept exists but Rust handles differently | Integer overflow (checked in debug mode) |
| `not_applicable` | C/C++ specific with no Rust equivalent | Preprocessor rules (#define, #include) |
| `rust_prevents` | Rust's design prevents the issue entirely | Use-after-free (borrow checker) |
| `unmapped` | Awaiting expert mapping | Initial state before analysis |

### MISRA Rust Categories

For MISRA guidelines, we also track MISRA's own Rust categorization from ADD-6:

| Category | Meaning |
|----------|---------|
| `required` | Code shall comply (formal deviation required if not) |
| `advisory` | Recommendations to follow as practical |
| `recommended` | Best practice recommendations |
| `disapplied` | Compliance not required |
| `implicit` | Rust compiler enforces this (maps to `rust_prevents`) |
| `n_a` | Does not apply to Rust |

## Usage

### Validation

Validate all JSON files against their schemas:

```bash
cd tools
uv run python validate_coding_standards.py
```

Validate a specific file:

```bash
uv run python validate_coding_standards.py --file=misra_c_to_fls.json
```

### Generating MISRA C Mappings

The `map_misra_to_fls.py` script generates automated mappings:

```bash
cd tools

# Generate all MISRA C mappings
uv run python map_misra_to_fls.py

# Generate only rules (skip directives)
uv run python map_misra_to_fls.py --rules-only

# Generate first N guidelines for testing
uv run python map_misra_to_fls.py --limit 50 --verbose
```

### Regenerating Standards Files

**MISRA** (requires PDFs in `cache/misra-standards/`):

```bash
uv run python extract_misra_rules.py
```

**CERT** (scrapes from SEI wiki):

```bash
uv run python scrape_cert_rules.py
```

### Cross-Reference Analysis

Analyze FLS coverage frequency across all mapped standards:

```bash
uv run python analyze_fls_coverage.py
```

## Mapping Workflow

### Automated Pass (Completed for MISRA C)

1. Load MISRA C:2025 rules from `standards/misra_c_2025.json`
2. Load MISRA ADD-6 Rust applicability from `misra_rust_applicability.json`
3. Match guideline titles against `concept_to_fls.json` keywords
4. Generate FLS ID lists from matched concepts
5. Apply MISRA ADD-6 applicability values
6. Output with `confidence: "medium"`

### Manual Review Pass (TODO)

1. Review each guideline with `confidence: "medium"` or `"low"`
2. Verify FLS ID assignments are correct
3. Add/remove FLS IDs as needed
4. Update notes with specific rationale
5. Upgrade `confidence` to `"high"` when verified

## Key Files

### concept_to_fls.json

Maps C language concepts to FLS sections:

```json
{
  "memory_allocation": {
    "keywords": ["malloc", "free", "alloc", ...],
    "fls_ids": ["fls_svkx6szhr472", ...],
    "fls_sections": ["15.1", "15.2", ...],
    "typical_applicability_all_rust": "partial",
    "typical_applicability_safe_rust": "rust_prevents",
    "rationale": "Safe Rust prevents use-after-free..."
  }
}
```

### misra_rust_applicability.json

MISRA ADD-6 data for Rust applicability:

```json
{
  "guidelines": {
    "Rule 11.11": {
      "applicability_all_rust": "Yes",
      "applicability_safe_rust": "Yes",
      "adjusted_category": "implicit",
      "comment": "enforced by rustc"
    }
  }
}
```

## Schema Details

### fls_mapping.schema.json

Each mapping entry contains:

```json
{
  "guideline_id": "Rule 11.11",
  "guideline_type": "rule",
  "applicability_all_rust": "rust_prevents",
  "applicability_safe_rust": "rust_prevents",
  "fls_ids": ["fls_3i4ou0dq64ny", "fls_ppd1xwve3tr7"],
  "fls_sections": ["4.7", "4.7.2"],
  "fls_rationale_type": "rust_prevents",
  "misra_rust_category": "implicit",
  "misra_rust_comment": "enforced by rustc",
  "confidence": "medium",
  "notes": "Rust compiler enforces pointer type compatibility"
}
```

### fls_rationale_type

When `fls_ids` are present, `fls_rationale_type` is **required** and explains WHY those FLS sections are referenced:

| Value | Meaning | When to Use |
|-------|---------|-------------|
| `direct_mapping` | Rule maps directly to these FLS concepts | Guideline applies to Rust the same way as C |
| `rust_alternative` | Rust has a different/better mechanism | FLS shows what Rust uses instead |
| `rust_prevents` | Rust's design prevents the issue | FLS shows how Rust's design avoids the problem |
| `no_equivalent` | C concept doesn't exist in Rust | FLS shows related concepts for context |
| `partial_mapping` | Some aspects map, others don't | Mixed applicability |

This field is especially important for `not_applicable` rules - it explains why FLS IDs are included even though the rule doesn't apply to Rust.

## Data Sources

- **MISRA C:2025**: Extracted from official PDF (not redistributed)
- **MISRA C:2025 ADD-6**: Rust Applicability addendum (not redistributed)
- **MISRA C++:2023**: Extracted from official PDF (not redistributed)
- **CERT C**: Scraped from https://wiki.sei.cmu.edu/confluence/display/c/
- **CERT C++**: Scraped from https://wiki.sei.cmu.edu/confluence/display/cplusplus/
- **FLS**: https://rust-lang.github.io/fls/

## Contributing

When adding or updating mappings:

1. Use the validation script to ensure schema compliance
2. Include meaningful `notes` explaining the mapping rationale
3. Set appropriate `confidence` level based on certainty
4. For MISRA, cross-reference with ADD-6 for Rust applicability
5. Consider both `applicability_all_rust` and `applicability_safe_rust`

## License

The mapping data in this repository is provided for safety analysis purposes.

- MISRA standards are copyright MISRA Ltd. Only rule numbers and titles are extracted.
- CERT standards are available under SEI terms. Only rule numbers and titles are used.
- FLS is available under Apache 2.0 / MIT license.
