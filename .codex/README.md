# การใช้งาน Multi-Agent ของโปรเจกต์นี้

> **Current workflow (16 November 2026):** UX/UI now uses the Codex `ui` role with `gpt-6.1-terra` and medium reasoning. The Gemini/Antigravity bridge described below is historical and must not be invoked for project work unless the user explicitly requests it again. See `AGENTS.md` and `.codex/agents/ui.toml` for the active instructions.

ตั้งค่าเมื่อ 7 ตุลาคม 2026 สำหรับโปรเจกต์นี้

## Created

- `.codex/config.toml`: เปิด multi-agent และจำกัด native subagent threads ที่เปิดพร้อมกันไว้ 2
- `.codex/agents/explorer.toml`
- `.codex/agents/logic.toml`
- `.codex/agents/coder.toml`
- `.codex/agents/reviewer.toml`
- `.codex/agents/ui.toml`: งาน UX/UI ผ่าน Codex โดยใช้ `gpt-6.1-terra` / medium
- `AGENTS.md`: ขอบเขตงาน, workflow, กฎ business logic, PHP/JS/SQL และการประหยัด context
- `.codex/run_agent.py`: ตัวเรียก role ผ่าน Codex CLI และตรวจ effective config โดยไม่ใช้โมเดล
- `.codex/gemini_bridge.py`: ให้ Codex ส่งงาน UI ไป Gemini แล้วรับ proposal และ token usage กลับมาตรวจ
- `.codex/gemini.toml`: โมเดลและขนาด context ของตัวประสาน Gemini
- `.codex/BRIDGE.md`: วิธีใช้ Codex และ Gemini จากคำสั่งผู้ใช้ครั้งเดียว
- `.codex/handoff.example.json`: ตัวอย่างขอบเขตงานที่ coordinator ส่งให้ Gemini
- `.codex/tests/test_gemini_bridge.py`: ตรวจการรับผล ขอบเขตไฟล์ การรักษา user edits และ rollback
- `.gitignore`: ไม่ให้ runtime handoff และ source excerpts เข้า Git
- `.codex/README.md`: คู่มือนี้

โฟลเดอร์นี้ว่างก่อนตั้งค่า ไม่มี business source code ถูกแก้ไข

## Updated / Preserved existing settings

เพิ่ม project trust setting ใน Codex config ของเครื่องที่ใช้งาน เพื่อให้ Codex โหลด project config ได้

ตรวจว่าค่าเดิมทุกค่าและ bytes เดิมยังคงอยู่ รวมถึง parent model `gpt-6.1-sol`, reasoning `high`, Windows sandbox settings, project `warehouse`, และ TUI settings

ไฟล์สำรองของ config เก็บไว้ภายนอก repository

## Agents

| Role | Model | Reasoning | Sandbox | งาน |
| --- | --- | --- | --- | --- |
| explorer | gpt-6-luna | low | read-only | หาไฟล์และ trace flow |
| logic | gpt-6.2-sol | high | read-only | วิเคราะห์ root cause / business rules |
| coder | gpt-6.2-sol | medium | workspace-write | แก้ implementation ตาม scope ที่อนุญาต |
| reviewer | gpt-6-luna | medium | read-only | ตรวจ diff, regression และ bug |
| ui | gpt-6.1-terra | medium | workspace-write | ปรับ UX/UI และ responsive ตามขอบเขตที่อนุญาต |

โมเดลของ role ต้องอยู่ในรายการที่บัญชีปัจจุบันใช้ได้ โดย `logic` และ `coder` เปลี่ยนเป็น `gpt-6.2-sol` เมื่อ 19 พฤศจิกายน 2026 หากเปลี่ยนบัญชีหรือ workspace ให้ตรวจ availability ใหม่

## How Codex should use these agents

เปิดโปรเจกต์นี้ใน Codex/VS Code และเริ่ม session ใหม่เพื่อโหลด config กับ `AGENTS.md`

- ค้นตำแหน่ง code: explorer
- วิเคราะห์ปัญหา: explorer เมื่อยังไม่รู้ตำแหน่ง แล้ว logic ตามความจำเป็น
- แก้เล็กน้อยในไฟล์ที่รู้ตำแหน่ง: coordinator หรือ coder
- แก้ business logic ซับซ้อน: explorer เมื่อจำเป็น -> logic -> coder -> reviewer
- ตรวจงานเดิม: reviewer
- ปรับ UX/UI: ui; เน้นใช้งานง่าย อ่านง่าย สีไม่เยอะ และรักษา design system เดิม

อย่าเรียกทุก role ทุกงาน และอย่าให้หลายตัวแก้ไฟล์เดียวกันพร้อมกัน

เรียกชื่อ role ได้โดยตรงจาก terminal ที่ root ของโปรเจกต์:

```powershell
python .codex/run_agent.py explorer "หาไฟล์คำนวณ Storage Charge และ trace flow โดยไม่แก้ไฟล์"
python .codex/run_agent.py logic "วิเคราะห์ root cause ตามไฟล์และ requirement ที่ระบุ โดยไม่แก้ไฟล์"
python .codex/run_agent.py coder "แก้ function ที่ระบุตาม requirement นี้ และตรวจ affected flow"
python .codex/run_agent.py reviewer "ตรวจ diff ปัจจุบันและ affected flow โดยไม่แก้ไฟล์"
python .codex/run_agent.py ui "ปรับ UI ที่ระบุให้ใช้งานง่าย โดยรักษา logic และ field names เดิม"
```

คำสั่งเหล่านี้เป็นตัวอย่างแยกกัน ไม่ใช่ลำดับที่ต้องเรียกทั้งหมด คำสั่งใช้งานจริงเรียกโมเดลและใช้ usage ตามบัญชี

ตัวเรียกใช้ instructions/model/reasoning/sandbox จาก role file, สืบทอด auth/provider ของผู้ใช้, เปิดหนึ่ง CLI session ต่อการเรียก และปิดการ spawn ต่อภายใน role นั้น สามารถใช้ `-` เป็น task เพื่ออ่านรายละเอียดจาก stdin ได้

```powershell
python .codex/run_agent.py all --check
```

`--check` ตรวจทั้ง 5 role ผ่าน Codex app-server โดยไม่ส่งคำขอไปยังโมเดล ถ้าไม่พบ executable ให้ระบุ `--codex "path\to\codex.exe"` ตัวเรียกต้องเข้าถึง runtime directory ส่วนตัวของ Codex ได้

## Validation

- CLI ที่ตรวจ: `codex-cli 0.162.0-alpha.2` ซึ่งมากับ VS Code extension `26.1002.51308`
- TOML ทั้ง 5 ไฟล์ parse ผ่าน Python 3.11 `tomllib`
- Codex app-server `--strict-config` โหลด project layer ผ่าน ไม่มี disabled trust layer
- Codex `debug prompt-input` ยืนยันว่า project instructions ถูกโหลด
- `run_agent.py all --check` ยืนยัน model, reasoning, sandbox และ developer instructions ของทั้ง 4 role จาก effective config จริง
- ค่าตั้งต้นของ parent ยังคงเป็น `gpt-6.1-sol` / `high`
- ไม่ได้เรียกโมเดลเพื่อทดสอบงานจริงของแต่ละ role
- Gemini bridge: Antigravity CLI 1.3.1, ตรวจ model access จาก `agy models` จริง
- Bridge unit tests: ผ่าน 14 ข้อ รวม stale user edits, Windows path aliases และ rollback เมื่อเขียนไฟล์หรือรายงานไม่ได้
- Live bridge test: Gemini รับ CSS ตัวอย่าง ส่ง proposal กลับมา ผ่าน coordinator review, apply และตรวจ bytes ว่าต่างเฉพาะ padding 8px -> 16px; `status` แสดง usage ของงานจริง

คำสั่ง `debug prompt-input` แสดงเฉพาะ input messages ไม่แสดง tool schema จึงใช้ยืนยัน native custom-role selection ผ่าน UI ไม่ได้ หาก client มีเครื่องมือเลือก custom role ให้ใช้ชื่อจาก role file; หากไม่มี ให้ใช้ตัวเรียกด้านบน ซึ่งตรวจการโหลดค่าของแต่ละ role แล้ว หลีกเลี่ยงเรียกทั้ง native subagent และ CLI role ซ้ำสำหรับงานเดียวกัน

## Unsupported config removed/avoided

- ไม่ใส่ key ที่เดา เช่น token budget, routing table หรือ Gemini provider
- ใช้ standalone role files ที่มี `name`, `description`, `developer_instructions` ตามเอกสารปัจจุบัน แทนการเพิ่ม role registration แบบเดิมซ้ำ
- ไม่ใช้ legacy `agents.max_threads` เมื่อเวอร์ชันนี้รองรับ `max_concurrent_threads_per_session`
- ไม่เปิด experimental flags หรือเปลี่ยน parent model/provider/auth/approval settings
- native subagent thread limit ไม่ได้จำกัดจำนวน CLI processes ที่เปิดแยกเอง ให้เรียกตัว runner ตามลำดับสำหรับงานที่มี dependency

## Legacy Gemini responsibility (inactive)

ส่วนด้านล่างเป็นประวัติของ workflow เดิมเท่านั้น ปัจจุบันให้ Codex `ui` role รับงาน UX/UI แทน และไม่เรียก Gemini bridge อัตโนมัติ

ผู้ใช้สั่ง Codex ครั้งเดียวได้แล้ว: Codex วิเคราะห์และทำ logic ตามที่จำเป็น ส่งเฉพาะงาน UI / CSS / Tailwind / responsive ให้ Gemini ผ่าน Antigravity CLI จากนั้นตรวจ proposal นำการแก้ไขที่ตรง scope มาใช้ และตรวจผลจริงก่อนรายงาน ผู้ใช้ไม่ต้องคัดลอก prompt ไปสั่ง Gemini เอง งาน backend ล้วนข้าม Gemini เพื่อประหยัด usage

เริ่ม session ใหม่ในโปรเจกต์ที่มี `AGENTS.md` นี้ แล้วสั่ง เช่น **“แก้ logic ตาม requirement นี้ และให้ Gemini ปรับ UI ที่เกี่ยวข้อง จากนั้นตรวจผลรวมให้ด้วย”** โปรเจกต์นี้ยังไม่มี application source จึงต้องมีไฟล์งานจริงก่อนสั่งแก้หน้าเว็บ

Gemini ใช้ cached login ของ Antigravity ซึ่งแยกจากบัญชี Codex ค่าเริ่มต้น UI คือ `gemini-4-argon-medium`; summary อย่างเดียวคือ `gemini-4-argon-low` ทั้งสองชื่ออยู่ในรายการ `agy models` ที่ตรวจจริงเมื่อ 16 ตุลาคม 2026 หากต้องการเปลี่ยนโมเดล ให้ใช้ชื่อที่มีจริงใน `agy models` และแก้ `model` หรือ `summary_model` ใน `.codex/gemini.toml` ตามประเภทงาน

อ่าน [คู่มือตัวประสาน](BRIDGE.md) สำหรับการย้ายไปโปรเจกต์อื่น รายงาน token และข้อจำกัด

อ้างอิง [OpenAI Docs: Subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents) และ [Configuration Reference](https://learn.chatgpt.com/docs/config-file/config-reference)
