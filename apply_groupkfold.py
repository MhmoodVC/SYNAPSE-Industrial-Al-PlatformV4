from pathlib import Path
import re

for file_path in ["scripts/train_pipeline.py", "src/evaluation/audit_report.py"]:
    p = Path(file_path)
    if not p.exists():
        continue
    content = p.read_text(encoding="utf-8")
    
    # 1. ???? ??????? GroupKFold
    if "GroupKFold" not in content:
        content = re.sub(r"from sklearn\.model_selection import ([^\n]+)", 
                         r"from sklearn.model_selection import \1, GroupKFold", content)
    
    # 2. ??????? ??????? cross_val_predict ???????? GroupKFold ???????? run_id
    # ??? ??? ???? ??? run (?????? run_id ?? run)
    target_cv = "cv=GroupKFold(n_splits=3), groups=train_df['run_id']" if "train_df" in content else "cv=GroupKFold(n_splits=3), groups=df['run_id']"
    
    content = re.sub(r"cv=\s*3", target_cv, content)
    content = re.sub(r"cv=StratifiedKFold\([^\)]+\)", target_cv, content)
    
    p.write_text(content, encoding="utf-8")
    print(f"Updated {file_path} with GroupKFold protocol.")
