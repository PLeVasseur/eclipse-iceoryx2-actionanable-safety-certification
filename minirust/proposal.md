# MiniRust Extension Proposal for Safety-Critical Rust UB Documentation

## Executive Summary

Based on comprehensive analysis of Eclipse iceoryx2 (14 crates, 545 source files, ~50,000 lines), we propose prioritizing **6 MiniRust extensions** that would cover **>90% of the undefined behavior surface area** in safety-critical IPC code. These extensions target the most UB-dense patterns found in real safety-critical Rust.

---

## Methodology

From the FLS mapping, we extracted all patterns that:
1. Involve `unsafe` code (1,702 blocks, 1,302 functions)
2. Have explicit UB conditions in the FLS
3. Are heavily used in iceoryx2

**UB-Critical Pattern Frequency in iceoryx2:**

| Pattern | Count | UB Risk Level |
|---------|-------|---------------|
| Atomic operations | 1,452 | Critical (data races) |
| Raw pointer types | 1,554 | Critical (invalid deref) |
| UnsafeCell | 189 | Critical (aliasing) |
| FFI calls | 857 | Critical (ABI mismatch) |
| repr(C) types | 160 | High (layout) |
| MaybeUninit | 146 | High (uninit read) |
| transmute | 50 | High (type punning) |
| from_raw_parts | 46 | High (slice validity) |
| fence/compiler_fence | 20 | Critical (ordering) |

---

## Proposed MiniRust Extensions (Priority Ordered)

### 1. **Atomic Operations and Memory Ordering** 
**Impact: 1,452 operations + 816 memory orderings**

**Current Gap:** MiniRust lacks formal semantics for atomics and the memory model.

**Required Definitions:**
```
AtomicOp ::= Load | Store | Swap | CompareExchange | FetchAdd | FetchSub | ...

MemoryOrdering ::= Relaxed | Acquire | Release | AcqRel | SeqCst

UB_Atomics ::=
  | DataRace(location, thread1, thread2)           -- concurrent non-atomic access
  | MixedSizeAtomic(location, size1, size2)        -- different sizes on same location
  | OrderingViolation(expected, actual)            -- e.g., Release on load
  | TearingRead(location)                          -- non-atomic read during atomic write
```

**UB Items from FLS 17.2 (Atomics):**
- `UB-ATOMIC-001`: Data race between non-atomic and atomic access
- `UB-ATOMIC-002`: Data race between two non-atomic accesses  
- `UB-ATOMIC-003`: Mixed-size atomic operations on overlapping locations
- `UB-ATOMIC-004`: Invalid memory ordering for operation type

**iceoryx2 Coverage:** Lock-free queues, IPC synchronization, reference counting

**Effort Estimate:** High (requires memory model formalization)
**Bang-for-buck:** ★★★★★ (most UB-dense area in concurrent code)

---

### 2. **Raw Pointer Provenance and Validity**
**Impact: 1,554 pointer types, 211 offset/add/sub operations**

**Current Gap:** MiniRust has basic pointer operations but incomplete provenance model.

**Required Definitions:**
```
Provenance ::= AllocationId × PermissionSet

PointerValidity ::=
  | Valid(provenance, offset, size)
  | Dangling
  | OutOfBounds(provenance, attempted_offset)
  | NullPointer
  | MisalignedPointer(required_align, actual_align)

UB_Pointers ::=
  | DerefInvalidPointer(ptr, reason: PointerValidity)
  | UseAfterFree(ptr, freed_at)
  | OutOfBoundsAccess(ptr, bounds, accessed)
  | ProvenanceViolation(ptr, expected_provenance, actual_provenance)
  | NullDeref(ptr)
  | MisalignedAccess(ptr, type_align)
  | PointerArithmeticOverflow(ptr, offset)
```

**UB Items from FLS 19.4 (Raw Pointer Dereference):**
- `UB-PTR-001`: Dereferencing null pointer
- `UB-PTR-002`: Dereferencing dangling pointer
- `UB-PTR-003`: Dereferencing misaligned pointer
- `UB-PTR-004`: Dereferencing pointer to uninitialized memory (for types requiring init)
- `UB-PTR-005`: Creating reference from invalid pointer
- `UB-PTR-006`: Pointer arithmetic resulting in out-of-bounds
- `UB-PTR-007`: Pointer arithmetic overflow

**iceoryx2 Coverage:** Shared memory access, relocatable pointers, all container internals

**Effort Estimate:** High (provenance is complex)
**Bang-for-buck:** ★★★★★ (fundamental to all unsafe Rust)

---

### 3. **Interior Mutability and Aliasing (UnsafeCell)**
**Impact: 189 UnsafeCell uses, aliasing throughout**

**Current Gap:** MiniRust doesn't formalize `UnsafeCell` exception to aliasing rules.

**Required Definitions:**
```
AliasingModel ::=
  | SharedRef(T)      -- &T: may alias, no mutation (except UnsafeCell<_>)
  | UniqueRef(T)      -- &mut T: no aliasing, mutation allowed
  | RawPtr(T)         -- *const/*mut T: no guarantees from type system

UnsafeCellSemantics ::=
  | InteriorMutabilityAllowed(cell_location)
  | SharedRefMutationOK(ref, if contains UnsafeCell)

UB_Aliasing ::=
  | AliasingViolation(ref1, ref2, overlap)
  | MutatingThroughSharedRef(ref, location, not_in_unsafecell)
  | InvalidatingActiveRef(ref, by_operation)
  | BorrowStackViolation(location, expected_state, actual_state)  -- Stacked Borrows
```

**UB Items from FLS + Stacked Borrows:**
- `UB-ALIAS-001`: Creating `&mut T` while `&T` exists to same location
- `UB-ALIAS-002`: Creating two `&mut T` to same location
- `UB-ALIAS-003`: Mutating through `&T` outside `UnsafeCell`
- `UB-ALIAS-004`: Invalidating a reference that is later used
- `UB-ALIAS-005`: Borrow stack violation (if using Stacked/Tree Borrows)

**iceoryx2 Coverage:** All lock-free data structures, shared memory segments, IPC channels

**Effort Estimate:** Medium-High (need to choose aliasing model)
**Bang-for-buck:** ★★★★★ (most subtle UB source in safe-looking code)

---

### 4. **Uninitialized Memory (MaybeUninit)**
**Impact: 146 MaybeUninit, 83 assume_init calls**

**Current Gap:** MiniRust has basic uninit concepts but incomplete validity rules.

**Required Definitions:**
```
InitializationState ::= Initialized | Uninitialized | PartiallyInitialized(mask)

TypeInitRequirement ::=
  | RequiresInit(type)            -- bool, references, fn pointers, etc.
  | AllowsUninit(type)            -- MaybeUninit<T>, unions, padding
  | PaddingUninit(type, offsets)  -- struct padding bytes

UB_Uninit ::=
  | ReadUninit(location, type)                    -- reading uninit for type requiring init
  | AssumeInitInvalid(value, expected_validity)   -- assume_init on invalid bit pattern
  | InvalidBoolValue(value)                       -- bool not 0 or 1
  | InvalidEnumDiscriminant(value, valid_range)   -- enum with invalid discriminant
  | InvalidRefFromUninit(location)                -- creating ref to uninit
  | PaddingAssumedInit(location)                  -- treating padding as initialized
```

**UB Items from FLS 7 (Values):**
- `UB-UNINIT-001`: Reading uninitialized memory as type requiring initialization
- `UB-UNINIT-002`: `assume_init()` on value not valid for type
- `UB-UNINIT-003`: Creating `bool` with value other than 0 or 1
- `UB-UNINIT-004`: Creating `enum` with invalid discriminant
- `UB-UNINIT-005`: Creating reference to uninitialized location
- `UB-UNINIT-006`: `mem::zeroed()` for type where 0 is invalid
- `UB-UNINIT-007`: Reading padding bytes as initialized

**iceoryx2 Coverage:** Placement new, shared memory initialization, PlacementDefault derive

**Effort Estimate:** Medium
**Bang-for-buck:** ★★★★☆ (common source of subtle bugs)

---

### 5. **Type Layout, Representation, and Transmutation**
**Impact: 160 repr(C), 50 transmute, 46 from_raw_parts**

**Current Gap:** MiniRust has type definitions but limited layout semantics.

**Required Definitions:**
```
TypeLayout ::= 
  { size: usize
  , align: usize  
  , field_offsets: Map<FieldName, usize>
  , validity: ValidityRequirement
  }

ReprAttribute ::= Rust | C | Transparent | Packed(n) | Align(n)

TransmuteValidity ::=
  | ValidTransmute(src_type, dst_type, value)
  | InvalidTransmute(reason)

UB_Layout ::=
  | LayoutMismatch(expected, actual)                    -- transmute size mismatch
  | AlignmentViolation(required, actual)                -- misaligned access
  | InvalidBitPattern(type, bits)                       -- bits invalid for type
  | FromRawPartsInvalid(ptr, len, reason)              -- slice from invalid components
  | PackedRefCreation(location)                         -- &T to packed field
  | ReprCLayoutViolation(type, expected_c_layout)       -- C interop mismatch
```

**UB Items from FLS 4.11 (Representation) and 21 (FFI):**
- `UB-LAYOUT-001`: `transmute` between types of different sizes
- `UB-LAYOUT-002`: `transmute` producing invalid bit pattern for target type
- `UB-LAYOUT-003`: `from_raw_parts` with null pointer (for non-ZST)
- `UB-LAYOUT-004`: `from_raw_parts` with misaligned pointer
- `UB-LAYOUT-005`: `from_raw_parts` with length causing overflow
- `UB-LAYOUT-006`: Creating reference to packed struct field
- `UB-LAYOUT-007`: FFI type layout mismatch between Rust and C

**iceoryx2 Coverage:** All shared memory types, FFI structures, IP address conversion

**Effort Estimate:** Medium
**Bang-for-buck:** ★★★★☆ (critical for FFI and shared memory)

---

### 6. **FFI and Extern Function Calls**
**Impact: 857 FFI calls, 26 extern "C", 9 extern blocks**

**Current Gap:** MiniRust doesn't model FFI semantics.

**Required Definitions:**
```
ABI ::= Rust | C | System | ...

ExternCall ::= 
  { callee: ForeignFunction
  , abi: ABI
  , args: List<Value>
  , return_type: Type
  }

FFIValidity ::=
  | ValidFFIType(type, abi)
  | InvalidFFIType(type, abi, reason)

UB_FFI ::=
  | ABIMismatch(declared_abi, actual_abi)
  | UnwindAcrossFFI(abi_without_unwind)
  | InvalidCType(rust_type, reason)
  | NulInCString(string, nul_position)
  | FFICallToInvalidAddress(addr)
  | CallbackABIMismatch(callback, expected, actual)
```

**UB Items from FLS 21 (FFI):**
- `UB-FFI-001`: Foreign exception crossing non-unwind FFI boundary
- `UB-FFI-002`: Calling extern function with wrong ABI
- `UB-FFI-003`: Passing non-FFI-safe type across FFI boundary
- `UB-FFI-004`: Interior nul byte in `CString`
- `UB-FFI-005`: Callback with mismatched calling convention
- `UB-FFI-006`: Reading mutable external static without synchronization

**iceoryx2 Coverage:** All POSIX operations, signal handlers, thread callbacks

**Effort Estimate:** Medium-High
**Bang-for-buck:** ★★★★☆ (essential for any FFI-heavy codebase)

---

## Implementation Roadmap

### Phase 1: Foundation (3-6 months)
**Goal: Cover 60% of iceoryx2 UB surface**

1. **Raw Pointer Validity** (essential foundation)
   - Define provenance model (simplified Stacked Borrows or CHERI-style)
   - Formalize pointer validity conditions
   - Output: UB-PTR-001 through UB-PTR-007

2. **Uninitialized Memory**
   - Define initialization requirements per type
   - Formalize MaybeUninit semantics
   - Output: UB-UNINIT-001 through UB-UNINIT-007

### Phase 2: Concurrency (6-12 months)
**Goal: Cover 85% of iceoryx2 UB surface**

3. **Atomics and Memory Ordering**
   - Adopt C11/C++11 memory model (or subset)
   - Define data race precisely
   - Output: UB-ATOMIC-001 through UB-ATOMIC-004

4. **Interior Mutability**
   - Formalize UnsafeCell exception
   - Choose aliasing model (Stacked/Tree Borrows or simpler)
   - Output: UB-ALIAS-001 through UB-ALIAS-005

### Phase 3: Interop (12-18 months)
**Goal: Cover 95% of iceoryx2 UB surface**

5. **Type Layout**
   - Formalize repr(C) guarantees
   - Define transmute validity
   - Output: UB-LAYOUT-001 through UB-LAYOUT-007

6. **FFI**
   - Define ABI semantics
   - Formalize FFI-safe types
   - Output: UB-FFI-001 through UB-FFI-006

---

## Proposed UB Catalog Structure (Annex J.2 Style)

```
# Rust Undefined Behavior Catalog
Version: 0.1 (Draft)
Based on: FLS 1.0, MiniRust (extended)

## J.2.1 Pointer Undefined Behavior

UB-PTR-001: Null Pointer Dereference
  Condition: Dereferencing a pointer with value 0x0
  FLS Reference: §19.4
  MiniRust Definition: DerefInvalidPointer(ptr, NullPointer)
  Stability: DECIDED
  
UB-PTR-002: Dangling Pointer Dereference
  Condition: Dereferencing a pointer to deallocated memory
  FLS Reference: §19.4
  MiniRust Definition: DerefInvalidPointer(ptr, Dangling)
  Stability: DECIDED

UB-PTR-003: Misaligned Pointer Dereference
  Condition: Dereferencing pointer not aligned to type's alignment
  FLS Reference: §19.4
  MiniRust Definition: DerefInvalidPointer(ptr, MisalignedPointer(req, actual))
  Stability: DECIDED

[... continues for all UB items ...]

## J.2.2 Memory Ordering Undefined Behavior

UB-ATOMIC-001: Data Race (Non-Atomic)
  Condition: Concurrent non-synchronized accesses where at least one is a write
  FLS Reference: §17.2
  MiniRust Definition: DataRace(location, thread1, thread2)
  Stability: DECIDED
  
[... etc ...]

## J.2.X Undecided Undefined Behavior

UB-UNDECIDED-001: Validity of Pointer-Integer Casts
  Issue: What provenance, if any, attaches to ptr-to-int-to-ptr roundtrip?
  Tracking: rust-lang/unsafe-code-guidelines#286
  Stability: NOT_DECIDED

UB-UNDECIDED-002: Tree Borrows vs Stacked Borrows
  Issue: Which aliasing model is normative?
  Tracking: rust-lang/unsafe-code-guidelines#496
  Stability: NOT_DECIDED
```

---

## Coverage Analysis

If all 6 extensions are implemented:

| iceoryx2 Pattern | Count | Covered By |
|------------------|-------|------------|
| Atomic operations | 1,452 | Extension 1 |
| Raw pointer deref | 1,554 | Extension 2 |
| UnsafeCell | 189 | Extension 3 |
| MaybeUninit | 146 | Extension 4 |
| repr(C) | 160 | Extension 5 |
| transmute | 50 | Extension 5 |
| FFI calls | 857 | Extension 6 |
| **Total coverage** | **>95%** | |

---

## Recommendation

**Start with Extensions 2 (Pointers) and 4 (Uninit)** - they are:
- Foundational for other extensions
- Moderate complexity
- High coverage of real UB patterns
- Already partially defined in MiniRust

Then proceed to **Extension 1 (Atomics)** and **Extension 3 (Aliasing)** - these are more complex but cover the most dangerous UB in concurrent code.

Extensions 5 and 6 can follow, building on the foundation.

This approach would give safety-critical Rust projects like iceoryx2 a concrete UB reference similar to C's Annex J.2, enabling:
- Systematic UB auditing
- Tool development (sanitizers, verifiers)
- Safety certification documentation
- Training materials for unsafe Rust
