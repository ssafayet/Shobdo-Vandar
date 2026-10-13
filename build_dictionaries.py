#!/usr/bin/env python3
# Copyright (c) 2026 Tahmid
# This software is released under the MIT License.
# See the LICENSE file in the project root for full license details.
"""
Shobdo Vandar dictionary builder 📚🇧🇩
Compiles en-bn, bn-en and bn-bn dictionaries for Kindle (MOBI) and CrossPoint Reader (StarDict).
"""

import sys

from shobdo_vandar.cli import main
from shobdo_vandar.log import Colors


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{Colors.RED}Process interrupted by user. Exiting safely.{Colors.END}")
        sys.exit(0)
