# Copyright (c) 2026 Tahmid
# This software is released under the MIT License.
# See the LICENSE file in the project root for full license details.
"""Command-line pipeline: ingest sources, then compile the requested dictionary formats."""

import os
import sys
import time
import argparse

from .config import DB_NAME, get_project_version
from .log import Colors, log_info, log_success, log_error, log_step
from .lexicon import init_database, populate_staging, build_master_lexicon, print_statistics, cleanup_database
from .kindle import compile_kindle_dictionaries
from .stardict import compile_crosspoint_dictionaries
from .preview import preview_entry


def print_banner():
    version = get_project_version()

    banner = f"""
{Colors.CYAN}██████╗ ██╗██╗     ██╗███╗   ██╗ ██████╗ ██╗   ██╗ █████╗ ██╗     
██╔══██╗██║██║     ██║████╗  ██║██╔════╝ ██║   ██║██╔══██╗██║     
██████╔╝██║██║     ██║██╔██╗ ██║██║  ███╗██║   ██║███████║██║     
██╔═══╝ ██║██║     ██║██║╚██╗██║██║   ██║██║   ██║██╔══██║██║     
██║     ██║███████╗██║██║ ╚████║╚██████╔╝╚██████╔╝██║  ██║███████╗
╚═╝     ╚═╝╚══════╝╚═╝╚═╝  ╚═══╝ ╚═════╝  ╚═════╝ ╚═╝  ╚═╝╚══════╝
      ██████╗  ██████╗████████╗██╗ ██████╗ ███╗   ██╗ █████╗ ██████╗ ╚██╗  
     ██╔════╝ ██╔════╝╚══██╔══╝██║██╔═══██╗████╗  ██║██╔══██╗██╔══██╗ ╚██╗ 
     ██║  ███╗██║        ██║   ██║██║   ██║██╔██╗ ██║███████║██████╔╝  ██║ 
     ██║   ██║██║        ██║   ██║██║   ██║██║╚██╗██║██╔══██║██╔══██╗  ██║ 
     ╚██████╔╝╚██████╗   ██║   ██║╚██████╔╝██║ ╚████║██║  ██║██║  ██║ ╔██╝ 
      ╚═════╝  ╚═════╝   ╚═╝   ╚═╝ ╚═════╝ ╚═╝  ╚═══╝╚═╝  ╚═╝╚═╝  ╚═╝ ╔═╝  
                  - Standalone CLI Dictionary Builder v{version} -{Colors.END}
"""
    print(banner)


def main():
    print_banner()
    
    parser = argparse.ArgumentParser(description="Standalone Bilingual Kindle & CrossPoint Reader Dictionary Compiler Pipeline.")
    parser.add_argument('-r', '--rebuild', action='store_true', help="Force clear database and run full raw ingestion from scratch.")
    parser.add_argument('-c', '--compile-only', action='store_true', help="Skip database ingestion and only compile dictionary outputs from existing database.")
    parser.add_argument('-t', '--target', choices=['all', 'kindle', 'crosspoint'], default='all',
                        help="Output to compile: Kindle MOBI, CrossPoint Reader StarDict, or both (default: all).")
    parser.add_argument('-p', '--preview', type=str, metavar="WORD", help="Query a word and display a beautiful terminal preview of its Kindle layout.")
    parser.add_argument('--cleanup', action='store_true', help="Drop staging tables and vacuum database post-build to reduce disk footprint.")
    args = parser.parse_args()
    
    # 1. Preview Mode: Immediately run preview and exit
    if args.preview:
        preview_entry(args.preview)
        sys.exit(0)
        
    # Check if database exists or needs creation
    db_exists = os.path.exists(DB_NAME)
    
    # Determine pipeline actions
    needs_ingestion = args.rebuild or not db_exists
    needs_compilation = not args.preview
    
    if args.compile_only:
        needs_ingestion = False
        if not db_exists:
            log_error(f"Cannot run --compile-only because database '{DB_NAME}' does not exist. Run without flags first.")
            sys.exit(1)
            
    # 2. execute Ingestion Pipeline if needed
    if needs_ingestion:
        log_step(1, "Database Initialization")
        init_database()
        
        log_step(2, "Staging Ingestion from Raw Sources")
        start = time.time()
        populate_staging()
        log_info(f"Staging Ingestion completed in {time.time() - start:.2f} seconds.")
        
        log_step(3, "Master Lexicon Merging & Consolidation")
        build_master_lexicon()
        
    # 3. execute Compilation Pipeline if needed
    if needs_compilation:
        if args.target in ('all', 'kindle'):
            compile_kindle_dictionaries()

        if args.target in ('all', 'crosspoint'):
            compile_crosspoint_dictionaries()

        log_step(7, "Final Data Reports & Validation")
        print_statistics()

        # Cleanup staging database if requested
        if args.cleanup:
            cleanup_database()

        log_success("All pipeline stages completed successfully!")
