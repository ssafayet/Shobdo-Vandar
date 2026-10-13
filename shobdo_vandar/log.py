# Copyright (c) 2026 Tahmid
# This software is released under the MIT License.
# See the LICENSE file in the project root for full license details.
"""Colored console logging mirrored to build.log."""

import re
import sys
import logging


# ANSI Color Codes for Premium Terminal Aesthetics
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    END = '\033[0m'

# Logger setup
logger = logging.getLogger("ShobdoVandar")
logger.setLevel(logging.INFO)

class AnsiStrippingFormatter(logging.Formatter):
    ANSI_ESCAPE = re.compile(r'\x1b\[[0-9;]*m')
    def format(self, record):
        orig_msg = record.msg
        if isinstance(record.msg, str):
            record.msg = self.ANSI_ESCAPE.sub('', record.msg)
        formatted = super().format(record)
        record.msg = orig_msg
        return formatted

if not logger.handlers:
    # Console handler
    c_handler = logging.StreamHandler(sys.stdout)
    c_format = logging.Formatter('%(message)s')
    c_handler.setFormatter(c_format)
    logger.addHandler(c_handler)
    
    # File handler
    f_handler = logging.FileHandler('build.log', mode='w', encoding='utf-8')
    f_format = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    f_handler.setFormatter(AnsiStrippingFormatter(f_format._fmt))
    logger.addHandler(f_handler)

def log_info(msg):
    logger.info(f"{Colors.BLUE}[INFO]{Colors.END} {msg}")

def log_success(msg):
    logger.info(f"{Colors.GREEN}[SUCCESS]{Colors.END} {msg}")

def log_warning(msg):
    logger.warning(f"{Colors.YELLOW}[WARNING]{Colors.END} {msg}")

def log_error(msg):
    logger.error(f"{Colors.RED}[ERROR]{Colors.END} {msg}")

def log_step(step_num, title):
    logger.info(f"\n{Colors.BOLD}{Colors.HEADER}--- Step {step_num}: {title} ---{Colors.END}")
