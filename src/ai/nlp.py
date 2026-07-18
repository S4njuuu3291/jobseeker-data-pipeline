import os
import re
import json
import time
import httpx
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# ============================================
# HTTP Client (abaikan proxy)
# ============================================
http_client = httpx.Client(
    trust_env=False,
    timeout=httpx.Timeout(120.0)  # timeout lebih besar
)

client = OpenAI(
    api_key=os.environ.get("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com",
    http_client=http_client,
)

# ============================================
# PILIH MODEL YANG LEBIH STABIL
# ============================================
# deepseek-v4-flash → cepat tapi rawan error JSON
# deepseek-chat    → DeepSeek-V3, lebih stabil untuk structured output
# deepseek-reasoner → DeepSeek-R1, paling akurat tapi lebih lambat
MODEL_NAME = "deepseek-chat"  # ganti ke "deepseek-reasoner" jika butuh akurasi maksimal


# ============================================
# FILTER JOB (IT vs Non-IT) - TIDAK BERUBAH
# ============================================
SYSTEM_PROMPT_FILTER = """
Klasifikasikan judul ke IT (true) atau non-IT (false).
Output HARUS berupa JSON valid dengan format: {"is_it": true/false}
Jangan tambahkan teks lain selain JSON.
"""

IT_PATTERN = re.compile(
    r'\b('
    r'data|software|devops|cloud|security|network|system|database|'
    r'ai|ml|bi|it|'
    r'etl|backend|frontend|fullstack|full-stack|'
    r'engineering|engineer|developer|architect|'
    r'scientist|'
    r'site reliability|sre|infrastructure|platform|devsecops|'
    r'kafka|test|qa|automation|product owner'
    r')\b', 
    re.I
)

NON_IT_INDICATORS = [
    "management", "supervisor", "internship", "staff", "officer", 
    "coordinator", "sales", "marketing", "finance", "accounting", 
    "hr", "recruitment", "logistic", "production", "quality assurance",
    "business development", "continuity", "operational risk", "total rewards",
    "store inventory", "account manager", "banking", "loan", 
    "processing", "continuity management"
]

def filter_job(title: str) -> bool:
    if IT_PATTERN.search(title):
        return True

    for attempt in range(2):
        try:
            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT_FILTER},
                    {"role": "user", "content": f"Judul: {title}"}
                ],
                temperature=0.1,
                max_tokens=50,
                response_format={"type": "json_object"}
            )
            content = response.choices[0].message.content
            if content and content.strip():
                result = json.loads(content)
                return result.get("is_it", False)
            else:
                print(f"⚠️  Response kosong untuk '{title}', retry {attempt+1}/2")
                time.sleep(0.5)
        except Exception as e:
            print(f"⚠️  AI error untuk '{title}': {e}")
            time.sleep(0.5)
    
    title_lower = title.lower()
    fallback_it = any(kw in title_lower for kw in ["engineer", "developer", "architect", "scientist", "analyst"])
    if any(kw in title_lower for kw in NON_IT_INDICATORS):
        fallback_it = False
    print(f"⚠️  Fallback untuk '{title}': {fallback_it}")
    return fallback_it


# ============================================
# SCHEMA DEFINISI
# ============================================
full_data_schema = {
    "job_id": str,
    "job_title": str,
    "role": str,           # 👈 TAMBAH
    "company_name": str,
    "location": str,
    "salary_min": int,
    "salary_max": int,
    "salary_currency": str,
    "salary_period": str,
    "job_type": str,
    "seniority": str,
    "work_mode": str,
    "experience_min": int,
    "experience_max": int,
    "education": str,
    "company_industry": str,
    "skills": list,
    "benefits": list,
    "posting_date": str,
    "scraped_at": str,
    "job_url": str,
    "platform": str,
    "keyword": str,
    "job_description": str,
}

data_schema_ai = {
    "job_title": str,          # Judul asli dari card
    "role": str,               # 👈 TAMBAH: Peran inti (tanpa senior/junior)
                               # Ambil dari job_title, buang kata: Senior, Junior, Lead, Staff,
                               # Principal, Associate, Intern, Magang, L2, L1, Sr., Jr., dll.
                               # Contoh: "Senior Data Engineer" -> "Data Engineer"
                               #         "Junior Big Data Engineer" -> "Big Data Engineer"
                               #         "ETL Developer" -> "ETL Developer"
    "company_name": str,
    "location": str,
    "salary_min": int,
    "salary_max": int,
    "salary_currency": str,
    "salary_period": str,
    "job_type": str,
    "seniority": str,
    "work_mode": str,
    "experience_min": int,
    "experience_max": int,
    "education": str,
    "company_industry": str,
    "skills": list,
    "benefits": list,
    "posting_date": str,
}

# ============================================
# SISTEM PROMPT (diperkuat) - DOUBLE CURLY BRACES!
# ============================================
current_date = time.strftime("%Y-%m-%d")

SYSTEM_PROMPT_PARSE = """Anda adalah parser data lowongan kerja.
Ekstrak informasi dari job description dan kembalikan JSON valid dengan schema berikut.

Tanggal saat ini: {current_date} (digunakan untuk posting_date jika tidak ada tanggal di job description, atau lakukan pengurangan tanggal jika tanggal menggunakan format: "4 hari yang lalu", "2 minggu yang lalu", dll).

PERINGATAN: HANYA KEMBALIKAN JSON TANPA TEKS LAIN. PASTIKAN STRING TERTUTUP DENGAN KUTIP DUA (").

{{
    "job_title": str,          # Judul lowongan lengkap dari card. Default: "Unknown"
    "role": str,               # Peran inti. Ambil dari job_title, buang kata-kata senioritas:
                               # Senior, Junior, Lead, Staff, Principal, Associate, Intern,
                               # Magang, L1, L2, Sr., Jr., dll.
                               # Contoh: "Senior Data Engineer" -> "Data Engineer"
                               #         "Junior Big Data Engineer" -> "Big Data Engineer"
                               #         "ETL Developer" -> "ETL Developer"
                               #         "Data Analyst" -> "Data Analyst"
                               # Default: "Unknown"
    "company_name": str,       # Nama perusahaan. Default: "Unknown"
    "location": str,           # Format: "City" (use universal name) atau "Remote". Default: "Unknown"
    "salary_min": int,         # Angka bulat. Jika tidak ada: 0
    "salary_max": int,         # Angka bulat. Jika hanya satu angka, gunakan sama. Jika tidak ada: 0
    "salary_currency": str,    # enum: "IDR" / "USD" / "SGD" / "MYR" / "EUR" / "PHP" / "THB". Default: "IDR"
    "salary_period": str,      # enum: "monthly" / "yearly" / "hourly" / "daily" / "weekly". Default: "monthly"
    "job_type": str,           # enum: "full_time" / "part_time" / "contract" / "internship" / "freelance"
    "seniority": str,          # enum: "intern" / "junior" / "mid" / "senior" / "lead" / "manager" / "executive"
    "work_mode": str,          # enum: "remote" / "hybrid" / "on_site". Default: "unknown"
    "experience_min": int,     # Tahun pengalaman minimal. Default: 0
    "experience_max": int,     # Tahun pengalaman maksimal. Default: 0
    "education": str,          # enum: "high_school" / "diploma" / "bachelor" / "master" / "phd". Default: "unknown"
    "company_industry": str,   # Bebas, misal: "Financial Services", "Technology". Default: "Unknown"
    "skills": list,            # array of strings. Default: []
    "benefits": list,          # array of strings. Default: []
    "posting_date": str        # ISO 8601 (YYYY-MM-DD). Default: hari ini
}}

Kembalikan JSON valid, tanpa teks lain.""".format(current_date=current_date)


# ============================================
# FUNGSI REPAIR JSON (otomatis)
# ============================================
def repair_and_parse_json(raw: str) -> dict:
    """Mencoba memperbaiki JSON yang rusak/terpotong."""
    if not raw or not raw.strip():
        return {}

    # 1. Hapus markdown code block
    cleaned = re.sub(r'```json\s*', '', raw)
    cleaned = re.sub(r'```\s*', '', cleaned)
    cleaned = cleaned.strip()

    # 2. Coba pakai json_repair library (jika terinstall)
    try:
        from json_repair import repair_json
        repaired = repair_json(cleaned)
        return json.loads(repaired)
    except ImportError:
        pass  # library tidak terinstall, lanjut ke fallback
    except Exception:
        pass

    # 3. Fallback 1: cari JSON dengan regex (ambil dari { sampai })
    match = re.search(r'\{.*\}', cleaned, re.DOTALL)
    if match:
        candidate = match.group()
        try:
            # coba parse langsung
            return json.loads(candidate)
        except json.JSONDecodeError:
            # coba perbaiki secara manual: tambahkan kutip hilang, dll
            try:
                # hapus trailing comma sebelum }
                candidate = re.sub(r',\s*\}', '}', candidate)
                # hapus trailing comma sebelum ]
                candidate = re.sub(r',\s*\]', ']', candidate)
                # perbaiki string yang tidak tertutup (kasus umum)
                candidate = re.sub(r'([^\\])"([^"]*)$', r'\1"\2"', candidate)
                return json.loads(candidate)
            except:
                pass

    # 4. Fallback terakhir: return empty
    return {}


# ============================================
# FUNGSI UTAMA PARSE_JOB (dengan retry & backoff)
# ============================================
def parse_job(
    job_title: str,
    job_description: str,
    job_url: str = "",
    keyword: str = "",
) -> dict:
    """
    Parse job description menggunakan AI, kembalikan dict sesuai data_schema_ai.

    NOTE: company_name TIDAK perlu di-pass dari luar — AI akan extract
    langsung dari job_description (nama perusahaan biasanya ada di header card).
    """
    default = {
        "job_title": job_title or "Unknown",
        "role": "Unknown",  # 👈 TAMBAH default
        "company_name": "Unknown",
        "location": "Unknown",
        "salary_min": 0,
        "salary_max": 0,
        "salary_currency": "IDR",
        "salary_period": "monthly",
        "job_type": "full_time",
        "seniority": "mid",
        "work_mode": "unknown",
        "experience_min": 0,
        "experience_max": 0,
        "education": "unknown",
        "company_industry": "Unknown",
        "skills": [],
        "benefits": [],
        "posting_date": time.strftime("%Y-%m-%d"),
    }

    desc_trimmed = job_description[:6000] if job_description else ""  # potong lebih panjang

    if not desc_trimmed.strip():
        print(f"⚠️  Job description kosong untuk '{job_title}', pakai default")
        return default

    max_retries = 3
    backoff_seconds = [1, 2, 4]  # exponential backoff

    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=MODEL_NAME,  # pakai model stabil
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT_PARSE},
                    {
                        "role": "user",
                        "content": (
                            f"Job Title: {job_title}\n"
                            f"Job URL: {job_url}\n"
                            f"Keyword: {keyword}\n\n"
                            f"Job Description:\n{desc_trimmed}"
                        ),
                    },
                ],
                temperature=0.1,
                max_tokens=2000,  # dinaikkan agar JSON tidak terpotong
                response_format={"type": "json_object"},
            )

            content = response.choices[0].message.content

            if not content or not content.strip():
                print(f"⚠️  Response kosong untuk '{job_title}', retry {attempt+1}/{max_retries}")
                time.sleep(backoff_seconds[attempt] if attempt < len(backoff_seconds) else 3)
                continue

            # 🔧 Repair JSON
            parsed = repair_and_parse_json(content)

            if parsed:
                # Merge dengan default
                merged = {**default, **parsed}
                # Pastikan job_title dari argumen tetap dipakai
                merged["job_title"] = job_title or merged.get("job_title", "Unknown")
                
                # 🔥 NORMALISASI ROLE: pastikan gak kosong
                if not merged.get("role") or merged["role"] == "Unknown":
                    # Fallback: ambil dari job_title
                    merged["role"] = normalize_role_from_title(job_title)
                
                if not merged.get("posting_date"):
                    merged["posting_date"] = time.strftime("%Y-%m-%d")
                return merged
            else:
                print(f"⚠️  Gagal repair JSON untuk '{job_title}', retry {attempt+1}/{max_retries}")
                time.sleep(backoff_seconds[attempt] if attempt < len(backoff_seconds) else 3)

        except Exception as e:
            print(f"⚠️  Parse AI error untuk '{job_title}': {e}, retry {attempt+1}/{max_retries}")
            time.sleep(backoff_seconds[attempt] if attempt < len(backoff_seconds) else 3)

    # ⚠️ Fallback terakhir: coba ekstrak informasi penting pakai regex
    print(f"⚠️  Fallback total untuk '{job_title}', coba regex minimal...")
    fallback_result = default.copy()
    fallback_result["job_title"] = job_title or "Unknown"
    fallback_result["company_name"] = "Unknown"
    fallback_result["role"] = normalize_role_from_title(job_title)  # 👈 TAMBAH

    # Regex sederhana untuk gaji (contoh: Rp9.000.000 - 13.000.000)
    salary_pattern = re.compile(r'Rp\s*([\d.,]+)\s*[-–]\s*([\d.,]+)', re.I)
    match = salary_pattern.search(job_description)
    if match:
        try:
            min_sal = int(re.sub(r'[.,]', '', match.group(1)))
            max_sal = int(re.sub(r'[.,]', '', match.group(2)))
            fallback_result["salary_min"] = min_sal
            fallback_result["salary_max"] = max_sal
            fallback_result["salary_currency"] = "IDR"
            fallback_result["salary_period"] = "monthly"
        except:
            pass

    # Regex untuk lokasi (cari kata "Jakarta", "Bekasi", dll)
    loc_pattern = re.compile(r'(Jakarta|Bekasi|Tangerang|Depok|Bandung|Surabaya|Yogyakarta|Semarang|Medan)', re.I)
    loc_match = loc_pattern.search(job_description)
    if loc_match:
        fallback_result["location"] = loc_match.group(1) + ", Indonesia"

    # Regex untuk pengalaman (3-5 tahun)
    exp_pattern = re.compile(r'(\d+)\s*[-–]\s*(\d+)\s*tahun')
    exp_match = exp_pattern.search(job_description)
    if exp_match:
        fallback_result["experience_min"] = int(exp_match.group(1))
        fallback_result["experience_max"] = int(exp_match.group(2))

    # Regex untuk skills (ambil dari bagian Skills:)
    skills_section = re.search(r'Skills\s*([\s\S]*?)(?=\n\n|\n[A-Z]|$)', job_description, re.I)
    if skills_section:
        raw_skills = skills_section.group(1)
        skills_list = re.findall(r'\b([A-Za-z0-9+#.]+(?:\s+[A-Za-z0-9+#.]+){0,2})\b', raw_skills)
        fallback_result["skills"] = [s.strip() for s in skills_list if len(s.strip()) > 1][:15]

    # Regex untuk job type
    if "kontrak" in job_description.lower():
        fallback_result["job_type"] = "contract"
    elif "full time" in job_description.lower() or "penuh waktu" in job_description.lower():
        fallback_result["job_type"] = "full_time"
    elif "part time" in job_description.lower() or "paruh waktu" in job_description.lower():
        fallback_result["job_type"] = "part_time"

    # Regex untuk work_mode
    if "remote" in job_description.lower():
        fallback_result["work_mode"] = "remote"
    elif "hybrid" in job_description.lower():
        fallback_result["work_mode"] = "hybrid"
    elif "lokasi" in job_description.lower() or "on site" in job_description.lower():
        fallback_result["work_mode"] = "on_site"

    return fallback_result


# ============================================
# 🆕 FUNGSI NORMALISASI ROLE
# ============================================
def normalize_role_from_title(title: str) -> str:
    """
    Ekstrak role inti dari job title (hilangkan senioritas).
    Contoh: "Senior Data Engineer" -> "Data Engineer"
            "Junior Big Data Engineer" -> "Big Data Engineer"
            "ETL Developer" -> "ETL Developer"
    """
    if not title or title == "Unknown":
        return "Unknown"
    
    # 1. Hapus kata-kata senioritas
    seniority_words = [
        "senior", "jr", "jr.", "junior", "mid", "middle", 
        "lead", "staff", "principal", "associate", "assistant",
        "intern", "magang", "l1", "l2", "l3", "sr", "sr.",
        "entry", "fresh", "graduate", "trainee", "apprentice",
        "manager", "executive", "vp", "director", "head"
    ]
    
    # Split title, filter kata-kata senioritas
    words = title.split()
    role_words = []
    for w in words:
        # Hapus tanda baca di akhir kata
        clean_w = re.sub(r'[^\w\s]', '', w).lower()
        if clean_w not in seniority_words:
            role_words.append(w)
    
    # Gabungkan kembali
    role = " ".join(role_words).strip()
    
    # 2. Kalau hasilnya kosong, coba ambil 2 kata pertama
    if not role or role == "Unknown":
        words = title.split()
        if len(words) >= 2:
            role = " ".join(words[:2])
        elif len(words) == 1:
            role = words[0]
        else:
            role = "Unknown"
    
    # 3. Bersihkan dari kata-kata yang tersisa
    role = re.sub(r'\(.*?\)', '', role).strip()
    role = re.sub(r'[^\w\s\-]', '', role).strip()
    
    return role


# ============================================
# TEST
# ============================================
if __name__ == "__main__":
    job_content = ["""
        Middle Data EngineerCeleratesRp10.000.000 - 13.000.000/BulanKomputer & Perangkat Lunak lokasi di tangsel. Data EngineerKontrak · Kerja di lokasiMinimal Sarjana (S1)3 - 5 tahun pengalamanTayang 4 hari yang laluDiperbarui 4 hari yang laluLAMAR & CHAT DI APLIKASILamarPersyaratanKerja di lokasi3 - 5 tahun pengalamanMinimal Sarjana (S1)SkillsHadoopETLSQLMicrosoft SQL ServerPythonGoogle Cloud PlatformData EngineeringBenefit KerjaLaptop ProvidedWork InsuranceHealth InsuranceTHRCareer Path Loker ini dikelola olehRRekruterOnline kemarinDeskripsi pekerjaan Middle Data Engineer CeleratesResponsibilities1. Design, develop, and maintain scalable data pipelines and ETL processes2. Manage and optimize data workflows using GCP services3. Build and maintain data warehouses and data lakes4. Collaborate with Data Analysts, Data Scientists, and Business Teams to support data needs5. Ensure data quality, integrity, and security across systems6. Monitor and troubleshoot data pipeline performance issues7. Create technical documentation related to data architecture and processesRequirements1. 3–5 years of experience as a Data Engineer.2. Hands-on experience with Python, Google Cloud Platform (GCP), BigQuery, and Big Data technologies.3. Proven experience building and maintaining scalable ETL/ELT pipelines and processing large datasets.4. Strong SQL skills with a good understanding of data modeling and data warehousing.5. Experience with Airflow/Cloud Composer and cloud-native data architectures is a plus.6. Available to join immediately or within a short notice period.Tentang PerusahaanCeleratesInformation Technology and Services51 - 200 karyawan Celerates adalah perusahaan yang bergerak dalam bidang pengembangan sumber daya manusia dan bertujuan untuk membantu talenta-talenta dalam bidang IT untuk mengakselerasikan karir mereka.Celerates menawarkan program unggulan yaitu Celerates Acceleration Program, sebuah program akselerasi karir selama 1 tahun yang terdiri dari training intensive, mentoring, case study, mini project, networking dan project placement.Lihat Lebih BanyakTips Aman Cari KerjaPemberi kerja yang benar tidak akan meminta akun Telegram, top-ups atau pembayaran dalam bentuk apapun. Jangan berikan kontak pribadi, informasi bank, maupun kartu kredit kamu.Pelajari SelengkapnyaLaporkan Lowongan IniLowongan Lainnya UntukmuData EngineerRp 9 jt-12 jtPenuh Waktu3–5 tahunMinimal Sarjana (S1)InsigniaJakarta Barat, DKI Jakarta2 hari yang laluSenior Data EngineerRp 18 jt-21 jtKontrak5–10 tahunMinimal Sarjana (S1)Insura Media SolusiJakarta Selatan, DKI Jakarta4 hari yang laluData EngineerRp 12 jt-17 jtPerusahaan PremiumHybridKontrak3–5 tahun+1PT. Cycent Inovasi KaizenJakarta Pusat, DKI Jakarta4 hari yang laluDatabase ArchitechRp 10 jt-20 jtPenuh Waktu5–10 tahunMinimal Sarjana (S1)Pt. Jaya Agung TeknologiJakarta Utara, DKI Jakarta5 hari yang laluData EngineerRp 8,5 jt-11 jtPerusahaan PremiumKontrak3–5 tahunMinimal Sarjana (S1)PT Avows TechnologiesJakarta Selatan, DKI Jakarta7 hari yang lalu
    """,
    ]

    print("=" * 50)
    print("TEST PARSE_JOB (dengan improvement)")
    print("=" * 50)

    for idx, job_text in enumerate(job_content):
        print(f"\n--- Test Case {idx+1} ---")
        parsed = parse_job(
            job_title="Data Engineer",
            job_description=job_text,
            job_url=f"https://example.com/job/{idx+1}",
            keyword="data+engineer"
        )
        print("Parsed Job:")
        for key, value in parsed.items():
            print(f"  {key}: {value}")
        
        parsed = parse_job(
            job_title="Data Engineer",
            job_description=job_text,
            job_url=f"https://example.com/job/{idx+1}",
            keyword="data+engineer"
        )
        print("Parsed Job:")
        for key, value in parsed.items():
            print(f"  {key}: {value}")

        parsed = parse_job(
            job_title="Data Engineer",
            job_description=job_text,
            job_url=f"https://example.com/job/{idx+1}",
            keyword="data+engineer"
        )
        print("Parsed Job:")
        for key, value in parsed.items():
            print(f"  {key}: {value}")