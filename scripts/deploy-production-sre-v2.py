#!/usr/bin/env python3
"""Compatibility entrypoint: all new releases use the canonical V2 release CLI.

The completed 74a54256 SRE rollout is retained in the closeout evidence.
"""
from production_release import main

if __name__ == '__main__':
    raise SystemExit(main())
