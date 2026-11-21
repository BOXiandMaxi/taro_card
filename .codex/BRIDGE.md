# Legacy Gemini bridge (inactive)

This document describes the old Gemini/Antigravity workflow. The active project instructions in `AGENTS.md` now assign UX/UI work to the Codex `ui` role (`gpt-6.1-terra`, medium). Do not invoke this bridge for project work unless the user explicitly requests it again.

---

# สั่ง Codex ครั้งเดียว แล้วให้ Gemini รับงาน UI

Codex เป็น coordinator และผู้ตรวจผล Gemini ทำงานผ่าน Antigravity CLI โดยรับเฉพาะ excerpts ที่จำเป็น ส่ง exact-text proposal กลับมา แล้ว Codex ตรวจและนำมาใช้ตาม scope ผู้ใช้ไม่ต้องเปิด terminal อีกหน้ามาคัดลอก prompt ระหว่างสองตัว

## ใช้งาน

1. เปิดโปรเจกต์ที่มี `.codex/` และ `AGENTS.md` นี้ใน Codex แล้วเริ่ม session ใหม่ เพื่อโหลดคำสั่งประสานงาน
2. สั่ง requirement ตามปกติ เช่น “แก้การคำนวณตาม requirement นี้ และให้ Gemini ปรับ UI ส่วนที่เกี่ยวข้อง แล้วตรวจผลรวมให้ด้วย” หรือ “ให้ Gemini ปรับหน้า X ให้ responsive แล้ว Codex ตรวจผลให้ด้วย”
3. Codex ตรวจโค้ดจริง แบ่งงาน ส่ง Gemini เฉพาะส่วน UI อ่าน proposal ตรวจ scope นำมาใช้ และรายงานผลทดสอบ งาน backend ล้วนไม่ต้องเรียก Gemini

การเรียก Antigravity ต้องเข้าถึง runtime ส่วนตัวนอก sandbox ของ Codex จึงอาจมี execution approval ของระบบตาม permission profile นี่ไม่ใช่การขอให้ผู้ใช้คัดลอกงานไปทำอีกแอป ไม่มีการตั้งค่า bypass approvals

Codex และ Gemini อาจใช้คนละบัญชี ตัวประสานใช้ cached login ของ `agy.exe` ไม่เปลี่ยนบัญชี ไม่อ่าน OAuth token และไม่ใช้ API key ใหม่ ตัวประสานไม่ได้ยืนยันบัญชีหรือสิทธิ์แพ็กเกจเอง

## รูปแบบ handoff สำหรับ Codex

Coordinator สร้าง `.agent-handoff/request.json` หลังอ่าน implementation และ dependencies แล้ว ตัวอย่าง:

```json
{
  "kind": "ui",
  "task": "ปรับระยะห่าง card สำหรับมือถือ ตาม requirement ของผู้ใช้",
  "context": "logic และชื่อ input เดิมต้องคงไว้",
  "constraints": ["ไม่เปลี่ยน event handlers หรือ API contracts"],
  "files": [
    {"path": "assets/css/page.css", "start": 1, "end": 80, "editable": true},
    {"path": "pages/page.php", "start": 1, "end": 60, "editable": false}
  ]
}
```

ชื่อไฟล์และเลขบรรทัดนี้เป็นตัวอย่าง ต้องเปลี่ยนตามไฟล์จริง ใช้ / ใน relative paths ช่วงบรรทัดรวม start และ end หากไม่ระบุจะส่งทั้งไฟล์ภายในเพดาน context 80,000 bytes งานสร้างไฟล์ใหม่ต้องระบุชื่อไฟล์ UI ใหม่ให้ชัดเจน ไม่ส่ง credentials หรือ source ที่ไม่เกี่ยวข้อง

คำสั่งที่ Codex รันให้:

```powershell
python -B .codex/gemini_bridge.py propose .agent-handoff/request.json --dry-run
python -B .codex/gemini_bridge.py propose .agent-handoff/request.json
```

`--dry-run` ตรวจ request โดยไม่เรียกโมเดล ส่วน `propose` ส่งงานหนึ่งครั้งและคืน path ของ `result.json` กับ `proposal.diff` ใต้ `.agent-handoff/runs/` ซึ่งถูก ignore โดย Git โมเดลไม่ได้รับ working directory จริงของโปรเจกต์

Codex อ่านทั้งสองไฟล์ ตรวจทุก edit ก่อนเรียก:

```powershell
python -B .codex/gemini_bridge.py apply PATH_TO_RESULT_JSON
```

ก่อนเขียน bridge ตรวจ path, allowlist, ข้อความที่ต้องเปลี่ยน และ SHA-256 ของไฟล์เดิม หากผู้ใช้แก้ไฟล์ระหว่างรอ Gemini จะหยุด เพื่อให้ Codex อ่านไฟล์ใหม่และสร้าง handoff ใหม่ การเปลี่ยนไฟล์แบบ PHP/HTML/JS ผสมกันยังต้องอาศัย Codex ตรวจความหมายของ diff; นามสกุลไฟล์อย่างเดียวไม่ยืนยันว่า business logic ปลอดภัย หลัง apply ต้องตรวจ diff และ affected flow จริง ค่า `review_required` จึงคงเป็น true

`kind: "summary"` ใช้สำหรับสรุปเท่านั้นและห้าม edits ปกติใช้ summary ที่มากับ UI proposal เพื่อไม่เรียกโมเดลซ้ำ ไม่เรียก bridge จาก subagent หรือสั่งให้ Gemini เรียก Codex กลับ

## โมเดลและ token

ค่าตั้งอยู่ที่ `.codex/gemini.toml` ซึ่งเป็น config ของสคริปต์นี้เอง ไม่ใช่ key ใน Codex config:

- UI: `gemini-4-argon-medium`
- Summary: `gemini-4-argon-low`
- Timeout: 240 วินาที
- หากต้องการเปลี่ยนระดับ ให้ใช้ชื่อที่มีจริงใน `agy models` เช่น `gemini-4-argon-high`

อ่านสถานะล่าสุดโดยไม่เรียกโมเดล:

```powershell
python -B .codex/gemini_bridge.py status
```

รายงาน `usage` เป็นจำนวน token ที่ Antigravity ส่งกลับสำหรับงานนั้น ไม่ใช่โควตารวมของบัญชี และไม่รวม usage ฝั่ง Codex ค่าเหล่านี้ถูกเก็บใน `result.json` ของแต่ละงาน สำหรับโควตาบัญชีให้ดู `/usage` หรือ `/quota` ใน Antigravity

แม้ excerpts มีขนาดเล็ก usage ยังรวม context ภายในของ Antigravity ด้วย การทดสอบจริงหนึ่งครั้งรายงาน input 28,920, output 2,391, total 31,311 tokens; thinking 2,033 เป็น field ที่รายงานแยก ไม่บวกซ้ำกับ total ตัวประสานเรียกเฉพาะงานที่จำเป็น โดยค่าเริ่มต้นปัจจุบันใช้ Gemini 4 Argon ตามที่ผู้ใช้กำหนด

`proposed` หมายถึงได้ proposal, `applied` หมายถึง bridge เขียนไฟล์แล้ว และ `failed` หมายถึงเกิดปัญหา ไม่มีสถานะไหนแทนผลทดสอบ application การตอบ summary แบบไม่มี edits ใช้รายงานได้โดยไม่เรียก apply

## ย้ายไปโปรเจกต์อื่น

นำ `.codex/` และ `AGENTS.md` ไปที่ root ของโปรเจกต์ใหม่ ถ้ามีไฟล์เดิมให้ merge คำสั่งและ config แทนการทับทั้งไฟล์ เพิ่ม `.agent-handoff/` ใน `.gitignore` เดิม โปรเจกต์ปลายทางต้อง trusted ตามระบบ Codex และเริ่ม session ใหม่

ตัวประสานใช้โฟลเดอร์เหนือ `.codex/` เป็น project root อัตโนมัติ เมื่อวาง `.codex/` ไว้ในโปรเจกต์ใหม่จึงใช้ไฟล์จากโปรเจกต์นั้น Codex อ่าน implementation และ dependencies จริงแล้วเลือก excerpts ส่งให้ Gemini; Gemini รับเฉพาะส่วนที่ส่งมาและคืน UI proposal ให้ Codex ตรวจและนำมาใช้ ไม่ได้อ่านทั้ง repository โดยอัตโนมัติ ต้องวางไฟล์ไว้ที่ root โดยตรง ไม่ใช่วางโฟลเดอร์ `ai_agent` ซ้อนอยู่ข้างในโปรเจกต์

บนเครื่องเดิมใช้ native CLI และบัญชีเดิมได้ทันที บนเครื่องใหม่ต้องติดตั้ง Python 3.11+ และ Antigravity CLI ที่รองรับ headless/schema และล็อกอินบัญชี Gemini ของตนเองก่อน ไม่ต้องคัดลอก auth files ตัวสคริปต์หา `agy.exe` จาก PATH หรือ `%USERPROFILE%\.gemini\bin\agy.exe` หากอยู่ที่อื่นให้ตั้ง `executable` หรือส่ง `--agy`

ตรวจ installation/model access เมื่อจำเป็น:

```powershell
python -B .codex/gemini_bridge.py doctor
python -B .codex/gemini_bridge.py doctor --offline
```

ทั้งสองคำสั่งไม่เรียก inference; `--offline` ไม่ตรวจสิทธิ์โมเดลผ่านบริการ หาก login/runtime เข้าไม่ได้ อย่าเข้าใจว่า permission error แปลว่าบัญชีหลุดเสมอ ต้องตรวจ sandbox และสถานะ login แยกกัน ไม่มีการเปลี่ยน provider หรือบัญชี Codex เพื่อใช้ Gemini

## ตรวจ implementation

```powershell
python -B -m unittest discover -s .codex/tests -v
```

การทดสอบตรวจ stale edits, paths, excerpt boundaries, malformed/failed responses, read-only summaries, file creation, BOM/CRLF และ rollback โดยไม่เรียกโมเดล โฟลเดอร์โปรเจกต์นี้ยังไม่มี application source จึงยังไม่ได้ตรวจ PHP/database/business flow ของระบบจริง

ตรวจจริงเมื่อ 7 ตุลาคม 2026: ส่ง `style.css` ตัวอย่างให้ Gemini เปลี่ยน `.card` padding 8px → 16px, ตรวจ proposal/diff, apply แล้วเปรียบเทียบ bytes ทั้งไฟล์ว่าต่างเฉพาะค่าที่สั่ง ผ่านครบขั้นตอน พร้อมอ่าน usage จาก `status` ได้ ไฟล์ตัวอย่างและรายงานใต้ `.agent-handoff/smoke-project/` ถูกลบตามคำขอผู้ใช้แล้ว เก็บเฉพาะชุด regression tests และไม่ได้แก้ไฟล์ application

Antigravity ที่ตรวจคือ 1.3.1 โปรโตคอล headless อาจเปลี่ยนตามเวอร์ชัน หากอัปเดตแล้วมีปัญหาให้ตรวจ `doctor` และ error ของ run ก่อน retry

อ้างอิง: [Google Antigravity: Headless CLI](https://antigravity.google/docs/cli/headless/), [OpenAI: AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md)
