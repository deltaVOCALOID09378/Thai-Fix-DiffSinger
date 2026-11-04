# ==============================================================================
# File Name: autodsdict.py
# Version: 1.1
# Target Path: DiffTrainer-main\dt_modules\autodsdict.py
# Role: Automated DiffSinger Dictionary (dsdict.yaml) Generator supporting Thai DiffSinger AI, Thai Arpasing, Thai VCCV, and English Arpasing / โมดูลสร้างไฟล์พจนานุกรม dsdict.yaml อัตโนมัติ รองรับชุดโฟนีมภาษาไทยและภาษาอังกฤษเต็มรูปแบบ
# Credits: Made And Checked By DELTA SYNTH & All Agentic AI
# Original by agentasteriski (DiffTrainer) & Patiphat Wongyai (Delta)
# ==============================================================================

import os, glob, yaml, sys
from pathlib import Path

# ==============================================================================
# 1. ฐานข้อมูลชุดโฟนีมมาตรฐาน (Standard Phoneme Type Definitions)
#    รองรับ Thai DiffSinger AI, Thai Arpasing, Thai VCCV และ English Arpasing
# ==============================================================================

# ชุดโฟนีมแบบระบุชื่อเต็ม (Full-Symbol Exact Match) เพื่อความแม่นยำสูงสุดใน OpenUtau & DiffSinger
EXACT_PHONEME_TYPES = {
    # --- Silence / Breath / Glottal Stop ---
    "SP": "vowel",
    "AP": "vowel",
    "pau": "vowel",
    "sil": "vowel",
    "br": "vowel",
    "-": "stop",
    "q": "stop",
    "cl": "stop",
    "vf": "stop",

    # --- Thai DiffSinger AI Phonemizer: Consonants (พยัญชนะต้น) ---
    "b": "stop",       # บ
    "ch": "affricate", # ช
    "d": "stop",       # ด
    "f": "fricative",  # ฟ
    "ng": "nasal",     # ง (พยัญชนะต้นและตัวสะกด)
    "h": "fricative",  # ฮ
    "j": "affricate",  # จ
    "kk": "stop",      # ก
    "k": "stop",       # ค / ก (Arpasing & VCCV)
    "l": "liquid",     # ล
    "m": "nasal",      # ม
    "n": "nasal",      # น
    "pp": "stop",      # ป
    "p": "stop",       # พ / ป (Arpasing & VCCV)
    "r": "liquid",     # ร
    "s": "fricative",  # ซ
    "tt": "stop",      # ต
    "t": "stop",       # ท / ต (Arpasing & VCCV)
    "w": "semivowel",  # ว
    "y": "semivowel",  # ย

    # --- Thai Arpasing & Thai VCCV Additional Consonants ---
    "kh": "stop",      # ค (Thai Arpasing / VCCV)
    "ph": "stop",      # พ (Thai Arpasing / VCCV)
    "th": "stop",      # ท (Thai Arpasing / VCCV) / English Arpasing fricative
    "g": "nasal",      # ง (Thai Arpasing / VCCV) / English stop

    # --- Thai DiffSinger AI Phonemizer: Vowels (สระ) ---
    "a": "vowel",      # อา
    "i": "vowel",      # อี
    "u": "vowel",      # อู
    "e": "vowel",      # เอ
    "o": "vowel",      # โอ
    "A": "vowel",      # แอ
    "O": "vowel",      # ออ เอาะ
    "E": "vowel",      # เออ
    "Ua": "vowel",     # เอือ
    "U": "vowel",      # อือ
    "ia": "vowel",     # เอีย
    "ua": "vowel",     # อัว
    "I": "vowel",      # อัย ไอ ใอ อาย
    "au": "vowel",     # เอา อาว
    "am": "vowel",     # อำ อัม อาม

    # --- Thai Arpasing & English Arpasing Vowels (สระ) ---
    "ah": "vowel",     # อา / English AH
    "ih": "vowel",     # อี / English IH
    "uh": "vowel",     # อู / English UH
    "eh": "vowel",     # เอ / English EH
    "oh": "vowel",     # โอ
    "ae": "vowel",     # แอ / English AE
    "ao": "vowel",     # ออ / English AO
    "er": "vowel",     # เออ / English ER
    "eu": "vowel",     # เอือ
    "ue": "vowel",     # อือ
    "ay": "vowel",     # ไอ อัย ใอ อาย / English AY
    "aw": "vowel",     # เอา อาว / English AW
    "aa": "vowel",     # English AA
    "ey": "vowel",     # English EY
    "iy": "vowel",     # English IY
    "ow": "vowel",     # English OW
    "oy": "vowel",     # English OY
    "uw": "vowel",     # English UW
    "ax": "vowel",     # English AX (Schwa)
    "ix": "vowel",     # English IX

    # --- Thai VCCV Vowels (สระ) ---
    "@": "vowel",      # แอ
    "Q": "vowel",      # ออ เอาะ
    "3": "vowel",      # เออ
    "6": "vowel",      # เอือ
    "1": "vowel",      # อือ

    # --- Thai DiffSinger AI Phonemizer: Consonant Endings (ตัวสะกด) ---
    "M": "nasal",      # ม (ตัวสะกด)
    "Y": "semivowel",  # ย (ตัวสะกด)
    "W": "semivowel",  # ว (ตัวสะกด)
    "K": "stop",       # ก (ตัวสะกด)
    "B": "stop",       # บ (ตัวสะกด)
    "D": "stop",       # ด (ตัวสะกด)
    "N": "nasal",      # น (ตัวสะกดทางเลือก)

    # --- English Arpasing Consonants (พยัญชนะภาษาอังกฤษเพิ่มเติม) ---
    "dh": "fricative",
    "dx": "liquid",
    "hh": "fricative",
    "jh": "affricate",
    "sh": "fricative",
    "uh": "vowel",
    "v": "fricative",
    "z": "fricative",
    "zh": "fricative",
    "dr": "affricate",
    "tr": "affricate",
    "ts": "affricate",
    "dz": "affricate",
}

# ชุดแมปพยัญชนะ สระ และตัวสะกดภาษาไทยเป็นโฟนีม (สำหรับสร้าง Entries เสริมอัตโนมัติ)
THAI_GRAPHEME_TO_DIFFSINGER = {
    # พยัญชนะต้น (Consonants)
    "บ": ["b"], "ช": ["ch"], "ด": ["d"], "ฟ": ["f"], "ง": ["ng"],
    "ฮ": ["h"], "จ": ["j"], "ก": ["kk"], "ค": ["k"], "ล": ["l"],
    "ม": ["m"], "น": ["n"], "ป": ["pp"], "พ": ["p"], "ร": ["r"],
    "ซ": ["s"], "ต": ["tt"], "ท": ["t"], "ว": ["w"], "ย": ["y"], "อ": ["-"],
    # สระ (Vowels)
    "อา": ["a"], "อี": ["i"], "อู": ["u"], "เอ": ["e"], "โอ": ["o"],
    "แอ": ["A"], "ออ": ["O"], "เอาะ": ["O"], "เออ": ["E"], "เอือ": ["Ua"],
    "อือ": ["U"], "เอีย": ["ia"], "อัว": ["ua"],
    "อัย": ["I"], "ไอ": ["I"], "ใอ": ["I"], "อาย": ["I"],
    "เอา": ["au"], "อาว": ["au"],
    "อำ": ["am"], "อัม": ["am"], "อาม": ["am"],
}


def resolve_phoneme_type(phoneme: str, fallback_map: dict) -> str:
    """
    ตรวจสอบและคืนค่าประเภทของโฟนีม (vowel, stop, affricate, fricative, liquid, nasal, semivowel)
    รองรับการตัดคำนำหน้ารหัสภาษา (เช่น th/kk -> kk, en/ae -> ae) และเลขวรรณยุกต์/ความเค้นเสียง
    Determine the exact phoneme type for OpenUtau & DiffSinger dsdict.yaml.
    """
    if not phoneme:
        return "stop"

    base_ph = phoneme.split("/")[-1].strip()
    if not base_ph:
        return "stop"

    # 1. ตรวจสอบแบบตรงตัวทั้งหมด (Exact Match) เพื่อรักษาตัวพิมพ์เล็ก-ใหญ่ของ Thai DiffSinger (เช่น A, O, E, Ua, U, I, M, Y, W, K, B, D)
    if base_ph in EXACT_PHONEME_TYPES:
        return EXACT_PHONEME_TYPES[base_ph]

    # 2. ตรวจสอบกรณีมีตัวเลขระดับความเค้นเสียงของ English Arpasing ต่อท้าย (เช่น ah0, iy1, er0)
    stripped_digits = base_ph.rstrip("0123456789")
    if stripped_digits and stripped_digits in EXACT_PHONEME_TYPES:
        return EXACT_PHONEME_TYPES[stripped_digits]
    if stripped_digits and stripped_digits.lower() in EXACT_PHONEME_TYPES:
        return EXACT_PHONEME_TYPES[stripped_digits.lower()]

    # 3. ตรวจสอบแบบตัวพิมพ์เล็กสำหรับโฟนีมทั่วไป
    if base_ph.lower() in EXACT_PHONEME_TYPES:
        return EXACT_PHONEME_TYPES[base_ph.lower()]

    # 4. Fallback ไปยังตารางตัวอักษรแรกตามโค้ดต้นฉบับ
    return fallback_map.get(base_ph[0], "stop")


def extract_dict_lang_ext(dictionary_file: str) -> str:
    """
    ดึงรหัสภาษาจากชื่อไฟล์ dictionary อย่างปลอดภัย (เช่น dictionary-th.txt -> th, dictionary.txt -> default)
    Safely extract language extension from dictionary filename without IndexError.
    """
    stem = os.path.splitext(os.path.basename(dictionary_file))[0]
    if "-" in stem:
        parts = stem.split("-", 1)
        if len(parts) > 1 and parts[1].strip():
            return parts[1].strip()
    return stem


def parse_dictionary_line(line: str):
    """
    แยกคำศัพท์ (Grapheme) และลำดับโฟนีม (Phoneme Sequence) จากแต่ละบรรทัดของไฟล์ dictionary.txt
    รองรับทั้งรูปแบบ 'word\tph1 ph2' และรูปแบบบรรทัดที่มีเฉพาะโฟนีมเดี่ยว
    Parse a line from dictionary file safely.
    """
    cleaned = line.strip()
    if not cleaned or cleaned.startswith("#"):
        return None, []

    if "\t" in cleaned:
        parts = cleaned.split("\t", 1)
        grapheme = parts[0].strip()
        phonemes = parts[1].strip().split()
    else:
        tokens = cleaned.split()
        grapheme = tokens[0]
        phonemes = tokens[1:] if len(tokens) > 1 else [tokens[0]]

    if not grapheme or not phonemes:
        return None, []
    return grapheme, phonemes


def dictgenerator(aco_folder_dir, main_stuff):
    """
    ฟังก์ชันหลักสำหรับสร้างไฟล์พจนานุกรม dsdict.yaml (คงชื่อและพารามิเตอร์เดิม 100% เพื่อความเข้ากันได้ของระบบ)
    Main generator function for dsdict.yaml and language-specific dsdict-[lang].yaml files.
    """
    aco_folder_onnx = os.path.join(aco_folder_dir, "onnx")
    phoneme_types_list = {
        "a": "vowel", "i": "vowel", "u": "vowel", "e": "vowel", "o": "vowel",
        "A": "vowel", "I": "vowel", "U": "vowel", "E": "vowel", "O": "vowel", "N": "nasal", "M": "nasal",
        "b": "stop", "d": "stop", "g": "stop", "k": "stop", "p": "stop", "q": "stop", "t": "stop",
        "c": "affricate", "j": "affricate",
        "f": "fricative", "h": "fricative", "s": "fricative", "v": "fricative", "z": "fricative",
        "l": "liquid", "r": "liquid",
        "m": "nasal", "n": "nasal",
        "w": "semivowel", "y": "semivowel",
        "-": "stop", "@": "vowel", "Q": "vowel", "3": "vowel", "6": "vowel", "1": "vowel",
        "Y": "semivowel", "W": "semivowel", "K": "stop", "B": "stop", "D": "stop",
    }
    ou_canon_languages = {"zh", "en", "de", "it", "ja", "yue", "ko", "pt", "ru", "es"}

    os.makedirs(main_stuff, exist_ok=True)
    lang_dictionary_files = sorted(glob.glob(os.path.join(aco_folder_onnx, "*.txt")))
    print("[INFO / ข้อมูล] Dictionary files found / พบไฟล์พจนานุกรม:", [os.path.basename(dict_name) for dict_name in lang_dictionary_files])

    training_config = os.path.join(aco_folder_dir, "config.yaml")
    extra_phonemes = []
    if os.path.exists(training_config):
        with open(training_config, "r", encoding="utf-8") as extrasource:
            config = yaml.safe_load(extrasource) or {}
            extra_phonemes = config.get("extra_phonemes", []) or []
    print(f"[INFO / ข้อมูล] Found {len(extra_phonemes)} extra phonemes / พบโฟนีมเพิ่มเติม {len(extra_phonemes)} รายการ")

    # ตรวจสอบไฟล์ phonemes.json ในโฟลเดอร์ onnx เพิ่มเติมเพื่อให้มั่นใจว่าไม่มีโฟนีมของ Thai DiffSinger หรือ Arpasing ตกหล่น
    phonemes_json_path = os.path.join(aco_folder_onnx, "phonemes.json")
    if os.path.exists(phonemes_json_path):
        try:
            import json
            with open(phonemes_json_path, "r", encoding="utf-8") as pf:
                ph_json_data = json.load(pf)
            if isinstance(ph_json_data, dict):
                for ph_key in ph_json_data.keys():
                    if ph_key not in extra_phonemes and ph_key not in ("AP", "SP", "pad", "bos", "eos", "unk"):
                        extra_phonemes.append(ph_key)
            elif isinstance(ph_json_data, list):
                for ph_key in ph_json_data:
                    if ph_key not in extra_phonemes and ph_key not in ("AP", "SP", "pad", "bos", "eos", "unk"):
                        extra_phonemes.append(ph_key)
        except Exception as exc:
            print(f"[WARNING / คำเตือน] Could not read phonemes.json: {exc}")

    language_specific_phonemes = {}
    general_phonemes = []

    for phoneme in extra_phonemes:
        phoneme_str = str(phoneme).strip()
        if not phoneme_str or phoneme_str in ("AP", "SP", "pau", "sil", "pad", "bos", "eos", "unk") or "trash" in phoneme_str:
            continue
        if "/" in phoneme_str:  # Check for language prefix
            lang_code, basephoneme = phoneme_str.split("/", 1)
            if lang_code not in language_specific_phonemes:
                language_specific_phonemes[lang_code] = []
            if basephoneme not in language_specific_phonemes[lang_code]:
                language_specific_phonemes[lang_code].append(basephoneme)
        else:
            if phoneme_str not in general_phonemes:
                general_phonemes.append(phoneme_str)

    # ==========================================================================
    # กรณีที่ 1: มีไฟล์พจนานุกรมเพียงไฟล์เดียว (Single Dictionary Mode)
    # ==========================================================================
    if len(lang_dictionary_files) == 1:
        dictionary_file = lang_dictionary_files[0]
        dictionary_ext = extract_dict_lang_ext(dictionary_file)

        symbols = []
        entries = []
        seen_symbols = {"SP", "AP"}
        seen_entries = {"SP", "AP"}

        def add_single_symbol(sym_name: str):
            if sym_name and sym_name not in seen_symbols and "trash" not in sym_name:
                seen_symbols.add(sym_name)
                ph_type = resolve_phoneme_type(sym_name, phoneme_types_list)
                symbols.append({"symbol": sym_name, "type": ph_type})

        def add_single_entry(grapheme_name: str, ph_list: list):
            if grapheme_name and grapheme_name not in seen_entries:
                seen_entries.add(grapheme_name)
                entries.append({"grapheme": grapheme_name, "phonemes": ph_list})

        for phoneme in general_phonemes:
            add_single_symbol(phoneme)
            add_single_entry(phoneme, [phoneme])

        if dictionary_ext in language_specific_phonemes:
            for phoneme in language_specific_phonemes[dictionary_ext]:
                add_single_symbol(phoneme)
                add_single_entry(phoneme, [phoneme])

        with open(dictionary_file, "r", encoding="utf-8") as f:
            for line in f:
                grapheme, ph_seq = parse_dictionary_line(line)
                if not grapheme:
                    continue
                for ph in ph_seq:
                    add_single_symbol(ph)
                    add_single_entry(ph, [ph])
                add_single_entry(grapheme, ph_seq)

        # เพิ่มการแมปคำอ่านภาษาไทยพื้นฐานหากตรวจพบโฟนีม Thai DiffSinger
        for th_grapheme, th_phs in THAI_GRAPHEME_TO_DIFFSINGER.items():
            if all(p in seen_symbols for p in th_phs):
                add_single_entry(th_grapheme, th_phs)

        out_path = os.path.join(main_stuff, "dsdict.yaml")
        print(f"[SUCCESS / สำเร็จ] Writing file: dsdict.yaml with {len(symbols)} symbols and {len(entries)} entries")
        with open(out_path, "w", encoding="utf-8") as out_f:
            out_f.write("symbols:\n")
            out_f.write("- {symbol: SP, type: vowel}\n")
            out_f.write("- {symbol: AP, type: vowel}\n")
            for item in symbols:
                out_f.write(f"- {{symbol: \"{item['symbol']}\", type: {item['type']}}}\n")
            out_f.write("\nentries:\n")
            for item in entries:
                ph_formatted = ", ".join(f"\"{p}\"" for p in item["phonemes"])
                out_f.write(f"- {{grapheme: \"{item['grapheme']}\", phonemes: [{ph_formatted}]}}\n")
            out_f.write("- {grapheme: \"SP\", phonemes: [SP]}\n")
            out_f.write("- {grapheme: \"AP\", phonemes: [AP]}\n")

    # ==========================================================================
    # กรณีที่ 2: มีไฟล์พจนานุกรมหลายภาษา (Multi-Language / Thai + English Mode)
    # ==========================================================================
    else:
        all_symbols = []
        all_entries = []
        seen_all_symbols = {"SP", "AP"}
        seen_all_entries = {"SP", "AP"}

        def add_global_symbol(sym_name: str):
            if sym_name and sym_name not in seen_all_symbols and "trash" not in sym_name:
                seen_all_symbols.add(sym_name)
                ph_type = resolve_phoneme_type(sym_name, phoneme_types_list)
                all_symbols.append({"symbol": sym_name, "type": ph_type})

        def add_global_entry(grapheme_name: str, ph_list: list):
            if grapheme_name and grapheme_name not in seen_all_entries:
                seen_all_entries.add(grapheme_name)
                all_entries.append({"grapheme": grapheme_name, "phonemes": ph_list})

        for phoneme in general_phonemes:
            add_global_symbol(phoneme)
            add_global_entry(phoneme, [phoneme])

        # First, accumulate all symbols from all dictionaries
        for dictionary_file in lang_dictionary_files:
            dictionary_ext = extract_dict_lang_ext(dictionary_file)

            with open(dictionary_file, "r", encoding="utf-8") as f:
                for line in f:
                    grapheme, ph_seq = parse_dictionary_line(line)
                    if not grapheme:
                        continue
                    prefixed_seq = [f"{dictionary_ext}/{ph}" if "/" not in ph else ph for ph in ph_seq]
                    for raw_ph, pref_ph in zip(ph_seq, prefixed_seq):
                        add_global_symbol(pref_ph)
                        add_global_entry(raw_ph, [pref_ph])
                    add_global_entry(grapheme, prefixed_seq)

            if dictionary_ext in language_specific_phonemes:
                for phoneme in language_specific_phonemes[dictionary_ext]:
                    pref_ph = f"{dictionary_ext}/{phoneme}" if "/" not in phoneme else phoneme
                    add_global_symbol(pref_ph)
                    add_global_entry(phoneme, [pref_ph])

        # หากมีรหัสภาษาใน extra_phonemes ที่ไม่มีไฟล์ .txt แยก ให้เพิ่มเข้ามารวมด้วย
        for lang_code, ph_list in language_specific_phonemes.items():
            for phoneme in ph_list:
                pref_ph = f"{lang_code}/{phoneme}" if "/" not in phoneme else phoneme
                add_global_symbol(pref_ph)
                add_global_entry(phoneme, [pref_ph])

        # Now, write each dsdict-[dictionary_ext].yaml file
        for dictionary_file in lang_dictionary_files:
            dictionary_ext = extract_dict_lang_ext(dictionary_file)

            symbols = []
            replacements = []
            entries = []
            seen_local_symbols = set()
            seen_local_replacements = set()
            seen_local_entries = {"SP", "AP"}

            with open(dictionary_file, "r", encoding="utf-8") as f:
                for line in f:
                    grapheme, ph_seq = parse_dictionary_line(line)
                    if not grapheme:
                        continue
                    prefixed_seq = [f"{dictionary_ext}/{ph}" if "/" not in ph else ph for ph in ph_seq]
                    for raw_ph, pref_ph in zip(ph_seq, prefixed_seq):
                        if pref_ph not in seen_local_symbols:
                            seen_local_symbols.add(pref_ph)
                            ph_type = resolve_phoneme_type(raw_ph, phoneme_types_list)
                            symbols.append({"symbol": pref_ph, "type": ph_type})
                        if raw_ph not in seen_local_replacements:
                            seen_local_replacements.add(raw_ph)
                            replacements.append({"from": raw_ph, "to": pref_ph})
                        if raw_ph not in seen_local_entries:
                            seen_local_entries.add(raw_ph)
                            entries.append({"grapheme": raw_ph, "phonemes": [pref_ph]})

                    if grapheme not in seen_local_entries:
                        seen_local_entries.add(grapheme)
                        entries.append({"grapheme": grapheme, "phonemes": prefixed_seq})

            if dictionary_ext in language_specific_phonemes:
                for raw_ph in language_specific_phonemes[dictionary_ext]:
                    pref_ph = f"{dictionary_ext}/{raw_ph}" if "/" not in raw_ph else raw_ph
                    if pref_ph not in seen_local_symbols:
                        seen_local_symbols.add(pref_ph)
                        ph_type = resolve_phoneme_type(raw_ph, phoneme_types_list)
                        symbols.append({"symbol": pref_ph, "type": ph_type})
                    if raw_ph not in seen_local_replacements:
                        seen_local_replacements.add(raw_ph)
                        replacements.append({"from": raw_ph, "to": pref_ph})
                    if raw_ph not in seen_local_entries:
                        seen_local_entries.add(raw_ph)
                        entries.append({"grapheme": raw_ph, "phonemes": [pref_ph]})

            out_path = os.path.join(main_stuff, f"dsdict-{dictionary_ext}.yaml")
            print(f"[SUCCESS / สำเร็จ] Writing file: dsdict-{dictionary_ext}.yaml with {len(symbols)} language symbols")
            with open(out_path, "w", encoding="utf-8") as out_f:
                out_f.write("symbols:\n")
                out_f.write("- {symbol: SP, type: vowel}\n")
                out_f.write("- {symbol: AP, type: vowel}\n")
                for item in all_symbols:
                    out_f.write(f"- {{symbol: \"{item['symbol']}\", type: {item['type']}}}\n")
                if dictionary_ext not in ou_canon_languages and replacements:
                    out_f.write("\nreplacements:\n")
                    for item in replacements:
                        out_f.write(f"- {{from: \"{item['from']}\", to: \"{item['to']}\"}}\n")
                out_f.write("\nentries:\n")
                for item in entries:
                    ph_formatted = ", ".join(f"\"{p}\"" for p in item["phonemes"])
                    out_f.write(f"- {{grapheme: \"{item['grapheme']}\", phonemes: [{ph_formatted}]}}\n")
                out_f.write("- {grapheme: \"SP\", phonemes: [SP]}\n")
                out_f.write("- {grapheme: \"AP\", phonemes: [AP]}\n")

        # Finally, write the base dsdict.yaml
        dsdict_path = os.path.join(main_stuff, "dsdict.yaml")
        print(f"[SUCCESS / สำเร็จ] Writing file: dsdict.yaml with {len(all_symbols)} total symbols")
        with open(dsdict_path, "w", encoding="utf-8") as out_f:
            out_f.write("symbols:\n")
            out_f.write("- {symbol: SP, type: vowel}\n")
            out_f.write("- {symbol: AP, type: vowel}\n")
            for item in all_symbols:
                out_f.write(f"- {{symbol: \"{item['symbol']}\", type: {item['type']}}}\n")
            out_f.write("\nentries:\n")
            for item in all_entries:
                ph_formatted = ", ".join(f"\"{p}\"" for p in item["phonemes"])
                out_f.write(f"- {{grapheme: \"{item['grapheme']}\", phonemes: [{ph_formatted}]}}\n")
            out_f.write("- {grapheme: \"SP\", phonemes: [SP]}\n")
            out_f.write("- {grapheme: \"AP\", phonemes: [AP]}\n")


# ==============================================================================
# ส่วนการรันแบบ Standalone CLI (รองรับการลากโฟลเดอร์โมเดลมาวางผ่านไฟล์ .bat)
# ==============================================================================
if __name__ == "__main__":
    print("==============================================================================")
    print("  DELTA SYNTH - Automated DiffSinger Dictionary Generator v1.1")
    print("  ระบบสร้างพจนานุกรม dsdict.yaml อัตโนมัติ (Thai DiffSinger & English Arpasing)")
    print("==============================================================================")
    if len(sys.argv) >= 2:
        target_aco_dir = sys.argv[1]
        target_out_dir = sys.argv[2] if len(sys.argv) >= 3 else target_aco_dir
        if os.path.isdir(target_aco_dir):
            dictgenerator(target_aco_dir, target_out_dir)
            print("[COMPLETE / เสร็จสมบูรณ์] สร้างไฟล์พจนานุกรมเรียบร้อยแล้ว")
        else:
            print(f"[ERROR / ข้อผิดพลาด] ไม่พบโฟลเดอร์เป้าหมาย: {target_aco_dir}")
    else:
        print("[USAGE / วิธีใช้งาน] python autodsdict.py <acoustic_checkpoint_folder> [output_folder]")