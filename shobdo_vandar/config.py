# Copyright (c) 2026 Tahmid
# This software is released under the MIT License.
# See the LICENSE file in the project root for full license details.
"""Shared build locations and project version."""

import os
import json


# Sources, the database and build output all live in the repository root, so the
# pipeline behaves the same whatever directory it is launched from.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DB_NAME = os.path.join(PROJECT_ROOT, 'lexicon.db')
BUILD_DIR = os.path.join(PROJECT_ROOT, 'build')


def get_project_version():
    """Helper to read the project version from version.json."""
    version = "1.2.0"
    try:
        version_path = os.path.join(PROJECT_ROOT, 'version.json')
        if os.path.exists(version_path):
            with open(version_path, 'r', encoding='utf-8') as f:
                version = json.load(f).get('version', '1.2.0')
    except Exception:
        pass
    return version
