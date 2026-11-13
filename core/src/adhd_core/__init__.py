"""Checks for Crowd-Sourced ADHD submission bundles.

The verdict is a pure function of the bundle, the slot spec and this
package's version. No network, no clock, no randomness.
"""

from .result import Check, Result
from .runner import check_bundle

__version__ = "0.1.0"

__all__ = ["Check", "Result", "check_bundle", "__version__"]
