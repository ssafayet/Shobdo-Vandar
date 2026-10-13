# Copyright (c) 2026 Tahmid
# This software is released under the MIT License.
# See the LICENSE file in the project root for full license details.
"""Kindle output: XHTML/OPF sources compiled to MOBI with kindlegen."""

import os
import re
import sys
import json
import time
import sqlite3
from xml.sax.saxutils import escape as xml_escape

from .config import DB_NAME, BUILD_DIR, get_project_version
from .log import Colors, log_info, log_success, log_warning, log_error, log_step


def xml_escape_attr(text):
    """Escapes text for use inside XML attribute values (including quotes)."""
    if not text:
        return ""
    return xml_escape(text).replace('"', '&quot;').replace("'", '&apos;')


class KindleDictionaryCompiler:
    def __init__(self, output_dir, direction='en-bn', db_name=DB_NAME, entries_per_shard=1000):
        self.output_dir = output_dir
        self.direction = direction
        self.db_name = db_name
        self.entries_per_shard = entries_per_shard
        
        self.version = get_project_version()

        # Direction specific metadata
        if direction == 'en-bn':
            self.input_lang = 'en'
            self.output_lang = 'bn'
            self.index_name = 'english'
            self.title = f"Shobdo Vandar English-to-Bangla Dictionary v{self.version}"
        elif direction == 'bn-en':
            self.input_lang = 'bn'
            self.output_lang = 'en'
            self.index_name = 'bangla'
            self.title = f"Shobdo Vandar Bangla-to-English Dictionary v{self.version}"
        elif direction == 'bn-bn':
            self.input_lang = 'bn'
            self.output_lang = 'bn'
            self.index_name = 'bangla'
            self.title = f"Shobdo Vandar Bangla-to-Bangla Dictionary v{self.version}"
            
        os.makedirs(self.output_dir, exist_ok=True)

    def write_stylesheet(self):
        """Writes clean, minimalist stylesheet.css for Kindle."""
        css_path = os.path.join(self.output_dir, 'stylesheet.css')
        with open(css_path, 'w', encoding='utf-8') as f:
            f.write("""
            /* Georgia-serif e-ink popover styling */
            body { font-family: Georgia, serif; margin: 0; padding: 2px 4px; line-height: 1.25; }
            h2 { font-size: 1.15em; margin: 0 0 2px 0; font-weight: bold; }
            p { margin: 2px 0; }
            ol { margin: 3px 0 3px 15px; padding: 0; }
            li { margin-bottom: 3px; padding-left: 2px; }
            .pron { color: #666; font-size: 0.85em; font-family: sans-serif; margin-left: 5px; }
            .pos { font-style: italic; color: #555; font-size: 0.85em; }
            .context { font-style: italic; color: #555; font-weight: bold; font-size: 0.85em; }
            .example { font-style: italic; color: #444; margin-left: 10px; }
            .example-en { font-style: italic; color: #444; display: block; margin-left: 10px; margin-top: 2px; }
            .example-bn { color: #005580; display: block; margin-left: 25px; font-size: 0.95em; }
            .attributions { font-size: 0.75em; color: #777; margin-top: 10px; }
            hr { border: 0; border-top: 1px solid #ddd; margin: 6px 0; }
            """)
        log_info(f"Written: {css_path}")

    def render_entry_xhtml(self, lemma, pos, senses, inflections):
        """Compiles structured entry content into Kindle-compatible XHTML markup."""
        escaped_lemma = xml_escape(lemma)
        escaped_lemma_attr = xml_escape_attr(lemma)
        
        # Build inflections block if any
        inflections_xml = ""
        if inflections:
            escaped_pos_attr = xml_escape_attr(pos if pos else 'unk')
            inflections_xml = f'    <idx:infl inflgrp="{escaped_pos_attr}">\n'
            for infl in inflections:
                inflections_xml += f'      <idx:iform value="{xml_escape_attr(infl)}"/>\n'
            inflections_xml += '    </idx:infl>\n'
            
        # Check if we have a pronunciation in any sense
        pron_xml = ""
        for s in senses:
            if s.get('pronunciation'):
                pron_xml = f' <span class="pron">{xml_escape(s["pronunciation"])}</span>'
                break
            
        # Build senses body HTML
        senses_html = ""
        if len(senses) == 1:
            s = senses[0]
            if s.get('source') == 'MuntashirAkon':
                # MuntashirAkon contains pre-cleansed XML/XHTML definitions
                senses_html = s['meanings'][0]
            else:
                meanings = ", ".join(s['meanings'])
                context_html = f' <span class="context">[{xml_escape(s["context"])}]</span>' if s.get('context') else ""
                pos_label = s.get('pos', '')
                pos_html = ""
                if pos_label and pos_label.lower() not in ["unk", "unknown", "none", "null"]:
                    pos_html = f'<span class="pos">({xml_escape(pos_label)})</span> '
                senses_html = f'<p>{pos_html}{context_html}<b>{xml_escape(meanings)}</b></p>'
                if s.get('example_en'):
                    senses_html += f'<p class="example-en">💬 {xml_escape(s["example_en"])}</p>'
                    if s.get('example_bn'):
                        senses_html += f'<p class="example-bn">➔ {xml_escape(s["example_bn"])}</p>'
                elif s.get('example'):
                    senses_html += f'<p class="example">💬 {xml_escape(s["example"])}</p>'
        else:
            senses_html = '<ol>'
            for s in senses:
                meanings = ", ".join(s['meanings'])
                context_html = f' <span class="context">[{xml_escape(s["context"])}]</span>' if s.get('context') else ""
                pos_label = s.get('pos', '')
                pos_html = ""
                if pos_label and pos_label.lower() not in ["unk", "unknown", "none", "null"]:
                    pos_html = f'<span class="pos">({xml_escape(pos_label)})</span> '
                senses_html += f'<li>{pos_html}{context_html}{xml_escape(meanings)}'
                if s.get('example_en'):
                    senses_html += f'<br/><span class="example-en">💬 {xml_escape(s["example_en"])}</span>'
                    if s.get('example_bn'):
                        senses_html += f'<span class="example-bn">➔ {xml_escape(s["example_bn"])}</span>'
                elif s.get('example'):
                    senses_html += f'<br/><span class="example">💬 {xml_escape(s["example"])}</span>'
                senses_html += '</li>'
            senses_html += '</ol>'
            
        entry_xml = f"""
        <idx:entry name="{self.index_name}" scriptable="yes" spell="yes">
          <idx:short>
            <idx:orth value="{escaped_lemma_attr}">
              <b>{escaped_lemma}</b>{pron_xml}
            </idx:orth>
{inflections_xml}            {senses_html}
          </idx:short>
        </idx:entry>
        <hr/>
        """
        return entry_xml

    def compile_xhtml_shards(self):
        """Fetches master data and writes sharded XHTML files in build directory."""
        conn = sqlite3.connect(self.db_name)
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT lemma, pos, senses_json, inflections_json 
                FROM master_lexicon 
                WHERE lookup_direction = ?
                ORDER BY LOWER(lemma) ASC
            """, (self.direction,))
            rows = cursor.fetchall()
        finally:
            conn.close()
        
        shard_files = []
        shard_idx = 0
        total_entries = len(rows)
        
        if total_entries == 0:
            return []
            
        import xml.etree.ElementTree as ET
        
        for i in range(0, total_entries, self.entries_per_shard):
            chunk = rows[i:i+self.entries_per_shard]
            filename = f"content_{shard_idx}.html"
            filepath = os.path.join(self.output_dir, filename)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                # XHTML Header with exact Kindle dictionary schemas
                f.write("""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN" "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">
<html xmlns="http://www.w3.org/1999/xhtml"
      xmlns:idx="http://www.amazon.com/xmlns/idx"
      xmlns:mbp="http://www.amazon.com/xmlns/mbp"
      xmlns:mm="http://www.amazon.com/xmlns/mobi">
<head>
    <meta http-equiv="Content-Type" content="text/html; charset=utf-8" />
    <link rel="stylesheet" type="text/css" href="stylesheet.css" />
    <title>Dictionary Content</title>
</head>
<body>
<mbp:frameset>
""")
                
                # Write Entries
                for lemma, pos, senses_json, inflections_json in chunk:
                    senses = json.loads(senses_json)
                    inflections = json.loads(inflections_json) if inflections_json else []
                    entry_xhtml = self.render_entry_xhtml(lemma, pos, senses, inflections)
                    f.write(entry_xhtml)
                    
                # XHTML Footer
                f.write("""
</mbp:frameset>
</body>
</html>
""")
            
            # Validate well-formedness to catch markup errors early
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    xml_content = f.read()
                # Strip DOCTYPE to prevent external DTD loading overhead/network errors
                clean_xml = re.sub(r'<!DOCTYPE[^>]*>', '', xml_content)
                ET.fromstring(clean_xml)
            except ET.ParseError as e:
                log_error(f"XHTML Well-Formedness Error in shard file '{filename}': {e}")
                # We do not crash the pipeline but alert the developer clearly
                
            shard_files.append(filename)
            shard_idx += 1
            
        log_info(f"Compiled {shard_idx} XHTML shards containing {total_entries:,} entries.")
        return shard_files

    def compile_opf(self, shard_filenames):
        """Generates the OPF metadata package file binding languages and sharded contents."""
        opf_path = os.path.join(self.output_dir, 'dict.opf')
        
        manifest_items = ""
        spine_items = ""
        
        for idx, fname in enumerate(shard_filenames):
            manifest_items += f'    <item id="content_{idx}" href="{fname}" media-type="application/xhtml+xml"/>\n'
            spine_items += f'    <itemref idref="content_{idx}"/>\n'
            
        opf_content = f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="uid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">
    <dc:title>{self.title}</dc:title>
    <dc:language>{self.input_lang}</dc:language>
    <dc:creator>Tahmid</dc:creator>
    <dc:publisher>Shobdo Vandar v{self.version}</dc:publisher>
    
    <!-- Kindle Dictionary Metadata Declarations -->
    <meta name="BookType" content="dictionary"/>
    <x-metadata>
      <DictionaryInLanguage>{self.input_lang}</DictionaryInLanguage>
      <DictionaryOutLanguage>{self.output_lang}</DictionaryOutLanguage>
      <DefaultLookupIndex>{self.index_name}</DefaultLookupIndex>
      <meta name="dictionary_version" content="{self.version}"/>
    </x-metadata>
  </metadata>
  
  <manifest>
    <item id="stylesheet" href="stylesheet.css" media-type="text/css"/>
{manifest_items}  </manifest>
  
  <spine>
{spine_items}  </spine>
  
  <guide>
    <reference type="search" title="Search" href="{shard_filenames[0]}"/>
  </guide>
</package>
"""
        with open(opf_path, 'w', encoding='utf-8') as f:
            f.write(opf_content)

    def compile_all(self):
        """Runs the entire package compiler."""
        log_info(f"Starting Kindle compiler output for: {self.direction}...")
        self.write_stylesheet()
        shards = self.compile_xhtml_shards()
        if shards:
            self.compile_opf(shards)
            log_success(f"Compilation for direction '{self.direction}' completed successfully!")
        else:
            log_warning(f"No entries found for direction: {self.direction}")


def compile_mobi(opf_path, output_mobi_path):
    """Attempts to compile an OPF package file into a MOBI file using Amazon's official kindlegen compiler."""
    import shutil
    import subprocess
    
    # 1. Search for kindlegen in PATH
    kindlegen_path = shutil.which('kindlegen')
    
    # 2. Search for kindlegen in local workspace folder
    if not kindlegen_path:
        local_names = ['kindlegen.exe', 'kindlegen'] if sys.platform == 'win32' else ['kindlegen']
        for name in local_names:
            local_path = os.path.abspath(f'./{name}')
            if os.path.exists(local_path):
                if sys.platform == 'win32' or os.access(local_path, os.X_OK):
                    kindlegen_path = local_path
                    break
            
    # 3. Check standard application paths for Kindle Previewer
    if not kindlegen_path:
        common_paths = []
        if sys.platform == 'darwin':
            common_paths = [
                "/Applications/Kindle Previewer 3.app/Contents/lib/fc/bin/kindlegen",
                "/Applications/Kindle Previewer 3.app/Contents/MacOS/lib/fc/bin/kindlegen",
                "/Applications/Kindle Previewer.app/Contents/lib/fc/bin/kindlegen"
            ]
        elif sys.platform == 'win32':
            local_appdata = os.environ.get('LOCALAPPDATA', '')
            user_profile = os.environ.get('USERPROFILE', '')
            if local_appdata:
                common_paths.append(os.path.join(local_appdata, r"Amazon\Kindle Previewer 3\lib\fc\bin\kindlegen.exe"))
            if user_profile:
                common_paths.append(os.path.join(user_profile, r"AppData\Local\Amazon\Kindle Previewer 3\lib\fc\bin\kindlegen.exe"))
                
        for p in common_paths:
            if os.path.exists(p):
                # Ensure the binary has execute permissions (macOS/Linux)
                if sys.platform != 'win32':
                    try:
                        if not os.access(p, os.X_OK):
                            os.chmod(p, 0o755)
                    except Exception as e:
                        log_warning(f"Could not set execute permission on {p}: {e}")
                kindlegen_path = p
                break
                
    if kindlegen_path:
        log_info(f"Auto-compiling MOBI using Amazon's official kindlegen: '{kindlegen_path}'...")
        output_dir = os.path.dirname(output_mobi_path)
        mobi_filename = os.path.basename(output_mobi_path)
        try:
            cmd = [kindlegen_path, opf_path, "-o", mobi_filename]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if res.returncode in [0, 1]:  # kindlegen return code 1 is a warning, which is fine
                log_success(f"Successfully generated MOBI file at: {output_mobi_path}")
                return True
            else:
                log_warning(f"kindlegen failed with code {res.returncode}. Output:\n{res.stdout}\n{res.stderr}")
        except Exception as e:
            log_error(f"Error running kindlegen: {e}")
            
    log_warning(f"{Colors.RED}Kindle's official compiler 'kindlegen' was NOT found on your system.{Colors.END}")
    print(f"   {Colors.YELLOW}Please perform the following steps to build your e-books:{Colors.END}")
    print(f"   1. Download Kindle Previewer 3 for Mac from Amazon's official CDN:")
    print(f"      {Colors.CYAN}https://d2bzeorukaqrvt.cloudfront.net/KindlePreviewerInstaller.pkg{Colors.END}")
    print(f"   2. Install Kindle Previewer 3 on your Mac by running the downloaded installer.")
    print(f"   3. Run this Python script again. It will automatically detect the installation and build the .mobi files!")
    return False


def compile_kindle_dictionaries():
    """Compiles all three directions into Kindle XHTML/OPF sources, then into MOBI files when kindlegen is available."""
    log_step(4, "Compiling Kindle XHTML Shards & OPF Configs")
    start = time.time()
    
    # 1. Compile English to Bangla Dictionary
    en_bn_compiler = KindleDictionaryCompiler(
        output_dir=os.path.join(BUILD_DIR, 'en-bn'),
        direction='en-bn',
        db_name=DB_NAME,
        entries_per_shard=1000
    )
    en_bn_compiler.compile_all()
    
    print("\n" + "="*80 + "\n")
    
    # 2. Compile Bangla to English Dictionary
    bn_en_compiler = KindleDictionaryCompiler(
        output_dir=os.path.join(BUILD_DIR, 'bn-en'),
        direction='bn-en',
        db_name=DB_NAME,
        entries_per_shard=1000
    )
    bn_en_compiler.compile_all()
    
    print("\n" + "="*80 + "\n")
    
    # 3. Compile Bangla to Bangla Dictionary
    bn_bn_compiler = KindleDictionaryCompiler(
        output_dir=os.path.join(BUILD_DIR, 'bn-bn'),
        direction='bn-bn',
        db_name=DB_NAME,
        entries_per_shard=1000
    )
    bn_bn_compiler.compile_all()
    
    # 4. Auto-compile MOBI files if tools are available
    log_step(5, "Auto-Compiling MOBI E-Books")
    
    version = get_project_version()
        
    en_bn_filename = f"Shobdo_Vandar_en-bn_v{version}.mobi"
    bn_en_filename = f"Shobdo_Vandar_bn-en_v{version}.mobi"
    bn_bn_filename = f"Shobdo_Vandar_bn-bn_v{version}.mobi"
    
    en_bn_mobi = os.path.join(BUILD_DIR, 'en-bn', en_bn_filename)
    bn_en_mobi = os.path.join(BUILD_DIR, 'bn-en', bn_en_filename)
    bn_bn_mobi = os.path.join(BUILD_DIR, 'bn-bn', bn_bn_filename)
    
    # Explicitly delete old MOBI files if they exist to prevent false-positive success reports
    for path in [en_bn_mobi, bn_en_mobi, bn_bn_mobi]:
        if os.path.exists(path):
            try:
                os.remove(path)
                log_info(f"Cleaned up preexisting MOBI file: {path}")
            except Exception as e:
                log_warning(f"Could not remove preexisting MOBI file at {path}: {e}")
    
    en_bn_success = compile_mobi(os.path.join(BUILD_DIR, 'en-bn', 'dict.opf'), en_bn_mobi)
    print("\n" + "-"*40 + "\n")
    bn_en_success = compile_mobi(os.path.join(BUILD_DIR, 'bn-en', 'dict.opf'), bn_en_mobi)
    print("\n" + "-"*40 + "\n")
    bn_bn_success = compile_mobi(os.path.join(BUILD_DIR, 'bn-bn', 'dict.opf'), bn_bn_mobi)
    
    log_success(f"Entire compilation completed in {time.time() - start:.2f} seconds!")
    
    if en_bn_success or bn_en_success or bn_bn_success:
        print(f"\n{Colors.BOLD}{Colors.GREEN}🎉 SUCCESS! Your MOBI e-books have been compiled directly in:{Colors.END}")
        if en_bn_success and os.path.exists(en_bn_mobi):
            print(f"   • English-to-Bangla : {Colors.CYAN}{en_bn_mobi}{Colors.END}")
        if bn_en_success and os.path.exists(bn_en_mobi):
            print(f"   • Bangla-to-English : {Colors.CYAN}{bn_en_mobi}{Colors.END}")
        if bn_bn_success and os.path.exists(bn_bn_mobi):
            print(f"   • Bangla-to-Bangla  : {Colors.CYAN}{bn_bn_mobi}{Colors.END}")
        print()
    else:
        print(f"\n{Colors.BOLD}{Colors.GREEN}👉 To build MOBI e-books, compile using Kindle Previewer or run:{Colors.END}")
        print(f"   kindlegen ./build/en-bn/dict.opf -o {en_bn_filename}")
        print(f"   kindlegen ./build/bn-en/dict.opf -o {bn_en_filename}")
        print(f"   kindlegen ./build/bn-bn/dict.opf -o {bn_bn_filename}\n")
        
    # CI/CD failure propagation: Fail building if compiler fails on CI
    if os.environ.get('GITHUB_ACTIONS') == 'true':
        if not (en_bn_success and bn_en_success and bn_bn_success):
            log_error("MOBI compilation failed for one or more targets in CI environment!")
            sys.exit(1)
