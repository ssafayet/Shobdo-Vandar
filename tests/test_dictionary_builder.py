import sys
import os
import unittest
import json
import shutil
import sqlite3
import struct
import tempfile
import zipfile
import xml.etree.ElementTree as ET

# Add project root to path to import the shobdo_vandar package
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from shobdo_vandar.normalize import BanglaNormalizer, bangla_nuqta_variants
from shobdo_vandar.morphology import EnglishMorphologyEngine, BanglaMorphologyEngine
from shobdo_vandar.lexicon import init_database
from shobdo_vandar.kindle import xml_escape_attr, KindleDictionaryCompiler
from shobdo_vandar.stardict import StarDictCompiler


class TestBanglaNormalizer(unittest.TestCase):
    def test_nfc_standardization(self):
        # 1. Test standard NFC decomposition merging (Nuqta + Ra -> Rra)
        decomposed = "\u09b0\u09bc" # র + ়
        normalized = BanglaNormalizer.normalize(decomposed)
        self.assertEqual(normalized, "\u09dc") # ড়

    def test_custom_vowel_merges(self):
        # 2. Test composite vowel conversion (E-kar + Aa-kar -> O-kar)
        decomposed_o = "\u09c7\u09be"
        normalized_o = BanglaNormalizer.normalize(decomposed_o)
        self.assertEqual(normalized_o, "\u09cb") # ো (O-kar)
        
        decomposed_ou = "\u09c7\u09d7"
        normalized_ou = BanglaNormalizer.normalize(decomposed_ou)
        self.assertEqual(normalized_ou, "\u09cc") # ৌ (Ou-kar)

    def test_punc_and_whitespace_strip(self):
        # 3. Test removal of brackets, quotes, and punctuation
        raw = " (হিতৈষী) ।"
        self.assertEqual(BanglaNormalizer.normalize(raw), "হিতৈষী")


class TestEnglishMorphologyEngine(unittest.TestCase):
    def test_regular_inflections(self):
        # Test regular verb forms
        forms = EnglishMorphologyEngine.generate_inflections("walk", "verb")
        self.assertIn("walks", forms)
        self.assertIn("walking", forms)
        self.assertIn("walked", forms)
        
        # Test regular noun forms
        forms = EnglishMorphologyEngine.generate_inflections("cat", "noun")
        self.assertIn("cats", forms)

    def test_irregular_overrides(self):
        # Test irregular verb override mapping
        forms = EnglishMorphologyEngine.generate_inflections("see", "verb")
        self.assertIn("saw", forms)
        self.assertIn("seen", forms)
        self.assertIn("sees", forms)
        self.assertNotIn("seeed", forms) # Ensure default regular suffix isn't generated
        
        # Test irregular noun override mapping
        forms = EnglishMorphologyEngine.generate_inflections("child", "noun")
        self.assertEqual(forms, ["children"])

    def test_adjective_length_limit(self):
        # Short adjectives should take suffixes
        short_forms = EnglishMorphologyEngine.generate_inflections("tall", "adjective")
        self.assertIn("taller", short_forms)
        self.assertIn("tallest", short_forms)
        
        # Long adjectives should NOT take suffixes
        long_forms = EnglishMorphologyEngine.generate_inflections("benevolent", "adjective")
        self.assertEqual(long_forms, [])


class TestBanglaMorphologyEngine(unittest.TestCase):
    def test_nominal_suffixes(self):
        # Generate noun/adjective inflections
        forms = BanglaMorphologyEngine.generate_inflections("মানুষ", "noun")
        self.assertIn("মানুষটি", forms)
        self.assertIn("মানুষগুলো", forms)
        self.assertIn("মানুষকে", forms)

    def test_verb_conjugations(self):
        # Generate regular verb inflections (e.g. করা -> করি, করেছে, করব, করলেন)
        forms = BanglaMorphologyEngine.generate_inflections("করা", "verb")
        self.assertIn("করি", forms)
        self.assertIn("করছি", forms)
        self.assertIn("করবে", forms)
        self.assertIn("করলেন", forms)
        self.assertNotIn("করাটি", forms) # Noun suffixes should be blocked for verbs

    def test_verb_conjugations_wa_ending(self):
        # Generate Wa-ending verb conjugations (e.g. খাওয়া -> খাই, খায়, খাব, খেলাম, খেতে)
        forms = BanglaMorphologyEngine.generate_inflections("খাওয়া", "ক্রিয়া")
        self.assertIn("খাই", forms)
        self.assertIn("খায়", forms)
        self.assertIn("খাব", forms)
        self.assertIn("খেলাম", forms)
        self.assertIn("খেতে", forms)
        self.assertNotIn("খাওয়াটি", forms)


class TestXmlFormatting(unittest.TestCase):
    def test_xml_attribute_quote_escaping(self):
        # Ensure quotes inside attributes are escaped properly
        raw = 'inch"'
        escaped = xml_escape_attr(raw)
        self.assertEqual(escaped, "inch&quot;")

    def test_render_entry_xhtml_nesting(self):
        # Set up a compiler instance
        compiler = KindleDictionaryCompiler(output_dir="./build/test-build", direction="en-bn")
        
        # Render a mockup entry
        senses = [{'sense_id': 1, 'pos': 'noun', 'meanings': ['বিড়াল']}]
        inflections = ['cats']
        entry_xhtml = compiler.render_entry_xhtml("cat", "noun", senses, inflections)
        
        # Parse output and verify well-formed XML structure
        # Since it is a fragment, wrap it in a root tag
        wrapped_fragment = f"<root xmlns:idx='http://www.amazon.com/xmlns/idx'>{entry_xhtml}</root>"
        root = ET.fromstring(wrapped_fragment)
        
        # Find idx:entry -> idx:short -> idx:orth
        namespaces = {'idx': 'http://www.amazon.com/xmlns/idx'}
        entry = root.find('.//idx:entry', namespaces)
        self.assertIsNotNone(entry)
        
        short = entry.find('.//idx:short', namespaces)
        self.assertIsNotNone(short)
        
        orth = short.find('.//idx:orth', namespaces)
        self.assertIsNotNone(orth)
        
        # Ensure idx:infl is a child of idx:short (sibling to idx:orth), NOT nested in idx:orth
        infl_inside_orth = orth.find('.//idx:infl', namespaces)
        self.assertIsNone(infl_inside_orth) # MUST NOT be inside idx:orth
        
        infl_inside_short = short.find('./idx:infl', namespaces)
        self.assertIsNotNone(infl_inside_short) # MUST be a direct child of idx:short


def read_stardict_records(path, suffix_bytes):
    """Parses .idx (8-byte suffix) or .syn (4-byte suffix) into (word, big-endian fields) tuples."""
    with open(path, 'rb') as f:
        data = f.read()
    records = []
    pos = 0
    while pos < len(data):
        end = data.index(b'\0', pos)
        fields = struct.unpack('>' + 'I' * (suffix_bytes // 4), data[end + 1:end + 1 + suffix_bytes])
        records.append((data[pos:end].decode('utf-8'), fields))
        pos = end + 1 + suffix_bytes
    return records


def ascii_case_cmp(a, b):
    """Mirrors CrossPoint's StringUtils::asciiCaseCmp over UTF-8 bytes."""
    a, b = a.encode('utf-8').lower(), b.encode('utf-8').lower()
    return (a > b) - (a < b)


class TestStarDictCompiler(unittest.TestCase):
    MANUSH = "মানুষ"  # মানুষ (no nuqta letters)
    KHAOYA_PRECOMPOSED = "খাওয়া"  # খাওয়া with precomposed য়

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp_dir, 'lexicon.db')
        init_database(self.db_path)

        rows = [
            ('child', 'en-bn', 'noun', [{'pos': 'noun', 'meanings': ['শিশু']}], ['children']),
            ('Apple', 'en-bn', 'noun', [{'pos': 'noun', 'meanings': ['আপেল'], 'pronunciation': '/ˈæp.əl/'}], ['apples']),
            ('apex', 'en-bn', 'unk', [{'pos': 'unk', 'meanings': ['শীর্ষ'], 'example': 'the <apex> & more'}], []),
            ('Zebra', 'en-bn', 'noun', [{'pos': 'noun', 'meanings': ['জেব্রা']},
                                        {'pos': 'noun', 'meanings': ['ডোরাকাটা']}], ['zebras']),
            (self.MANUSH, 'bn-bn', 'noun',
             [{'pos': 'unk', 'meanings': ['<p>মানুষ বি. মনুষ্য</p>'], 'source': 'MuntashirAkon'}],
             [self.MANUSH + "টি"]),  # মানুষটি
            (self.KHAOYA_PRECOMPOSED, 'bn-bn', 'verb',
             [{'pos': 'verb', 'meanings': ['ভোজন করা']}], ["খাই"]),  # খাই
        ]
        conn = sqlite3.connect(self.db_path)
        conn.executemany("""
            INSERT INTO master_lexicon (lemma, normalized_lemma, lookup_direction, pos, senses_json, inflections_json, source_attributions)
            VALUES (?, ?, ?, ?, ?, ?, 'Test')
        """, [(lemma, lemma.lower(), d, pos, json.dumps(s, ensure_ascii=False), json.dumps(i, ensure_ascii=False))
              for lemma, d, pos, s, i in rows])
        conn.commit()
        conn.close()

    def tearDown(self):
        shutil.rmtree(self.tmp_dir)

    def compile(self, direction):
        compiler = StarDictCompiler(output_dir=self.tmp_dir, direction=direction, db_name=self.db_path)
        zip_path = compiler.compile_all()
        base = os.path.join(compiler.dict_dir, compiler.stem)
        return compiler, zip_path, base

    def lookup(self, base, word):
        """Emulates CrossPoint's exact-match-then-synonym lookup; returns (headword, definition) or None."""
        idx = read_stardict_records(base + '.idx', 8)
        with open(base + '.dict', 'rb') as f:
            dict_data = f.read()

        def definition(ordinal):
            headword, (offset, size) = idx[ordinal]
            return headword, dict_data[offset:offset + size].decode('utf-8')

        for ordinal, (headword, _) in enumerate(idx):
            if ascii_case_cmp(headword, word) == 0:
                return definition(ordinal)
        if os.path.exists(base + '.syn'):
            for synonym, (ordinal,) in read_stardict_records(base + '.syn', 4):
                if ascii_case_cmp(synonym, word) == 0:
                    return definition(ordinal)
        return None

    def test_index_sorted_for_crosspoint_binary_search(self):
        _, _, base = self.compile('en-bn')
        words = [w for w, _ in read_stardict_records(base + '.idx', 8)]
        self.assertEqual(words, ['apex', 'Apple', 'child', 'Zebra'])
        for a, b in zip(words, words[1:]):
            self.assertLessEqual(ascii_case_cmp(a, b), 0)

    def test_ifo_declares_html_and_counts(self):
        _, _, base = self.compile('en-bn')
        with open(base + '.ifo', encoding='utf-8') as f:
            lines = f.read().split('\n')
        self.assertEqual(lines[0], "StarDict's dict ifo file")
        self.assertIn('wordcount=4', lines)
        self.assertIn('synwordcount=3', lines)
        self.assertIn(f'idxfilesize={os.path.getsize(base + ".idx")}', lines)
        # CrossPoint only treats definitions as HTML when the value is exactly "h"
        self.assertIn('sametypesequence=h', lines)

    def test_lookup_resolves_headwords_case_insensitively_and_inflections_via_syn(self):
        _, _, base = self.compile('en-bn')
        headword, definition = self.lookup(base, 'APPLE')
        self.assertEqual(headword, 'Apple')
        self.assertIn('আপেল', definition)
        self.assertIn('/ˈæp.əl/', definition)

        headword, _ = self.lookup(base, 'children')
        self.assertEqual(headword, 'child')

    def test_definition_html_is_escaped_and_free_of_kindle_markup(self):
        _, _, base = self.compile('en-bn')
        _, definition = self.lookup(base, 'apex')
        self.assertIn('the &lt;apex&gt; &amp; more', definition)
        _, definition = self.lookup(base, 'zebra')
        self.assertTrue(definition.startswith('<ol><li>'))
        for word in ['apex', 'apple', 'child', 'zebra']:
            _, definition = self.lookup(base, word)
            self.assertNotIn('idx:', definition)
            ET.fromstring(f'<root>{definition}</root>')  # well-formed for CrossPoint's strict parser

    def test_bangla_inflections_and_nuqta_spellings_resolve(self):
        _, _, base = self.compile('bn-bn')
        headword, definition = self.lookup(base, self.MANUSH + "টি")
        self.assertEqual(headword, self.MANUSH)
        self.assertEqual(definition, '<p>মানুষ বি. মনুষ্য</p>')  # MuntashirAkon HTML passes through

        # NFC text carries য় decomposed; it must still find the precomposed headword
        decomposed = "খাওয়া"
        headword, _ = self.lookup(base, decomposed)
        self.assertEqual(headword, self.KHAOYA_PRECOMPOSED)

    def test_zip_unpacks_into_named_dictionary_folder(self):
        compiler, zip_path, _ = self.compile('en-bn')
        with zipfile.ZipFile(zip_path) as zf:
            names = sorted(zf.namelist())
        folder = compiler.folder_name
        self.assertEqual(names, sorted(f'{folder}/{compiler.stem}{ext}' for ext in ['.dict', '.idx', '.ifo', '.syn']))

    def test_bangla_nuqta_variants(self):
        self.assertEqual(bangla_nuqta_variants("য়"), {"য়"})
        self.assertEqual(bangla_nuqta_variants("ড়"), {"ড়"})
        self.assertEqual(bangla_nuqta_variants("abc"), set())


if __name__ == '__main__':
    unittest.main()
