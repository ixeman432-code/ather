"""
Athar Hadith KB
Source: approved project Excel workbook.
The workbook is read once when this module starts.
"""

from pathlib import Path
import random
import openpyxl

EXCEL_PATH = Path(__file__).resolve().parents[1] / "data" / "raw" / "hadith_data.xlsx"

RESULT_MAP = {
"excellent": "ثناء",
"neutral": "تشجيع",
"poor": "تنبيه لطيف",
}

HADITHS = []

def _load_hadiths():
if not EXCEL_PATH.exists():
return []

wb = openpyxl.load_workbook(EXCEL_PATH, read_only=True, data_only=True)
ws = wb[wb.sheetnames[0]]

rows = ws.iter_rows(values_only=True)
headers = next(rows, None)
if not headers:
return []

headers = [str(x).strip() if x is not None else "" for x in headers]
data = []

for values in rows:
row = dict(zip(headers, values))
if str(row.get("معتمد؟") or "").strip() != "نعم":
continue

text = str(row.get("نص العرض") or "").strip()
source = str(row.get("رابط المصدر") or "").strip()
if not text or not source:
continue

target_age = row.get("العمر المستهدف")
try:
target_age = int(float(target_age))
except (TypeError, ValueError):
continue

data.append({
"id": str(row.get("رقم الحديث") or "").strip(),
"value": str(row.get("القيمة") or "").strip(),
"text": text,
"source": source,
"text_en": str(row.get("الترجمة الإنجليزية") or "").strip(),
"tone": str(row.get("النبرة") or "").strip(),
"age_target": target_age,
"approved_en": (
str(row.get("ترجمة معتمدة") or "").strip() == "نعم"
if "ترجمة معتمدة" in headers
else False
),
})

wb.close()
return data

HADITHS = _load_hadiths()

def get_hadith_pool(classification, child_age, language="ar"):
"""
Return suitable approved hadiths.

Age 4-9 -> Excel target age 9
Age 10-12 -> Excel target age 10

English is returned only when the workbook contains an explicitly
approved English translation. The current workbook has no such
approved-translation column, so English currently returns [].
"""
result = RESULT_MAP.get(classification)
if not result:
return []

try:
age = int(child_age)
except (TypeError, ValueError):
return []

target_age = 9 if age <= 9 else 10 if age <= 12 else None
if target_age is None:
return []

if language == "en":
return [
h for h in HADITHS
if h["tone"] == result
and h["age_target"] == target_age
and h["approved_en"]
and h["text_en"]
]

return [
h for h in HADITHS
if h["tone"] == result
and h["age_target"] == target_age
]
