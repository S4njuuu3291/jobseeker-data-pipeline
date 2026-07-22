import os
import re
import json
import time
from dotenv import load_dotenv

load_dotenv()

# ============================================
# Lazy imports & client
# ============================================
_client = None

def _get_client():
    global _client
    if _client is None:
        import httpx
        from openai import OpenAI
        http_client = httpx.Client(
            trust_env=False,
            timeout=httpx.Timeout(120.0)
        )
        _client = OpenAI(
            api_key=os.environ.get("DEEPSEEK_API_KEY"),
            base_url="https://api.deepseek.com",
            http_client=http_client,
        )
    return _client


# ============================================
# MODEL & HARGA
# ============================================
MODEL_NAME = "deepseek-v4-flash"

# 💰 HARGA PER 1M TOKENS (USD)
MODEL_PRICES = {
    "deepseek-v4-flash": {
        "input": 0.14,
        "output": 0.28,
        "cache_hit": 0.0028
    },
    "deepseek-v4-pro": {
        "input": 0.435,
        "output": 0.87,
        "cache_hit": 0.0087
    },
    "deepseek-chat": {
        "input": 0.14,
        "output": 0.28,
        "cache_hit": 0.0028
    },
    "deepseek-reasoner": {
        "input": 0.55,
        "output": 2.19,
        "cache_hit": 0.011
    }
}

# ============================================
# SYSTEM PROMPT
# ============================================
current_date = time.strftime("%Y-%m-%d")

SYSTEM_PROMPT_PARSE = f"""Anda adalah parser data lowongan kerja.
Ekstrak informasi dari job description dan kembalikan JSON valid dengan schema berikut.

Tanggal saat ini: {current_date}

PERINGATAN: HANYA KEMBALIKAN JSON TANPA TEKS LAIN. PASTIKAN STRING TERTUTUP DENGAN KUTIP DUA (").

{{
    "job_title": str,          # Judul lowongan lengkap dari card. Default: "Unknown"
    "role": str,               # Peran inti (tanpa senioritas). Default: "Unknown"
    "company_name": str,       # Nama perusahaan. Default: "Unknown"
    "location": str,           # Format: "City" atau "Remote". Default: "Unknown"
    "salary_min": int,         # Angka bulat. Jika tidak ada: 0
    "salary_max": int,         # Angka bulat. Jika tidak ada: 0
    "salary_currency": str,    # enum: "IDR" / "USD" / "SGD" / "MYR" / "EUR". Default: "IDR"
    "salary_period": str,      # enum: "monthly" / "yearly". Default: "monthly"
    "job_type": str,           # enum: "full_time" / "contract" / "part_time" / "internship" / "freelance"
    "seniority": str,          # enum: "intern" / "junior" / "mid" / "senior" / "lead" / "manager" / "executive"
    "work_mode": str,          # enum: "remote" / "hybrid" / "on_site". Default: "unknown"
    "experience_min": int,     # Tahun pengalaman minimal. Default: 0
    "experience_max": int,     # Tahun pengalaman maksimal. Default: 0
    "education": str,          # enum: "high_school" / "diploma" / "bachelor" / "master" / "phd". Default: "unknown"
    "company_industry": str,   # Bebas. Default: "Unknown"
    "skills": list,            # array of strings. Default: []
    "benefits": list,          # array of strings. Default: []
    "posting_date": str        # ISO 8601 (YYYY-MM-DD). Default: hari ini
}}

Kembalikan JSON valid, tanpa teks lain."""


# ============================================
# FUNGSI HITUNG BIAYA
# ============================================
def calculate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> dict:
    """Hitung estimasi biaya berdasarkan token."""
    prices = MODEL_PRICES.get(model, MODEL_PRICES["deepseek-v4-flash"])
    
    cost_input = (prompt_tokens / 1_000_000) * prices["input"]
    cost_output = (completion_tokens / 1_000_000) * prices["output"]
    
    return {
        "input": cost_input,
        "output": cost_output,
        "total": cost_input + cost_output
    }


# ============================================
# FUNGSI REPAIR JSON
# ============================================
def repair_and_parse_json(raw: str) -> dict:
    """Mencoba memperbaiki JSON yang rusak/terpotong."""
    if not raw or not raw.strip():
        return {}

    cleaned = re.sub(r'```json\s*', '', raw)
    cleaned = re.sub(r'```\s*', '', cleaned)
    cleaned = cleaned.strip()

    try:
        from json_repair import repair_json
        repaired = repair_json(cleaned)
        return json.loads(repaired)
    except (ImportError, Exception):
        pass

    match = re.search(r'\{.*\}', cleaned, re.DOTALL)
    if match:
        candidate = match.group()
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            try:
                candidate = re.sub(r',\s*\}', '}', candidate)
                candidate = re.sub(r',\s*\]', ']', candidate)
                candidate = re.sub(r'([^\\])"([^"]*)$', r'\1"\2"', candidate)
                return json.loads(candidate)
            except:
                pass

    return {}


# ============================================
# FUNGSI NORMALISASI ROLE
# ============================================
def normalize_role_from_title(title: str) -> str:
    if not title or title == "Unknown":
        return "Unknown"
    
    seniority_words = [
        "senior", "jr", "jr.", "junior", "mid", "middle", 
        "lead", "staff", "principal", "associate", "assistant",
        "intern", "magang", "l1", "l2", "l3", "sr", "sr.",
        "entry", "fresh", "graduate", "trainee", "apprentice",
        "manager", "executive", "vp", "director", "head"
    ]
    
    words = title.split()
    role_words = []
    for w in words:
        clean_w = re.sub(r'[^\w\s]', '', w).lower()
        if clean_w not in seniority_words:
            role_words.append(w)
    
    role = " ".join(role_words).strip()
    
    if not role or role == "Unknown":
        words = title.split()
        if len(words) >= 2:
            role = " ".join(words[:2])
        elif len(words) == 1:
            role = words[0]
        else:
            role = "Unknown"
    
    role = re.sub(r'\(.*?\)', '', role).strip()
    role = re.sub(r'[^\w\s\-]', '', role).strip()
    
    return role


# ============================================
# 🔥 FUNGSI UTAMA: PARSE_JOB (dengan API usage di result)
# ============================================
def parse_job(
    job_title: str,
    job_description: str,
    job_url: str = "",
    keyword: str = "",
    verbose: bool = True,
) -> dict:
    """
    Parse job description menggunakan AI, kembalikan dict LENGKAP dengan:
    - Hasil parsing (data_schema_ai)
    - API usage info
    - Metadata
    
    Returns:
        dict: {
            # === HASIL PARSING ===
            "job_title": str,
            "role": str,
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
            
            # === API USAGE INFO ===
            "api_model": str,                    # Model yang digunakan
            "api_usage_prompt_tokens": int,      # Token input
            "api_usage_completion_tokens": int,  # Token output
            "api_usage_total_tokens": int,       # Total token
            "api_cache_hit_tokens": int,         # Token dari cache (diskon 50x)
            "api_cache_miss_tokens": int,        # Token tidak dari cache
            "api_finish_reason": str,            # "stop" / "length" / "content_filter"
            "api_cost_usd": float,               # Estimasi biaya dalam USD
            "api_cost_idr": float,               # Estimasi biaya dalam IDR (kurs 16.000)
            "api_attempt": int,                  # Percobaan ke berapa yang berhasil
            
            # === METADATA ===
            "parsed_success": bool,              # True jika AI berhasil, False jika fallback
            "parsed_at": str,                    # Timestamp parsing
        }
    """
    default = {
        "job_title": job_title or "Unknown",
        "role": "Unknown",
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

    desc_trimmed = job_description[:6000] if job_description else ""

    if not desc_trimmed.strip():
        print(f"Job description kosong untuk '{job_title}', pakai default")
        result = default.copy()
        result.update({
            "api_model": MODEL_NAME,
            "api_usage_prompt_tokens": 0,
            "api_usage_completion_tokens": 0,
            "api_usage_total_tokens": 0,
            "api_cache_hit_tokens": 0,
            "api_cache_miss_tokens": 0,
            "api_finish_reason": "empty_description",
            "api_cost_usd": 0.0,
            "api_cost_idr": 0.0,
            "api_attempt": 0,
            "parsed_success": False,
            "parsed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        })
        return result

    max_retries = 3
    backoff_seconds = [1, 2, 4]
    parsed_success = False
    usage_info = {}

    for attempt in range(max_retries):
        try:
            response = _get_client().chat.completions.create(
                model=MODEL_NAME,
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
                max_tokens=2000,
                response_format={"type": "json_object"},
            )

            content = response.choices[0].message.content

            # 📊 Ambil token usage
            usage = response.usage
            prompt_tokens = usage.prompt_tokens
            completion_tokens = usage.completion_tokens
            total_tokens = usage.total_tokens
            
            # 💰 Hitung biaya
            cost = calculate_cost(MODEL_NAME, prompt_tokens, completion_tokens)
            
            usage_info = {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "cache_hit_tokens": getattr(usage, "prompt_cache_hit_tokens", 0),
                "cache_miss_tokens": getattr(usage, "prompt_cache_miss_tokens", 0),
                "finish_reason": response.choices[0].finish_reason or "unknown",
                "cost_usd": round(cost["total"], 8),
                "cost_idr": round(cost["total"] * 16000, 2),
                "model": MODEL_NAME,
                "attempt": attempt + 1,
            }

            if verbose:
                print(f"💰 Token: {total_tokens} total (P:{prompt_tokens} / C:{completion_tokens})")
                print(f"   Estimasi biaya: ${usage_info['cost_usd']:.6f} (Rp {usage_info['cost_idr']:.2f})")
                print(f"   Cache hit: {usage_info['cache_hit_tokens']} tokens")

            if not content or not content.strip():
                print(f"Response kosong untuk '{job_title}', retry {attempt+1}/{max_retries}")
                time.sleep(backoff_seconds[attempt] if attempt < len(backoff_seconds) else 3)
                continue

            parsed = repair_and_parse_json(content)

            if parsed:
                # Merge hasil parsing dengan default
                merged = {**default, **parsed}
                merged["job_title"] = job_title or merged.get("job_title", "Unknown")
                
                if not merged.get("role") or merged["role"] == "Unknown":
                    merged["role"] = normalize_role_from_title(job_title)
                
                if not merged.get("posting_date"):
                    merged["posting_date"] = time.strftime("%Y-%m-%d")
                
                parsed_success = True
                break
            else:
                print(f"Gagal repair JSON untuk '{job_title}', retry {attempt+1}/{max_retries}")
                time.sleep(backoff_seconds[attempt] if attempt < len(backoff_seconds) else 3)

        except Exception as e:
            print(f"Parse AI error untuk '{job_title}': {e}, retry {attempt+1}/{max_retries}")
            time.sleep(backoff_seconds[attempt] if attempt < len(backoff_seconds) else 3)

    # ⚠️ FALLBACK: jika semua percobaan gagal
    if not parsed_success:
        print(f"⚠️ Fallback total untuk '{job_title}', coba regex minimal...")
        fallback_result = default.copy()
        fallback_result["job_title"] = job_title or "Unknown"
        fallback_result["role"] = normalize_role_from_title(job_title)

        # Regex untuk gaji
        salary_pattern = re.compile(r'Rp\s*([\d.,]+)\s*[-–]\s*([\d.,]+)', re.I)
        match = salary_pattern.search(job_description)
        if match:
            try:
                min_sal = int(re.sub(r'[.,]', '', match.group(1)))
                max_sal = int(re.sub(r'[.,]', '', match.group(2)))
                fallback_result["salary_min"] = min_sal
                fallback_result["salary_max"] = max_sal
            except:
                pass

        # Regex untuk lokasi
        loc_pattern = re.compile(r'(Jakarta|Bekasi|Tangerang|Depok|Bandung|Surabaya|Yogyakarta|Semarang|Medan)', re.I)
        loc_match = loc_pattern.search(job_description)
        if loc_match:
            fallback_result["location"] = loc_match.group(1) + ", Indonesia"

        # Regex untuk pengalaman
        exp_pattern = re.compile(r'(\d+)\s*[-–]\s*(\d+)\s*tahun')
        exp_match = exp_pattern.search(job_description)
        if exp_match:
            fallback_result["experience_min"] = int(exp_match.group(1))
            fallback_result["experience_max"] = int(exp_match.group(2))

        # Regex untuk skills
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

        # Regex untuk work_mode
        if "remote" in job_description.lower():
            fallback_result["work_mode"] = "remote"
        elif "hybrid" in job_description.lower():
            fallback_result["work_mode"] = "hybrid"
        elif "lokasi" in job_description.lower() or "on site" in job_description.lower():
            fallback_result["work_mode"] = "on_site"

        merged = fallback_result
        usage_info = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "cache_hit_tokens": 0,
            "cache_miss_tokens": 0,
            "finish_reason": "fallback_regex",
            "cost_usd": 0.0,
            "cost_idr": 0.0,
            "model": MODEL_NAME,
            "attempt": 0,
        }

    # 🔥 GABUNGKAN HASIL PARSING + API USAGE + METADATA
    final_result = {
        # === HASIL PARSING (dari data_schema_ai) ===
        "job_title": merged.get("job_title", "Unknown"),
        "role": merged.get("role", "Unknown"),
        "company_name": merged.get("company_name", "Unknown"),
        "location": merged.get("location", "Unknown"),
        "salary_min": merged.get("salary_min", 0),
        "salary_max": merged.get("salary_max", 0),
        "salary_currency": merged.get("salary_currency", "IDR"),
        "salary_period": merged.get("salary_period", "monthly"),
        "job_type": merged.get("job_type", "full_time"),
        "seniority": merged.get("seniority", "mid"),
        "work_mode": merged.get("work_mode", "unknown"),
        "experience_min": merged.get("experience_min", 0),
        "experience_max": merged.get("experience_max", 0),
        "education": merged.get("education", "unknown"),
        "company_industry": merged.get("company_industry", "Unknown"),
        "skills": merged.get("skills", []),
        "benefits": merged.get("benefits", []),
        "posting_date": merged.get("posting_date", time.strftime("%Y-%m-%d")),
        
        # === API USAGE INFO ===
        "api_model": usage_info.get("model", MODEL_NAME),
        "api_usage_prompt_tokens": usage_info.get("prompt_tokens", 0),
        "api_usage_completion_tokens": usage_info.get("completion_tokens", 0),
        "api_usage_total_tokens": usage_info.get("total_tokens", 0),
        "api_cache_hit_tokens": usage_info.get("cache_hit_tokens", 0),
        "api_cache_miss_tokens": usage_info.get("cache_miss_tokens", 0),
        "api_finish_reason": usage_info.get("finish_reason", "unknown"),
        "api_cost_usd": usage_info.get("cost_usd", 0.0),
        "api_cost_idr": usage_info.get("cost_idr", 0.0),
        
        # === METADATA ===
        "api_attempt": usage_info.get("attempt", 0),
        "parsed_success": parsed_success,
        "parsed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    return final_result


# ============================================
# TEST
# ============================================
if __name__ == "__main__":
    job_content = ["""
        Middle Data EngineerCeleratesRp10.000.000 - 13.000.000/BulanKomputer & Perangkat Lunak Data EngineerKontrak · Kerja di lokasiMinimal Sarjana (S1)3 - 5 tahun pengalamanTayang 4 hari yang laluDiperbarui 4 hari yang laluLAMAR & CHAT DI APLIKASILamarPersyaratanKerja di lokasi3 - 5 tahun pengalamanMinimal Sarjana (S1)SkillsHadoopETLSQLMicrosoft SQL ServerPythonGoogle Cloud PlatformData EngineeringBenefit KerjaLaptop ProvidedWork InsuranceHealth InsuranceTHRCareer Path Loker ini dikelola olehRRekruterOnline kemarinDeskripsi pekerjaan Middle Data Engineer CeleratesResponsibilities1. Design, develop, and maintain scalable data pipelines and ETL processes2. Manage and optimize data workflows using GCP services3. Build and maintain data warehouses and data lakes4. Collaborate with Data Analysts, Data Scientists, and Business Teams to support data needs5. Ensure data quality, integrity, and security across systems6. Monitor and troubleshoot data pipeline performance issues7. Create technical documentation related to data architecture and processesRequirements1. 3–5 years of experience as a Data Engineer.2. Hands-on experience with Python, Google Cloud Platform (GCP), BigQuery, and Big Data technologies.3. Proven experience building and maintaining scalable ETL/ELT pipelines and processing large datasets.4. Strong SQL skills with a good understanding of data modeling and data warehousing.5. Experience with Airflow/Cloud Composer and cloud-native data architectures is a plus.6. Available to join immediately or within a short notice period.Tentang PerusahaanCeleratesInformation Technology and Services51 - 200 karyawan Celerates adalah perusahaan yang bergerak dalam bidang pengembangan sumber daya manusia dan bertujuan untuk membantu talenta-talenta dalam bidang IT untuk mengakselerasikan karir mereka.
    """]

    print("=" * 60)
    print("TEST PARSE_JOB dengan API Usage di Result")
    print("=" * 60)

    for idx, job_text in enumerate(job_content):
        print(f"\n--- Test Case {idx+1} ---")
        
        result = parse_job(
            job_title="Data Engineer",
            job_description=job_text,
            job_url=f"https://example.com/job/{idx+1}",
            keyword="data+engineer",
            verbose=True
        )
        
        print("\n📊 HASIL LENGKAP:")
        print("-" * 40)
        print("🔹 HASIL PARSING:")
        for key in ["job_title", "role", "company_name", "location", "salary_min", "salary_max", 
                    "job_type", "seniority", "work_mode", "experience_min", "experience_max", 
                    "education", "company_industry"]:
            print(f"    {key}: {result.get(key)}")
        
        print("\n🔹 SKILLS & BENEFITS:")
        print(f"    skills: {result.get('skills', [])[:5]}..." if len(result.get('skills', [])) > 5 else f"    skills: {result.get('skills', [])}")
        print(f"    benefits: {result.get('benefits', [])}")
        
        print("\n🔹 API USAGE:")
        print(f"    api_model: {result.get('api_model')}")
        print(f"    api_usage_total_tokens: {result.get('api_usage_total_tokens')}")
        print(f"    api_usage_prompt_tokens: {result.get('api_usage_prompt_tokens')}")
        print(f"    api_usage_completion_tokens: {result.get('api_usage_completion_tokens')}")
        print(f"    api_cache_hit_tokens: {result.get('api_cache_hit_tokens')}")
        print(f"    api_finish_reason: {result.get('api_finish_reason')}")
        print(f"    api_cost_usd: ${result.get('api_cost_usd', 0):.8f}")
        print(f"    api_cost_idr: Rp {result.get('api_cost_idr', 0):.2f}")
        print(f"    api_attempt: {result.get('api_attempt')}")
        
        print("\n🔹 METADATA:")
        print(f"    parsed_success: {result.get('parsed_success')}")
        print(f"    parsed_at: {result.get('parsed_at')}")
        print("-" * 40)