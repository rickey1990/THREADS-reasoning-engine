# THREADS — public test bundle

**THREADS** = **T**emporal **H**istorical **R**elational **E**ngine for **A**dversarial **D**eterministic **S**ystems.

This folder contains the exact Python source snapshot plus public test/benchmark scripts needed to reproduce the THREADS checks.

## Requirements

- Python 3.10+
- NumPy 1.24+

No model weights, GPU, network access, or external solver are required for the core tests.

## Fastest test

From this folder:

```bash
python THREADS_test_runner.py
```

This runs the original regression suite plus a lightweight diagnostic subset of the 60-category benchmark.

## Full 60-category benchmark

```bash
python THREADS_test_runner.py --micro60
```

## Applied tests

```bash
python THREADS_test_runner.py --applied
```

## Paper-10 scientific benchmark

```bash
python THREADS_test_runner.py --paper10
```

**Warning:** Paper-10 contains the million-event distractor experiment and can require roughly 1 GB of process memory on the reported implementation.

## Everything

```bash
python THREADS_test_runner.py --full
```

## Test fairness

THREADS receives the structured facts/events/constraints and the requested operation. Expected answers and independent oracles are used by the benchmark only to grade the result after THREADS has computed it. Ordinary relation walks receive the relation program as part of the query; the bounded program-induction test is the exception that searches a supplied finite operator library.

## Internal package name

The Python package is still named `srmh` to preserve the tested source snapshot and benchmark history. The research project is published as **THREADS**.

## Installation and COUNT semantics

Install the package in editable mode with:

```bash
python -m pip install -e ./source
```

`Graph` is an explicit multigraph, so `COUNT` counts parallel edge witnesses.
`Engine` and `Ledger` store observations of logical transitions; `Engine` COUNT
counts each distinct positive subject/relation/object transition once. Repeated
or independently lineaged observations therefore do not manufacture additional
engine edges. This preserves the evidence-copy policy used by the regression
suite and is intentionally different from `Graph` COUNT.

## Licensing

This repository uses a split noncommercial licence. See `LICENSING.md`, `LICENSE-CODE.txt`, and `LICENSE-DOCUMENTATION.txt` before reuse.
