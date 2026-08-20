# Installation

Required for CDR: installation instructions for each file / executable.

## Requirements

- Python 3.10 or newer
- PyYAML

## Diagnostic Server (Jetson, Ubuntu)

```bash
git clone <repo-url>
cd lunar-medical-diagnostic
pip3 install pyyaml
python3 -m tests.test_engine     # confirm it works
```

## Crew Terminal (Raspberry Pi 5, Ubuntu)

*(Cruz: fill in once the terminal exists.)*

## Offline verification

The system must run with no internet connection. To verify:

```bash
# disconnect from the network entirely, then:
python3 -m engine.cli
```

If it fails, something is reaching out to the internet and must be removed.
