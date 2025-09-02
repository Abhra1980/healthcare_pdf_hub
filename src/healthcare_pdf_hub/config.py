import os
from pathlib import Path
from typing import Dict 
#pdf_dir = Path("./medical_report")

# ABS_DEFAULTS = {
#     "medical":  Path(r"C:\Data Science\Healthcare-PDF-Hub-Modular\src\healthcare_pdf_hub\medical_report"),
#     "medicine": Path(r"C:\Data Science\Healthcare-PDF-Hub-Modular\src\healthcare_pdf_hub\medicine"),
#     "hospital": Path(r"C:\Data Science\Healthcare-PDF-Hub-Modular\src\healthcare_pdf_hub\hospital"),
# }

ABS_DEFAULTS = {
    "medical":  Path("./src/healthcare_pdf_hub/medical_report"),
    "medicine": Path("./src/healthcare_pdf_hub/medicine"),
    "hospital": Path("./src/healthcare_pdf_hub/hospital"),
}

REL_FALLBACKS = {
    "medical":  Path("./medical_report"),
    "medicine": Path("./medicine"),
    "hospital": Path("./hospital"),
}

def choose_resource_dirs() -> Dict[str, Path]:
    """
    Resolves the resource folders in this order:
      1) Environment variables HPDFHUB_* if set
      2) Absolute Windows defaults (as requested)
      3) Relative fallbacks under project root
    """
    med_env  = os.getenv("HPDFHUB_MEDICAL_DIR")
    medi_env = os.getenv("HPDFHUB_MEDICINE_DIR")
    hosp_env = os.getenv("HPDFHUB_HOSPITAL_DIR")

    dirs = {
        "medical":  Path(med_env)  if med_env  else ABS_DEFAULTS["medical"],
        "medicine": Path(medi_env) if medi_env else ABS_DEFAULTS["medicine"],
        "hospital": Path(hosp_env) if hosp_env else ABS_DEFAULTS["hospital"],
    }

    # If any doesn't exist, fallback to relative if available
    for key, p in list(dirs.items()):
        if not p.exists() and REL_FALLBACKS[key].exists():
            dirs[key] = REL_FALLBACKS[key]

    return dirs

