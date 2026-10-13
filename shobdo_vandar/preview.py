# Copyright (c) 2026 Tahmid
# This software is released under the MIT License.
# See the LICENSE file in the project root for full license details.
"""Terminal preview of how an entry renders in a dictionary popup."""

import os
import re
import json
import sqlite3

from .config import DB_NAME
from .log import Colors, log_error


def preview_entry(lemma, db_name=DB_NAME):
    """Provides a gorgeous terminal preview mockup of how a word will look in Kindle."""
    if not os.path.exists(db_name):
        log_error("Database lexicon.db not found. Please run the compiler pipeline first.")
        return
        
    # Check if Bangla or English to determine direction
    # Simple regex check for English characters
    is_english = bool(re.match(r'^[a-zA-Z]', lemma))
    directions = ['en-bn'] if is_english else ['bn-en', 'bn-bn']
    
    conn = sqlite3.connect(db_name)
    try:
        cursor = conn.cursor()
        
        found_any = False
        for direction in directions:
            cursor.execute("""
                SELECT lemma, pos, senses_json, inflections_json, source_attributions 
                FROM master_lexicon 
                WHERE LOWER(lemma) = ? AND lookup_direction = ?
            """, (lemma.lower(), direction))
            row = cursor.fetchone()
            if not row:
                continue
                
            found_any = True
            lemma_val, pos, senses_json, inflections_json, sources = row
            senses = json.loads(senses_json)
            inflections = json.loads(inflections_json) if inflections_json else []
            
            # Extract pronunciation if present in any sense
            pron_val = ""
            for s in senses:
                if s.get('pronunciation'):
                    pron_val = f" {Colors.BLUE}{s['pronunciation']}{Colors.END}"
                    break
                    
            primary_sense = senses[0] if senses else {}
            dir_title = "Bangla-to-Bangla (bn-bn)" if direction == 'bn-bn' else ("Bangla-to-English (bn-en)" if direction == 'bn-en' else "English-to-Bangla (en-bn)")
            
            if primary_sense.get('source') == 'MuntashirAkon':
                import html as py_html
                raw_html = primary_sense['meanings'][0]
                clean_lines = []
                text = py_html.unescape(raw_html)
                text = re.sub(r'</?p>|<br\s*/?>', '\n', text)
                text = re.sub(r'<[^>]+>', '', text)
                for line in text.split('\n'):
                    l = line.strip()
                    if l:
                        clean_lines.append(l)
                
                # 1. RENDER POPUP BUBBLE
                print(f"\n{Colors.BOLD}{Colors.HEADER}┌──[ 📱 Kindle Lookup Popup Preview ({dir_title}) ]──────────────────────────────────┐{Colors.END}")
                print(f"│  {Colors.BOLD}{lemma_val:<25}{Colors.END}{pron_val} {Colors.CYAN}({pos}){Colors.END}")
                for idx, line in enumerate(clean_lines[:4]):
                    print(f"│  {Colors.BOLD if idx == 0 else Colors.END}{Colors.GREEN if idx == 0 else ''}{line}{Colors.END}")
                if len(clean_lines) > 4:
                    print(f"│  ...")
                if inflections:
                    print(f"│  {Colors.YELLOW}🔗 Inflections:{Colors.END} {', '.join(inflections)}")
                print(f"│  {Colors.BLUE}Source credits:{Colors.END} {sources}")
                print(f"{Colors.HEADER}└──────────────────────────────────────────────────────────────────────┘{Colors.END}")
                
                # 2. RENDER FULL PAGE VIEW
                print(f"\n{Colors.BOLD}{Colors.HEADER}┌──[ 📖 Kindle Full Page View Mockup ({dir_title}) ]─────────────────────────────────┐{Colors.END}")
                print(f"│  {Colors.BOLD}{Colors.UNDERLINE}{lemma_val.upper()}{Colors.END}{pron_val} {Colors.CYAN}({pos}){Colors.END}")
                print(f"│  Attributed Sources: {sources}")
                print("│")
                print(f"│  {Colors.BOLD}Senses & Contexts:{Colors.END}")
                for line in clean_lines:
                    print(f"│    {line}")
                if inflections:
                    print("│")
                    print(f"│  {Colors.BOLD}Hidden Inflection Index Aliases:{Colors.END}")
                    print(f"│    {Colors.YELLOW}{', '.join(inflections)}{Colors.END}")
                print(f"{Colors.HEADER}└──────────────────────────────────────────────────────────────────────┘{Colors.END}\n")
            else:
                primary_meaning = primary_sense.get('meanings', [""])[0] if primary_sense.get('meanings') else ""
                secondary_meanings = ", ".join(primary_sense.get('meanings', [])[1:4]) if len(primary_sense.get('meanings', [])) > 1 else ""
                context_tag = f" ({Colors.YELLOW}{primary_sense.get('context')}{Colors.END})" if primary_sense.get('context') else ""
                
                # 1. RENDER POPUP BUBBLE
                print(f"\n{Colors.BOLD}{Colors.HEADER}┌──[ 📱 Kindle Lookup Popup Preview ({dir_title}) ]──────────────────────────────────┐{Colors.END}")
                print(f"│  {Colors.BOLD}{lemma_val:<25}{Colors.END}{pron_val} {Colors.CYAN}({pos}){Colors.END}{context_tag}")
                print(f"│  {Colors.BOLD}{Colors.GREEN}{primary_meaning}{Colors.END}" + (f" ({secondary_meanings})" if secondary_meanings else ""))
                if inflections:
                    print(f"│  {Colors.YELLOW}🔗 Inflections:{Colors.END} {', '.join(inflections)}")
                print(f"│  {Colors.BLUE}Source credits:{Colors.END} {sources}")
                print(f"{Colors.HEADER}└──────────────────────────────────────────────────────────────────────┘{Colors.END}")
                
                # 2. RENDER FULL PAGE VIEW
                print(f"\n{Colors.BOLD}{Colors.HEADER}┌──[ 📖 Kindle Full Page View Mockup ({dir_title}) ]─────────────────────────────────┐{Colors.END}")
                print(f"│  {Colors.BOLD}{Colors.UNDERLINE}{lemma_val.upper()}{Colors.END}{pron_val} {Colors.CYAN}({pos}){Colors.END}")
                print(f"│  Attributed Sources: {sources}")
                print("│")
                print(f"│  {Colors.BOLD}Senses & Contexts:{Colors.END}")
                for idx, sense in enumerate(senses):
                    meanings = ", ".join(sense['meanings'])
                    context_str = f" ({Colors.YELLOW}{sense['context']}{Colors.END})" if sense.get('context') else ""
                    print(f"│    {idx+1}. [{Colors.CYAN}{sense['pos']}{Colors.END}]{context_str} {Colors.BOLD}{meanings}{Colors.END}")
                    if sense.get('example_en'):
                        print(f"│       {Colors.GREEN}💬 En: {sense['example_en']}{Colors.END}")
                        if sense.get('example_bn'):
                            print(f"│       {Colors.GREEN}   Bn: {sense['example_bn']}{Colors.END}")
                    elif sense.get('example'):
                        print(f"│       {Colors.GREEN}💬 Example: {sense['example']}{Colors.END}")
                        
                if inflections:
                    print("│")
                    print(f"│  {Colors.BOLD}Hidden Inflection Index Aliases:{Colors.END}")
                    print(f"│    {Colors.YELLOW}{', '.join(inflections)}{Colors.END}")
                print(f"{Colors.HEADER}└──────────────────────────────────────────────────────────────────────┘{Colors.END}\n")
    finally:
        conn.close()
        
    if not found_any:
        log_error(f"Entry '{lemma}' not found in the master database.")
        # Near-match search
        conn = sqlite3.connect(db_name)
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT DISTINCT lemma FROM master_lexicon 
                WHERE LOWER(lemma) LIKE ? OR LOWER(lemma) LIKE ?
                LIMIT 5
            """, (f"%{lemma.lower()}%", f"{lemma.lower()}%"))
            suggestions = [r[0] for r in cursor.fetchall()]
            if suggestions:
                print(f"👉 Did you mean: {Colors.YELLOW}{', '.join(suggestions)}{Colors.END}?")
        except Exception:
            pass
