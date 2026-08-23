#!/usr/bin/env python3
"""Compare the pinned baseline with a read-only local upstream checkout.

This command never fetches, merges, writes a manifest, or modifies either
repository. It reports whether the reviewed pin is exact or a newer linear
upstream candidate is available for a separate human-reviewed sync.
"""

import argparse
from pathlib import Path

import verify_upstream


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reference-repo",
        required=True,
        type=Path,
        help="read-only official upstream checkout",
    )
    args = parser.parse_args()

    pin = verify_upstream.load_pin()
    verify_upstream.verify_repository(
        verify_upstream.PROJECT_ROOT, pin, require_runtime_unchanged=True
    )
    reference = args.reference_repo.resolve()
    candidate = verify_upstream.git(reference, "rev-parse", "HEAD").stdout.strip()

    if candidate == pin.commit:
        verify_upstream.verify_repository(
            reference, pin, require_runtime_unchanged=False
        )
        print("sync_status=exact")
    else:
        relation = verify_upstream.git(
            reference,
            "merge-base",
            "--is-ancestor",
            pin.commit,
            candidate,
            check=False,
        )
        if relation.returncode != 0:
            verify_upstream.fail(
                f"reference HEAD {candidate} is not a descendant of pin {pin.commit}"
            )
        changed = verify_upstream.git(
            reference,
            "diff",
            "--name-only",
            pin.commit,
            candidate,
        ).stdout.splitlines()
        print("sync_status=update-available")
        print(f"candidate_commit={candidate}")
        print(f"changed_paths={len(changed)}")
    print(f"reference_repo={reference}")
    print(f"pinned_commit={pin.commit}")


if __name__ == "__main__":
    main()
