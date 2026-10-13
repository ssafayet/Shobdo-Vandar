# Copyright (c) 2026 Tahmid
# This software is released under the MIT License.
# See the LICENSE file in the project root for full license details.
"""Heuristic English and Bangla inflection generators."""




class EnglishMorphologyEngine:
    # Irregular dictionaries for direct mapping override
    IRREGULAR_VERBS = {
        'teach': ['teaches', 'taught', 'teaching'],
        'write': ['writes', 'wrote', 'written', 'writing'],
        'go': ['goes', 'went', 'gone', 'going'],
        'run': ['runs', 'ran', 'running'],
        'do': ['does', 'did', 'done', 'doing'],
        'see': ['sees', 'saw', 'seen', 'seeing'],
        'have': ['has', 'had', 'having'],
        'bring': ['brings', 'brought', 'bringing'],
        'buy': ['buys', 'bought', 'buying'],
        'catch': ['catches', 'caught', 'catching'],
        'think': ['thinks', 'thought', 'thinking'],
        'take': ['takes', 'took', 'taken', 'taking'],
        'make': ['makes', 'made', 'making'],
        'give': ['gives', 'gave', 'given', 'giving'],
        'come': ['comes', 'came', 'coming'],
        'find': ['finds', 'found', 'finding'],
        'get': ['gets', 'got', 'gotten', 'getting'],
        'say': ['says', 'said', 'saying'],
        'know': ['knows', 'knew', 'known', 'knowing'],
        'tell': ['tells', 'told', 'telling'],
        'speak': ['speaks', 'spoke', 'spoken', 'speaking'],
        'lose': ['loses', 'lost', 'losing'],
        'send': ['sends', 'sent', 'sending'],
        'spend': ['spends', 'spent', 'spending'],
        'build': ['builds', 'built', 'building'],
        'lend': ['lends', 'lent', 'lending'],
        'cut': ['cuts', 'cutting'],
        'put': ['puts', 'putting'],
        'hit': ['hits', 'hitting'],
        'let': ['lets', 'letting'],
        'set': ['sets', 'setting'],
        'hurt': ['hurts', 'hurting'],
        'cost': ['costs', 'costing'],
        'shut': ['shuts', 'shutting'],
        'read': ['reads', 'read', 'reading']
    }
    
    IRREGULAR_NOUNS = {
        'child': ['children'],
        'mouse': ['mice'],
        'foot': ['feet'],
        'man': ['men'],
        'woman': ['women'],
        'tooth': ['teeth'],
        'goose': ['geese'],
        'person': ['people'],
        'ox': ['oxen'],
        'louse': ['lice'],
        'die': ['dice'],
        'focus': ['focuses', 'foci'],
        'nucleus': ['nucleuses', 'nuclei'],
        'radius': ['radiuses', 'radii'],
        'index': ['indexes', 'indices'],
        'vertex': ['vertexes', 'vertices'],
        'matrix': ['matrixes', 'matrices'],
        'datum': ['data'],
        'medium': ['media'],
        'analysis': ['analyses'],
        'crisis': ['crises'],
        'thesis': ['theses'],
        'parenthesis': ['parentheses'],
        'oasis': ['oases'],
        'life': ['lives'],
        'knife': ['knives'],
        'leaf': ['leaves'],
        'wife': ['wives'],
        'half': ['halves'],
        'thief': ['thieves'],
        'wolf': ['wolves'],
        'shelf': ['shelves'],
        'calf': ['calves'],
        'loaf': ['loaves'],
        'sheaf': ['sheaves'],
        'elf': ['elves']
    }

    @classmethod
    def generate_inflections(cls, lemma, pos):
        """Generates inflected forms for a base lemma based on its Part of Speech (POS)."""
        lemma = lemma.strip().lower()
        forms = set()
        
        # POS-specific rules
        if pos in ['verb', 'v']:
            if lemma in cls.IRREGULAR_VERBS:
                return cls.IRREGULAR_VERBS[lemma]
            
            # Regular verbs
            # 3rd Person Present Singular (-s / -es)
            if lemma.endswith(('sh', 'ch', 's', 'x', 'z', 'o')):
                forms.add(lemma + 'es')
            elif lemma.endswith('y') and not lemma[-2] in 'aeiou':
                forms.add(lemma[:-1] + 'ies')
            else:
                forms.add(lemma + 's')
                
            # Gerund / Present Participle (-ing)
            if lemma.endswith('e') and not lemma.endswith('ee'):
                forms.add(lemma[:-1] + 'ing')
            elif lemma.endswith('p') and lemma[-2] in 'aeiou' and not lemma[-3] in 'aeiou':
                forms.add(lemma + 'ping') # e.g. stop -> stopping
            else:
                forms.add(lemma + 'ing')
                
            # Past / Past Participle (-ed)
            if lemma.endswith('e'):
                forms.add(lemma + 'd')
            elif lemma.endswith('y') and not lemma[-2] in 'aeiou':
                forms.add(lemma[:-1] + 'ied')
            else:
                forms.add(lemma + 'ed')
                
        elif pos in ['noun', 'n']:
            if lemma in cls.IRREGULAR_NOUNS:
                return cls.IRREGULAR_NOUNS[lemma]
                
            # Regular plural rules
            if lemma.endswith(('sh', 'ch', 's', 'x', 'z')):
                forms.add(lemma + 'es')
            elif lemma.endswith('y') and not lemma[-2] in 'aeiou':
                forms.add(lemma[:-1] + 'ies')
            elif lemma.endswith('fe'):
                forms.add(lemma[:-2] + 'ves')
            elif lemma.endswith('f') and not lemma.endswith('ff'):
                forms.add(lemma[:-1] + 'ves')
            else:
                forms.add(lemma + 's')
                
        elif pos in ['adjective', 'adj']:
            # Comparative/Superlative suffixes only for short adjectives (length <= 5)
            if len(lemma) <= 5:
                if lemma.endswith('y') and not lemma[-2] in 'aeiou':
                    forms.add(lemma[:-1] + 'ier')
                    forms.add(lemma[:-1] + 'iest')
                elif lemma.endswith('e'):
                    forms.add(lemma + 'r')
                    forms.add(lemma + 'st')
                else:
                    forms.add(lemma + 'er')
                    forms.add(lemma + 'est')
        
        return sorted(forms)


class BanglaMorphologyEngine:
    NOUN_SUFFIXES = ['টি', 'টা', 'গুলো', 'গুলি', 'দের', 'র', 'এর', 'কে', 'তে', 'এ', 'য়ে']
    
    @classmethod
    def generate_inflections(cls, lemma, pos=None):
        """Generates common Bangla inflections (nominal suffixes or verbal tenses) based on POS."""
        lemma = lemma.strip()
        forms = set()
        if len(lemma) < 2:
            return []
            
        is_verb = False
        if pos:
            pos_lower = pos.lower()
            if any(x in pos_lower for x in ['verb', 'v', 'ক্রিয়া', 'ক্রি.']):
                is_verb = True
                
        if is_verb:
            # Verbal Conjugation Heuristics
            if lemma.endswith('ওয়া'):
                # Verbs like খাওয়া, পাওয়া
                base = lemma[:-3]
                forms.add(base + 'ই')
                forms.add(base + 'স')
                forms.add(base + 'য়')
                forms.add(base + 'ন')
                forms.add(base + 'চ্ছ')
                forms.add(base + 'চ্ছি')
                forms.add(base + 'চ্ছে')
                forms.add(base + 'চ্ছেন')
                forms.add(base + 'ব')
                forms.add(base + 'বে')
                forms.add(base + 'বেন')
                # Vowel shifted past tenses for standard verbs
                if base in ['খা', 'পা', 'যা']:
                    shifted_base = 'খে' if base == 'খা' else ('পে' if base == 'পা' else 'গে')
                    forms.add(shifted_base + 'লাম')
                    forms.add(shifted_base + 'লে')
                    forms.add(shifted_base + 'লেন')
                    forms.add(shifted_base + 'ত')
                    forms.add(shifted_base + 'তেন')
                    forms.add(shifted_base + 'তে')
            elif lemma.endswith('া'):
                # Standard verbs like করা, দেখা, বলা
                base = lemma[:-1]
                for end in ['ি', 'িস', 'ে', 'েন', 'ছ', 'ছি', 'ছে', 'ছেন', 'ব', 'বে', 'বেন', 'লে', 'তে', 'ত', 'ুন', 'লাম', 'লেন', 'তেন']:
                    forms.add(base + end)
            else:
                # Fallback base conjugation
                base = lemma
                for end in ['ি', 'িস', 'ে', 'েন', 'ছ', 'ছি', 'ছে', 'ছেন', 'ব', 'বে', 'বেন', 'লে', 'তে', 'ত', 'ুন', 'লাম', 'লেন', 'তেন']:
                    forms.add(base + end)
        else:
            # Nominal/Noun Suffix Heuristics
            for suffix in cls.NOUN_SUFFIXES:
                if not lemma.endswith(suffix):
                    forms.add(lemma + suffix)
                    
        return sorted(forms)
