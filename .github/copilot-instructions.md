# AI Agent Constraints & Token Optimization Rules

## Terminal Rules
- **RTK (Rust Token Killer)** — selalu panggil secara **eksplisit** dengan prefix `rtk ` untuk setiap perintah yang biasanya menyemburkan log output (npm install, pip install, git log, pytest, dll.).
- RTK **tidak bekerja otomatis** via hook — WAJIB dieksekusi eksplisit: `rtk npm install`, `rtk pip install`, `rtk pytest`, dll.
- Untuk perintah sederhana/cepat (ls, mv, rm, touch, mkdir, echo) tidak perlu `rtk`.
- Jika perintah gagal, jangan ulang langsung; periksa cache RTK terlebih dahulu jika tersedia.

## Code Reading & Modification Rules
- **NEVER re-read files** multiple times in a single chat session unless explicitly instructed or if external modifications occurred. Keep track of what you have read in your temporary context.
- **DO NOT rewrite or output the entire file** when making modifications.

## Output Condensation
- **Be extremely concise and terse**. Give code solutions first, then provide minimal explanations (max 2 sentences) only if highly critical.
- Avoid polite introductory filler phrases (e.g., "Sure, I can help with that", "Here is the modified code"). Jump straight to the solution.

## Looping & Thinking Prevention
- If a command fails or a solution does not work, **DO NOT repeat the exact same approach**.
- If you find yourself in a thinking loop or executing the same terminal command more than twice, stop immediately and ask the user for guidance or external logs.
