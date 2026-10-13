# Copyright (c) 2026 Tahmid
# This software is released under the MIT License.
# See the LICENSE file in the project root for full license details.
"""Bangla text normalization and spelling variants."""

import re
import unicodedata


class BanglaNormalizer:
    @staticmethod
    def normalize(text):
        """Normalizes raw Bangla text by standardizing Unicode characters, stripping punctuation and cleaning variants."""
        if not text:
            return ""
        
        # 0. Apply standard Unicode Normalization Form C (NFC)
        text = unicodedata.normalize('NFC', text)
        
        # Standardize Nuqta decomposition to combined Unicode characters
        text = text.replace('\u09b0\u09bc', '\u09dc') # র + ় -> ড়
        text = text.replace('\u09a2\u09bc', '\u09dd') # ঢ + ় -> ঢ়
        text = text.replace('\u09af\u09bc', '\u09df') # য + ় -> য়
        
        # 1. Strip whitespace
        text = text.strip()
        
        # 2. Remove Kindle/dictionary artifacts like pipe symbols (common tail marker in some formats)
        text = text.replace('|', '')
        
        # 3. Standardize Bangla vowel signs (specifically O-KAR 'ো' and OU-KAR 'ৌ' NFC conversion)
        # Replacing composite forms (e.g., E-KAR + AA-KAR = O-KAR) with single Unicode points
        text = re.sub(r'\u09c7\u09be', '\u09cb', text) # E-kar + Aa-kar -> O-kar
        text = re.sub(r'\u09c7\u09d7', '\u09cc', text) # E-kar + Gullah -> Ou-kar
        
        # 4. Remove Zero-Width Joiner (ZWJ) and Zero-Width Non-Joiner (ZWNJ) if not visually significant
        text = text.replace('\u200d', '') # ZWJ
        text = text.replace('\u200c', '') # ZWNJ
        
        # 5. Remove common trailing punctuation and danda (।), double danda, brackets, quotes
        punctuation_list = ['।', ',', '.', '?', '!', ':', ';', '(', ')', '-', '[', ']', '"', "'"]
        for punc in punctuation_list:
            text = text.replace(punc, '')
        
        return text.strip()

    @staticmethod
    def english_to_bangla_digits(text):
        """Converts English digits to Bangla numerals."""
        digits_map = {'0': '০', '1': '১', '2': '২', '3': '৩', '4': '৪', '5': '৫', '6': '৬', '7': '৭', '8': '৮', '9': '৯'}
        return "".join(digits_map.get(char, char) for char in text)


# Bangla nuqta letters are Unicode composition exclusions: NFC text carries them decomposed,
# while many keyboards emit the precomposed code point. Both spellings must resolve.
BANGLA_NUQTA_PAIRS = [
    ('ড়', 'ড়'),  # ড় <-> ড + ়
    ('ঢ়', 'ঢ়'),  # ঢ় <-> ঢ + ়
    ('য়', 'য়'),  # য় <-> য + ়
]


def bangla_nuqta_variants(word):
    """Returns the fully precomposed and fully decomposed nuqta spellings of a word, excluding the word itself."""
    composed = decomposed = word
    for precomposed, sequence in BANGLA_NUQTA_PAIRS:
        composed = composed.replace(sequence, precomposed)
        decomposed = decomposed.replace(precomposed, sequence)
    return {composed, decomposed} - {word}
