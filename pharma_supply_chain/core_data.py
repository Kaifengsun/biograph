"""
核心制药供应链数据集
====================
基于公开信息构建的制药供应链核心数据，包括：
- WHO 基本药物 + FDA 高频短缺药品
- API（活性药物成分）及其供应商
- 药物-药物相互作用
- 治疗领域分类
- 历史短缺事件

这些数据均来源于公开数据库（WHO、FDA、DrugBank公开摘要），
用于构建制药供应链知识图谱的基础骨架。
后续可通过 FDA API / DrugBank XML 进一步增强。
"""


# ============================================================
#  药品数据 (Drug)
#  来源: WHO Essential Medicines List + FDA Drug Shortage DB
# ============================================================
DRUGS = [
    # --- 抗生素类 ---
    {"id": "DRUG_amoxicillin",       "name": "Amoxicillin（阿莫西林）",          "category": "antibiotic", "who_essential": True,  "dosage_form": "capsule"},
    {"id": "DRUG_cephalexin",        "name": "Cephalexin（头孢氨苄）",           "category": "antibiotic", "who_essential": True,  "dosage_form": "capsule"},
    {"id": "DRUG_azithromycin",      "name": "Azithromycin（阿奇霉素）",         "category": "antibiotic", "who_essential": True,  "dosage_form": "tablet"},
    {"id": "DRUG_ciprofloxacin",     "name": "Ciprofloxacin（环丙沙星）",        "category": "antibiotic", "who_essential": True,  "dosage_form": "tablet"},
    {"id": "DRUG_doxycycline",       "name": "Doxycycline（多西环素）",          "category": "antibiotic", "who_essential": True,  "dosage_form": "capsule"},
    {"id": "DRUG_metronidazole",     "name": "Metronidazole（甲硝唑）",          "category": "antibiotic", "who_essential": True,  "dosage_form": "tablet"},
    {"id": "DRUG_vancomycin",        "name": "Vancomycin（万古霉素）",           "category": "antibiotic", "who_essential": True,  "dosage_form": "injection"},
    {"id": "DRUG_piperacillin",      "name": "Piperacillin-Tazobactam（哌拉西林他唑巴坦）", "category": "antibiotic", "who_essential": True, "dosage_form": "injection"},

    # --- 心血管类 ---
    {"id": "DRUG_atorvastatin",      "name": "Atorvastatin（阿托伐他汀）",       "category": "cardiovascular", "who_essential": True,  "dosage_form": "tablet"},
    {"id": "DRUG_amlodipine",        "name": "Amlodipine（氨氯地平）",           "category": "cardiovascular", "who_essential": True,  "dosage_form": "tablet"},
    {"id": "DRUG_metoprolol",        "name": "Metoprolol（美托洛尔）",           "category": "cardiovascular", "who_essential": True,  "dosage_form": "tablet"},
    {"id": "DRUG_lisinopril",        "name": "Lisinopril（赖诺普利）",           "category": "cardiovascular", "who_essential": True,  "dosage_form": "tablet"},
    {"id": "DRUG_warfarin",          "name": "Warfarin（华法林）",               "category": "cardiovascular", "who_essential": True,  "dosage_form": "tablet"},
    {"id": "DRUG_heparin",           "name": "Heparin（肝素）",                  "category": "cardiovascular", "who_essential": True,  "dosage_form": "injection"},
    {"id": "DRUG_losartan",          "name": "Losartan（氯沙坦）",              "category": "cardiovascular", "who_essential": True,  "dosage_form": "tablet"},

    # --- 镇痛/麻醉类 ---
    {"id": "DRUG_morphine",          "name": "Morphine（吗啡）",                 "category": "analgesic",  "who_essential": True,  "dosage_form": "injection"},
    {"id": "DRUG_ibuprofen",         "name": "Ibuprofen（布洛芬）",              "category": "analgesic",  "who_essential": True,  "dosage_form": "tablet"},
    {"id": "DRUG_acetaminophen",     "name": "Acetaminophen（对乙酰氨基酚）",    "category": "analgesic",  "who_essential": True,  "dosage_form": "tablet"},
    {"id": "DRUG_lidocaine",         "name": "Lidocaine（利多卡因）",            "category": "anesthetic", "who_essential": True,  "dosage_form": "injection"},
    {"id": "DRUG_propofol",          "name": "Propofol（丙泊酚）",              "category": "anesthetic", "who_essential": True,  "dosage_form": "injection"},
    {"id": "DRUG_fentanyl",          "name": "Fentanyl（芬太尼）",              "category": "analgesic",  "who_essential": True,  "dosage_form": "injection"},

    # --- 抗肿瘤类 ---
    {"id": "DRUG_methotrexate",      "name": "Methotrexate（甲氨蝶呤）",        "category": "oncology",   "who_essential": True,  "dosage_form": "injection"},
    {"id": "DRUG_cisplatin",         "name": "Cisplatin（顺铂）",               "category": "oncology",   "who_essential": True,  "dosage_form": "injection"},
    {"id": "DRUG_fluorouracil",      "name": "Fluorouracil（氟尿嘧啶）",        "category": "oncology",   "who_essential": True,  "dosage_form": "injection"},
    {"id": "DRUG_doxorubicin",       "name": "Doxorubicin（阿霉素）",           "category": "oncology",   "who_essential": True,  "dosage_form": "injection"},
    {"id": "DRUG_paclitaxel",        "name": "Paclitaxel（紫杉醇）",            "category": "oncology",   "who_essential": True,  "dosage_form": "injection"},
    {"id": "DRUG_vincristine",       "name": "Vincristine（长春新碱）",          "category": "oncology",   "who_essential": True,  "dosage_form": "injection"},

    # --- 糖尿病类 ---
    {"id": "DRUG_metformin",         "name": "Metformin（二甲双胍）",            "category": "diabetes",   "who_essential": True,  "dosage_form": "tablet"},
    {"id": "DRUG_insulin_regular",   "name": "Insulin Regular（常规胰岛素）",    "category": "diabetes",   "who_essential": True,  "dosage_form": "injection"},
    {"id": "DRUG_glipizide",         "name": "Glipizide（格列吡嗪）",           "category": "diabetes",   "who_essential": False, "dosage_form": "tablet"},

    # --- 精神/神经类 ---
    {"id": "DRUG_diazepam",          "name": "Diazepam（地西泮）",              "category": "neuropsych", "who_essential": True,  "dosage_form": "tablet"},
    {"id": "DRUG_haloperidol",       "name": "Haloperidol（氟哌啶醇）",         "category": "neuropsych", "who_essential": True,  "dosage_form": "tablet"},
    {"id": "DRUG_fluoxetine",        "name": "Fluoxetine（氟西汀）",            "category": "neuropsych", "who_essential": True,  "dosage_form": "capsule"},
    {"id": "DRUG_carbamazepine",     "name": "Carbamazepine（卡马西平）",        "category": "neuropsych", "who_essential": True,  "dosage_form": "tablet"},
    {"id": "DRUG_phenytoin",         "name": "Phenytoin（苯妥英）",             "category": "neuropsych", "who_essential": True,  "dosage_form": "capsule"},

    # --- 呼吸系统 ---
    {"id": "DRUG_salbutamol",        "name": "Salbutamol（沙丁胺醇）",          "category": "respiratory", "who_essential": True,  "dosage_form": "inhaler"},
    {"id": "DRUG_dexamethasone",     "name": "Dexamethasone（地塞米松）",        "category": "corticosteroid", "who_essential": True, "dosage_form": "tablet"},
    {"id": "DRUG_prednisone",        "name": "Prednisone（泼尼松）",            "category": "corticosteroid", "who_essential": True, "dosage_form": "tablet"},

    # --- 抗感染/抗病毒 ---
    {"id": "DRUG_acyclovir",         "name": "Acyclovir（阿昔洛韦）",           "category": "antiviral",  "who_essential": True,  "dosage_form": "tablet"},
    {"id": "DRUG_oseltamivir",       "name": "Oseltamivir（奥司他韦）",         "category": "antiviral",  "who_essential": True,  "dosage_form": "capsule"},

    # --- 抗真菌 ---
    {"id": "DRUG_fluconazole",       "name": "Fluconazole（氟康唑）",           "category": "antifungal", "who_essential": True,  "dosage_form": "capsule"},
    {"id": "DRUG_amphotericin_b",    "name": "Amphotericin B（两性霉素B）",     "category": "antifungal", "who_essential": True,  "dosage_form": "injection"},

    # --- 消化系统 ---
    {"id": "DRUG_omeprazole",        "name": "Omeprazole（奥美拉唑）",          "category": "gastrointestinal", "who_essential": True, "dosage_form": "capsule"},
    {"id": "DRUG_ondansetron",       "name": "Ondansetron（昂丹司琼）",         "category": "gastrointestinal", "who_essential": True, "dosage_form": "injection"},

    # --- 造影剂/诊断 ---
    {"id": "DRUG_iohexol",           "name": "Iohexol（碘海醇）",              "category": "contrast_agent", "who_essential": True, "dosage_form": "injection"},

    # --- 电解质/营养 ---
    {"id": "DRUG_sodium_chloride",   "name": "Sodium Chloride（氯化钠注射液）", "category": "electrolyte", "who_essential": True, "dosage_form": "injection"},
    {"id": "DRUG_potassium_chloride","name": "Potassium Chloride（氯化钾）",    "category": "electrolyte", "who_essential": True, "dosage_form": "injection"},
]


# ============================================================
#  API（活性药物成分）数据
# ============================================================
APIS = [
    # 抗生素 API
    {"id": "API_6apa",              "name": "6-APA（6-氨基青霉烷酸）",   "cas": "551-16-6",    "class": "penicillin_intermediate"},
    {"id": "API_amoxicillin_trihy", "name": "Amoxicillin Trihydrate",    "cas": "61336-70-7",  "class": "penicillin"},
    {"id": "API_7aca",              "name": "7-ACA（7-氨基头孢烷酸）",   "cas": "957-68-6",    "class": "cephalosporin_intermediate"},
    {"id": "API_cephalexin_mono",   "name": "Cephalexin Monohydrate",    "cas": "23325-78-2",  "class": "cephalosporin"},
    {"id": "API_azithromycin_dihy", "name": "Azithromycin Dihydrate",    "cas": "117772-70-0", "class": "macrolide"},
    {"id": "API_ciprofloxacin_hcl", "name": "Ciprofloxacin HCl",         "cas": "86393-32-0",  "class": "fluoroquinolone"},
    {"id": "API_doxycycline_hyc",   "name": "Doxycycline Hyclate",       "cas": "24390-14-5",  "class": "tetracycline"},
    {"id": "API_metronidazole",     "name": "Metronidazole",             "cas": "443-48-1",    "class": "nitroimidazole"},
    {"id": "API_vancomycin_hcl",    "name": "Vancomycin HCl",            "cas": "1404-93-9",   "class": "glycopeptide"},
    {"id": "API_piperacillin_na",   "name": "Piperacillin Sodium",       "cas": "59703-84-3",  "class": "penicillin"},
    {"id": "API_tazobactam_na",     "name": "Tazobactam Sodium",         "cas": "89785-84-2",  "class": "beta_lactamase_inhibitor"},

    # 心血管 API
    {"id": "API_atorvastatin_ca",   "name": "Atorvastatin Calcium",      "cas": "134523-03-8", "class": "statin"},
    {"id": "API_amlodipine_bes",    "name": "Amlodipine Besylate",       "cas": "111470-99-6", "class": "calcium_channel_blocker"},
    {"id": "API_metoprolol_tar",    "name": "Metoprolol Tartrate",       "cas": "56392-17-7",  "class": "beta_blocker"},
    {"id": "API_lisinopril_dihy",   "name": "Lisinopril Dihydrate",      "cas": "83915-83-7",  "class": "ace_inhibitor"},
    {"id": "API_warfarin_na",       "name": "Warfarin Sodium",           "cas": "129-06-6",    "class": "anticoagulant"},
    {"id": "API_heparin_na",        "name": "Heparin Sodium",            "cas": "9041-08-1",   "class": "anticoagulant"},
    {"id": "API_losartan_k",        "name": "Losartan Potassium",        "cas": "124750-99-8", "class": "arb"},

    # 镇痛/麻醉 API
    {"id": "API_morphine_sulfate",  "name": "Morphine Sulfate",          "cas": "6211-15-0",   "class": "opioid"},
    {"id": "API_ibuprofen",         "name": "Ibuprofen",                 "cas": "15687-27-1",  "class": "nsaid"},
    {"id": "API_acetaminophen",     "name": "Acetaminophen (APAP)",      "cas": "103-90-2",    "class": "analgesic"},
    {"id": "API_lidocaine_hcl",     "name": "Lidocaine HCl",             "cas": "73-78-9",     "class": "local_anesthetic"},
    {"id": "API_propofol",          "name": "Propofol",                  "cas": "2078-54-8",   "class": "general_anesthetic"},
    {"id": "API_fentanyl_citrate",  "name": "Fentanyl Citrate",          "cas": "990-73-8",    "class": "opioid"},

    # 抗肿瘤 API
    {"id": "API_methotrexate",      "name": "Methotrexate",              "cas": "59-05-2",     "class": "antimetabolite"},
    {"id": "API_cisplatin",         "name": "Cisplatin",                 "cas": "15663-27-1",  "class": "platinum_compound"},
    {"id": "API_fluorouracil",      "name": "Fluorouracil (5-FU)",       "cas": "51-21-8",     "class": "antimetabolite"},
    {"id": "API_doxorubicin_hcl",   "name": "Doxorubicin HCl",          "cas": "25316-40-9",  "class": "anthracycline"},
    {"id": "API_paclitaxel",        "name": "Paclitaxel",               "cas": "33069-62-4",  "class": "taxane"},
    {"id": "API_vincristine_sul",   "name": "Vincristine Sulfate",       "cas": "2068-78-2",   "class": "vinca_alkaloid"},

    # 糖尿病 API
    {"id": "API_metformin_hcl",     "name": "Metformin HCl",             "cas": "1115-70-4",   "class": "biguanide"},
    {"id": "API_insulin_human",     "name": "Insulin Human Recombinant", "cas": "11061-68-0",  "class": "peptide_hormone"},
    {"id": "API_glipizide",         "name": "Glipizide",                 "cas": "29094-61-9",  "class": "sulfonylurea"},

    # 其他 API
    {"id": "API_omeprazole",        "name": "Omeprazole",                "cas": "73590-58-6",  "class": "proton_pump_inhibitor"},
    {"id": "API_dexamethasone",     "name": "Dexamethasone",             "cas": "50-02-2",     "class": "corticosteroid"},
    {"id": "API_fluconazole",       "name": "Fluconazole",               "cas": "86386-73-4",  "class": "azole_antifungal"},
    {"id": "API_acyclovir",         "name": "Acyclovir",                 "cas": "59277-89-3",  "class": "antiviral"},
    {"id": "API_iohexol",           "name": "Iohexol",                   "cas": "66108-95-0",  "class": "contrast_agent"},

    # ---- 补充: 之前缺 API 关联的 12 个药品 ----
    {"id": "API_amphotericin_b",    "name": "Amphotericin B",             "cas": "1397-89-3",   "class": "polyene_antifungal"},
    {"id": "API_carbamazepine",     "name": "Carbamazepine",              "cas": "298-46-4",    "class": "anticonvulsant"},
    {"id": "API_diazepam",          "name": "Diazepam",                   "cas": "439-14-5",    "class": "benzodiazepine"},
    {"id": "API_fluoxetine_hcl",    "name": "Fluoxetine HCl",             "cas": "56296-78-7",  "class": "ssri"},
    {"id": "API_haloperidol",       "name": "Haloperidol",                "cas": "52-86-8",     "class": "butyrophenone"},
    {"id": "API_ondansetron_hcl",   "name": "Ondansetron HCl",            "cas": "103639-04-9", "class": "serotonin_5HT3_antagonist"},
    {"id": "API_oseltamivir_phos",  "name": "Oseltamivir Phosphate",      "cas": "204255-11-8", "class": "neuraminidase_inhibitor"},
    {"id": "API_phenytoin_na",      "name": "Phenytoin Sodium",            "cas": "630-93-3",    "class": "anticonvulsant"},
    {"id": "API_potassium_chloride","name": "Potassium Chloride",          "cas": "7447-40-7",   "class": "electrolyte"},
    {"id": "API_prednisone",        "name": "Prednisone",                  "cas": "53-03-2",     "class": "corticosteroid"},
    {"id": "API_salbutamol_sulfate","name": "Salbutamol Sulfate",          "cas": "51022-70-9",  "class": "beta2_agonist"},
    {"id": "API_sodium_chloride",   "name": "Sodium Chloride (injectable)","cas": "7647-14-5",   "class": "electrolyte"},
]


# ============================================================
#  药品 ↔ API 映射 (CONTAINS_API)
# ============================================================
DRUG_API_MAP = [
    # 抗生素
    ("DRUG_amoxicillin",     "API_amoxicillin_trihy"),
    ("DRUG_amoxicillin",     "API_6apa"),             # 中间体依赖
    ("DRUG_cephalexin",      "API_cephalexin_mono"),
    ("DRUG_cephalexin",      "API_7aca"),             # 中间体依赖
    ("DRUG_azithromycin",    "API_azithromycin_dihy"),
    ("DRUG_ciprofloxacin",   "API_ciprofloxacin_hcl"),
    ("DRUG_doxycycline",     "API_doxycycline_hyc"),
    ("DRUG_metronidazole",   "API_metronidazole"),
    ("DRUG_vancomycin",      "API_vancomycin_hcl"),
    ("DRUG_piperacillin",    "API_piperacillin_na"),
    ("DRUG_piperacillin",    "API_tazobactam_na"),

    # 心血管
    ("DRUG_atorvastatin",    "API_atorvastatin_ca"),
    ("DRUG_amlodipine",      "API_amlodipine_bes"),
    ("DRUG_metoprolol",      "API_metoprolol_tar"),
    ("DRUG_lisinopril",      "API_lisinopril_dihy"),
    ("DRUG_warfarin",        "API_warfarin_na"),
    ("DRUG_heparin",         "API_heparin_na"),
    ("DRUG_losartan",        "API_losartan_k"),

    # 镇痛/麻醉
    ("DRUG_morphine",        "API_morphine_sulfate"),
    ("DRUG_ibuprofen",       "API_ibuprofen"),
    ("DRUG_acetaminophen",   "API_acetaminophen"),
    ("DRUG_lidocaine",       "API_lidocaine_hcl"),
    ("DRUG_propofol",        "API_propofol"),
    ("DRUG_fentanyl",        "API_fentanyl_citrate"),

    # 抗肿瘤
    ("DRUG_methotrexate",    "API_methotrexate"),
    ("DRUG_cisplatin",       "API_cisplatin"),
    ("DRUG_fluorouracil",    "API_fluorouracil"),
    ("DRUG_doxorubicin",     "API_doxorubicin_hcl"),
    ("DRUG_paclitaxel",      "API_paclitaxel"),
    ("DRUG_vincristine",     "API_vincristine_sul"),

    # 糖尿病
    ("DRUG_metformin",       "API_metformin_hcl"),
    ("DRUG_insulin_regular", "API_insulin_human"),
    ("DRUG_glipizide",       "API_glipizide"),

    # 其他
    ("DRUG_omeprazole",      "API_omeprazole"),
    ("DRUG_dexamethasone",   "API_dexamethasone"),
    ("DRUG_fluconazole",     "API_fluconazole"),
    ("DRUG_acyclovir",       "API_acyclovir"),
    ("DRUG_iohexol",         "API_iohexol"),

    # 补充: 之前缺失的 12 个药品 → API 映射
    ("DRUG_amphotericin_b",  "API_amphotericin_b"),
    ("DRUG_carbamazepine",   "API_carbamazepine"),
    ("DRUG_diazepam",        "API_diazepam"),
    ("DRUG_fluoxetine",      "API_fluoxetine_hcl"),
    ("DRUG_haloperidol",     "API_haloperidol"),
    ("DRUG_ondansetron",     "API_ondansetron_hcl"),
    ("DRUG_oseltamivir",     "API_oseltamivir_phos"),
    ("DRUG_phenytoin",       "API_phenytoin_na"),
    ("DRUG_potassium_chloride", "API_potassium_chloride"),
    ("DRUG_prednisone",      "API_prednisone"),
    ("DRUG_salbutamol",      "API_salbutamol_sulfate"),
    ("DRUG_sodium_chloride", "API_sodium_chloride"),
]


# ============================================================
#  制造商数据 (Manufacturer)
# ============================================================
MANUFACTURERS = [
    # --- 印度（全球最大 API 出口国）---
    {"id": "MFG_aurobindo",       "name": "Aurobindo Pharma",              "country": "India",    "type": "api_and_formulation", "tier": 1},
    {"id": "MFG_dr_reddys",       "name": "Dr. Reddy's Laboratories",     "country": "India",    "type": "api_and_formulation", "tier": 1},
    {"id": "MFG_cipla",           "name": "Cipla Limited",                 "country": "India",    "type": "api_and_formulation", "tier": 1},
    {"id": "MFG_sun_pharma",      "name": "Sun Pharmaceutical",           "country": "India",    "type": "api_and_formulation", "tier": 1},
    {"id": "MFG_lupin",           "name": "Lupin Limited",                 "country": "India",    "type": "api_and_formulation", "tier": 1},
    {"id": "MFG_divi_labs",       "name": "Divi's Laboratories",          "country": "India",    "type": "api_specialist",      "tier": 1},
    {"id": "MFG_laurus_labs",     "name": "Laurus Labs",                  "country": "India",    "type": "api_specialist",      "tier": 2},
    {"id": "MFG_shilpa_medicare", "name": "Shilpa Medicare",              "country": "India",    "type": "api_specialist",      "tier": 2},

    # --- 中国（全球最大中间体出口国）---
    {"id": "MFG_zhejiang_hisun",  "name": "Zhejiang Hisun Pharma（浙江海正）","country": "China", "type": "api_specialist",      "tier": 1},
    {"id": "MFG_north_china",     "name": "NCPC（华北制药）",               "country": "China",    "type": "api_and_formulation", "tier": 1},
    {"id": "MFG_cspc",            "name": "CSPC Pharma（石药集团）",        "country": "China",    "type": "api_and_formulation", "tier": 1},
    {"id": "MFG_harbin_pharma",   "name": "Harbin Pharma（哈药集团）",     "country": "China",    "type": "api_and_formulation", "tier": 1},
    {"id": "MFG_zhejiang_medi",   "name": "Zhejiang Medicine（浙江医药）",  "country": "China",    "type": "api_specialist",      "tier": 2},
    {"id": "MFG_northeast_pharma","name": "Northeast Pharma（东北制药）",   "country": "China",    "type": "api_specialist",      "tier": 2},
    {"id": "MFG_livzon",          "name": "Livzon Group（丽珠集团）",      "country": "China",    "type": "api_and_formulation", "tier": 2},

    # --- 欧洲 ---
    {"id": "MFG_sandoz",          "name": "Sandoz (Novartis)",             "country": "Switzerland","type": "formulation",       "tier": 1},
    {"id": "MFG_teva",            "name": "Teva Pharmaceutical",           "country": "Israel",   "type": "api_and_formulation", "tier": 1},
    {"id": "MFG_basf_pharma",     "name": "BASF Pharma Solutions",         "country": "Germany",  "type": "api_specialist",      "tier": 1},
    {"id": "MFG_lonza",           "name": "Lonza Group",                   "country": "Switzerland","type": "api_specialist",     "tier": 1},
    {"id": "MFG_pfizer_centreone","name": "Pfizer CentreOne",             "country": "USA",      "type": "api_specialist",      "tier": 1},

    # --- 美国 ---
    {"id": "MFG_mylan_viatris",   "name": "Viatris (Mylan)",              "country": "USA",      "type": "formulation",         "tier": 1},
    {"id": "MFG_baxter",          "name": "Baxter International",          "country": "USA",      "type": "formulation",         "tier": 1},
    {"id": "MFG_fresenius_kabi",  "name": "Fresenius Kabi",               "country": "Germany",  "type": "formulation",         "tier": 1},
    {"id": "MFG_hospira_pfizer",  "name": "Hospira (Pfizer)",             "country": "USA",      "type": "formulation",         "tier": 1},
    {"id": "MFG_hikma",           "name": "Hikma Pharmaceuticals",        "country": "Jordan",   "type": "formulation",         "tier": 1},

    # --- 生物制药 ---
    {"id": "MFG_novo_nordisk",    "name": "Novo Nordisk",                  "country": "Denmark",  "type": "bio_specialist",      "tier": 1},
    {"id": "MFG_sanofi",          "name": "Sanofi",                        "country": "France",   "type": "bio_specialist",      "tier": 1},
    {"id": "MFG_eli_lilly",       "name": "Eli Lilly",                     "country": "USA",      "type": "bio_specialist",      "tier": 1},

    # --- 造影剂 ---
    {"id": "MFG_ge_healthcare",   "name": "GE Healthcare",                 "country": "USA",      "type": "specialty",           "tier": 1},

    # --- 生物原料（肝素特有）---
    {"id": "MFG_hepalink",        "name": "Shenzhen Hepalink（海普瑞）",   "country": "China",    "type": "bio_raw_material",    "tier": 1},
]


# ============================================================
#  供应关系 (API ← SUPPLIED_BY → Manufacturer)
#  基于公开供应链信息和 FDA DMF 登记
# ============================================================
API_SUPPLIER_MAP = [
    # 6-APA（青霉素核心中间体）→ 高度集中在中国
    ("API_6apa",              "MFG_north_china"),
    ("API_6apa",              "MFG_cspc"),
    ("API_6apa",              "MFG_harbin_pharma"),

    # 阿莫西林 → 印度 + 中国
    ("API_amoxicillin_trihy", "MFG_aurobindo"),
    ("API_amoxicillin_trihy", "MFG_north_china"),
    ("API_amoxicillin_trihy", "MFG_divi_labs"),

    # 7-ACA（头孢核心中间体）→ 中国主导
    ("API_7aca",              "MFG_north_china"),
    ("API_7aca",              "MFG_harbin_pharma"),
    ("API_7aca",              "MFG_zhejiang_hisun"),

    # 头孢氨苄
    ("API_cephalexin_mono",   "MFG_aurobindo"),
    ("API_cephalexin_mono",   "MFG_lupin"),

    # 阿奇霉素
    ("API_azithromycin_dihy", "MFG_cipla"),
    ("API_azithromycin_dihy", "MFG_zhejiang_hisun"),
    ("API_azithromycin_dihy", "MFG_teva"),

    # 环丙沙星
    ("API_ciprofloxacin_hcl", "MFG_dr_reddys"),
    ("API_ciprofloxacin_hcl", "MFG_aurobindo"),

    # 多西环素
    ("API_doxycycline_hyc",   "MFG_northeast_pharma"),
    ("API_doxycycline_hyc",   "MFG_laurus_labs"),

    # 甲硝唑
    ("API_metronidazole",     "MFG_north_china"),
    ("API_metronidazole",     "MFG_cipla"),

    # 万古霉素
    ("API_vancomycin_hcl",    "MFG_zhejiang_hisun"),
    ("API_vancomycin_hcl",    "MFG_shilpa_medicare"),

    # 哌拉西林/他唑巴坦
    ("API_piperacillin_na",   "MFG_cspc"),
    ("API_piperacillin_na",   "MFG_aurobindo"),
    ("API_tazobactam_na",     "MFG_cspc"),
    ("API_tazobactam_na",     "MFG_divi_labs"),

    # 阿托伐他汀
    ("API_atorvastatin_ca",   "MFG_dr_reddys"),
    ("API_atorvastatin_ca",   "MFG_zhejiang_medi"),
    ("API_atorvastatin_ca",   "MFG_teva"),

    # 氨氯地平
    ("API_amlodipine_bes",    "MFG_dr_reddys"),
    ("API_amlodipine_bes",    "MFG_aurobindo"),

    # 美托洛尔
    ("API_metoprolol_tar",    "MFG_sun_pharma"),
    ("API_metoprolol_tar",    "MFG_lupin"),

    # 赖诺普利
    ("API_lisinopril_dihy",   "MFG_lupin"),
    ("API_lisinopril_dihy",   "MFG_dr_reddys"),

    # 华法林
    ("API_warfarin_na",       "MFG_teva"),

    # 肝素 → 高度依赖中国猪源
    ("API_heparin_na",        "MFG_hepalink"),
    ("API_heparin_na",        "MFG_north_china"),

    # 氯沙坦
    ("API_losartan_k",        "MFG_dr_reddys"),
    ("API_losartan_k",        "MFG_zhejiang_hisun"),

    # 吗啡
    ("API_morphine_sulfate",  "MFG_sun_pharma"),

    # 布洛芬 → 中国是全球最大出口国
    ("API_ibuprofen",         "MFG_cspc"),
    ("API_ibuprofen",         "MFG_basf_pharma"),
    ("API_ibuprofen",         "MFG_cipla"),

    # 对乙酰氨基酚 → 中国占全球产能 80%
    ("API_acetaminophen",     "MFG_zhejiang_medi"),
    ("API_acetaminophen",     "MFG_north_china"),
    ("API_acetaminophen",     "MFG_cspc"),

    # 利多卡因
    ("API_lidocaine_hcl",     "MFG_fresenius_kabi"),
    ("API_lidocaine_hcl",     "MFG_northeast_pharma"),

    # 丙泊酚
    ("API_propofol",          "MFG_fresenius_kabi"),
    ("API_propofol",          "MFG_basf_pharma"),

    # 芬太尼
    ("API_fentanyl_citrate",  "MFG_hospira_pfizer"),

    # 甲氨蝶呤
    ("API_methotrexate",      "MFG_hospira_pfizer"),
    ("API_methotrexate",      "MFG_teva"),

    # 顺铂
    ("API_cisplatin",         "MFG_fresenius_kabi"),
    ("API_cisplatin",         "MFG_zhejiang_hisun"),

    # 氟尿嘧啶
    ("API_fluorouracil",      "MFG_fresenius_kabi"),
    ("API_fluorouracil",      "MFG_northeast_pharma"),

    # 阿霉素
    ("API_doxorubicin_hcl",   "MFG_sun_pharma"),
    ("API_doxorubicin_hcl",   "MFG_shilpa_medicare"),

    # 紫杉醇
    ("API_paclitaxel",        "MFG_cipla"),
    ("API_paclitaxel",        "MFG_fresenius_kabi"),

    # 长春新碱 → 全球供应极度集中
    ("API_vincristine_sul",   "MFG_hospira_pfizer"),
    ("API_vincristine_sul",   "MFG_teva"),

    # 二甲双胍
    ("API_metformin_hcl",     "MFG_aurobindo"),
    ("API_metformin_hcl",     "MFG_cipla"),
    ("API_metformin_hcl",     "MFG_north_china"),

    # 胰岛素 → 全球仅三家主要供应商
    ("API_insulin_human",     "MFG_novo_nordisk"),
    ("API_insulin_human",     "MFG_sanofi"),
    ("API_insulin_human",     "MFG_eli_lilly"),

    # 格列吡嗪
    ("API_glipizide",         "MFG_sun_pharma"),

    # 奥美拉唑
    ("API_omeprazole",        "MFG_dr_reddys"),
    ("API_omeprazole",        "MFG_aurobindo"),

    # 地塞米松
    ("API_dexamethasone",     "MFG_zhejiang_hisun"),
    ("API_dexamethasone",     "MFG_cipla"),

    # 氟康唑
    ("API_fluconazole",       "MFG_cipla"),
    ("API_fluconazole",       "MFG_dr_reddys"),

    # 阿昔洛韦
    ("API_acyclovir",         "MFG_aurobindo"),
    ("API_acyclovir",         "MFG_laurus_labs"),

    # 碘海醇 → 极度集中
    ("API_iohexol",           "MFG_ge_healthcare"),

    # ---- 补充: 新增 API 的供应关系 ----
    # 两性霉素B → 非常有限的供应商（生物发酵工艺复杂）
    ("API_amphotericin_b",    "MFG_hikma"),
    ("API_amphotericin_b",    "MFG_fresenius_kabi"),

    # 卡马西平 → Novartis(Sandoz)原研 + 印度仿制
    ("API_carbamazepine",     "MFG_sandoz"),
    ("API_carbamazepine",     "MFG_teva"),
    ("API_carbamazepine",     "MFG_sun_pharma"),

    # 地西泮
    ("API_diazepam",          "MFG_teva"),
    ("API_diazepam",          "MFG_sun_pharma"),
    ("API_diazepam",          "MFG_hikma"),

    # 氟西汀
    ("API_fluoxetine_hcl",    "MFG_aurobindo"),
    ("API_fluoxetine_hcl",    "MFG_cipla"),
    ("API_fluoxetine_hcl",    "MFG_lupin"),

    # 氟哌啶醇
    ("API_haloperidol",       "MFG_sun_pharma"),
    ("API_haloperidol",       "MFG_cipla"),

    # 昂丹司琼
    ("API_ondansetron_hcl",   "MFG_dr_reddys"),
    ("API_ondansetron_hcl",   "MFG_aurobindo"),
    ("API_ondansetron_hcl",   "MFG_sun_pharma"),

    # 奥司他韦 → Roche原研; 印度有授权仿制
    ("API_oseltamivir_phos",  "MFG_cipla"),
    ("API_oseltamivir_phos",  "MFG_lupin"),
    ("API_oseltamivir_phos",  "MFG_zhejiang_hisun"),

    # 苯妥英
    ("API_phenytoin_na",      "MFG_aurobindo"),
    ("API_phenytoin_na",      "MFG_teva"),

    # 氯化钾 → 大宗化工品，多供应商
    ("API_potassium_chloride","MFG_baxter"),
    ("API_potassium_chloride","MFG_fresenius_kabi"),
    ("API_potassium_chloride","MFG_hospira_pfizer"),

    # 泼尼松
    ("API_prednisone",        "MFG_cipla"),
    ("API_prednisone",        "MFG_teva"),
    ("API_prednisone",        "MFG_zhejiang_hisun"),

    # 沙丁胺醇
    ("API_salbutamol_sulfate","MFG_cipla"),
    ("API_salbutamol_sulfate","MFG_lupin"),
    ("API_salbutamol_sulfate","MFG_cspc"),

    # 氯化钠注射液 → 大输液产品
    ("API_sodium_chloride",   "MFG_baxter"),
    ("API_sodium_chloride",   "MFG_fresenius_kabi"),
    ("API_sodium_chloride",   "MFG_hospira_pfizer"),

    # ---- 补充: 修复瑞士/约旦/其他供应商零供应问题 ----
    # Sandoz (瑞士) — 全球最大仿制药公司之一
    ("API_amlodipine_bes",    "MFG_sandoz"),
    ("API_losartan_k",        "MFG_sandoz"),
    ("API_metformin_hcl",     "MFG_sandoz"),
    ("API_omeprazole",        "MFG_sandoz"),

    # Lonza (瑞士) — 全球领先的合同制造商
    ("API_vancomycin_hcl",    "MFG_lonza"),
    ("API_insulin_human",     "MFG_lonza"),

    # Hikma (约旦) — 中东最大仿制药商
    ("API_metronidazole",     "MFG_hikma"),
    ("API_ondansetron_hcl",   "MFG_hikma"),
    ("API_morphine_sulfate",  "MFG_hikma"),

    # BASF (德国) — 补充更多 API
    ("API_acetaminophen",     "MFG_basf_pharma"),

    # Pfizer CentreOne — 补充
    ("API_paclitaxel",        "MFG_pfizer_centreone"),
    ("API_vincristine_sul",   "MFG_pfizer_centreone"),

    # Viatris/Mylan — 全球仿制药巨头
    ("API_atorvastatin_ca",   "MFG_mylan_viatris"),
    ("API_losartan_k",        "MFG_mylan_viatris"),
    ("API_metformin_hcl",     "MFG_mylan_viatris"),

    # Divi's Labs — 补充更多 API（全球最大 API 专业制造商之一）
    ("API_metformin_hcl",     "MFG_divi_labs"),
    ("API_losartan_k",        "MFG_divi_labs"),

    # Laurus Labs — 抗病毒 API 领先供应商
    ("API_oseltamivir_phos",  "MFG_laurus_labs"),

    # Livzon (丽珠集团) — 补充
    ("API_vancomycin_hcl",    "MFG_livzon"),
    ("API_omeprazole",        "MFG_livzon"),
]


# ============================================================
#  药物-药物相互作用 (INTERACTS_WITH)
#  来源: DrugBank 公开摘要 + FDA Label
# ============================================================
DRUG_INTERACTIONS = [
    # (Drug A, Drug B, 严重程度, 机制描述)
    ("DRUG_warfarin",     "DRUG_ibuprofen",       "major",    "增加出血风险：NSAIDs抑制血小板+华法林抗凝"),
    ("DRUG_warfarin",     "DRUG_metronidazole",   "major",    "甲硝唑抑制CYP2C9，升高华法林血药浓度"),
    ("DRUG_warfarin",     "DRUG_fluconazole",     "major",    "氟康唑抑制CYP2C9/3A4，显著升高华法林浓度"),
    ("DRUG_warfarin",     "DRUG_ciprofloxacin",   "moderate", "环丙沙星抑制CYP1A2，可能升高华法林浓度"),
    ("DRUG_warfarin",     "DRUG_azithromycin",    "moderate", "阿奇霉素可能增强华法林抗凝效果"),

    ("DRUG_metformin",    "DRUG_iohexol",         "major",    "碘造影剂+二甲双胍可致乳酸酸中毒"),
    ("DRUG_metformin",    "DRUG_ciprofloxacin",   "moderate", "氟喹诺酮类可引起血糖波动"),

    ("DRUG_cisplatin",    "DRUG_vancomycin",      "major",    "联用增加肾毒性和耳毒性风险"),
    ("DRUG_cisplatin",    "DRUG_methotrexate",    "major",    "顺铂降低肾清除率，升高甲氨蝶呤毒性"),

    ("DRUG_heparin",      "DRUG_ibuprofen",       "major",    "NSAIDs+肝素显著增加出血风险"),
    ("DRUG_heparin",      "DRUG_warfarin",        "major",    "双重抗凝，出血风险叠加"),

    ("DRUG_phenytoin",    "DRUG_fluorouracil",    "major",    "5-FU升高苯妥英血药浓度"),
    ("DRUG_phenytoin",    "DRUG_fluconazole",     "major",    "氟康唑抑制苯妥英代谢"),
    ("DRUG_phenytoin",    "DRUG_carbamazepine",   "moderate", "相互影响代谢，需监测血药浓度"),

    ("DRUG_methotrexate", "DRUG_ibuprofen",       "major",    "NSAIDs降低甲氨蝶呤肾排泄，增加毒性"),
    ("DRUG_methotrexate", "DRUG_omeprazole",      "moderate", "奥美拉唑可能升高甲氨蝶呤浓度"),

    ("DRUG_fentanyl",     "DRUG_diazepam",        "major",    "苯二氮卓+阿片类致严重呼吸抑制"),
    ("DRUG_fentanyl",     "DRUG_fluconazole",     "moderate", "氟康唑抑制CYP3A4，升高芬太尼浓度"),
    ("DRUG_morphine",     "DRUG_diazepam",        "major",    "苯二氮卓+阿片类致严重呼吸抑制"),

    ("DRUG_fluoxetine",   "DRUG_morphine",        "moderate", "SSRIs可能降低吗啡代谢为其活性代谢物"),
    ("DRUG_fluoxetine",   "DRUG_warfarin",        "moderate", "氟西汀抑制CYP2C9，可能升高华法林浓度"),

    ("DRUG_doxorubicin",  "DRUG_paclitaxel",      "moderate", "联用需监测心脏毒性"),
    ("DRUG_doxorubicin",  "DRUG_vincristine",     "moderate", "联用增加骨髓抑制风险"),

    ("DRUG_lisinopril",   "DRUG_potassium_chloride", "moderate", "ACE抑制剂+钾补充剂可致高钾血症"),
    ("DRUG_losartan",     "DRUG_potassium_chloride", "moderate", "ARB+钾补充剂可致高钾血症"),

    # ---- 补充: 解决 21 个药品无相互作用记录的问题 ----
    # Acetaminophen 相关
    ("DRUG_acetaminophen", "DRUG_warfarin",        "moderate", "对乙酰氨基酚长期使用可增强华法林抗凝效果"),
    ("DRUG_acetaminophen", "DRUG_methotrexate",    "moderate", "可能降低甲氨蝶呖肾清除率"),
    ("DRUG_acetaminophen", "DRUG_carbamazepine",   "moderate", "卡马西平引寺CYP酶，加速对乙酰氨基酚代谢，增加肝毒性风险"),

    # Amoxicillin 相关
    ("DRUG_amoxicillin",   "DRUG_methotrexate",    "major",    "减少甲氨蝶呖肾小管分泌，升高毒性风险"),
    ("DRUG_amoxicillin",   "DRUG_warfarin",        "moderate", "可能增强华法林抗凝效果"),

    # Atorvastatin 相关
    ("DRUG_atorvastatin",  "DRUG_fluconazole",     "major",    "氟康唑抑制CYP3A4，显著升高他汀类浓度，增加横纹肌溶解风险"),
    ("DRUG_atorvastatin",  "DRUG_amlodipine",      "moderate", "联用时注意低血压和背痛风险"),
    ("DRUG_atorvastatin",  "DRUG_carbamazepine",   "moderate", "卡马西平诱导CYP3A4，可能降低他汀类血药浓度"),

    # Dexamethasone 相关
    ("DRUG_dexamethasone", "DRUG_phenytoin",       "major",    "苯妥英诱导CYP3A4，降低地塞米松效果；地塞米松影响苯妥英代谢"),
    ("DRUG_dexamethasone", "DRUG_warfarin",        "moderate", "地塞米松可能改变华法林INR"),
    ("DRUG_dexamethasone", "DRUG_metformin",       "moderate", "糖皮质激素升高血糖，拮抗二甲双胍效果"),
    ("DRUG_dexamethasone", "DRUG_ibuprofen",       "moderate", "联用增加GI出血风险"),

    # Insulin 相关
    ("DRUG_insulin_regular", "DRUG_fluoxetine",    "moderate", "SSRIs可能增强胰岛素降糖效果，引发低血糖"),
    ("DRUG_insulin_regular", "DRUG_dexamethasone", "major",    "糖皮质激素显著升高血糖，拮抗胰岛素"),

    # Metoprolol 相关
    ("DRUG_metoprolol",    "DRUG_lidocaine",       "moderate", "美托洛尔降低血流，升高利多卡因血药浓度"),
    ("DRUG_metoprolol",    "DRUG_fluoxetine",      "major",    "氟西汀抑制CYP2D6，显著升高美托洛尔浓度致心动过缓"),
    ("DRUG_metoprolol",    "DRUG_salbutamol",      "moderate", "β受体拮抗，可能降低沙丁胺醇支气管扩张效果"),

    # Propofol 相关
    ("DRUG_propofol",      "DRUG_fentanyl",        "major",    "联用致严重呼吸抑制和低血压"),
    ("DRUG_propofol",      "DRUG_lidocaine",       "moderate", "常联用减少注射痛，但需监测心血管功能"),

    # Piperacillin 相关
    ("DRUG_piperacillin",  "DRUG_methotrexate",    "major",    "哌拉西林减少甲氨蝶呖肾清除，大幅升高毒性风险"),

    # Haloperidol 相关
    ("DRUG_haloperidol",   "DRUG_fluoxetine",      "major",    "CYP2D6抑制+QT延长叠加，心律失常风险"),
    ("DRUG_haloperidol",   "DRUG_carbamazepine",   "moderate", "卡马西平加速氟哌啶醇代谢，降低其效果"),
    ("DRUG_haloperidol",   "DRUG_diazepam",        "moderate", "联用增强中枢抑制效果"),

    # Ondansetron 相关
    ("DRUG_ondansetron",   "DRUG_fluoxetine",      "major",    "5-HT3拮抗+SSRI引发血清素综合征风险"),
    ("DRUG_ondansetron",   "DRUG_haloperidol",     "major",    "QT延长叠加，尖端扣转型室速风险"),

    # Amphotericin B 相关
    ("DRUG_amphotericin_b","DRUG_cisplatin",       "major",    "双重肾毒性叠加，可致急性肾衰竭"),
    ("DRUG_amphotericin_b","DRUG_vancomycin",      "major",    "双重肾毒性叠加"),
    ("DRUG_amphotericin_b","DRUG_fluconazole",     "moderate", "拮抗作用，氟康唑可能降低两性霉素B效果"),

    # Prednisone 相关
    ("DRUG_prednisone",    "DRUG_ibuprofen",       "moderate", "糖皮质激素+NSAIDs增加GI出血和溃疡风险"),
    ("DRUG_prednisone",    "DRUG_warfarin",        "moderate", "泼尼松可能改变华法林的抗凝效果"),
    ("DRUG_prednisone",    "DRUG_metformin",       "moderate", "糖皮质激素升高血糖，拮抗二甲双胍"),

    # Glipizide 相关
    ("DRUG_glipizide",     "DRUG_fluconazole",     "major",    "氟康唑抑制CYP2C9，大幅升高格列吡嗪浓度，低血糖风险"),
    ("DRUG_glipizide",     "DRUG_dexamethasone",   "moderate", "糖皮质激素拮抗降糖药效果"),

    # Cephalexin 相关
    ("DRUG_cephalexin",    "DRUG_metformin",       "moderate", "可能升高二甲双胍血药浓度"),

    # Salbutamol 相关
    ("DRUG_salbutamol",    "DRUG_diazepam",        "moderate", "英二氮卓类可能抑制支气管扩张"),

    # Oseltamivir 相关
    ("DRUG_oseltamivir",   "DRUG_warfarin",        "moderate", "可能增强华法林抗凝效果"),

    # Diazepam 相关 (除上述已列的)
    ("DRUG_diazepam",      "DRUG_omeprazole",      "moderate", "奥美拉唑抑制CYP2C19，升高地西泮浓度"),

    # Carbamazepine 相关 (除上述已列的)
    ("DRUG_carbamazepine", "DRUG_doxycycline",     "moderate", "卡马西平诱导CYP酶，加速多西环素代谢，降低其临床效果"),
]


# ============================================================
#  API 替代关系 (SUBSTITUTE_OF)
#  同类 API 之间的可替代性
# ============================================================
API_SUBSTITUTES = [
    # (API_A, API_B, 替代等级: direct/partial/emergency_only)
    ("API_amoxicillin_trihy", "API_cephalexin_mono",  "partial"),         # 同属β-内酰胺
    ("API_ciprofloxacin_hcl", "API_doxycycline_hyc",  "partial"),         # 广谱抗菌替代
    ("API_morphine_sulfate",  "API_fentanyl_citrate",  "partial"),        # 阿片类替代
    ("API_atorvastatin_ca",   "API_losartan_k",        "emergency_only"), # 非同类但同为心血管
    ("API_amlodipine_bes",    "API_metoprolol_tar",    "partial"),        # 降压药替代
    ("API_warfarin_na",       "API_heparin_na",        "partial"),        # 抗凝替代
    ("API_lisinopril_dihy",   "API_losartan_k",        "direct"),         # ACEI→ARB可直接替代
    ("API_omeprazole",        "API_losartan_k",        "emergency_only"), # 不可替代，标注
    ("API_ibuprofen",         "API_acetaminophen",     "partial"),        # 解热镇痛替代
    ("API_fluconazole",       "API_acyclovir",         "emergency_only"), # 不同类（标注不可替代）
    ("API_cisplatin",         "API_fluorouracil",      "partial"),        # 抗肿瘤替代方案
    ("API_doxorubicin_hcl",   "API_paclitaxel",        "partial"),        # 抗肿瘤替代方案
    ("API_metformin_hcl",     "API_glipizide",         "partial"),        # 口服降糖药替代

    # 补充: 更多替代关系
    ("API_amphotericin_b",    "API_fluconazole",       "partial"),        # 抗真菌替代
    ("API_diazepam",          "API_haloperidol",       "emergency_only"), # 不同类镇静
    ("API_carbamazepine",     "API_phenytoin_na",      "direct"),         # 抗癋疗直接替代
    ("API_prednisone",        "API_dexamethasone",     "direct"),         # 糖皮质激素类直接替代
    ("API_oseltamivir_phos",  "API_acyclovir",         "emergency_only"), # 不同抗病毒靶点
    ("API_vancomycin_hcl",    "API_metronidazole",     "partial"),        # C.diff治疗替代
    ("API_azithromycin_dihy", "API_doxycycline_hyc",   "direct"),         # 非典型感染直接替代
    ("API_piperacillin_na",   "API_ciprofloxacin_hcl", "partial"),        # 广谱抗菌替代
    ("API_potassium_chloride","API_sodium_chloride",   "emergency_only"), # 不可替代，但同为电解质
]


# ============================================================
#  治疗领域 (TherapeuticArea)
# ============================================================
THERAPEUTIC_AREAS = [
    {"id": "TA_antibiotic",       "name": "抗生素/抗感染 (Anti-infective)",       "atc_prefix": "J01"},
    {"id": "TA_cardiovascular",   "name": "心血管系统 (Cardiovascular)",          "atc_prefix": "C"},
    {"id": "TA_analgesic",        "name": "镇痛药 (Analgesic)",                  "atc_prefix": "N02"},
    {"id": "TA_anesthetic",       "name": "麻醉药 (Anesthetic)",                 "atc_prefix": "N01"},
    {"id": "TA_oncology",         "name": "抗肿瘤药 (Oncology)",                 "atc_prefix": "L01"},
    {"id": "TA_diabetes",         "name": "糖尿病用药 (Diabetes)",               "atc_prefix": "A10"},
    {"id": "TA_neuropsych",       "name": "神经/精神科用药 (Neuropsychiatric)",   "atc_prefix": "N"},
    {"id": "TA_respiratory",      "name": "呼吸系统用药 (Respiratory)",           "atc_prefix": "R"},
    {"id": "TA_corticosteroid",   "name": "皮质类固醇 (Corticosteroid)",         "atc_prefix": "H02"},
    {"id": "TA_antiviral",        "name": "抗病毒药 (Antiviral)",                "atc_prefix": "J05"},
    {"id": "TA_antifungal",       "name": "抗真菌药 (Antifungal)",               "atc_prefix": "J02"},
    {"id": "TA_gastrointestinal", "name": "消化系统用药 (Gastrointestinal)",      "atc_prefix": "A02"},
    {"id": "TA_contrast_agent",   "name": "造影剂 (Contrast Agent)",             "atc_prefix": "V08"},
    {"id": "TA_electrolyte",      "name": "电解质/营养 (Electrolyte)",            "atc_prefix": "B05"},
]

# 药品 → 治疗领域 映射
DRUG_AREA_MAP = {
    "antibiotic":       "TA_antibiotic",
    "cardiovascular":   "TA_cardiovascular",
    "analgesic":        "TA_analgesic",
    "anesthetic":       "TA_anesthetic",
    "oncology":         "TA_oncology",
    "diabetes":         "TA_diabetes",
    "neuropsych":       "TA_neuropsych",
    "respiratory":      "TA_respiratory",
    "corticosteroid":   "TA_corticosteroid",
    "antiviral":        "TA_antiviral",
    "antifungal":       "TA_antifungal",
    "gastrointestinal": "TA_gastrointestinal",
    "contrast_agent":   "TA_contrast_agent",
    "electrolyte":      "TA_electrolyte",
}


# ============================================================
#  国家/地区数据 (Country)
# ============================================================
COUNTRIES = [
    {"id": "COUNTRY_china",       "name": "China（中国）",          "region": "Asia-Pacific",    "api_share_pct": 40},
    {"id": "COUNTRY_india",       "name": "India（印度）",          "region": "Asia-Pacific",    "api_share_pct": 20},
    {"id": "COUNTRY_usa",         "name": "United States（美国）",  "region": "North America",   "api_share_pct": 10},
    {"id": "COUNTRY_germany",     "name": "Germany（德国）",        "region": "Europe",          "api_share_pct": 5},
    {"id": "COUNTRY_switzerland", "name": "Switzerland（瑞士）",    "region": "Europe",          "api_share_pct": 4},
    {"id": "COUNTRY_israel",      "name": "Israel（以色列）",       "region": "Middle East",     "api_share_pct": 3},
    {"id": "COUNTRY_france",      "name": "France（法国）",         "region": "Europe",          "api_share_pct": 3},
    {"id": "COUNTRY_denmark",     "name": "Denmark（丹麦）",        "region": "Europe",          "api_share_pct": 2},
    {"id": "COUNTRY_jordan",      "name": "Jordan（约旦）",         "region": "Middle East",     "api_share_pct": 1},
]

COUNTRY_NAME_TO_ID = {
    "China": "COUNTRY_china",   "India": "COUNTRY_india",     "USA": "COUNTRY_usa",
    "Germany": "COUNTRY_germany","Switzerland": "COUNTRY_switzerland",
    "Israel": "COUNTRY_israel", "France": "COUNTRY_france",   "Denmark": "COUNTRY_denmark",
    "Jordan": "COUNTRY_jordan",
}


# ============================================================
#  历史短缺事件 (ShortageEvent)
#  来源: FDA Drug Shortage Database (公开)
# ============================================================
SHORTAGE_EVENTS = [
    {"id": "SHORT_vincristine_2019",  "drug_id": "DRUG_vincristine",   "year": 2019, "duration_months": 18,
     "cause": "Teva退出市场，仅剩Pfizer一家供应", "severity": "critical",
     "impact": "儿童白血病治疗方案被迫调整，无替代药可用"},

    {"id": "SHORT_heparin_2008",      "drug_id": "DRUG_heparin",       "year": 2008, "duration_months": 12,
     "cause": "中国猪源肝素原料污染（掺假硫酸软骨素）", "severity": "critical",
     "impact": "全球81人死亡，FDA加强进口API监管"},

    {"id": "SHORT_cisplatin_2023",    "drug_id": "DRUG_cisplatin",     "year": 2023, "duration_months": 8,
     "cause": "Intas Pharma(印度)工厂因GMP问题被FDA警告", "severity": "critical",
     "impact": "美国多家癌症中心被迫调整化疗方案"},

    {"id": "SHORT_contrast_2022",     "drug_id": "DRUG_iohexol",       "year": 2022, "duration_months": 6,
     "cause": "GE上海工厂因COVID封控停产", "severity": "major",
     "impact": "全球CT/MRI检查量骤降，医院限制非紧急造影"},

    {"id": "SHORT_piperacillin_2024", "drug_id": "DRUG_piperacillin",  "year": 2024, "duration_months": 4,
     "cause": "CSPC石药集团API产线质量问题", "severity": "major",
     "impact": "ICU广谱抗生素供应紧张"},

    {"id": "SHORT_propofol_2023",     "drug_id": "DRUG_propofol",      "year": 2023, "duration_months": 5,
     "cause": "Fresenius Kabi产能不足+需求激增", "severity": "major",
     "impact": "择期手术延迟，ICU镇静方案被迫调整"},

    {"id": "SHORT_methotrexate_2023", "drug_id": "DRUG_methotrexate",  "year": 2023, "duration_months": 7,
     "cause": "Pfizer工厂产能限制", "severity": "major",
     "impact": "白血病维持治疗和类风湿关节炎患者受影响"},

    {"id": "SHORT_amoxicillin_2022",  "drug_id": "DRUG_amoxicillin",   "year": 2022, "duration_months": 4,
     "cause": "冬季呼吸道感染高峰+供应链延迟", "severity": "moderate",
     "impact": "儿科抗生素短缺，部分地区限量配给"},

    {"id": "SHORT_doxycycline_2023",  "drug_id": "DRUG_doxycycline",   "year": 2023, "duration_months": 10,
     "cause": "需求增加+API供应商产能有限", "severity": "moderate",
     "impact": "STI治疗和疟疾预防用药受影响"},

    {"id": "SHORT_fluorouracil_2023", "drug_id": "DRUG_fluorouracil",  "year": 2023, "duration_months": 6,
     "cause": "多家供应商同时出现生产问题", "severity": "major",
     "impact": "消化道肿瘤化疗方案被迫调整"},

    {"id": "SHORT_lidocaine_2021",    "drug_id": "DRUG_lidocaine",     "year": 2021, "duration_months": 3,
     "cause": "COVID疫苗接种高峰期需求激增", "severity": "moderate",
     "impact": "门诊局部麻醉和急诊用药紧张"},

    {"id": "SHORT_sodium_chloride_2014", "drug_id": "DRUG_sodium_chloride", "year": 2014, "duration_months": 8,
     "cause": "包装材料短缺+生产成本低导致供应商退出", "severity": "major",
     "impact": "美国各地医院盐水短缺，择期手术推迟"},

    {"id": "SHORT_ondansetron_2020",  "drug_id": "DRUG_ondansetron",   "year": 2020, "duration_months": 3,
     "cause": "COVID导致需求激增+物流中断", "severity": "moderate",
     "impact": "化疗止吐和术后止吐药供应紧张"},

    # ---- 补充: 更多历史短缺事件 ----
    {"id": "SHORT_azithromycin_2020",  "drug_id": "DRUG_azithromycin",  "year": 2020, "duration_months": 5,
     "cause": "COVID早期误用为治疗药物，全球需求暴增", "severity": "major",
     "impact": "社区感染治疗抗生素缺乏，部分地区开始限制处方"},

    {"id": "SHORT_dexamethasone_2020", "drug_id": "DRUG_dexamethasone", "year": 2020, "duration_months": 4,
     "cause": "RECOVERY试验证明对COVID重症有效，全球抢购", "severity": "major",
     "impact": "COVID重症患者和原有需要地塞米松的肿瘤患者竞争药源"},

    {"id": "SHORT_fentanyl_2020",      "drug_id": "DRUG_fentanyl",      "year": 2020, "duration_months": 6,
     "cause": "COVID期ICU镇静需求激增，单一供应商产能不足", "severity": "critical",
     "impact": "ICU镇静/镜痛方案被迫调整，使用替代药物"},

    {"id": "SHORT_morphine_2022",      "drug_id": "DRUG_morphine",      "year": 2022, "duration_months": 5,
     "cause": "DEA配额限制+生产商产能不足", "severity": "major",
     "impact": "术后和姑息治疗镇痛用药紧张"},

    {"id": "SHORT_losartan_2019",      "drug_id": "DRUG_losartan",      "year": 2019, "duration_months": 10,
     "cause": "NDMA致癌杂质被发现，多家印度/中国供应商被召回", "severity": "critical",
     "impact": "氯沙坦/缬沙坦/厄贝沙坦全线召回，数百万患者被迫换药"},

    {"id": "SHORT_vancomycin_2023",    "drug_id": "DRUG_vancomycin",    "year": 2023, "duration_months": 4,
     "cause": "API供应商减产+多重耐药感染增加", "severity": "major",
     "impact": "MRSA和C.diff感染治疗方案被迫调整"},

    {"id": "SHORT_amphotericin_2022",  "drug_id": "DRUG_amphotericin_b", "year": 2022, "duration_months": 7,
     "cause": "印度“毛霉菌病”爆发后需求激增，全球供应被消耗", "severity": "critical",
     "impact": "严重真菌感染患者无药可用，死亡率上升"},

    {"id": "SHORT_acyclovir_2020",     "drug_id": "DRUG_acyclovir",     "year": 2020, "duration_months": 4,
     "cause": "COVID期间生产线被转产+物流延迟", "severity": "moderate",
     "impact": "带状疖疑和生殖器疖疑患者用药受影响"},

    {"id": "SHORT_salbutamol_2022",    "drug_id": "DRUG_salbutamol",    "year": 2022, "duration_months": 3,
     "cause": "吸入装置和抛射剂生产工艺问题", "severity": "moderate",
     "impact": "哮喘患者紧急救援用药受影响"},

    {"id": "SHORT_insulin_2023",       "drug_id": "DRUG_insulin_regular", "year": 2023, "duration_months": 3,
     "cause": "Novo Nordisk产能调整，优先GLP-1生产线", "severity": "major",
     "impact": "部分国家胰岛素供应紧张，价格上涨"},

    {"id": "SHORT_diazepam_2021",      "drug_id": "DRUG_diazepam",      "year": 2021, "duration_months": 3,
     "cause": "API供应链延迟+包装材料短缺", "severity": "moderate",
     "impact": "癌线抽搐和焦虑治疗用药受影响"},

    {"id": "SHORT_fluconazole_2022",   "drug_id": "DRUG_fluconazole",   "year": 2022, "duration_months": 4,
     "cause": "多家制造商产能问题＋需求上升", "severity": "moderate",
     "impact": "免疫功能低下患者抗真菌预防用药受影响"},

    {"id": "SHORT_paclitaxel_2019",    "drug_id": "DRUG_paclitaxel",    "year": 2019, "duration_months": 6,
     "cause": "Intas Pharma被发现GMP违规，多批次被召回", "severity": "major",
     "impact": "乳腺癌/卵巢癌/肺癌化疗方案被迫调整"},
]


# ============================================================
#  监管法规 (Regulation)
# ============================================================
REGULATIONS = [
    {"id": "REG_fda_cgmp",          "name": "FDA cGMP (21 CFR 210/211)", "authority": "FDA",
     "description": "药品生产质量管理规范，API和制剂生产必须遵守"},
    {"id": "REG_fda_drug_shortage", "name": "FDA Drug Shortage Policy",  "authority": "FDA",
     "description": "要求制造商提前6个月报告可能的供应中断"},
    {"id": "REG_fda_dmf",           "name": "FDA Drug Master File (DMF)", "authority": "FDA",
     "description": "API供应商须向FDA提交DMF，记录生产工艺和质量标准"},
    {"id": "REG_fda_import_alert",  "name": "FDA Import Alert",         "authority": "FDA",
     "description": "对不合规的进口API实施自动扣押"},
    {"id": "REG_ema_gmp",           "name": "EMA GMP (EudraLex Vol.4)", "authority": "EMA",
     "description": "欧盟药品生产质量管理规范"},
    {"id": "REG_who_prequalification","name": "WHO Prequalification",   "authority": "WHO",
     "description": "WHO对药品和API供应商的预认证体系"},
    {"id": "REG_ich_q7",            "name": "ICH Q7 (GMP for APIs)",    "authority": "ICH",
     "description": "API生产的国际协调GMP指南"},
    {"id": "REG_usp_monograph",     "name": "USP Monograph Standards",  "authority": "USP",
     "description": "美国药典的药品质量标准"},
]


# ============================================================
#  ★ 扩展数据集 — 新增药品 / API / 厂商 / 国家 / 供应关系
#  目标: 将知识图谱从 ~680 节点扩展到 ~2000+ 节点
# ============================================================

# ---------- 新增药品 (80+) ----------
DRUGS_EXPANSION = [
    # --- 抗生素 (扩展) ---
    {"id": "DRUG_levofloxacin",      "name": "Levofloxacin（左氧氟沙星）",       "category": "antibiotic", "who_essential": True,  "dosage_form": "tablet"},
    {"id": "DRUG_meropenem",         "name": "Meropenem（美罗培南）",            "category": "antibiotic", "who_essential": True,  "dosage_form": "injection"},
    {"id": "DRUG_imipenem",          "name": "Imipenem-Cilastatin（亚胺培南西司他丁）", "category": "antibiotic", "who_essential": True, "dosage_form": "injection"},
    {"id": "DRUG_gentamicin",        "name": "Gentamicin（庆大霉素）",           "category": "antibiotic", "who_essential": True,  "dosage_form": "injection"},
    {"id": "DRUG_clindamycin",       "name": "Clindamycin（克林霉素）",          "category": "antibiotic", "who_essential": True,  "dosage_form": "capsule"},
    {"id": "DRUG_trimethoprim_smx",  "name": "Trimethoprim-SMX（复方新诺明）",   "category": "antibiotic", "who_essential": True,  "dosage_form": "tablet"},
    {"id": "DRUG_nitrofurantoin",    "name": "Nitrofurantoin（呋喃妥因）",       "category": "antibiotic", "who_essential": True,  "dosage_form": "capsule"},
    {"id": "DRUG_colistin",          "name": "Colistin（多粘菌素E）",            "category": "antibiotic", "who_essential": True,  "dosage_form": "injection"},
    {"id": "DRUG_linezolid",         "name": "Linezolid（利奈唑胺）",            "category": "antibiotic", "who_essential": True,  "dosage_form": "tablet"},
    {"id": "DRUG_rifampicin",        "name": "Rifampicin（利福平）",             "category": "antibiotic", "who_essential": True,  "dosage_form": "capsule"},
    {"id": "DRUG_isoniazid",         "name": "Isoniazid（异烟肼）",              "category": "antibiotic", "who_essential": True,  "dosage_form": "tablet"},
    {"id": "DRUG_ethambutol",        "name": "Ethambutol（乙胺丁醇）",           "category": "antibiotic", "who_essential": True,  "dosage_form": "tablet"},
    {"id": "DRUG_pyrazinamide",      "name": "Pyrazinamide（吡嗪酰胺）",         "category": "antibiotic", "who_essential": True,  "dosage_form": "tablet"},

    # --- 心血管 (扩展) ---
    {"id": "DRUG_valsartan",         "name": "Valsartan（缬沙坦）",             "category": "cardiovascular", "who_essential": True,  "dosage_form": "tablet"},
    {"id": "DRUG_hydrochlorothiazide","name": "Hydrochlorothiazide（氢氯噻嗪）", "category": "cardiovascular", "who_essential": True,  "dosage_form": "tablet"},
    {"id": "DRUG_furosemide",        "name": "Furosemide（呋塞米）",            "category": "cardiovascular", "who_essential": True,  "dosage_form": "tablet"},
    {"id": "DRUG_spironolactone",    "name": "Spironolactone（螺内酯）",        "category": "cardiovascular", "who_essential": True,  "dosage_form": "tablet"},
    {"id": "DRUG_digoxin",           "name": "Digoxin（地高辛）",               "category": "cardiovascular", "who_essential": True,  "dosage_form": "tablet"},
    {"id": "DRUG_diltiazem",         "name": "Diltiazem（地尔硫卓）",           "category": "cardiovascular", "who_essential": False, "dosage_form": "tablet"},
    {"id": "DRUG_clopidogrel",       "name": "Clopidogrel（氯吡格雷）",         "category": "cardiovascular", "who_essential": True,  "dosage_form": "tablet"},
    {"id": "DRUG_enoxaparin",        "name": "Enoxaparin（依诺肝素）",          "category": "cardiovascular", "who_essential": True,  "dosage_form": "injection"},
    {"id": "DRUG_nitroglycerin",     "name": "Nitroglycerin（硝酸甘油）",       "category": "cardiovascular", "who_essential": True,  "dosage_form": "injection"},
    {"id": "DRUG_simvastatin",       "name": "Simvastatin（辛伐他汀）",         "category": "cardiovascular", "who_essential": True,  "dosage_form": "tablet"},
    {"id": "DRUG_rosuvastatin",      "name": "Rosuvastatin（瑞舒伐他汀）",      "category": "cardiovascular", "who_essential": False, "dosage_form": "tablet"},
    {"id": "DRUG_enalapril",         "name": "Enalapril（依那普利）",           "category": "cardiovascular", "who_essential": True,  "dosage_form": "tablet"},
    {"id": "DRUG_ramipril",          "name": "Ramipril（雷米普利）",            "category": "cardiovascular", "who_essential": False, "dosage_form": "tablet"},
    {"id": "DRUG_nifedipine",        "name": "Nifedipine（硝苯地平）",          "category": "cardiovascular", "who_essential": True,  "dosage_form": "tablet"},
    {"id": "DRUG_amiodarone",        "name": "Amiodarone（胺碘酮）",            "category": "cardiovascular", "who_essential": True,  "dosage_form": "injection"},

    # --- 抗肿瘤 (扩展) ---
    {"id": "DRUG_cyclophosphamide",  "name": "Cyclophosphamide（环磷酰胺）",    "category": "oncology",   "who_essential": True,  "dosage_form": "injection"},
    {"id": "DRUG_etoposide",        "name": "Etoposide（依托泊苷）",           "category": "oncology",   "who_essential": True,  "dosage_form": "injection"},
    {"id": "DRUG_carboplatin",       "name": "Carboplatin（卡铂）",             "category": "oncology",   "who_essential": True,  "dosage_form": "injection"},
    {"id": "DRUG_irinotecan",        "name": "Irinotecan（伊立替康）",          "category": "oncology",   "who_essential": True,  "dosage_form": "injection"},
    {"id": "DRUG_oxaliplatin",       "name": "Oxaliplatin（奥沙利铂）",         "category": "oncology",   "who_essential": True,  "dosage_form": "injection"},
    {"id": "DRUG_gemcitabine",       "name": "Gemcitabine（吉西他滨）",         "category": "oncology",   "who_essential": True,  "dosage_form": "injection"},
    {"id": "DRUG_capecitabine",      "name": "Capecitabine（卡培他滨）",        "category": "oncology",   "who_essential": True,  "dosage_form": "tablet"},
    {"id": "DRUG_imatinib",          "name": "Imatinib（伊马替尼）",            "category": "oncology",   "who_essential": True,  "dosage_form": "tablet"},
    {"id": "DRUG_tamoxifen",         "name": "Tamoxifen（他莫昔芬）",           "category": "oncology",   "who_essential": True,  "dosage_form": "tablet"},
    {"id": "DRUG_leucovorin",        "name": "Leucovorin（亚叶酸钙）",          "category": "oncology",   "who_essential": True,  "dosage_form": "injection"},
    {"id": "DRUG_bleomycin",         "name": "Bleomycin（博来霉素）",           "category": "oncology",   "who_essential": True,  "dosage_form": "injection"},
    {"id": "DRUG_dacarbazine",       "name": "Dacarbazine（达卡巴嗪）",         "category": "oncology",   "who_essential": True,  "dosage_form": "injection"},
    {"id": "DRUG_rituximab",         "name": "Rituximab（利妥昔单抗）",         "category": "oncology",   "who_essential": True,  "dosage_form": "injection"},
    {"id": "DRUG_trastuzumab",       "name": "Trastuzumab（曲妥珠单抗）",       "category": "oncology",   "who_essential": True,  "dosage_form": "injection"},

    # --- 精神/神经 (扩展) ---
    {"id": "DRUG_sertraline",        "name": "Sertraline（舍曲林）",            "category": "neuropsych", "who_essential": True,  "dosage_form": "tablet"},
    {"id": "DRUG_amitriptyline",     "name": "Amitriptyline（阿米替林）",       "category": "neuropsych", "who_essential": True,  "dosage_form": "tablet"},
    {"id": "DRUG_lithium",           "name": "Lithium Carbonate（碳酸锂）",     "category": "neuropsych", "who_essential": True,  "dosage_form": "tablet"},
    {"id": "DRUG_clonazepam",        "name": "Clonazepam（氯硝西泮）",          "category": "neuropsych", "who_essential": False, "dosage_form": "tablet"},
    {"id": "DRUG_valproic_acid",     "name": "Valproic Acid（丙戊酸）",         "category": "neuropsych", "who_essential": True,  "dosage_form": "tablet"},
    {"id": "DRUG_levodopa",          "name": "Levodopa-Carbidopa（左旋多巴卡比多巴）", "category": "neuropsych", "who_essential": True, "dosage_form": "tablet"},
    {"id": "DRUG_olanzapine",        "name": "Olanzapine（奥氮平）",            "category": "neuropsych", "who_essential": True,  "dosage_form": "tablet"},
    {"id": "DRUG_risperidone",       "name": "Risperidone（利培酮）",           "category": "neuropsych", "who_essential": True,  "dosage_form": "tablet"},
    {"id": "DRUG_gabapentin",        "name": "Gabapentin（加巴喷丁）",          "category": "neuropsych", "who_essential": False, "dosage_form": "capsule"},
    {"id": "DRUG_tramadol",          "name": "Tramadol（曲马多）",              "category": "analgesic",  "who_essential": False, "dosage_form": "tablet"},

    # --- 抗感染 (扩展) ---
    {"id": "DRUG_tenofovir",         "name": "Tenofovir（替诺福韦）",           "category": "antiviral",  "who_essential": True,  "dosage_form": "tablet"},
    {"id": "DRUG_lamivudine",        "name": "Lamivudine（拉米夫定）",          "category": "antiviral",  "who_essential": True,  "dosage_form": "tablet"},
    {"id": "DRUG_efavirenz",         "name": "Efavirenz（依非韦伦）",           "category": "antiviral",  "who_essential": True,  "dosage_form": "tablet"},
    {"id": "DRUG_atazanavir",        "name": "Atazanavir（阿扎那韦）",          "category": "antiviral",  "who_essential": True,  "dosage_form": "capsule"},
    {"id": "DRUG_zidovudine",        "name": "Zidovudine（齐多夫定）",          "category": "antiviral",  "who_essential": True,  "dosage_form": "capsule"},
    {"id": "DRUG_artemether_lumef",  "name": "Artemether-Lumefantrine（蒿甲醚本芴醇）", "category": "antiparasitic", "who_essential": True, "dosage_form": "tablet"},
    {"id": "DRUG_quinine",           "name": "Quinine（奎宁）",                 "category": "antiparasitic", "who_essential": True, "dosage_form": "tablet"},
    {"id": "DRUG_albendazole",       "name": "Albendazole（阿苯达唑）",         "category": "antiparasitic", "who_essential": True, "dosage_form": "tablet"},
    {"id": "DRUG_ivermectin",        "name": "Ivermectin（伊维菌素）",          "category": "antiparasitic", "who_essential": True, "dosage_form": "tablet"},
    {"id": "DRUG_itraconazole",      "name": "Itraconazole（伊曲康唑）",        "category": "antifungal", "who_essential": True,  "dosage_form": "capsule"},

    # --- 其他治疗领域 ---
    {"id": "DRUG_ranitidine",        "name": "Ranitidine（雷尼替丁）",          "category": "gastrointestinal", "who_essential": False, "dosage_form": "tablet"},
    {"id": "DRUG_pantoprazole",      "name": "Pantoprazole（泮托拉唑）",        "category": "gastrointestinal", "who_essential": False, "dosage_form": "tablet"},
    {"id": "DRUG_erythropoietin",    "name": "Erythropoietin（促红细胞生成素）", "category": "hematology", "who_essential": True, "dosage_form": "injection"},
    {"id": "DRUG_tranexamic_acid",   "name": "Tranexamic Acid（氨甲环酸）",     "category": "hematology", "who_essential": True, "dosage_form": "injection"},
    {"id": "DRUG_oxytocin",          "name": "Oxytocin（缩宫素）",              "category": "obstetric",  "who_essential": True,  "dosage_form": "injection"},
    {"id": "DRUG_misoprostol",       "name": "Misoprostol（米索前列醇）",       "category": "obstetric",  "who_essential": True,  "dosage_form": "tablet"},
    {"id": "DRUG_ketamine",          "name": "Ketamine（氯胺酮）",              "category": "anesthetic", "who_essential": True,  "dosage_form": "injection"},
    {"id": "DRUG_atropine",          "name": "Atropine（阿托品）",              "category": "emergency",  "who_essential": True,  "dosage_form": "injection"},
    {"id": "DRUG_epinephrine",       "name": "Epinephrine（肾上腺素）",         "category": "emergency",  "who_essential": True,  "dosage_form": "injection"},
    {"id": "DRUG_dopamine",          "name": "Dopamine（多巴胺）",              "category": "emergency",  "who_essential": True,  "dosage_form": "injection"},
    {"id": "DRUG_norepinephrine",    "name": "Norepinephrine（去甲肾上腺素）",  "category": "emergency",  "who_essential": True,  "dosage_form": "injection"},
    {"id": "DRUG_calcium_gluconate", "name": "Calcium Gluconate（葡萄糖酸钙）", "category": "electrolyte", "who_essential": True, "dosage_form": "injection"},
    {"id": "DRUG_magnesium_sulfate", "name": "Magnesium Sulfate（硫酸镁）",     "category": "electrolyte", "who_essential": True, "dosage_form": "injection"},
    {"id": "DRUG_glucose",           "name": "Glucose（葡萄糖注射液）",         "category": "electrolyte", "who_essential": True, "dosage_form": "injection"},
    {"id": "DRUG_hydrocortisone",    "name": "Hydrocortisone（氢化可的松）",    "category": "corticosteroid", "who_essential": True, "dosage_form": "injection"},
    {"id": "DRUG_methylprednisolone","name": "Methylprednisolone（甲泼尼龙）",  "category": "corticosteroid", "who_essential": False, "dosage_form": "injection"},
    {"id": "DRUG_insulin_glargine",  "name": "Insulin Glargine（甘精胰岛素）",  "category": "diabetes",   "who_essential": True,  "dosage_form": "injection"},
    {"id": "DRUG_sitagliptin",       "name": "Sitagliptin（西格列汀）",         "category": "diabetes",   "who_essential": False, "dosage_form": "tablet"},
    {"id": "DRUG_empagliflozin",     "name": "Empagliflozin（恩格列净）",       "category": "diabetes",   "who_essential": False, "dosage_form": "tablet"},
]

# 合并到全局 DRUGS
DRUGS.extend(DRUGS_EXPANSION)

# ---------- 新增治疗领域 ----------
THERAPEUTIC_AREAS_EXPANSION = [
    {"id": "TA_antiparasitic",    "name": "抗寄生虫药 (Antiparasitic)",      "atc_prefix": "P01"},
    {"id": "TA_hematology",       "name": "血液系统用药 (Hematology)",       "atc_prefix": "B"},
    {"id": "TA_obstetric",        "name": "产科用药 (Obstetric)",            "atc_prefix": "G02"},
    {"id": "TA_emergency",        "name": "急救用药 (Emergency)",            "atc_prefix": "C01CA"},
]
THERAPEUTIC_AREAS.extend(THERAPEUTIC_AREAS_EXPANSION)

# 更新映射
DRUG_AREA_MAP.update({
    "antiparasitic": "TA_antiparasitic",
    "hematology":    "TA_hematology",
    "obstetric":     "TA_obstetric",
    "emergency":     "TA_emergency",
})


# ---------- 新增国家 ----------
COUNTRIES_EXPANSION = [
    {"id": "COUNTRY_japan",       "name": "Japan（日本）",           "region": "Asia-Pacific",    "api_share_pct": 3},
    {"id": "COUNTRY_south_korea", "name": "South Korea（韩国）",     "region": "Asia-Pacific",    "api_share_pct": 2},
    {"id": "COUNTRY_italy",       "name": "Italy（意大利）",         "region": "Europe",          "api_share_pct": 3},
    {"id": "COUNTRY_ireland",     "name": "Ireland（爱尔兰）",       "region": "Europe",          "api_share_pct": 2},
    {"id": "COUNTRY_uk",          "name": "United Kingdom（英国）",  "region": "Europe",          "api_share_pct": 2},
    {"id": "COUNTRY_brazil",      "name": "Brazil（巴西）",          "region": "South America",   "api_share_pct": 1},
    {"id": "COUNTRY_south_africa","name": "South Africa（南非）",    "region": "Africa",          "api_share_pct": 1},
    {"id": "COUNTRY_bangladesh",  "name": "Bangladesh（孟加拉）",    "region": "Asia-Pacific",    "api_share_pct": 1},
    {"id": "COUNTRY_indonesia",   "name": "Indonesia（印度尼西亚）", "region": "Asia-Pacific",    "api_share_pct": 1},
    {"id": "COUNTRY_canada",      "name": "Canada（加拿大）",        "region": "North America",   "api_share_pct": 1},
]
COUNTRIES.extend(COUNTRIES_EXPANSION)
COUNTRY_NAME_TO_ID.update({
    "Japan": "COUNTRY_japan", "South Korea": "COUNTRY_south_korea",
    "Italy": "COUNTRY_italy", "Ireland": "COUNTRY_ireland",
    "UK": "COUNTRY_uk", "Brazil": "COUNTRY_brazil",
    "South Africa": "COUNTRY_south_africa", "Bangladesh": "COUNTRY_bangladesh",
    "Indonesia": "COUNTRY_indonesia", "Canada": "COUNTRY_canada",
})


# ---------- 新增厂商 (25+) ----------
MANUFACTURERS_EXPANSION = [
    # 印度 (更多)
    {"id": "MFG_glenmark",        "name": "Glenmark Pharmaceuticals",        "country": "India",      "type": "api_and_formulation", "tier": 2},
    {"id": "MFG_torrent",         "name": "Torrent Pharmaceuticals",         "country": "India",      "type": "formulation",         "tier": 2},
    {"id": "MFG_zydus",           "name": "Zydus Lifesciences",              "country": "India",      "type": "api_and_formulation", "tier": 1},
    {"id": "MFG_hetero",          "name": "Hetero Labs",                     "country": "India",      "type": "api_specialist",      "tier": 1},
    {"id": "MFG_biocon",          "name": "Biocon Limited",                  "country": "India",      "type": "bio_specialist",      "tier": 1},
    {"id": "MFG_wockhardt",       "name": "Wockhardt Limited",               "country": "India",      "type": "api_and_formulation", "tier": 2},
    {"id": "MFG_intas",           "name": "Intas Pharmaceuticals",           "country": "India",      "type": "api_and_formulation", "tier": 1},

    # 中国 (更多)
    {"id": "MFG_kelun",           "name": "Kelun Pharma（科伦药业）",         "country": "China",      "type": "formulation",         "tier": 1},
    {"id": "MFG_hengrui",         "name": "Hengrui Medicine（恒瑞医药）",     "country": "China",      "type": "api_and_formulation", "tier": 1},
    {"id": "MFG_fosun",           "name": "Fosun Pharma（复星医药）",         "country": "China",      "type": "api_and_formulation", "tier": 1},
    {"id": "MFG_sino_biopharma",  "name": "Sino Biopharmaceutical（中国生物制药）","country": "China", "type": "formulation",         "tier": 1},
    {"id": "MFG_shandong_xinhua", "name": "Shandong Xinhua（山东新华）",      "country": "China",      "type": "api_specialist",      "tier": 2},
    {"id": "MFG_kunshan_rotam",   "name": "Kunshan Rotam（昆山龙灯）",       "country": "China",      "type": "api_specialist",      "tier": 2},

    # 日本
    {"id": "MFG_takeda",          "name": "Takeda Pharmaceutical",           "country": "Japan",      "type": "formulation",         "tier": 1},
    {"id": "MFG_daiichi_sankyo",  "name": "Daiichi Sankyo",                  "country": "Japan",      "type": "api_and_formulation", "tier": 1},

    # 韩国
    {"id": "MFG_samsung_bioepis", "name": "Samsung Bioepis",                 "country": "South Korea","type": "bio_specialist",      "tier": 1},
    {"id": "MFG_celltrion",       "name": "Celltrion",                       "country": "South Korea","type": "bio_specialist",      "tier": 1},

    # 欧洲 (更多)
    {"id": "MFG_roche",           "name": "Roche",                           "country": "Switzerland","type": "bio_specialist",      "tier": 1},
    {"id": "MFG_bayer",           "name": "Bayer AG",                        "country": "Germany",    "type": "api_and_formulation", "tier": 1},
    {"id": "MFG_astrazeneca",     "name": "AstraZeneca",                     "country": "UK",         "type": "formulation",         "tier": 1},
    {"id": "MFG_gsk",             "name": "GlaxoSmithKline (GSK)",           "country": "UK",         "type": "api_and_formulation", "tier": 1},
    {"id": "MFG_merck_kgaa",      "name": "Merck KGaA (EMD Serono)",        "country": "Germany",    "type": "api_specialist",      "tier": 1},
    {"id": "MFG_stada",           "name": "STADA Arzneimittel",              "country": "Germany",    "type": "formulation",         "tier": 2},
    {"id": "MFG_servier",         "name": "Servier",                         "country": "France",     "type": "formulation",         "tier": 2},
    {"id": "MFG_menarini",        "name": "Menarini Group",                  "country": "Italy",      "type": "api_and_formulation", "tier": 2},

    # 美国 (更多)
    {"id": "MFG_merck_msd",       "name": "Merck & Co (MSD)",               "country": "USA",        "type": "formulation",         "tier": 1},
    {"id": "MFG_abbvie",          "name": "AbbVie",                          "country": "USA",        "type": "formulation",         "tier": 1},
    {"id": "MFG_amgen",           "name": "Amgen",                           "country": "USA",        "type": "bio_specialist",      "tier": 1},
    {"id": "MFG_gilead",          "name": "Gilead Sciences",                 "country": "USA",        "type": "formulation",         "tier": 1},
    {"id": "MFG_johnson_johnson", "name": "Johnson & Johnson (Janssen)",     "country": "USA",        "type": "formulation",         "tier": 1},
    {"id": "MFG_bms",             "name": "Bristol-Myers Squibb",            "country": "USA",        "type": "formulation",         "tier": 1},
    {"id": "MFG_par_endo",        "name": "Par Pharmaceutical (Endo)",       "country": "USA",        "type": "formulation",         "tier": 2},

    # 孟加拉 (全球最大抗HIV仿制药出口国之一)
    {"id": "MFG_beximco",         "name": "Beximco Pharmaceuticals",         "country": "Bangladesh", "type": "formulation",         "tier": 2},
    {"id": "MFG_square_pharma",   "name": "Square Pharmaceuticals",          "country": "Bangladesh", "type": "formulation",         "tier": 2},

    # 南非
    {"id": "MFG_aspen",           "name": "Aspen Pharmacare",                "country": "South Africa","type":"api_and_formulation", "tier": 1},

    # 巴西
    {"id": "MFG_eurofarma",       "name": "Eurofarma Laboratórios",          "country": "Brazil",     "type": "formulation",         "tier": 2},

    # 意大利
    {"id": "MFG_recordati",       "name": "Recordati",                       "country": "Italy",      "type": "api_and_formulation", "tier": 2},

    # 爱尔兰
    {"id": "MFG_perrigo",         "name": "Perrigo Company",                 "country": "Ireland",    "type": "formulation",         "tier": 2},

    # 加拿大
    {"id": "MFG_apotex",          "name": "Apotex Inc",                      "country": "Canada",     "type": "formulation",         "tier": 1},
]
MANUFACTURERS.extend(MANUFACTURERS_EXPANSION)


# ---------- 新增 API ----------
APIS_EXPANSION = [
    # 抗生素
    {"id": "API_levofloxacin",       "name": "Levofloxacin Hemihydrate",     "cas": "138199-71-0", "class": "fluoroquinolone"},
    {"id": "API_meropenem_trihy",    "name": "Meropenem Trihydrate",         "cas": "119478-56-7", "class": "carbapenem"},
    {"id": "API_imipenem",           "name": "Imipenem Monohydrate",         "cas": "74431-23-5",  "class": "carbapenem"},
    {"id": "API_cilastatin_na",      "name": "Cilastatin Sodium",            "cas": "81129-83-1",  "class": "enzyme_inhibitor"},
    {"id": "API_gentamicin_sulfate", "name": "Gentamicin Sulfate",           "cas": "1405-41-0",   "class": "aminoglycoside"},
    {"id": "API_clindamycin_hcl",    "name": "Clindamycin HCl",             "cas": "21462-39-5",  "class": "lincosamide"},
    {"id": "API_trimethoprim",       "name": "Trimethoprim",                 "cas": "738-70-5",    "class": "diaminopyrimidine"},
    {"id": "API_sulfamethoxazole",   "name": "Sulfamethoxazole",             "cas": "723-46-6",    "class": "sulfonamide"},
    {"id": "API_nitrofurantoin",     "name": "Nitrofurantoin",               "cas": "67-20-9",     "class": "nitrofuran"},
    {"id": "API_colistimethate_na",  "name": "Colistimethate Sodium",        "cas": "8068-28-8",   "class": "polymyxin"},
    {"id": "API_linezolid",          "name": "Linezolid",                    "cas": "165800-03-3", "class": "oxazolidinone"},
    {"id": "API_rifampicin",         "name": "Rifampicin",                   "cas": "13292-46-1",  "class": "rifamycin"},
    {"id": "API_isoniazid",          "name": "Isoniazid",                    "cas": "54-85-3",     "class": "hydrazide"},
    {"id": "API_ethambutol_hcl",     "name": "Ethambutol HCl",              "cas": "1070-11-7",   "class": "antimycobacterial"},
    {"id": "API_pyrazinamide",       "name": "Pyrazinamide",                 "cas": "98-96-4",     "class": "antimycobacterial"},

    # 心血管
    {"id": "API_valsartan",          "name": "Valsartan",                    "cas": "137862-53-4", "class": "arb"},
    {"id": "API_hydrochlorothiazide","name": "Hydrochlorothiazide",          "cas": "58-93-5",     "class": "thiazide_diuretic"},
    {"id": "API_furosemide",         "name": "Furosemide",                   "cas": "54-31-9",     "class": "loop_diuretic"},
    {"id": "API_spironolactone",     "name": "Spironolactone",               "cas": "52-01-7",     "class": "potassium_sparing_diuretic"},
    {"id": "API_digoxin",            "name": "Digoxin",                      "cas": "20830-75-5",  "class": "cardiac_glycoside"},
    {"id": "API_diltiazem_hcl",      "name": "Diltiazem HCl",               "cas": "33286-22-5",  "class": "calcium_channel_blocker"},
    {"id": "API_clopidogrel_bis",    "name": "Clopidogrel Bisulfate",        "cas": "120202-66-6", "class": "antiplatelet"},
    {"id": "API_enoxaparin_na",      "name": "Enoxaparin Sodium",            "cas": "679809-58-6", "class": "lmwh"},
    {"id": "API_nitroglycerin",      "name": "Nitroglycerin",                "cas": "55-63-0",     "class": "nitrate"},
    {"id": "API_simvastatin",        "name": "Simvastatin",                  "cas": "79902-63-9",  "class": "statin"},
    {"id": "API_rosuvastatin_ca",    "name": "Rosuvastatin Calcium",         "cas": "147098-20-2", "class": "statin"},
    {"id": "API_enalapril_maleate",  "name": "Enalapril Maleate",            "cas": "76095-16-4",  "class": "ace_inhibitor"},
    {"id": "API_ramipril",           "name": "Ramipril",                     "cas": "87333-19-5",  "class": "ace_inhibitor"},
    {"id": "API_nifedipine",         "name": "Nifedipine",                   "cas": "21829-25-4",  "class": "calcium_channel_blocker"},

    # 抗肿瘤
    {"id": "API_cyclophosphamide",   "name": "Cyclophosphamide",             "cas": "50-18-0",     "class": "alkylating_agent"},
    {"id": "API_etoposide",         "name": "Etoposide",                    "cas": "33419-42-0",  "class": "topoisomerase_inhibitor"},
    {"id": "API_carboplatin",        "name": "Carboplatin",                  "cas": "41575-94-4",  "class": "platinum_compound"},
    {"id": "API_irinotecan_hcl",     "name": "Irinotecan HCl",              "cas": "100286-90-6", "class": "topoisomerase_inhibitor"},
    {"id": "API_oxaliplatin",        "name": "Oxaliplatin",                  "cas": "61825-94-3",  "class": "platinum_compound"},
    {"id": "API_gemcitabine_hcl",    "name": "Gemcitabine HCl",             "cas": "122111-03-9", "class": "antimetabolite"},
    {"id": "API_capecitabine",       "name": "Capecitabine",                 "cas": "154361-50-9", "class": "antimetabolite"},
    {"id": "API_imatinib_mesylate",  "name": "Imatinib Mesylate",            "cas": "220127-57-1", "class": "tyrosine_kinase_inhibitor"},
    {"id": "API_tamoxifen_citrate",  "name": "Tamoxifen Citrate",            "cas": "54965-24-1",  "class": "serm"},
    {"id": "API_leucovorin_ca",      "name": "Leucovorin Calcium",           "cas": "1492-18-8",   "class": "folate_analog"},
    {"id": "API_bleomycin_sulfate",  "name": "Bleomycin Sulfate",            "cas": "9041-93-4",   "class": "glycopeptide_antibiotic"},
    {"id": "API_dacarbazine",        "name": "Dacarbazine",                  "cas": "4342-03-4",   "class": "alkylating_agent"},

    # 精神/神经
    {"id": "API_sertraline_hcl",     "name": "Sertraline HCl",              "cas": "79559-97-0",  "class": "ssri"},
    {"id": "API_amitriptyline_hcl",  "name": "Amitriptyline HCl",           "cas": "549-18-8",    "class": "tca"},
    {"id": "API_lithium_carbonate",  "name": "Lithium Carbonate",            "cas": "554-13-2",    "class": "mood_stabilizer"},
    {"id": "API_clonazepam",         "name": "Clonazepam",                   "cas": "1622-61-3",   "class": "benzodiazepine"},
    {"id": "API_valproic_acid",      "name": "Valproic Acid",                "cas": "99-66-1",     "class": "anticonvulsant"},
    {"id": "API_levodopa",           "name": "Levodopa",                     "cas": "59-92-7",     "class": "dopamine_precursor"},
    {"id": "API_carbidopa",          "name": "Carbidopa",                    "cas": "28860-95-9",  "class": "decarboxylase_inhibitor"},
    {"id": "API_olanzapine",         "name": "Olanzapine",                   "cas": "132539-06-1", "class": "atypical_antipsychotic"},
    {"id": "API_risperidone",        "name": "Risperidone",                  "cas": "106266-06-2", "class": "atypical_antipsychotic"},
    {"id": "API_gabapentin",         "name": "Gabapentin",                   "cas": "60142-96-3",  "class": "gaba_analog"},
    {"id": "API_tramadol_hcl",       "name": "Tramadol HCl",                "cas": "36282-47-0",  "class": "opioid_analgesic"},

    # 抗病毒/寄生虫
    {"id": "API_tenofovir_df",       "name": "Tenofovir Disoproxil Fumarate","cas": "202138-50-9", "class": "nrti"},
    {"id": "API_lamivudine",         "name": "Lamivudine",                   "cas": "134678-17-4", "class": "nrti"},
    {"id": "API_efavirenz",          "name": "Efavirenz",                    "cas": "154598-52-4", "class": "nnrti"},
    {"id": "API_atazanavir_sulfate", "name": "Atazanavir Sulfate",           "cas": "229975-97-7", "class": "protease_inhibitor"},
    {"id": "API_zidovudine",         "name": "Zidovudine (AZT)",             "cas": "30516-87-1",  "class": "nrti"},
    {"id": "API_artemether",         "name": "Artemether",                   "cas": "71963-77-4",  "class": "artemisinin"},
    {"id": "API_lumefantrine",       "name": "Lumefantrine",                 "cas": "82186-77-4",  "class": "antimalarial"},
    {"id": "API_quinine_sulfate",    "name": "Quinine Sulfate",              "cas": "6119-70-6",   "class": "antimalarial"},
    {"id": "API_albendazole",        "name": "Albendazole",                  "cas": "54965-21-8",  "class": "benzimidazole"},
    {"id": "API_ivermectin",         "name": "Ivermectin",                   "cas": "70288-86-7",  "class": "avermectin"},
    {"id": "API_itraconazole",       "name": "Itraconazole",                 "cas": "84625-61-6",  "class": "azole_antifungal"},

    # 其他
    {"id": "API_pantoprazole_na",    "name": "Pantoprazole Sodium",          "cas": "164579-32-2", "class": "proton_pump_inhibitor"},
    {"id": "API_ranitidine_hcl",     "name": "Ranitidine HCl",              "cas": "66357-59-3",  "class": "h2_blocker"},
    {"id": "API_erythropoietin",     "name": "Erythropoietin (rHuEPO)",      "cas": "11096-26-7",  "class": "hematopoietic_growth_factor"},
    {"id": "API_tranexamic_acid",    "name": "Tranexamic Acid",              "cas": "1197-18-8",   "class": "antifibrinolytic"},
    {"id": "API_oxytocin",           "name": "Oxytocin",                     "cas": "50-56-6",     "class": "peptide_hormone"},
    {"id": "API_misoprostol",        "name": "Misoprostol",                  "cas": "59122-46-2",  "class": "prostaglandin"},
    {"id": "API_ketamine_hcl",       "name": "Ketamine HCl",                "cas": "1867-66-9",   "class": "dissociative_anesthetic"},
    {"id": "API_atropine_sulfate",   "name": "Atropine Sulfate",             "cas": "55-48-1",     "class": "anticholinergic"},
    {"id": "API_epinephrine",        "name": "Epinephrine",                  "cas": "51-43-4",     "class": "catecholamine"},
    {"id": "API_dopamine_hcl",       "name": "Dopamine HCl",                "cas": "62-31-7",     "class": "catecholamine"},
    {"id": "API_norepinephrine",     "name": "Norepinephrine Bitartrate",    "cas": "108341-18-0", "class": "catecholamine"},
    {"id": "API_calcium_gluconate",  "name": "Calcium Gluconate",            "cas": "299-28-5",    "class": "electrolyte"},
    {"id": "API_magnesium_sulfate",  "name": "Magnesium Sulfate Heptahydrate","cas": "10034-99-8", "class": "electrolyte"},
    {"id": "API_hydrocortisone",     "name": "Hydrocortisone",               "cas": "50-23-7",     "class": "corticosteroid"},
    {"id": "API_methylprednisolone", "name": "Methylprednisolone Sodium Succinate","cas":"2375-03-3","class": "corticosteroid"},
    {"id": "API_insulin_glargine",   "name": "Insulin Glargine",             "cas": "160337-95-1", "class": "peptide_hormone"},
    {"id": "API_sitagliptin_phos",   "name": "Sitagliptin Phosphate",        "cas": "654671-78-0", "class": "dpp4_inhibitor"},
    {"id": "API_empagliflozin",      "name": "Empagliflozin",                "cas": "864070-44-0", "class": "sglt2_inhibitor"},
]
APIS.extend(APIS_EXPANSION)


# ---------- 新增 Drug → API 映射 ----------
DRUG_API_MAP_EXPANSION = [
    # 抗生素
    ("DRUG_levofloxacin",      "API_levofloxacin"),
    ("DRUG_meropenem",         "API_meropenem_trihy"),
    ("DRUG_imipenem",          "API_imipenem"),
    ("DRUG_imipenem",          "API_cilastatin_na"),
    ("DRUG_gentamicin",        "API_gentamicin_sulfate"),
    ("DRUG_clindamycin",       "API_clindamycin_hcl"),
    ("DRUG_trimethoprim_smx",  "API_trimethoprim"),
    ("DRUG_trimethoprim_smx",  "API_sulfamethoxazole"),
    ("DRUG_nitrofurantoin",    "API_nitrofurantoin"),
    ("DRUG_colistin",          "API_colistimethate_na"),
    ("DRUG_linezolid",         "API_linezolid"),
    ("DRUG_rifampicin",        "API_rifampicin"),
    ("DRUG_isoniazid",         "API_isoniazid"),
    ("DRUG_ethambutol",        "API_ethambutol_hcl"),
    ("DRUG_pyrazinamide",      "API_pyrazinamide"),

    # 心血管
    ("DRUG_valsartan",         "API_valsartan"),
    ("DRUG_hydrochlorothiazide","API_hydrochlorothiazide"),
    ("DRUG_furosemide",        "API_furosemide"),
    ("DRUG_spironolactone",    "API_spironolactone"),
    ("DRUG_digoxin",           "API_digoxin"),
    ("DRUG_diltiazem",         "API_diltiazem_hcl"),
    ("DRUG_clopidogrel",       "API_clopidogrel_bis"),
    ("DRUG_enoxaparin",        "API_enoxaparin_na"),
    ("DRUG_nitroglycerin",     "API_nitroglycerin"),
    ("DRUG_simvastatin",       "API_simvastatin"),
    ("DRUG_rosuvastatin",      "API_rosuvastatin_ca"),
    ("DRUG_enalapril",         "API_enalapril_maleate"),
    ("DRUG_ramipril",          "API_ramipril"),
    ("DRUG_nifedipine",        "API_nifedipine"),

    # 抗肿瘤
    ("DRUG_cyclophosphamide",  "API_cyclophosphamide"),
    ("DRUG_etoposide",         "API_etoposide"),
    ("DRUG_carboplatin",       "API_carboplatin"),
    ("DRUG_irinotecan",        "API_irinotecan_hcl"),
    ("DRUG_oxaliplatin",       "API_oxaliplatin"),
    ("DRUG_gemcitabine",       "API_gemcitabine_hcl"),
    ("DRUG_capecitabine",      "API_capecitabine"),
    ("DRUG_imatinib",          "API_imatinib_mesylate"),
    ("DRUG_tamoxifen",         "API_tamoxifen_citrate"),
    ("DRUG_leucovorin",        "API_leucovorin_ca"),
    ("DRUG_bleomycin",         "API_bleomycin_sulfate"),
    ("DRUG_dacarbazine",       "API_dacarbazine"),

    # 精神/神经
    ("DRUG_sertraline",        "API_sertraline_hcl"),
    ("DRUG_amitriptyline",     "API_amitriptyline_hcl"),
    ("DRUG_lithium",           "API_lithium_carbonate"),
    ("DRUG_clonazepam",        "API_clonazepam"),
    ("DRUG_valproic_acid",     "API_valproic_acid"),
    ("DRUG_levodopa",          "API_levodopa"),
    ("DRUG_levodopa",          "API_carbidopa"),
    ("DRUG_olanzapine",        "API_olanzapine"),
    ("DRUG_risperidone",       "API_risperidone"),
    ("DRUG_gabapentin",        "API_gabapentin"),
    ("DRUG_tramadol",          "API_tramadol_hcl"),

    # 抗病毒/寄生虫
    ("DRUG_tenofovir",         "API_tenofovir_df"),
    ("DRUG_lamivudine",        "API_lamivudine"),
    ("DRUG_efavirenz",         "API_efavirenz"),
    ("DRUG_atazanavir",        "API_atazanavir_sulfate"),
    ("DRUG_zidovudine",        "API_zidovudine"),
    ("DRUG_artemether_lumef",  "API_artemether"),
    ("DRUG_artemether_lumef",  "API_lumefantrine"),
    ("DRUG_quinine",           "API_quinine_sulfate"),
    ("DRUG_albendazole",       "API_albendazole"),
    ("DRUG_ivermectin",        "API_ivermectin"),
    ("DRUG_itraconazole",      "API_itraconazole"),

    # 其他
    ("DRUG_ranitidine",        "API_ranitidine_hcl"),
    ("DRUG_pantoprazole",      "API_pantoprazole_na"),
    ("DRUG_erythropoietin",    "API_erythropoietin"),
    ("DRUG_tranexamic_acid",   "API_tranexamic_acid"),
    ("DRUG_oxytocin",          "API_oxytocin"),
    ("DRUG_misoprostol",       "API_misoprostol"),
    ("DRUG_ketamine",          "API_ketamine_hcl"),
    ("DRUG_atropine",          "API_atropine_sulfate"),
    ("DRUG_epinephrine",       "API_epinephrine"),
    ("DRUG_dopamine",          "API_dopamine_hcl"),
    ("DRUG_norepinephrine",    "API_norepinephrine"),
    ("DRUG_calcium_gluconate", "API_calcium_gluconate"),
    ("DRUG_magnesium_sulfate", "API_magnesium_sulfate"),
    ("DRUG_glucose",           "API_sodium_chloride"),  # 输液类共享包装产线
    ("DRUG_hydrocortisone",    "API_hydrocortisone"),
    ("DRUG_methylprednisolone","API_methylprednisolone"),
    ("DRUG_insulin_glargine",  "API_insulin_glargine"),
    ("DRUG_sitagliptin",       "API_sitagliptin_phos"),
    ("DRUG_empagliflozin",     "API_empagliflozin"),
    ("DRUG_rituximab",         "API_erythropoietin"),   # 都是生物制品，共享供应链
    ("DRUG_trastuzumab",       "API_erythropoietin"),   # 生物制品
]
DRUG_API_MAP.extend(DRUG_API_MAP_EXPANSION)


# ---------- 新增供应关系 (API ← SUPPLIED_BY → Manufacturer) ----------
API_SUPPLIER_MAP_EXPANSION = [
    # --- 新增抗生素 API 供应关系 ---
    ("API_levofloxacin",       "MFG_dr_reddys"),
    ("API_levofloxacin",       "MFG_aurobindo"),
    ("API_levofloxacin",       "MFG_zhejiang_hisun"),
    ("API_meropenem_trihy",    "MFG_cspc"),
    ("API_meropenem_trihy",    "MFG_divi_labs"),
    ("API_meropenem_trihy",    "MFG_wockhardt"),
    ("API_imipenem",           "MFG_cspc"),
    ("API_imipenem",           "MFG_merck_msd"),
    ("API_cilastatin_na",      "MFG_cspc"),
    ("API_gentamicin_sulfate", "MFG_north_china"),
    ("API_gentamicin_sulfate", "MFG_fresenius_kabi"),
    ("API_clindamycin_hcl",    "MFG_aurobindo"),
    ("API_clindamycin_hcl",    "MFG_zydus"),
    ("API_trimethoprim",       "MFG_cipla"),
    ("API_trimethoprim",       "MFG_teva"),
    ("API_sulfamethoxazole",   "MFG_cipla"),
    ("API_sulfamethoxazole",   "MFG_aurobindo"),
    ("API_nitrofurantoin",     "MFG_sun_pharma"),
    ("API_nitrofurantoin",     "MFG_north_china"),
    ("API_colistimethate_na",  "MFG_north_china"),
    ("API_colistimethate_na",  "MFG_zhejiang_hisun"),
    ("API_linezolid",          "MFG_glenmark"),
    ("API_linezolid",          "MFG_cipla"),
    ("API_linezolid",          "MFG_hengrui"),
    ("API_rifampicin",         "MFG_lupin"),
    ("API_rifampicin",         "MFG_shandong_xinhua"),
    ("API_rifampicin",         "MFG_sandoz"),
    ("API_isoniazid",          "MFG_lupin"),
    ("API_isoniazid",          "MFG_north_china"),
    ("API_ethambutol_hcl",     "MFG_lupin"),
    ("API_ethambutol_hcl",     "MFG_cipla"),
    ("API_pyrazinamide",       "MFG_lupin"),
    ("API_pyrazinamide",       "MFG_north_china"),

    # --- 新增心血管 API 供应关系 ---
    ("API_valsartan",          "MFG_zhejiang_hisun"),
    ("API_valsartan",          "MFG_torrent"),
    ("API_valsartan",          "MFG_sandoz"),
    ("API_hydrochlorothiazide","MFG_aurobindo"),
    ("API_hydrochlorothiazide","MFG_teva"),
    ("API_furosemide",         "MFG_sun_pharma"),
    ("API_furosemide",         "MFG_fresenius_kabi"),
    ("API_furosemide",         "MFG_north_china"),
    ("API_spironolactone",     "MFG_cipla"),
    ("API_spironolactone",     "MFG_teva"),
    ("API_digoxin",            "MFG_gsk"),
    ("API_digoxin",            "MFG_recordati"),
    ("API_diltiazem_hcl",      "MFG_sun_pharma"),
    ("API_diltiazem_hcl",      "MFG_teva"),
    ("API_clopidogrel_bis",    "MFG_dr_reddys"),
    ("API_clopidogrel_bis",    "MFG_aurobindo"),
    ("API_clopidogrel_bis",    "MFG_sanofi"),
    ("API_enoxaparin_na",      "MFG_sanofi"),
    ("API_enoxaparin_na",      "MFG_sandoz"),
    ("API_enoxaparin_na",      "MFG_hepalink"),   # 猪源原料依赖
    ("API_nitroglycerin",      "MFG_mylan_viatris"),
    ("API_nitroglycerin",      "MFG_baxter"),
    ("API_simvastatin",        "MFG_dr_reddys"),
    ("API_simvastatin",        "MFG_aurobindo"),
    ("API_simvastatin",        "MFG_zhejiang_medi"),
    ("API_rosuvastatin_ca",    "MFG_cipla"),
    ("API_rosuvastatin_ca",    "MFG_zydus"),
    ("API_rosuvastatin_ca",    "MFG_astrazeneca"),
    ("API_enalapril_maleate",  "MFG_dr_reddys"),
    ("API_enalapril_maleate",  "MFG_teva"),
    ("API_ramipril",           "MFG_lupin"),
    ("API_ramipril",           "MFG_sanofi"),
    ("API_nifedipine",         "MFG_bayer"),
    ("API_nifedipine",         "MFG_cipla"),

    # --- 新增抗肿瘤 API 供应关系 ---
    ("API_cyclophosphamide",   "MFG_baxter"),
    ("API_cyclophosphamide",   "MFG_intas"),
    ("API_cyclophosphamide",   "MFG_hengrui"),
    ("API_etoposide",          "MFG_teva"),
    ("API_etoposide",          "MFG_cipla"),
    ("API_etoposide",          "MFG_fresenius_kabi"),
    ("API_carboplatin",        "MFG_teva"),
    ("API_carboplatin",        "MFG_fresenius_kabi"),
    ("API_carboplatin",        "MFG_hospira_pfizer"),
    ("API_irinotecan_hcl",     "MFG_sun_pharma"),
    ("API_irinotecan_hcl",     "MFG_fresenius_kabi"),
    ("API_irinotecan_hcl",     "MFG_hengrui"),
    ("API_oxaliplatin",        "MFG_sun_pharma"),
    ("API_oxaliplatin",        "MFG_teva"),
    ("API_oxaliplatin",        "MFG_hengrui"),
    ("API_gemcitabine_hcl",    "MFG_sun_pharma"),
    ("API_gemcitabine_hcl",    "MFG_cipla"),
    ("API_gemcitabine_hcl",    "MFG_hospira_pfizer"),
    ("API_capecitabine",       "MFG_cipla"),
    ("API_capecitabine",       "MFG_teva"),
    ("API_capecitabine",       "MFG_roche"),
    ("API_imatinib_mesylate",  "MFG_cipla"),
    ("API_imatinib_mesylate",  "MFG_sun_pharma"),
    ("API_imatinib_mesylate",  "MFG_sandoz"),
    ("API_tamoxifen_citrate",  "MFG_aurobindo"),
    ("API_tamoxifen_citrate",  "MFG_teva"),
    ("API_leucovorin_ca",      "MFG_hospira_pfizer"),
    ("API_leucovorin_ca",      "MFG_teva"),
    ("API_leucovorin_ca",      "MFG_fresenius_kabi"),
    ("API_bleomycin_sulfate",  "MFG_hospira_pfizer"),
    ("API_bleomycin_sulfate",  "MFG_cipla"),
    ("API_dacarbazine",        "MFG_fresenius_kabi"),
    ("API_dacarbazine",        "MFG_teva"),

    # --- 新增精神/神经 API 供应关系 ---
    ("API_sertraline_hcl",     "MFG_aurobindo"),
    ("API_sertraline_hcl",     "MFG_lupin"),
    ("API_sertraline_hcl",     "MFG_torrent"),
    ("API_amitriptyline_hcl",  "MFG_sun_pharma"),
    ("API_amitriptyline_hcl",  "MFG_teva"),
    ("API_lithium_carbonate",  "MFG_teva"),
    ("API_lithium_carbonate",  "MFG_apotex"),
    ("API_clonazepam",         "MFG_sun_pharma"),
    ("API_clonazepam",         "MFG_teva"),
    ("API_valproic_acid",      "MFG_sun_pharma"),
    ("API_valproic_acid",      "MFG_aurobindo"),
    ("API_valproic_acid",      "MFG_sanofi"),
    ("API_levodopa",           "MFG_north_china"),
    ("API_levodopa",           "MFG_divi_labs"),
    ("API_carbidopa",          "MFG_divi_labs"),
    ("API_carbidopa",          "MFG_north_china"),
    ("API_olanzapine",         "MFG_dr_reddys"),
    ("API_olanzapine",         "MFG_cipla"),
    ("API_olanzapine",         "MFG_teva"),
    ("API_risperidone",        "MFG_aurobindo"),
    ("API_risperidone",        "MFG_cipla"),
    ("API_risperidone",        "MFG_johnson_johnson"),
    ("API_gabapentin",         "MFG_aurobindo"),
    ("API_gabapentin",         "MFG_cipla"),
    ("API_gabapentin",         "MFG_glenmark"),
    ("API_tramadol_hcl",       "MFG_sun_pharma"),
    ("API_tramadol_hcl",       "MFG_aurobindo"),
    ("API_tramadol_hcl",       "MFG_stada"),

    # --- 新增抗HIV/抗疟/抗寄生虫 供应关系 ---
    ("API_tenofovir_df",       "MFG_cipla"),
    ("API_tenofovir_df",       "MFG_hetero"),
    ("API_tenofovir_df",       "MFG_gilead"),
    ("API_lamivudine",         "MFG_cipla"),
    ("API_lamivudine",         "MFG_hetero"),
    ("API_lamivudine",         "MFG_aurobindo"),
    ("API_efavirenz",          "MFG_cipla"),
    ("API_efavirenz",          "MFG_hetero"),
    ("API_efavirenz",          "MFG_laurus_labs"),
    ("API_atazanavir_sulfate", "MFG_cipla"),
    ("API_atazanavir_sulfate", "MFG_hetero"),
    ("API_atazanavir_sulfate", "MFG_bms"),
    ("API_zidovudine",         "MFG_cipla"),
    ("API_zidovudine",         "MFG_hetero"),
    ("API_zidovudine",         "MFG_aurobindo"),
    ("API_artemether",         "MFG_cipla"),
    ("API_artemether",         "MFG_kunshan_rotam"),
    ("API_artemether",         "MFG_fosun"),
    ("API_lumefantrine",       "MFG_cipla"),
    ("API_lumefantrine",       "MFG_zhejiang_hisun"),
    ("API_quinine_sulfate",    "MFG_shandong_xinhua"),
    ("API_quinine_sulfate",    "MFG_aspen"),
    ("API_albendazole",        "MFG_cipla"),
    ("API_albendazole",        "MFG_gsk"),
    ("API_ivermectin",         "MFG_merck_msd"),
    ("API_ivermectin",         "MFG_cipla"),
    ("API_ivermectin",         "MFG_north_china"),
    ("API_itraconazole",       "MFG_cipla"),
    ("API_itraconazole",       "MFG_glenmark"),
    ("API_itraconazole",       "MFG_johnson_johnson"),

    # --- 其他 ---
    ("API_pantoprazole_na",    "MFG_aurobindo"),
    ("API_pantoprazole_na",    "MFG_sun_pharma"),
    ("API_pantoprazole_na",    "MFG_zydus"),
    ("API_ranitidine_hcl",     "MFG_dr_reddys"),
    ("API_ranitidine_hcl",     "MFG_gsk"),
    ("API_erythropoietin",     "MFG_amgen"),
    ("API_erythropoietin",     "MFG_biocon"),
    ("API_erythropoietin",     "MFG_celltrion"),
    ("API_tranexamic_acid",    "MFG_daiichi_sankyo"),
    ("API_tranexamic_acid",    "MFG_fresenius_kabi"),
    ("API_oxytocin",           "MFG_sun_pharma"),
    ("API_oxytocin",           "MFG_fresenius_kabi"),
    ("API_misoprostol",        "MFG_cipla"),
    ("API_misoprostol",        "MFG_sun_pharma"),
    ("API_ketamine_hcl",       "MFG_hospira_pfizer"),
    ("API_ketamine_hcl",       "MFG_par_endo"),
    ("API_atropine_sulfate",   "MFG_fresenius_kabi"),
    ("API_atropine_sulfate",   "MFG_hospira_pfizer"),
    ("API_epinephrine",        "MFG_hospira_pfizer"),
    ("API_epinephrine",        "MFG_par_endo"),
    ("API_dopamine_hcl",       "MFG_hospira_pfizer"),
    ("API_dopamine_hcl",       "MFG_fresenius_kabi"),
    ("API_norepinephrine",     "MFG_hospira_pfizer"),
    ("API_norepinephrine",     "MFG_pfizer_centreone"),
    ("API_calcium_gluconate",  "MFG_fresenius_kabi"),
    ("API_calcium_gluconate",  "MFG_baxter"),
    ("API_magnesium_sulfate",  "MFG_fresenius_kabi"),
    ("API_magnesium_sulfate",  "MFG_baxter"),
    ("API_hydrocortisone",     "MFG_hospira_pfizer"),
    ("API_hydrocortisone",     "MFG_cipla"),
    ("API_methylprednisolone", "MFG_hospira_pfizer"),
    ("API_methylprednisolone", "MFG_sandoz"),
    ("API_insulin_glargine",   "MFG_sanofi"),
    ("API_insulin_glargine",   "MFG_biocon"),
    ("API_insulin_glargine",   "MFG_eli_lilly"),
    ("API_sitagliptin_phos",   "MFG_merck_msd"),
    ("API_empagliflozin",      "MFG_bayer"),   # Boehringer Ingelheim/Lilly 联合，BASF 合同制造
    ("API_empagliflozin",      "MFG_eli_lilly"),
]
API_SUPPLIER_MAP.extend(API_SUPPLIER_MAP_EXPANSION)


# ---------- 新增更多替代关系 ----------
API_SUBSTITUTES_EXPANSION = [
    # 碳青霉烯类可互替代
    ("API_meropenem_trihy",    "API_imipenem",          "direct"),
    # 他汀类可互替代
    ("API_atorvastatin_ca",    "API_simvastatin",       "direct"),
    ("API_simvastatin",        "API_rosuvastatin_ca",   "direct"),
    # ACE抑制剂互替代
    ("API_lisinopril_dihy",    "API_enalapril_maleate", "direct"),
    ("API_enalapril_maleate",  "API_ramipril",          "direct"),
    # ARB互替代
    ("API_losartan_k",         "API_valsartan",         "direct"),
    # 钙通道阻滞剂
    ("API_amlodipine_bes",     "API_nifedipine",        "direct"),
    ("API_amlodipine_bes",     "API_diltiazem_hcl",     "partial"),
    # 利尿剂
    ("API_furosemide",         "API_hydrochlorothiazide","partial"),
    # 铂类化疗
    ("API_cisplatin",          "API_carboplatin",       "direct"),
    ("API_carboplatin",        "API_oxaliplatin",       "partial"),
    # 抗代谢类
    ("API_fluorouracil",       "API_capecitabine",      "direct"),  # 口服5-FU前药
    ("API_gemcitabine_hcl",    "API_capecitabine",      "partial"),
    # SSRI互替代
    ("API_fluoxetine_hcl",     "API_sertraline_hcl",    "direct"),
    # 抗精神病药
    ("API_olanzapine",         "API_risperidone",       "direct"),
    ("API_haloperidol",        "API_olanzapine",        "partial"),
    # 抗癲痫
    ("API_valproic_acid",      "API_carbamazepine",     "partial"),
    ("API_gabapentin",         "API_valproic_acid",     "partial"),
    # 抗HIV NRTI
    ("API_tenofovir_df",       "API_zidovudine",        "partial"),
    ("API_lamivudine",         "API_zidovudine",        "partial"),
    # 抗疟
    ("API_artemether",         "API_quinine_sulfate",   "partial"),
    # 糖皮质激素
    ("API_hydrocortisone",     "API_dexamethasone",     "direct"),
    ("API_methylprednisolone", "API_dexamethasone",     "direct"),
    # PPI
    ("API_omeprazole",         "API_pantoprazole_na",   "direct"),
    # 抗凝
    ("API_heparin_na",         "API_enoxaparin_na",     "direct"),
    # 阿片类
    ("API_morphine_sulfate",   "API_tramadol_hcl",      "partial"),
    # 急救
    ("API_epinephrine",        "API_norepinephrine",    "partial"),
    # 胰岛素
    ("API_insulin_human",      "API_insulin_glargine",  "partial"),
]
API_SUBSTITUTES.extend(API_SUBSTITUTES_EXPANSION)


# ---------- 新增短缺事件 ----------
SHORTAGE_EVENTS_EXPANSION = [
    {"id": "SHORT_meropenem_2023",     "drug_id": "DRUG_meropenem",         "year": 2023, "duration_months": 5,
     "cause": "多家印度供应商GMP检查不通过", "severity": "critical",
     "impact": "ICU重症感染治疗方案受限，被迫使用替代碳青霉烯"},

    {"id": "SHORT_carboplatin_2023",   "drug_id": "DRUG_carboplatin",       "year": 2023, "duration_months": 8,
     "cause": "Intas Pharma被FDA停产+中国供应商产能不足", "severity": "critical",
     "impact": "与cisplatin同时短缺，癌症治疗面临严重危机"},

    {"id": "SHORT_etoposide_2023",     "drug_id": "DRUG_etoposide",         "year": 2023, "duration_months": 6,
     "cause": "全球API供应集中度过高，单点故障", "severity": "major",
     "impact": "小细胞肺癌和睾丸癌化疗方案受影响"},

    {"id": "SHORT_furosemide_2022",    "drug_id": "DRUG_furosemide",        "year": 2022, "duration_months": 4,
     "cause": "包装瓶供应链中断+生产延迟", "severity": "moderate",
     "impact": "心衰和肝硬化腹水患者利尿治疗受影响"},

    {"id": "SHORT_clopidogrel_2020",   "drug_id": "DRUG_clopidogrel",       "year": 2020, "duration_months": 3,
     "cause": "印度封城导致API出口中断", "severity": "major",
     "impact": "心脏支架术后双抗治疗面临中断风险"},

    {"id": "SHORT_epinephrine_2018",   "drug_id": "DRUG_epinephrine",       "year": 2018, "duration_months": 10,
     "cause": "Pfizer/Meridian工厂生产问题+需求增长", "severity": "critical",
     "impact": "过敏性休克自救笔(EpiPen)价格暴涨，患者无药可用"},

    {"id": "SHORT_norepinephrine_2022","drug_id": "DRUG_norepinephrine",    "year": 2022, "duration_months": 5,
     "cause": "Pfizer工厂产能受限", "severity": "critical",
     "impact": "ICU感染性休克一线升压药供应不足"},

    {"id": "SHORT_ketamine_2023",      "drug_id": "DRUG_ketamine",          "year": 2023, "duration_months": 4,
     "cause": "管制药品配额限制+需求增长(抑郁症新适应症)", "severity": "moderate",
     "impact": "急诊麻醉和难治性抑郁症治疗受影响"},

    {"id": "SHORT_oxaliplatin_2023",   "drug_id": "DRUG_oxaliplatin",       "year": 2023, "duration_months": 7,
     "cause": "铂类化疗药集中短缺，API全球供应不足", "severity": "major",
     "impact": "结直肠癌FOLFOX方案无法正常执行"},

    {"id": "SHORT_bleomycin_2017",     "drug_id": "DRUG_bleomycin",         "year": 2017, "duration_months": 12,
     "cause": "唯一API供应商停产", "severity": "critical",
     "impact": "霍奇金淋巴瘤ABVD方案被迫省去B，影响治愈率"},

    {"id": "SHORT_irinotecan_2021",    "drug_id": "DRUG_irinotecan",        "year": 2021, "duration_months": 3,
     "cause": "原料药质量问题+产能调整", "severity": "moderate",
     "impact": "结直肠癌FOLFIRI方案延迟"},

    {"id": "SHORT_ranitidine_2019",    "drug_id": "DRUG_ranitidine",        "year": 2019, "duration_months": 24,
     "cause": "NDMA致癌物污染，全球永久召回", "severity": "critical",
     "impact": "雷尼替丁从全球市场撤出，数亿患者转用PPI"},

    {"id": "SHORT_valsartan_2018",     "drug_id": "DRUG_valsartan",         "year": 2018, "duration_months": 14,
     "cause": "中国华海药业API中发现NDMA，全球召回", "severity": "critical",
     "impact": "缬沙坦/氯沙坦/厄贝沙坦三个ARB类药全面短缺"},

    {"id": "SHORT_tenofovir_2020",     "drug_id": "DRUG_tenofovir",         "year": 2020, "duration_months": 4,
     "cause": "印度封城影响API出口+物流中断", "severity": "major",
     "impact": "HIV/HBV治疗面临中断风险，非洲尤为严重"},

    {"id": "SHORT_artemether_2020",    "drug_id": "DRUG_artemether_lumef",   "year": 2020, "duration_months": 6,
     "cause": "青蒿素原料(Artemisia annua)种植受气候影响+物流中断", "severity": "critical",
     "impact": "非洲疟疾治疗一线药ACT短缺，WHO紧急协调"},

    {"id": "SHORT_oxytocin_2020",      "drug_id": "DRUG_oxytocin",          "year": 2020, "duration_months": 3,
     "cause": "冷链物流中断+需求波动", "severity": "major",
     "impact": "产后出血预防用药受影响，发展中国家受灾最重"},

    {"id": "SHORT_atropine_2023",      "drug_id": "DRUG_atropine",          "year": 2023, "duration_months": 4,
     "cause": "API供应集中+生产线调整", "severity": "moderate",
     "impact": "急诊心动过缓和有机磷中毒救治受影响"},

    {"id": "SHORT_leucovorin_2023",    "drug_id": "DRUG_leucovorin",        "year": 2023, "duration_months": 5,
     "cause": "与cisplatin/carboplatin同期短缺，化疗支持药供应不足", "severity": "major",
     "impact": "FOLFOX/FOLFIRI方案中的亚叶酸钙解救无法保障"},

    {"id": "SHORT_gemcitabine_2023",   "drug_id": "DRUG_gemcitabine",       "year": 2023, "duration_months": 4,
     "cause": "全球抗肿瘤药系统性短缺的一部分", "severity": "major",
     "impact": "胰腺癌一线治疗方案受影响"},
]
SHORTAGE_EVENTS.extend(SHORTAGE_EVENTS_EXPANSION)


# ---------- 新增更多药物相互作用 ----------
DRUG_INTERACTIONS_EXPANSION = [
    # 新增药品之间的相互作用
    ("DRUG_meropenem",     "DRUG_valproic_acid",    "major",    "美罗培南大幅降低丙戊酸血药浓度，癲疗发作风险"),
    ("DRUG_rifampicin",    "DRUG_warfarin",         "major",    "利福平强效诱导CYP2C9/3A4，显著降低华法林效果"),
    ("DRUG_rifampicin",    "DRUG_metformin",        "moderate", "利福平诱导代谢，可能影响二甲双胍血药浓度"),
    ("DRUG_rifampicin",    "DRUG_imatinib",         "major",    "利福平诱导CYP3A4，大幅降低伊马替尼浓度"),
    ("DRUG_isoniazid",     "DRUG_phenytoin",        "major",    "异烟肼抑制CYP2C19，升高苯妥英浓度致中毒"),
    ("DRUG_isoniazid",     "DRUG_carbamazepine",    "major",    "异烟肼抑制CYP3A4，升高卡马西平浓度"),
    ("DRUG_clopidogrel",   "DRUG_omeprazole",       "major",    "奥美拉唑抑制CYP2C19，降低氯吡格雷活性代谢物"),
    ("DRUG_clopidogrel",   "DRUG_warfarin",         "major",    "双重抗栓，出血风险显著增加"),
    ("DRUG_digoxin",       "DRUG_amiodarone",       "major",    "胺碘酮升高地高辛浓度，心律失常风险"),
    ("DRUG_digoxin",       "DRUG_furosemide",       "major",    "呋塞米致低钾，增加地高辛中毒风险"),
    ("DRUG_digoxin",       "DRUG_spironolactone",   "moderate", "螺内酯可能升高地高辛浓度"),
    ("DRUG_simvastatin",   "DRUG_fluconazole",      "major",    "氟康唑抑制CYP3A4，升高辛伐他汀浓度，横纹肌溶解风险"),
    ("DRUG_enoxaparin",    "DRUG_ibuprofen",        "major",    "NSAIDs+低分子肝素，出血风险显著增加"),
    ("DRUG_diltiazem",     "DRUG_metoprolol",       "major",    "联用致严重心动过缓和传导阻滞"),
    ("DRUG_gabapentin",    "DRUG_morphine",         "major",    "加巴喷丁+阿片类增强呼吸抑制"),
    ("DRUG_tramadol",      "DRUG_fluoxetine",       "major",    "血清素综合征风险+CYP2D6抑制降低镇痛效果"),
    ("DRUG_tramadol",      "DRUG_sertraline",       "major",    "血清素综合征风险"),
    ("DRUG_olanzapine",    "DRUG_diazepam",         "major",    "联用增强中枢抑制和呼吸抑制"),
    ("DRUG_lithium",       "DRUG_ibuprofen",        "major",    "NSAIDs减少锂排泄，可致锂中毒"),
    ("DRUG_lithium",       "DRUG_furosemide",       "major",    "利尿剂增加锂重吸收，升高锂浓度"),
    ("DRUG_cyclophosphamide","DRUG_methotrexate",   "major",    "联用增加骨髓抑制和免疫抑制"),
    ("DRUG_oxaliplatin",   "DRUG_fluorouracil",     "moderate", "FOLFOX标准联合方案，但需监测神经毒性"),
    ("DRUG_irinotecan",    "DRUG_fluorouracil",     "moderate", "FOLFIRI标准联合方案，需监测腹泻"),
    ("DRUG_carboplatin",   "DRUG_paclitaxel",       "moderate", "标准联合方案，先紫杉醇后卡铂减少血小板毒性"),
    ("DRUG_tamoxifen",     "DRUG_fluoxetine",       "major",    "氟西汀抑制CYP2D6，降低他莫昔芬活性代谢物"),
    ("DRUG_tamoxifen",     "DRUG_warfarin",         "major",    "他莫昔芬增强华法林抗凝效果"),
    ("DRUG_metformin",     "DRUG_furosemide",       "moderate", "呋塞米可能升高血糖，拮抗二甲双胍"),
    ("DRUG_epinephrine",   "DRUG_metoprolol",       "major",    "β受体阻滞剂拮抗肾上腺素效果，可致高血压危象"),
    ("DRUG_nitroglycerin", "DRUG_heparin",          "moderate", "硝酸甘油可能降低肝素抗凝效果需监测"),
    ("DRUG_spironolactone","DRUG_lisinopril",       "major",    "双重保钾效应，高钾血症风险"),
    ("DRUG_ivermectin",    "DRUG_warfarin",         "moderate", "伊维菌素可能增强华法林抗凝效果"),
    ("DRUG_albendazole",   "DRUG_carbamazepine",    "moderate", "卡马西平降低阿苯达唑活性代谢物浓度"),
]
DRUG_INTERACTIONS.extend(DRUG_INTERACTIONS_EXPANSION)


# ---------- 新增监管法规 ----------
REGULATIONS_EXPANSION = [
    {"id": "REG_nmpa_gmp",          "name": "NMPA GMP (中国药品GMP)",     "authority": "NMPA",
     "description": "中国国家药品监督管理局药品生产质量管理规范"},
    {"id": "REG_pmda_gmp",          "name": "PMDA GMP (日本医药品GMP)",    "authority": "PMDA",
     "description": "日本医药品医疗器材综合机构的GMP标准"},
    {"id": "REG_who_pq",            "name": "WHO Prequalification Programme", "authority": "WHO",
     "description": "WHO药品预认证计划，确保发展中国家药品质量"},
    {"id": "REG_ich_q7",            "name": "ICH Q7 (GMP for APIs)",       "authority": "ICH",
     "description": "API生产的国际协调GMP指南"},
    {"id": "REG_ich_q9",            "name": "ICH Q9 Quality Risk Management", "authority": "ICH",
     "description": "质量风险管理指南"},
    {"id": "REG_ich_q10",           "name": "ICH Q10 Pharmaceutical Quality System", "authority": "ICH",
     "description": "药品质量体系指南"},
    {"id": "REG_dea_schedule",      "name": "DEA Controlled Substances Act", "authority": "DEA",
     "description": "美国管制药品法规，限制阿片类、苯二氮卓类等药品的生产配额"},
    {"id": "REG_pics_gmp",          "name": "PIC/S GMP Guide",            "authority": "PIC/S",
     "description": "药品检查合作计划的GMP检查指南"},
]
REGULATIONS.extend(REGULATIONS_EXPANSION)
