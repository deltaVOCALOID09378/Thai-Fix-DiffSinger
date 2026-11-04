# ==============================================================================
# File Name: advexport.py
# Version: 1.1
# Target Path: DiffTrainer-main\dt_modules\advexport.py
# Role: Advanced Multi-Model OpenUtau DiffSinger Voicebank Exporter with Automated Thai character.yaml & dsconfig.yaml Configuration / โมดูลส่งออกโมเดลเสียง DiffSinger ขั้นสูงแบบแยกส่วนสำหรับ OpenUtau พร้อมตั้งค่ารองรับภาษาไทยอัตโนมัติ
# Credits: Made And Checked By DELTA SYNTH & All Agentic AI
# Original by agentasteriski (DiffTrainer) & Patiphat Wongyai (Delta)
# ==============================================================================

import os, shutil, yaml, glob, json, sys
from dt_modules import autodsdict  # type: ignore (stops vscode from whining)

THAI_SIGNATURE_PHONEMES = {"kk", "pp", "tt", "Ua", "am", "au", "kh", "ph", "th", "eu", "ue"}


def _unwrap_var(val, default=""):
    """ดึงค่าจากตัวแปร Tkinter/CustomTkinter Variable หรือคืนค่าปกติอย่างปลอดภัย / Safely extract value from CTk variable or primitive."""
    if val is None:
        return default
    if hasattr(val, "get") and callable(val.get):
        try:
            return val.get()
        except Exception:
            return default
    return val


def _resolve_onnx_dir(folder_dir) -> str:
    """แปลงพาธโฟลเดอร์โมเดลเป็นพาธโฟลเดอร์ย่อย onnx อย่างปลอดภัย (ป้องกันบัคพาธว่าง) / Safely resolve onnx subfolder."""
    clean_dir = str(_unwrap_var(folder_dir, "")).strip()
    if not clean_dir or not os.path.exists(clean_dir):
        return ""
    onnx_candidate = os.path.join(clean_dir, "onnx")
    return onnx_candidate if os.path.exists(onnx_candidate) else ""


def _detect_thai_support(folder_onnx: str) -> bool:
    """ตรวจสอบว่าโมเดลชุดนี้รองรับภาษาไทยหรือไม่ / Detect Thai language or Thai DiffSinger phonemes."""
    if not folder_onnx or not os.path.exists(folder_onnx):
        return False

    for txt_file in glob.glob(os.path.join(folder_onnx, "*.txt")):
        base_name = os.path.basename(txt_file).lower()
        if "-th." in base_name or "_th." in base_name or base_name == "th.txt":
            return True

    lang_json_path = os.path.join(folder_onnx, "languages.json")
    if os.path.exists(lang_json_path):
        try:
            with open(lang_json_path, "r", encoding="utf-8") as f:
                langs = json.load(f)
            if isinstance(langs, dict) and ("th" in langs or "tha" in langs):
                return True
        except Exception:
            pass

    ph_json_path = os.path.join(folder_onnx, "phonemes.json")
    if os.path.exists(ph_json_path):
        try:
            with open(ph_json_path, "r", encoding="utf-8") as f:
                phs = json.load(f)
            keys = phs.keys() if isinstance(phs, dict) else phs
            for k in keys:
                k_str = str(k)
                if k_str.startswith("th/") or k_str in THAI_SIGNATURE_PHONEMES:
                    return True
        except Exception:
            pass

    return False


def _ensure_thai_in_languages_json(lang_json_path: str) -> None:
    """ตรวจสอบและแน่ใจว่าไฟล์ languages.json มีรหัสภาษาไทย ('th') / Ensure 'th' exists in languages.json."""
    if not os.path.exists(lang_json_path):
        return
    try:
        with open(lang_json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and "th" not in data:
            next_id = max(data.values(), default=-1) + 1
            data["th"] = next_id
            with open(lang_json_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"[WARNING / คำเตือน] Could not update languages.json: {e}")


def run_adv_config(ou_name_var2, ou_export_location, aco_folder_dir, dur_folder_dir, var_folder_dir=None, pitch_folder_dir=None, vocoder_onnx=None, autodsdictvar2=None):
    print("\n[INFO / ข้อมูล] Making directories (Advanced Mode) / กำลังสร้างโครงสร้างโฟลเดอร์โหมดขั้นสูง...")
    aco_folder_onnx = _resolve_onnx_dir(aco_folder_dir)
    dur_folder_onnx = _resolve_onnx_dir(dur_folder_dir)
    var_folder_onnx = _resolve_onnx_dir(var_folder_dir)
    pitch_folder_onnx = _resolve_onnx_dir(pitch_folder_dir)

    is_thai_model = any(
        _detect_thai_support(p)
        for p in (aco_folder_onnx, dur_folder_onnx, var_folder_onnx, pitch_folder_onnx)
        if p
    )
    if is_thai_model:
        print("[INFO / ข้อมูล] Thai DiffSinger AI phonemes detected! Applying Thai configuration / ตรวจพบชุดโฟนีมภาษาไทย กำลังตั้งค่ารองรับภาษาไทยอัตโนมัติ")

    ou_name = str(_unwrap_var(ou_name_var2, "DiffSinger_Voicebank")).strip()
    if not ou_name:
        ou_name = "DiffSinger_Voicebank"
    ou_name_stripped = "".join(ou_name.split())
    main_stuff = os.path.join(ou_export_location, ou_name_stripped)
    dsmain = os.path.join(main_stuff, "dsmain")
    mainembeds = os.path.join(main_stuff, "embeds")
    dsdur = os.path.join(main_stuff, "dsdur")
    durembeds = os.path.join(dsdur, "embeds")
    dsvariance = os.path.join(main_stuff, "dsvariance")
    varembeds = os.path.join(dsvariance, "embeds")
    dspitch = os.path.join(main_stuff, "dspitch")
    pitchembeds = os.path.join(dspitch, "embeds")

    try:
        os.makedirs(main_stuff, exist_ok=True)
        os.makedirs(dsmain, exist_ok=True)
        os.makedirs(mainembeds, exist_ok=True)
        os.makedirs(dsdur, exist_ok=True)
        os.makedirs(durembeds, exist_ok=True)

        if var_folder_onnx:
            os.makedirs(dsvariance, exist_ok=True)
            os.makedirs(varembeds, exist_ok=True)

        if pitch_folder_onnx:
            os.makedirs(dspitch, exist_ok=True)
            os.makedirs(pitchembeds, exist_ok=True)

        with open(os.path.join(main_stuff, "character.txt"), "w", encoding="utf-8") as file:
            file.write(f"name={ou_name}\n")

        initial_char_config = {
            "name": ou_name,
            "singer_type": "diffsinger",
            "text_file_encoding": "utf-8",
            "default_phonemizer": "OpenUtau.Core.DiffSinger.DiffSingerPhonemizer",
            "image": "",
            "portrait": "",
            "portrait_opacity": 0.45,
        }
        if is_thai_model:
            initial_char_config["language"] = "th"

        with open(os.path.join(main_stuff, "character.yaml"), "w", encoding="utf-8") as file:
            yaml.dump(initial_char_config, file, allow_unicode=True, sort_keys=False)
    except Exception as e:
        print(f"[ERROR / ข้อผิดพลาด] Error creating directories: {e}")

    print("\n[INFO / ข้อมูล] Moving core files / กำลังคัดลอกไฟล์แกนหลัก...")
    try:
        if os.path.exists(os.path.join(aco_folder_onnx, "acoustic.onnx")):
            shutil.copy(os.path.join(aco_folder_onnx, "acoustic.onnx"), dsmain)
        if os.path.exists(os.path.join(aco_folder_onnx, "phonemes.json")):
            shutil.copy(os.path.join(aco_folder_onnx, "phonemes.json"), dsmain)
        if os.path.exists(os.path.join(aco_folder_onnx, "languages.json")):
            shutil.copy(os.path.join(aco_folder_onnx, "languages.json"), dsmain)
            if is_thai_model:
                _ensure_thai_in_languages_json(os.path.join(dsmain, "languages.json"))
        if os.path.exists(os.path.join(aco_folder_onnx, "dsconfig.yaml")):
            shutil.copy(os.path.join(aco_folder_onnx, "dsconfig.yaml"), main_stuff)
    except Exception as e:
        print(f"[ERROR / ข้อผิดพลาด] Error moving core files: {e}")

    print("\n[INFO / ข้อมูล] Moving acoustic embeds / กำลังคัดลอกไฟล์โทนเสียง Acoustic...")
    acoustic_embeds = []
    acoustic_color_suffix = []
    try:
        if aco_folder_onnx and os.path.exists(aco_folder_onnx):
            acoustic_emb_files = sorted([file for file in os.listdir(aco_folder_onnx) if file.endswith(".emb")])
            for emb_file in acoustic_emb_files:
                shutil.copy(os.path.join(aco_folder_onnx, emb_file), mainembeds)
                acoustic_emb = os.path.splitext(emb_file)[0]
                acoustic_embeds.append("embeds/" + acoustic_emb)
                acoustic_color_suffix.append(acoustic_emb)
    except Exception as e:
        print(f"[ERROR / ข้อผิดพลาด] Error moving acoustic embeds: {e}")

    print("\n[INFO / ข้อมูล] Moving duration files / กำลังคัดลอกไฟล์โมเดลความยาวเสียง (Duration)...")
    duration_embeds = []
    duration_color_suffix = []
    try:
        if dur_folder_onnx and os.path.exists(dur_folder_onnx):
            dur_emb_files = sorted([file for file in os.listdir(dur_folder_onnx) if file.endswith(".emb")])
            for emb_file in dur_emb_files:
                shutil.copy(os.path.join(dur_folder_onnx, emb_file), durembeds)
                duration_emb = os.path.splitext(emb_file)[0]
                duration_embeds.append("embeds/" + duration_emb)
                duration_color_suffix.append(duration_emb)
            if os.path.exists(os.path.join(dur_folder_onnx, "dur.onnx")):
                shutil.copy(os.path.join(dur_folder_onnx, "dur.onnx"), dsdur)
            if os.path.exists(os.path.join(dur_folder_onnx, "phonemes.json")):
                shutil.copy(os.path.join(dur_folder_onnx, "phonemes.json"), dsdur)
            if os.path.exists(os.path.join(dur_folder_onnx, "linguistic.onnx")):
                shutil.copy(os.path.join(dur_folder_onnx, "linguistic.onnx"), dsdur)
            if os.path.exists(os.path.join(dur_folder_onnx, "languages.json")):
                shutil.copy(os.path.join(dur_folder_onnx, "languages.json"), dsdur)
                if is_thai_model:
                    _ensure_thai_in_languages_json(os.path.join(dsdur, "languages.json"))
    except Exception as e:
        print(f"[ERROR / ข้อผิดพลาด] Error moving duration files: {e}")

    print("\n[INFO / ข้อมูล] Moving variance files / กำลังคัดลอกไฟล์โมเดล Variance...")
    variance_embeds = []
    variance_color_suffix = []
    try:
        if var_folder_onnx and os.path.exists(var_folder_onnx):
            var_emb_files = sorted([file for file in os.listdir(var_folder_onnx) if file.endswith(".emb")])
            for emb_file in var_emb_files:
                shutil.copy(os.path.join(var_folder_onnx, emb_file), varembeds)
                variance_emb = os.path.splitext(emb_file)[0]
                variance_embeds.append("embeds/" + variance_emb)
                variance_color_suffix.append(variance_emb)
            if os.path.exists(os.path.join(var_folder_onnx, "variance.onnx")):
                shutil.copy(os.path.join(var_folder_onnx, "variance.onnx"), dsvariance)
            if os.path.exists(os.path.join(var_folder_onnx, "linguistic.onnx")):
                shutil.copy(os.path.join(var_folder_onnx, "linguistic.onnx"), dsvariance)
            if os.path.exists(os.path.join(var_folder_onnx, "phonemes.json")):
                shutil.copy(os.path.join(var_folder_onnx, "phonemes.json"), dsvariance)
    except Exception as e:
        print(f"[ERROR / ข้อผิดพลาด] Error moving variance files: {e}")

    print("\n[INFO / ข้อมูล] Moving pitch files / กำลังคัดลอกไฟล์โมเดลระดับเสียง (Pitch)...")
    pitch_embeds = []
    pitch_color_suffix = []
    try:
        if pitch_folder_onnx and os.path.exists(pitch_folder_onnx):
            pitch_emb_files = sorted([file for file in os.listdir(pitch_folder_onnx) if file.endswith(".emb")])
            for emb_file in pitch_emb_files:
                shutil.copy(os.path.join(pitch_folder_onnx, emb_file), pitchembeds)
                pitch_emb = os.path.splitext(emb_file)[0]
                pitch_embeds.append("embeds/" + pitch_emb)
                pitch_color_suffix.append(pitch_emb)
            if os.path.exists(os.path.join(pitch_folder_onnx, "pitch.onnx")):
                shutil.copy(os.path.join(pitch_folder_onnx, "pitch.onnx"), dspitch)
            if os.path.exists(os.path.join(pitch_folder_onnx, "linguistic.onnx")):
                shutil.copy(os.path.join(pitch_folder_onnx, "linguistic.onnx"), dspitch)
            if os.path.exists(os.path.join(pitch_folder_onnx, "phonemes.json")):
                shutil.copy(os.path.join(pitch_folder_onnx, "phonemes.json"), dspitch)
    except Exception as e:
        print(f"[ERROR / ข้อผิดพลาด] Error moving pitch files: {e}")

    print("[INFO / ข้อมูล] Writing main configs / กำลังเขียนไฟล์ตั้งค่าหลัก character.yaml และ dsconfig.yaml...")
    subbanks = []
    try:
        for i, (acoustic_embed_color, acoustic_embed_suffix) in enumerate(zip(acoustic_color_suffix, acoustic_embeds), start=1):
            color = f"{i:02}: {acoustic_embed_color}"
            suffix = f"{acoustic_embed_suffix}"
            subbanks.append({"color": color, "suffix": suffix})

        char_yaml_path = os.path.join(main_stuff, "character.yaml")
        character_config = {}
        if os.path.exists(char_yaml_path):
            with open(char_yaml_path, "r", encoding="utf-8") as config:
                character_config = yaml.safe_load(config) or {}

        character_config["name"] = ou_name
        character_config["singer_type"] = "diffsinger"
        character_config["text_file_encoding"] = "utf-8"
        character_config["default_phonemizer"] = "OpenUtau.Core.DiffSinger.DiffSingerPhonemizer"
        if is_thai_model:
            character_config["language"] = "th"
        if subbanks:
            character_config["subbanks"] = subbanks

        with open(char_yaml_path, "w", encoding="utf-8") as config:
            yaml.dump(character_config, config, allow_unicode=True, sort_keys=False)

        main_dsconfig_path = os.path.join(main_stuff, "dsconfig.yaml")
        dsconfig_data = {}
        if os.path.exists(main_dsconfig_path):
            with open(main_dsconfig_path, "r", encoding="utf-8") as config:
                dsconfig_data = yaml.safe_load(config) or {}

        dsconfig_data["acoustic"] = "dsmain/acoustic.onnx"
        dsconfig_data["phonemes"] = "dsmain/phonemes.json"
        if os.path.exists(os.path.join(dsmain, "languages.json")):
            dsconfig_data["languages"] = "dsmain/languages.json"
        dsconfig_data["vocoder"] = dsconfig_data.get("vocoder") or "pc_nsf_hifigan_44.1k_hop512_128bin_2025.02"
        dsconfig_data["singer_type"] = "diffsinger"
        if subbanks:
            dsconfig_data["speakers"] = acoustic_embeds

        with open(main_dsconfig_path, "w", encoding="utf-8") as config:
            yaml.dump(dsconfig_data, config, allow_unicode=True, sort_keys=False)
    except Exception as e:
        print(f"[ERROR / ข้อผิดพลาด] Error writing OU main configs: {e}")

    print("[INFO / ข้อมูล] Writing sub-configs / กำลังเขียนไฟล์ตั้งค่าย่อย...")
    has_main_lang_json = os.path.exists(os.path.join(dsmain, "languages.json"))
    try:
        dur_dsconfig_src = os.path.join(dur_folder_onnx, "dsconfig.yaml") if dur_folder_onnx else ""
        dur_config_data = {}
        if dur_dsconfig_src and os.path.exists(dur_dsconfig_src):
            with open(dur_dsconfig_src, "r", encoding="utf-8") as config:
                dur_config_data = yaml.safe_load(config) or {}

        sample_rate = dur_config_data.get("sample_rate", 44100)
        hop_size = dur_config_data.get("hop_size", 512)
        use_continuous_acceleration = dur_config_data.get("use_continuous_acceleration", True)
        use_lang_id = dur_config_data.get("use_lang_id", False)
        hidden_size = dur_config_data.get("hidden_size", 256)

        dsdur_config = {
            "phonemes": "phonemes.json",
            "linguistic": "linguistic.onnx",
            "dur": "dur.onnx",
            "use_continuous_acceleration": use_continuous_acceleration,
            "sample_rate": sample_rate,
            "hidden_size": hidden_size,
            "hop_size": hop_size,
            "predict_dur": True,
            "use_lang_id": use_lang_id,
        }
        if has_main_lang_json:
            dsdur_config["languages"] = "../dsmain/languages.json"
        elif os.path.exists(os.path.join(dsdur, "languages.json")):
            dsdur_config["languages"] = "languages.json"
        if subbanks and duration_embeds:
            dsdur_config["speakers"] = duration_embeds

        with open(os.path.join(dsdur, "dsconfig.yaml"), "w", encoding="utf-8") as config:
            yaml.dump(dsdur_config, config, allow_unicode=True, sort_keys=False)

        try:
            if var_folder_onnx and os.path.exists(os.path.join(var_folder_onnx, "dsconfig.yaml")):
                with open(os.path.join(var_folder_onnx, "dsconfig.yaml"), "r", encoding="utf-8") as config:
                    var_config_data = yaml.safe_load(config) or {}

                dsvariance_config = {
                    "phonemes": "phonemes.json",
                    "linguistic": "linguistic.onnx",
                    "variance": "variance.onnx",
                    "use_continuous_acceleration": var_config_data.get("use_continuous_acceleration", True),
                    "sample_rate": var_config_data.get("sample_rate", sample_rate),
                    "hidden_size": var_config_data.get("hidden_size", hidden_size),
                    "hop_size": var_config_data.get("hop_size", hop_size),
                    "predict_dur": var_config_data.get("predict_dur", True),
                    "predict_voicing": var_config_data.get("predict_voicing", False),
                    "predict_tension": var_config_data.get("predict_tension", False),
                    "predict_energy": var_config_data.get("predict_energy", False),
                    "predict_breathiness": var_config_data.get("predict_breathiness", False),
                    "use_lang_id": var_config_data.get("use_lang_id", use_lang_id),
                }
                if has_main_lang_json:
                    dsvariance_config["languages"] = "../dsmain/languages.json"
                if subbanks and variance_embeds:
                    dsvariance_config["speakers"] = variance_embeds

                with open(os.path.join(dsvariance, "dsconfig.yaml"), "w", encoding="utf-8") as config:
                    yaml.dump(dsvariance_config, config, allow_unicode=True, sort_keys=False)
            else:
                print("[INFO / ข้อมูล] No variance selected / ไม่ได้เลือกโมเดล Variance แยก")
        except Exception as e:
            print(f"[ERROR / ข้อผิดพลาด] Error editing variance config: {e}")

        try:
            if pitch_folder_onnx and os.path.exists(os.path.join(pitch_folder_onnx, "dsconfig.yaml")):
                with open(os.path.join(pitch_folder_onnx, "dsconfig.yaml"), "r", encoding="utf-8") as config:
                    pitch_config_data = yaml.safe_load(config) or {}

                dspitch_config = {
                    "phonemes": "phonemes.json",
                    "linguistic": "linguistic.onnx",
                    "pitch": "pitch.onnx",
                    "use_expr": True,
                    "use_continuous_acceleration": pitch_config_data.get("use_continuous_acceleration", True),
                    "sample_rate": pitch_config_data.get("sample_rate", sample_rate),
                    "hidden_size": pitch_config_data.get("hidden_size", hidden_size),
                    "hop_size": pitch_config_data.get("hop_size", hop_size),
                    "predict_dur": pitch_config_data.get("predict_dur", True),
                    "use_lang_id": pitch_config_data.get("use_lang_id", use_lang_id),
                    "use_note_rest": pitch_config_data.get("use_note_rest", False),
                }
                if has_main_lang_json:
                    dspitch_config["languages"] = "../dsmain/languages.json"
                if subbanks and pitch_embeds:
                    dspitch_config["speakers"] = pitch_embeds

                with open(os.path.join(dspitch, "dsconfig.yaml"), "w", encoding="utf-8") as config:
                    yaml.dump(dspitch_config, config, allow_unicode=True, sort_keys=False)
            else:
                print("[INFO / ข้อมูล] No pitch selected / ไม่ได้เลือกโมเดล Pitch แยก")
        except Exception as e:
            print(f"[ERROR / ข้อผิดพลาด] Error editing pitch config: {e}")
    except Exception as e:
        print(f"[ERROR / ข้อผิดพลาด] Error editing sub-configs: {e}")

    vocoder_path = str(_unwrap_var(vocoder_onnx, "")).strip() if vocoder_onnx else ""
    if vocoder_path and os.path.exists(vocoder_path):
        print("[INFO / ข้อมูล] Making dsvocoder directory and necessary files / กำลังติดตั้ง Vocoder เฉพาะตัว...")
        try:
            os.makedirs(os.path.join(main_stuff, "dsvocoder"), exist_ok=True)
            vocoder_folder = os.path.dirname(vocoder_path)
            vocoder_file = os.path.basename(vocoder_path)
            vocoder_name = os.path.splitext(vocoder_file)[0]
            shutil.copy(vocoder_path, os.path.join(main_stuff, "dsvocoder"))
            vocoder_yaml_src = os.path.join(vocoder_folder, "vocoder.yaml")
            if os.path.exists(vocoder_yaml_src):
                shutil.copy(vocoder_yaml_src, os.path.join(main_stuff, "dsvocoder"))
            with open(os.path.join(main_stuff, "dsconfig.yaml"), "r", encoding="utf-8") as config:
                dsconfig_data2 = yaml.safe_load(config) or {}
                dsconfig_data2["vocoder"] = "dsvocoder/" + vocoder_name if not vocoder_name.startswith("dsvocoder") else vocoder_name
            with open(os.path.join(main_stuff, "dsconfig.yaml"), "w", encoding="utf-8") as config:
                yaml.dump(dsconfig_data2, config, allow_unicode=True, sort_keys=False)
        except Exception as e:
            print(f"[ERROR / ข้อผิดพลาด] Error adding custom vocoder: {e}")

    autodict = bool(_unwrap_var(autodsdictvar2, True)) if autodsdictvar2 is not None else is_thai_model
    if autodict or is_thai_model:
        autodsdict.dictgenerator(aco_folder_dir, main_stuff)

    lang_dictionary_files_yaml = glob.glob(os.path.join(main_stuff, "*.yaml"))
    for yaml_dictionary_file in lang_dictionary_files_yaml:
        filename = os.path.basename(yaml_dictionary_file)
        if filename not in ("dsconfig.yaml", "character.yaml") and os.path.exists(yaml_dictionary_file):
            shutil.copy(yaml_dictionary_file, dsmain)
            shutil.copy(yaml_dictionary_file, dsdur)
            if var_folder_onnx:
                shutil.copy(yaml_dictionary_file, dsvariance)
            if pitch_folder_onnx:
                shutil.copy(yaml_dictionary_file, dspitch)
            if filename != "dsdict.yaml":
                os.remove(yaml_dictionary_file)

    print("[SUCCESS / สำเร็จ] OU setup complete! / ส่งออกโมเดลเสียงขั้นสูงสำหรับ OpenUtau เสร็จสมบูรณ์!")