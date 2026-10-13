# Copyright (c) 2026 Tahmid
# This software is released under the MIT License.
# See the LICENSE file in the project root for full license details.
"""CrossPoint Reader output: uncompressed StarDict dictionaries."""

import os
import sys
import json
import time
import struct
import sqlite3
import zipfile
from xml.sax.saxutils import escape as xml_escape

from .config import DB_NAME, BUILD_DIR, get_project_version
from .log import Colors, log_info, log_success, log_warning, log_error, log_step
from .normalize import bangla_nuqta_variants


def stardict_sort_key(word):
    """Sort key matching StarDict's g_ascii_strcasecmp ordering, which CrossPoint's binary search relies on.

    UTF-8 bytes are compared with only ASCII letters case-folded (bytes.lower() leaves non-ASCII alone);
    ties are broken by the raw bytes so the order is total.
    """
    raw = word.encode('utf-8')
    return (raw.lower(), raw)


class StarDictCompiler:
    """Compiles one lookup direction into an uncompressed StarDict dictionary for CrossPoint Reader.

    CrossPoint (docs/dictionary.md) needs an uncompressed .idx plus .dict, takes an optional .syn for
    alternate forms, and lays out HTML definitions when the .ifo declares sametypesequence=h.
    """
    # StarDict caps headwords below 256 bytes; CrossPoint reads them into a 256-byte buffer
    MAX_WORD_BYTES = 255
    # CrossPoint truncates any definition beyond this size
    MAX_DEFINITION_BYTES = 64 * 1024

    DIRECTION_TITLES = {
        'en-bn': 'English-to-Bangla',
        'bn-en': 'Bangla-to-English',
        'bn-bn': 'Bangla-to-Bangla',
    }

    def __init__(self, output_dir, direction='en-bn', db_name=DB_NAME):
        self.output_dir = output_dir
        self.direction = direction
        self.db_name = db_name
        self.version = get_project_version()
        self.title = f"Shobdo Vandar {self.DIRECTION_TITLES[direction]} Dictionary v{self.version}"

        # The folder name is what CrossPoint lists under Settings -> Reader -> Dictionary
        self.folder_name = f"Shobdo Vandar {direction}"
        self.stem = f"shobdo_vandar_{direction}"
        self.dict_dir = os.path.join(self.output_dir, self.folder_name)
        self.zip_path = os.path.join(self.output_dir, f"Shobdo_Vandar_{direction}_v{self.version}_CrossPoint.zip")

        os.makedirs(self.dict_dir, exist_ok=True)

    @staticmethod
    def render_sense_html(sense, bold=False):
        """Renders one sense with tags CrossPoint's EPUB layout engine understands (it ignores CSS)."""
        if sense.get('source') == 'MuntashirAkon':
            # MuntashirAkon contains pre-cleansed XHTML definitions
            return sense['meanings'][0]

        html = ""
        pos_label = sense.get('pos', '')
        if pos_label and pos_label.lower() not in ["unk", "unknown", "none", "null"]:
            html += f'<i>({xml_escape(pos_label)})</i> '
        if sense.get('context'):
            html += f'<i>[{xml_escape(sense["context"])}]</i> '
        meanings = xml_escape(", ".join(sense['meanings']))
        html += f'<b>{meanings}</b>' if bold else meanings

        if sense.get('example_en'):
            html += f'<br/><i>{xml_escape(sense["example_en"])}</i>'
            if sense.get('example_bn'):
                html += f'<br/>{xml_escape(sense["example_bn"])}'
        elif sense.get('example'):
            html += f'<br/><i>{xml_escape(sense["example"])}</i>'
        return html

    def render_definition_html(self, senses):
        """Renders an entry body; CrossPoint already shows the headword above it."""
        html = ""
        for s in senses:
            if s.get('pronunciation'):
                html += f'<p><i>{xml_escape(s["pronunciation"])}</i></p>'
                break

        if len(senses) == 1:
            body = self.render_sense_html(senses[0], bold=True)
            html += body if senses[0].get('source') == 'MuntashirAkon' else f'<p>{body}</p>'
        else:
            html += '<ol>' + ''.join(f'<li>{self.render_sense_html(s)}</li>' for s in senses) + '</ol>'
        return html

    def is_valid_word(self, word):
        return bool(word) and '\0' not in word and len(word.encode('utf-8')) <= self.MAX_WORD_BYTES

    def fetch_entries(self):
        """Returns (lemma, definition_html, inflections) tuples in StarDict index order."""
        conn = sqlite3.connect(self.db_name)
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT lemma, senses_json, inflections_json
                FROM master_lexicon
                WHERE lookup_direction = ?
            """, (self.direction,))
            rows = cursor.fetchall()
        finally:
            conn.close()

        entries = []
        skipped = 0
        for lemma, senses_json, inflections_json in rows:
            if not self.is_valid_word(lemma):
                skipped += 1
                continue
            senses = json.loads(senses_json)
            inflections = json.loads(inflections_json) if inflections_json else []
            entries.append((lemma, self.render_definition_html(senses), inflections))

        if skipped:
            log_warning(f"Skipped {skipped:,} headwords longer than {self.MAX_WORD_BYTES} bytes (StarDict key limit).")
        entries.sort(key=lambda e: stardict_sort_key(e[0]))
        return entries

    def collect_synonyms(self, entries):
        """Maps inflections (and Bangla nuqta spellings) to headword ordinals for the .syn file.

        Forms that already exist as headwords are dropped: CrossPoint tries an exact match before .syn.
        """
        headword_keys = {lemma.encode('utf-8').lower() for lemma, _, _ in entries}
        is_bangla = self.direction in ('bn-en', 'bn-bn')

        synonyms = set()
        for ordinal, (lemma, _, inflections) in enumerate(entries):
            forms = {f.strip() for f in inflections}
            if is_bangla:
                for form in [lemma, *forms]:
                    forms |= bangla_nuqta_variants(form)
            for form in forms:
                if self.is_valid_word(form) and form.encode('utf-8').lower() not in headword_keys:
                    synonyms.add((form, ordinal))

        return sorted(synonyms, key=lambda s: (stardict_sort_key(s[0]), s[1]))

    def write_dict_and_idx(self, entries):
        """Writes definitions to .dict and their big-endian 32-bit offset/size records to .idx."""
        dict_path = os.path.join(self.dict_dir, f"{self.stem}.dict")
        idx_path = os.path.join(self.dict_dir, f"{self.stem}.idx")
        offset = 0
        with open(dict_path, 'wb') as dict_file, open(idx_path, 'wb') as idx_file:
            for lemma, definition, _ in entries:
                data = definition.encode('utf-8')
                if len(data) > self.MAX_DEFINITION_BYTES:
                    log_warning(f"Definition of '{lemma}' is {len(data):,} bytes; CrossPoint truncates it at 64 KB.")
                dict_file.write(data)
                idx_file.write(lemma.encode('utf-8') + b'\0' + struct.pack('>II', offset, len(data)))
                offset += len(data)

        if offset >= 2 ** 32:
            raise ValueError(f"{dict_path} exceeds 4 GB; CrossPoint does not support 64-bit offsets.")
        return os.path.getsize(idx_path)

    def write_syn(self, synonyms):
        syn_path = os.path.join(self.dict_dir, f"{self.stem}.syn")
        if not synonyms:
            # Remove a stale .syn from an earlier build so it cannot point at the wrong ordinals
            if os.path.exists(syn_path):
                os.remove(syn_path)
            return
        with open(syn_path, 'wb') as syn_file:
            for form, ordinal in synonyms:
                syn_file.write(form.encode('utf-8') + b'\0' + struct.pack('>I', ordinal))

    def write_ifo(self, word_count, syn_count, idx_size):
        """Writes .ifo metadata; CrossPoint only renders HTML when the line reads exactly sametypesequence=h."""
        lines = [
            "StarDict's dict ifo file",
            "version=2.4.2",
            f"bookname={self.title}",
            f"wordcount={word_count}",
        ]
        if syn_count:
            lines.append(f"synwordcount={syn_count}")
        lines += [
            f"idxfilesize={idx_size}",
            "sametypesequence=h",
            "author=Tahmid",
            "website=https://github.com/tahmidxp96/Shobdo-Vandar",
            f"description=Shobdo Vandar {self.DIRECTION_TITLES[self.direction]} dictionary for CrossPoint Reader, "
            f"compiled from open Bangla lexicons. Builder v{self.version}.",
            f"date={time.strftime('%Y.%m.%d')}",
        ]
        ifo_path = os.path.join(self.dict_dir, f"{self.stem}.ifo")
        with open(ifo_path, 'w', encoding='utf-8', newline='\n') as f:
            f.write("\n".join(lines) + "\n")

    def write_zip(self):
        """Packs the dictionary folder so it unzips straight into the SD card's /dictionaries/ folder."""
        with zipfile.ZipFile(self.zip_path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
            for name in sorted(os.listdir(self.dict_dir)):
                if os.path.splitext(name)[1] in ('.ifo', '.idx', '.dict', '.syn'):
                    zf.write(os.path.join(self.dict_dir, name), arcname=f"{self.folder_name}/{name}")

    def compile_all(self):
        """Builds the StarDict files and the release zip. Returns the zip path, or None if there are no entries."""
        log_info(f"Starting CrossPoint StarDict output for: {self.direction}...")
        entries = self.fetch_entries()
        if not entries:
            log_warning(f"No entries found for direction: {self.direction}")
            return None

        idx_size = self.write_dict_and_idx(entries)
        synonyms = self.collect_synonyms(entries)
        self.write_syn(synonyms)
        self.write_ifo(len(entries), len(synonyms), idx_size)
        self.write_zip()

        log_info(f"Compiled {len(entries):,} headwords and {len(synonyms):,} synonym forms into '{self.dict_dir}'.")
        log_success(f"CrossPoint dictionary package written to: {self.zip_path}")
        return self.zip_path


def compile_crosspoint_dictionaries():
    """Compiles all three directions into StarDict packages for CrossPoint Reader."""
    log_step(6, "Compiling CrossPoint Reader StarDict Dictionaries")
    start = time.time()
    output_dir = os.path.join(BUILD_DIR, 'crosspoint')
    zip_paths = []
    for direction in ['en-bn', 'bn-en', 'bn-bn']:
        zip_path = StarDictCompiler(output_dir=output_dir, direction=direction, db_name=DB_NAME).compile_all()
        if zip_path:
            zip_paths.append(zip_path)
    log_success(f"CrossPoint compilation completed in {time.time() - start:.2f} seconds!")

    if zip_paths:
        print(f"\n{Colors.BOLD}{Colors.GREEN}📖 CrossPoint Reader dictionaries are ready. Unzip into the SD card's /dictionaries/ folder:{Colors.END}")
        for zip_path in zip_paths:
            print(f"   • {Colors.CYAN}{zip_path}{Colors.END}")
        print()
    elif os.environ.get('GITHUB_ACTIONS') == 'true':
        log_error("CrossPoint compilation produced no dictionaries in CI environment!")
        sys.exit(1)
