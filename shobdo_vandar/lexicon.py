# Copyright (c) 2026 Tahmid
# This software is released under the MIT License.
# See the LICENSE file in the project root for full license details.
"""Source ingestion, merging and maintenance of the lexicon.db master lexicon."""

import os
import re
import csv
import json
import time
import sqlite3

from .config import DB_NAME, PROJECT_ROOT
from .log import Colors, log_info, log_success, log_warning, log_error
from .normalize import BanglaNormalizer
from .morphology import EnglishMorphologyEngine, BanglaMorphologyEngine


def init_database(db_name=DB_NAME):
    """Initializes the SQLite database with staging and master tables."""
    conn = sqlite3.connect(db_name)
    try:
        cursor = conn.cursor()
        
        # 1. Source Ingestion Table (Provenance & Audit Trail)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS source_ingestion (
            ingestion_id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_name TEXT NOT NULL,
            source_license TEXT NOT NULL,
            headword_raw TEXT NOT NULL,
            lookup_direction TEXT NOT NULL,   -- 'en-bn' or 'bn-en'
            pos_raw TEXT,
            sense_text_raw TEXT NOT NULL,
            example_raw TEXT,
            import_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        """)
        
        # 2. Master Lexicon Table (Deduplicated, Sense-Clustered & Cleaned)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS master_lexicon (
            lemma_id INTEGER PRIMARY KEY AUTOINCREMENT,
            lemma TEXT NOT NULL,
            normalized_lemma TEXT NOT NULL,
            lookup_direction TEXT NOT NULL,   -- 'en-bn' or 'bn-en'
            pos TEXT,
            senses_json TEXT NOT NULL,        -- JSON array of structured Senses
            inflections_json TEXT,            -- JSON array of hidden inflection aliases
            source_attributions TEXT          -- comma-separated source credits
        );
        """)
        
        # Add Index for high performance
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_source_ingestion_hw ON source_ingestion (headword_raw, lookup_direction);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_master_lexicon_hw ON master_lexicon (lemma, lookup_direction);")
        
        # Add expression-based indexes for lower case grouping and sorting
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_source_ingestion_lower ON source_ingestion (LOWER(headword_raw), lookup_direction);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_master_lexicon_lower ON master_lexicon (lookup_direction, LOWER(lemma));")
        
        conn.commit()
    finally:
        conn.close()
    log_success("Database schemas and indices verified successfully!")


def populate_staging(db_name=DB_NAME):
    """Reads actual dictionary files from MinhasKamal, Ridmik, and Aparajeyo, and ingests them into staging."""
    conn = sqlite3.connect(db_name)
    try:
        _populate_staging_impl(conn)
    finally:
        conn.close()

def _populate_staging_impl(conn):
    cursor = conn.cursor()
    
    # Clear previous run
    cursor.execute("DELETE FROM source_ingestion")
    conn.commit()
    
    # 1. Ingest MinhasKamal CSV
    minhas_path = os.path.join(PROJECT_ROOT, 'MinhasKamal', 'BengaliDictionary_93.csv')
    minhas_records = []
    if os.path.exists(minhas_path):
        log_info("Reading MinhasKamal CSV...")
        with open(minhas_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.reader(f)
            for row in reader:
                if len(row) >= 2 and row[0].strip() and row[1].strip():
                    minhas_records.append((
                        'MinhasKamal',
                        'MIT',
                        row[0].strip(),
                        'en-bn',
                        None,
                        row[1].strip(),
                        None
                    ))
        log_info(f"Parsed {len(minhas_records):,} records from MinhasKamal CSV.")
    else:
        log_warning("MinhasKamal CSV not found at 'MinhasKamal/BengaliDictionary_93.csv'!")

    # 2. Ingest Ridmik SQLite
    ridmik_path = os.path.join(PROJECT_ROOT, 'Ridmik', 'dictionary')
    ridmik_records = []
    if os.path.exists(ridmik_path):
        log_info("Reading Ridmik SQLite DB...")
        try:
            r_conn = sqlite3.connect(ridmik_path)
            r_cursor = r_conn.cursor()
            r_cursor.execute("SELECT en_word, bn_word FROM words")
            for en, bn in r_cursor.fetchall():
                if en and bn and en.strip() and bn.strip():
                    ridmik_records.append((
                        'Ridmik',
                        'Open Source',
                        en.strip(),
                        'en-bn',
                        None,
                        bn.strip(),
                        None
                    ))
            r_conn.close()
            log_info(f"Parsed {len(ridmik_records):,} records from Ridmik SQLite DB.")
        except Exception as e:
            log_error(f"Failed to read Ridmik SQLite: {e}")
    else:
        log_warning("Ridmik SQLite DB not found at 'Ridmik/dictionary'!")

    # 3. Ingest Aparajeyo Source
    aparajeyo_en_path = os.path.join(PROJECT_ROOT, 'Aparajeyo', 'entobn.abedb')
    aparajeyo_bn_path = os.path.join(PROJECT_ROOT, 'Aparajeyo', 'bntoen.abedb')
    aparajeyo_records = []
    
    # EN-to-BN
    if os.path.exists(aparajeyo_en_path):
        log_info("Reading Aparajeyo EN-BN (UTF-16)...")
        with open(aparajeyo_en_path, 'r', encoding='utf-16') as f:
            for line in f:
                if '=' in line and not line.startswith('['):
                    parts = line.strip().split('=', 1)
                    if len(parts) == 2 and parts[0].strip() and parts[1].strip():
                        aparajeyo_records.append((
                            'Aparajeyo',
                            'Open Source',
                            parts[0].strip(),
                            'en-bn',
                            None,
                            parts[1].strip(),
                            None
                        ))
        log_info(f"Parsed EN-BN records from Aparajeyo.")
    else:
        log_warning("Aparajeyo EN-BN abedb file not found!")
        
    # BN-to-EN
    aparajeyo_bn_count = 0
    if os.path.exists(aparajeyo_bn_path):
        log_info("Reading Aparajeyo BN-EN (UTF-16)...")
        with open(aparajeyo_bn_path, 'r', encoding='utf-16') as f:
            for line in f:
                if '=' in line and not line.startswith('['):
                    parts = line.strip().split('=', 1)
                    if len(parts) == 2 and parts[0].strip() and parts[1].strip():
                        aparajeyo_records.append((
                            'Aparajeyo',
                            'Open Source',
                            parts[0].strip(),
                            'bn-en',
                            None,
                            parts[1].strip(),
                            None
                        ))
                        aparajeyo_bn_count += 1
        log_info(f"Parsed {aparajeyo_bn_count:,} BN-EN records from Aparajeyo.")
    else:
        log_warning("Aparajeyo BN-EN abedb file not found!")

    # 4. Ingest Ankur CSV
    ankur_path = os.path.join(PROJECT_ROOT, 'Ankur', 'ankur_dictionary.csv')
    ankur_records = []
    if os.path.exists(ankur_path):
        log_info("Reading Ankur CSV...")
        with open(ankur_path, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader, None) # skip header
            for row in reader:
                if len(row) >= 2 and row[0].strip() and row[1].strip():
                    ankur_records.append((
                        'Ankur',
                        'GPL',
                        row[0].strip(),
                        'en-bn',
                        None,
                        row[1].strip(),
                        None
                    ))
        log_info(f"Parsed {len(ankur_records):,} records from Ankur CSV.")
    else:
        log_warning("Ankur CSV not found at 'Ankur/ankur_dictionary.csv'!")

    # 5. Ingest Wiktionary JSON
    wiktionary_path = os.path.join(PROJECT_ROOT, 'Wiktionary', 'wiktionary_dictionary.json')
    wiktionary_records = []
    if os.path.exists(wiktionary_path):
        log_info("Reading Wiktionary JSON...")
        with open(wiktionary_path, 'r', encoding='utf-8') as f:
            try:
                w_data = json.load(f)
                for item in w_data:
                    word = item.get('word', '').strip()
                    pos = item.get('pos', '').strip()
                    pron = item.get('pronunciation', '').strip()
                    meanings = ", ".join(item.get('meanings', []))
                    syns = ", ".join(item.get('synonyms', []))
                    ex_en = item.get('example_en', '').strip()
                    ex_bn = item.get('example_bn', '').strip()
                    
                    # format example string with bilingual and synonym info if available
                    ex_str = ""
                    if pron:
                        ex_str += f"pron: {pron} | "
                    if ex_en:
                        ex_str += f"en: {ex_en}"
                        if ex_bn:
                            ex_str += f" | bn: {ex_bn}"
                    if syns:
                        if ex_str and ex_str != f"pron: {pron} | ":
                             ex_str += f" [syns: {syns}]"
                        else:
                             ex_str += f"[syns: {syns}]"
                             
                    if word and meanings:
                        wiktionary_records.append((
                            'Wiktionary',
                            'CC-BY-SA 3.0',
                            word,
                            'en-bn',
                            pos if pos else None,
                            meanings,
                            ex_str if ex_str else None
                        ))
            except Exception as e:
                log_error(f"Failed to parse Wiktionary JSON: {e}")
        log_info(f"Parsed {len(wiktionary_records):,} records from Wiktionary JSON.")
    else:
        log_warning("Wiktionary JSON not found at 'Wiktionary/wiktionary_dictionary.json'!")

    # 6. Ingest Hunspell DIC
    hunspell_path = os.path.join(PROJECT_ROOT, 'Hunspell', 'bangla_spelling.dic')
    hunspell_records = []
    if os.path.exists(hunspell_path):
        log_info("Reading Hunspell DIC...")
        with open(hunspell_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            for line in lines[1:]:
                word = line.strip().split('/')[0].strip() # strip flags
                if word:
                    # Ingest Hunspell as verified spelling reference
                    hunspell_records.append((
                        'Hunspell',
                        'LGPL',
                        word,
                        'bn-en',
                        None,
                        'Verified Spelling Lemma',
                        None
                    ))
        log_info(f"Parsed {len(hunspell_records):,} records from Hunspell DIC.")
    else:
        log_warning("Hunspell DIC not found at 'Hunspell/bangla_spelling.dic'!")

    # 7. Ingest BoiBhai JSON
    boibhai_path = os.path.join(PROJECT_ROOT, 'BoiBhai', 'boibhai_dictionary.json')
    boibhai_records = []
    if os.path.exists(boibhai_path):
        log_info("Reading BoiBhai JSON...")
        with open(boibhai_path, 'r', encoding='utf-8') as f:
            try:
                b_data = json.load(f)
                for item in b_data:
                    word = item.get('word', '').strip()
                    pos = item.get('pos', '').strip()
                    pron = item.get('pronunciation', '').strip()
                    etym = item.get('etymology', '').strip()
                    meanings = ", ".join(item.get('meanings', []))
                    syns = ", ".join(item.get('synonyms', []))
                    ex = item.get('example', '').strip()
                    
                    ex_str = ""
                    if pron:
                        ex_str += f"pron: {pron} | "
                    if ex:
                        ex_str += f"ex: {ex}"
                    if etym:
                        if ex_str and ex_str != f"pron: {pron} | ":
                            ex_str += f" | etym: {etym}"
                        else:
                            ex_str += f"etym: {etym}"
                    if syns:
                        if ex_str and ex_str != f"pron: {pron} | ":
                            ex_str += f" [syns: {syns}]"
                        else:
                            ex_str += f"[syns: {syns}]"
                            
                    if word and meanings:
                        boibhai_records.append((
                            'BoiBhai',
                            'Open Source',
                            word,
                            'bn-bn',
                            pos if pos else None,
                            meanings,
                            ex_str if ex_str else None
                        ))
            except Exception as e:
                log_error(f"Failed to parse BoiBhai JSON: {e}")
        log_info(f"Parsed {len(boibhai_records):,} records from BoiBhai JSON.")
    else:
        log_warning("BoiBhai JSON not found at 'BoiBhai/boibhai_dictionary.json'!")

    # 8. Ingest MuntashirAkon BanglaDictionary SQLite DB
    muntashir_db = os.path.join(PROJECT_ROOT, 'MuntashirAkon', 'BanglaDictionary.db')
    muntashir_records = []
    if os.path.exists(muntashir_db):
        log_info("Reading MuntashirAkon BanglaDictionary SQLite DB...")
        try:
            m_conn = sqlite3.connect(muntashir_db)
            m_cursor = m_conn.cursor()
            m_cursor.execute("SELECT word_name, definition FROM words")
            rows = m_cursor.fetchall()
            m_conn.close()
            
            for word_name, definition in rows:
                if not word_name or not definition:
                    continue
                # Split multiple headwords if they are separated by pipes
                words = [w.strip() for w in word_name.split('|') if w.strip()]
                
                # XHTML and ampersand cleansing
                # Standardize <br> to <br />
                cleaned_def = re.sub(r'<br\s*([^>]*)>', r'<br />', definition)
                # Standardize & not followed by an entity to &amp;
                cleaned_def = re.sub(r'&(?!#[0-9]+;)(?![a-zA-Z0-9]+;)', r'&amp;', cleaned_def)
                # Replace undefined HTML non-breaking space with XML numeric entity
                cleaned_def = cleaned_def.replace('&nbsp;', '&#160;')
                # Strip trailing empty/unclosed tags (like class wrapper elements)
                cleaned_def = re.sub(r'<[a-zA-Z0-9]+\s*[^>]*>\s*$', '', cleaned_def.strip())
                
                for w in words:
                    muntashir_records.append((
                        'MuntashirAkon',
                        'GNU GPL',
                        w,
                        'bn-bn',
                        None,  # POS is embedded inside the HTML definition block
                        cleaned_def,
                        None
                    ))
        except Exception as e:
            log_error(f"Failed to parse MuntashirAkon DB: {e}")
        log_info(f"Parsed {len(muntashir_records):,} records from MuntashirAkon DB.")
    else:
        log_warning("MuntashirAkon DB not found at 'MuntashirAkon/BanglaDictionary.db'!")

    # Perform bulk inserts in transaction for high performance
    all_records = minhas_records + ridmik_records + aparajeyo_records + ankur_records + wiktionary_records + hunspell_records + boibhai_records + muntashir_records
    if all_records:
        log_info(f"Inserting {len(all_records):,} raw records into source_ingestion table...")
        cursor.executemany("""
            INSERT INTO source_ingestion (source_name, source_license, headword_raw, lookup_direction, pos_raw, sense_text_raw, example_raw)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, all_records)
        conn.commit()
        log_success(f"Successfully ingested {len(all_records):,} total raw records!")
    else:
        log_warning("No source files were found, and no records were ingested.")


def normalize_meaning(text, direction):
    """Normalizes definition meanings: Bangla normalization for en-bn/bn-bn, lowercase/punctuation strip for bn-en."""
    if not text:
        return ""
    text = text.strip()
    if direction in ['en-bn', 'bn-bn']:
        return BanglaNormalizer.normalize(text)
    else:
        text = text.lower()
        punctuation_list = [',', '.', '?', '!', ':', ';', '(', ')', '-', '[', ']', '"', "'", '_', '/', '\\']
        for punc in punctuation_list:
            text = text.replace(punc, '')
        return text.strip()


def build_master_lexicon(db_name=DB_NAME):
    """Merges raw staging entries, normalizes them, clusters senses, generates inflections, and inserts into master_lexicon."""
    conn = sqlite3.connect(db_name)
    try:
        _build_master_lexicon_impl(conn)
    finally:
        conn.close()

def _build_master_lexicon_impl(conn):
    cursor = conn.cursor()
    
    # Reset master
    cursor.execute("DELETE FROM master_lexicon")
    conn.commit()
    
    # Process Senses Grouped by Direction and Headword
    log_info("Grouping staging entries by headword and direction...")
    cursor.execute("""
        SELECT headword_raw, lookup_direction, GROUP_CONCAT(ingestion_id) 
        FROM source_ingestion
        GROUP BY LOWER(headword_raw), lookup_direction
    """)
    groups = cursor.fetchall()
    log_info(f"Found {len(groups):,} unique headwords to consolidate.")
    
    normalizer = BanglaNormalizer()
    morph_engine = EnglishMorphologyEngine()
    
    # Load curated contextual enrichments if file exists
    enrichments = {}
    enrichment_path = os.path.join(PROJECT_ROOT, 'contextual_enrichments.json')
    if os.path.exists(enrichment_path):
        log_info("Discovered 'contextual_enrichments.json'. Loading premium contextual enrichments...")
        try:
            with open(enrichment_path, 'r', encoding='utf-8') as f:
                enrichments = json.load(f)
            log_success(f"Loaded curated enrichments for {len(enrichments)} words.")
        except Exception as e:
            log_error(f"Failed to load 'contextual_enrichments.json': {e}")
            
    batch = []
    count = 0
    start_time = time.time()
    
    # Query optimizer: Rather than 145k queries inside a loop, we fetch raw fields into memory
    # mapping ingestion_id -> details
    log_info("Caching ingestion audit trails in memory for O(N) merge...")
    cursor.execute("SELECT ingestion_id, source_name, pos_raw, sense_text_raw, example_raw FROM source_ingestion")
    ingestion_map = {row[0]: row[1:] for row in cursor.fetchall()}
    
    # Source Priority Map (Lower value = higher priority)
    SOURCE_PRIORITY = {
        'CuratedContexts': 1,
        'Wiktionary': 2,
        'BoiBhai': 3,
        'MuntashirAkon': 4,
        'Ridmik': 5,
        'MinhasKamal': 6,
        'Aparajeyo': 7,
        'Ankur': 8,
        'Hunspell': 9
    }
    
    for raw_hw, direction, ingestion_ids_str in groups:
        ids = [int(x) for x in ingestion_ids_str.split(',')]
        
        # Sort ids by source priority
        ids = sorted(ids, key=lambda idx: SOURCE_PRIORITY.get(ingestion_map[idx][0], 99))
        
        lemma = raw_hw.replace('|', '').strip()
        normalized_lemma = normalizer.normalize(lemma) if direction in ['bn-en', 'bn-bn'] else lemma.strip().lower()
        
        senses = []
        pos_list = set()
        sources = set()
        
        # Check if we have hand-curated enrichments for this word
        hw_lookup = lemma.lower() if direction == 'en-bn' else lemma
        has_enrichment = direction == 'en-bn' and hw_lookup in enrichments
        
        if has_enrichment:
            curated_senses = enrichments[hw_lookup]
            sources.add("CuratedContexts")
            for idx, c_sense in enumerate(curated_senses):
                pos_label = c_sense.get('pos', 'unk')
                pos_list.add(pos_label)
                senses.append({
                    'sense_id': idx + 1,
                    'pos': pos_label,
                    'context': c_sense.get('context', ''),
                    'meanings': c_sense.get('meanings', []),
                    'example_en': c_sense.get('example_en', ''),
                    'example_bn': c_sense.get('example_bn', ''),
                    'source': 'CuratedContexts'
                })
                
        # Now process standard raw records
        active_source = None
        if senses:
            # CuratedContexts already loaded
            active_source = "CuratedContexts"
            
        for ing_id in ids:
            source, pos_raw, sense_raw, ex_raw = ingestion_map[ing_id]
            
            # Skip lower priority sources if we already have senses from a higher priority source
            if active_source is not None and source != active_source:
                continue
                
            sources.add(source)
            pos_label = pos_raw if pos_raw else "unk"
            pos_list.add(pos_label)
            
            # Extract pronunciation if embedded in example
            pron_val = ""
            ex_clean = ex_raw if ex_raw else ""
            if ex_clean.startswith("pron: "):
                parts = ex_clean.split(" | ", 1)
                if len(parts) == 2:
                    pron_val = parts[0].replace("pron: ", "").strip()
                    ex_clean = parts[1].strip()
                else:
                    pron_val = ex_clean.replace("pron: ", "").strip()
                    ex_clean = ""
            
            # If lookup direction is en-bn, strip out Latin characters and punctuation artifacts
            if direction == 'en-bn':
                sense_raw_clean = re.sub(r'[a-zA-Z\(\)\[\]\{\}\-\_\/\\]+', ' ', sense_raw)
                sense_raw_clean = re.sub(r'\s+', ' ', sense_raw_clean).strip()
            else:
                sense_raw_clean = sense_raw
            
            if source == 'MuntashirAkon':
                # Treat raw HTML block as a single unified meaning
                cleaned_meanings = [sense_raw_clean]
            else:
                # Clean senses and split by comma or semi-colon
                cleaned_meanings = [m.strip() for m in re.split(r'[,;।]', sense_raw_clean) if m.strip()]
            
            # Gather all meanings accumulated in senses so far (curated + other raw sources)
            flat_accumulated_meanings = []
            for cs in senses:
                flat_accumulated_meanings.extend(cs['meanings'])
            
            # Normalize accumulated meanings for robust comparison
            flat_accumulated_norm = [normalize_meaning(m, direction) for m in flat_accumulated_meanings]
            
            deduped = []
            for m in cleaned_meanings:
                m_norm = normalize_meaning(m, direction)
                if not m_norm:
                    continue
                # Robust match: exact normalized match OR substring/containment check
                is_dup = False
                for cur_norm in flat_accumulated_norm:
                    if not cur_norm:
                        continue
                    if m_norm == cur_norm or m_norm in cur_norm or cur_norm in m_norm:
                        is_dup = True
                        break
                if not is_dup:
                    deduped.append(m)
            cleaned_meanings = deduped
            
            if not cleaned_meanings:
                continue
            
            senses.append({
                'sense_id': len(senses) + 1,
                'pos': pos_label,
                'meanings': cleaned_meanings,
                'example': ex_clean,
                'pronunciation': pron_val,
                'source': source
            })
            active_source = source
            
        # Determine dominant POS
        dominant_pos = ", ".join(sorted(pos_list))
        
        # Generate Inflections
        inflections = []
        if direction == 'en-bn':
            for p in pos_list:
                inflections.extend(morph_engine.generate_inflections(lemma, p))
            inflections = sorted(set(inflections))  # Deduplicate
        elif direction in ['bn-en', 'bn-bn']:
            inflections = BanglaMorphologyEngine.generate_inflections(lemma, dominant_pos)
            
        batch.append((
            lemma,
            normalized_lemma,
            direction,
            dominant_pos,
            json.dumps(senses, ensure_ascii=False),
            json.dumps(inflections, ensure_ascii=False) if inflections else None,
            ", ".join(sorted(sources))
        ))
        
        count += 1
        if count % 20000 == 0:
            log_info(f"Processed {count:,} / {len(groups):,} master entries...")
            
    log_info("Bulk inserting master records into master_lexicon...")
    cursor.executemany("""
        INSERT INTO master_lexicon (lemma, normalized_lemma, lookup_direction, pos, senses_json, inflections_json, source_attributions)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, batch)
    conn.commit()
    
    elapsed = time.time() - start_time
    log_success(f"Master Lexicon successfully populated in {elapsed:.2f}s! ({len(batch):,} records)")


def print_statistics(db_name=DB_NAME):
    """Queries db_name and prints formatted final dictionary statistics (User Request 4)."""
    if not os.path.exists(db_name):
        log_warning("Database not found! Run the pipeline first to collect statistics.")
        return
        
    conn = sqlite3.connect(db_name)
    try:
        cursor = conn.cursor()
        
        # Get stats for each raw source
        cursor.execute("SELECT source_name, count(*) FROM source_ingestion GROUP BY source_name")
        source_counts = cursor.fetchall()
        
        # Get total unique master entries per direction
        cursor.execute("SELECT lookup_direction, count(*) FROM master_lexicon GROUP BY lookup_direction")
        direction_counts = cursor.fetchall()
        
        cursor.execute("SELECT count(*) FROM master_lexicon")
        total_master = cursor.fetchone()[0]
    finally:
        conn.close()
    
    print("\n" + f"{Colors.BOLD}{Colors.CYAN}┌──────────────────────────────────────────────────────────────────────┐")
    print(f"│               📊 FINAL DICTIONARY STATS & SUMMARY                    │")
    print(f"└──────────────────────────────────────────────────────────────────────┘{Colors.END}")
    
    print(f"{Colors.BOLD}📥 Raw Source Ingestion Counts (from staging):{Colors.END}")
    if source_counts:
        for src, count in source_counts:
            print(f"   • {Colors.CYAN}{src:<15}{Colors.END} : {count:>8,} raw records")
    else:
        print("   • No raw records ingested yet.")
        
    print(f"\n{Colors.BOLD}📚 Combined Master Lexicon (Deduplicated & Cleaned):{Colors.END}")
    if direction_counts:
        for direction, count in direction_counts:
            labels = {
                'en-bn': "English-to-Bangla (en-bn)",
                'bn-en': "Bangla-to-English (bn-en)",
                'bn-bn': "Bangla-to-Bangla (bn-bn)"
            }
            dir_label = labels.get(direction, f"Unknown ({direction})")
            print(f"   • {dir_label:<28} : {Colors.GREEN}{count:>8,}{Colors.END} unique entries")
        print(f"   ----------------------------------------------------------------")
        print(f"   • {Colors.BOLD}{'Total Combined Master Entries':<28} : {Colors.GREEN}{total_master:>8,}{Colors.END} unique words")
    else:
        print("   • No master entries created yet.")
        
    print(f"{Colors.CYAN}└──────────────────────────────────────────────────────────────────────┘{Colors.END}\n")


def cleanup_database(db_name=DB_NAME):
    """Drops the temporary staging table and vacuums the database to optimize size."""
    if not os.path.exists(db_name):
        return
    log_info("Cleaning up staging tables and vacuuming database...")
    conn = sqlite3.connect(db_name)
    try:
        cursor = conn.cursor()
        cursor.execute("DROP TABLE IF EXISTS source_ingestion")
        cursor.execute("VACUUM")
        conn.commit()
        log_success("Database shrunk and optimized successfully!")
    except Exception as e:
        log_warning(f"Failed to cleanup database: {e}")
    finally:
        conn.close()
