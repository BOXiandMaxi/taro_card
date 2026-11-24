<p align="center">☾ ✦ ☽</p>

# Tarot Reading

**พื้นที่เล็ก ๆ สำหรับเปิดไพ่ สำรวจคำถาม และทบทวนเรื่องราวของตัวเอง**

[เปิดเว็บไซต์](https://taro-card.onrender.com/) · [วิธีติดตั้ง](#เริ่มใช้งานบนเครื่อง) · [เอกสารโปรเจกต์](#เอกสารเพิ่มเติม)


---

## ✦ เกี่ยวกับโปรเจกต์

เว็บไซต์ดูไพ่ทาโรต์ภาษาไทยที่เริ่มจากความรู้สึกขัดใจเมื่อเว็บไซต์ดูดวงบางแห่งจำกัดการอ่านหรือให้คำทำนายสั้นเกินไป จึงทดลองสร้างพื้นที่อ่านไพ่ของตัวเองขึ้นมาเพื่อความสนุกและการเรียนรู้

ผู้ใช้เลือกคำถาม สับและเปิดไพ่ แล้วอ่านความหมายตามตำแหน่งที่ได้รับ คำอ่านมีไว้เพื่อความบันเทิงและใช้ประกอบการทบทวนตัวเอง ผลลัพธ์และการใช้งาน AI ขึ้นอยู่กับการตั้งค่าและโควตาของระบบ

## ☾ ภาพตัวอย่าง

พื้นที่สำหรับเพิ่มภาพหน้าจอจริงของโปรเจกต์ในภายหลัง:

| หน้าจอ | ภาพที่เตรียมไว้ |
| --- | --- |
| หน้าแรก | ✧ รอเพิ่มภาพ `docs/screenshots/home.webp` |
| เลือกและเปิดไพ่ | ✧ รอเพิ่มภาพ `docs/screenshots/reading.webp` |
| หน้าผลคำทำนาย | ✧ รอเพิ่มภาพ `docs/screenshots/result.webp` |

เมื่อมีภาพ ให้เพิ่มไฟล์ใน [โฟลเดอร์ภาพหน้าจอ](docs/screenshots/) ตามชื่อข้างต้น แล้วแทนข้อความในตารางด้วย Markdown เช่น `![หน้าแรก](docs/screenshots/home.webp)`

## ✦ การใช้งาน

**หน้าแรก → เลือกหัวข้อ → เลือกคำถาม → เลือกจำนวนไพ่ → สับและเลือกไพ่ → เปิดไพ่ → อ่านคำทำนาย**

- เลือกหัวข้อชีวิตประจำวัน การเงิน ความรัก การงาน หรือข้อความจากไพ่
- วางไพ่ได้ **3 ใบ**, **5 ใบ** หรือ **10 ใบแบบ Celtic Cross** พร้อมความหมายตามตำแหน่ง
- มีไพ่ Rider-Waite-Smith 78 ใบ พร้อมชื่อและความหมายภาษาไทย ภาพ WebP เก็บอยู่ในโปรเจกต์ ดูที่มาได้ใน [เอกสารลิขสิทธิ์ภาพ](docs/asset-licenses.md)
- Backend จัดลำดับสำรับด้วยการสุ่มที่ปลอดภัย เก็บไพ่ที่เลือกและทิศไพ่ให้คงเดิมเมื่อกลับมาเปิดอ่าน ระบบรองรับไพ่กลับหัวตามการตั้งค่า
- ผู้เยี่ยมชมเปิดไพ่และดูความหมายรายใบได้ เมื่อต้องการคำทำนายต้องเข้าสู่ระบบ และสามารถใช้ไพ่ชุดเดิมต่อได้
- สมาชิกดูและลบประวัติของตัวเองได้ ผู้ดูแลที่มีสิทธิ์ `admin` ดูสถิติการเข้าชมโดยประมาณได้

### การอ่านด้วย AI

Backend รองรับ OpenAI และ Gemini ผ่านการตั้งค่าฝั่งเซิร์ฟเวอร์ ไพ่และตำแหน่งมาจากระบบอ่านไพ่ ส่วน AI ใช้ข้อมูลเหล่านั้นในการเรียบเรียงคำอ่าน ผลลัพธ์ที่สร้างแล้วถูกเก็บไว้สำหรับเปิดดูซ้ำ

AI **ปิดเป็นค่าเริ่มต้น** หากไม่ได้ตั้งค่าหรือเรียกใช้งานไม่สำเร็จ ระบบใช้ความหมายไพ่ในฐานข้อมูลสร้างคำอ่านแทน รายละเอียดอยู่ใน [API contract](docs/api.md) และ [คู่มือ backend](backend/README.md)

### ความเป็นส่วนตัวและความปลอดภัย

ระบบจัดเก็บรหัสผ่านด้วย Argon2 ใช้คุกกี้สำหรับ session พร้อมตรวจสิทธิ์การเข้าถึงประวัติและรายงานสถิติ สถิติเก็บยอดเปิดหน้าและจำนวนเบราว์เซอร์โดยประมาณโดยไม่เก็บคำถามหรืออีเมลในตารางสถิติ เมื่อเปิดใช้ AI คำถามและข้อมูลไพ่อาจถูกส่งไปยังผู้ให้บริการภายนอก อ่านรายละเอียดใน [ร่างนโยบายความเป็นส่วนตัว](docs/privacy.md)

## ✦ เทคโนโลยี

| ส่วนงาน | เทคโนโลยี |
| --- | --- |
| Frontend | React, Vite, React Router, Tailwind CSS, Motion, Lucide |
| Backend | FastAPI, Pydantic, SQLAlchemy, Alembic |
| ฐานข้อมูล | MySQL-compatible เช่น MariaDB และ TiDB Cloud |
| การเผยแพร่ | Docker และ Render; TiDB Cloud สำหรับฐานข้อมูลภายนอก |

```text
frontend/                 หน้าเว็บและภาพไพ่ที่ใช้จริง
backend/                  API, โมเดล, migration และ tests
database/seeds/           ข้อมูลไพ่ คำถาม และรูปแบบการวางไพ่
database/assets/          manifest, ที่มาภาพ และเครื่องมือตรวจสอบ
docs/                     เอกสาร API, ฐานข้อมูล และการติดตั้ง
```

## เริ่มใช้งานบนเครื่อง

ตัวอย่างคำสั่งสำหรับ Windows PowerShell จากโฟลเดอร์โปรเจกต์ เตรียม Python 3.11+, Node.js ที่รองรับ Vite 6 และฐานข้อมูล MySQL/MariaDB ที่สร้างไว้แล้ว ดู [SQL สำหรับสร้างฐานข้อมูล](database/documentation/create_database.sql)

1. ตั้งค่า environment และติดตั้ง backend:

   ```powershell
   Copy-Item .env.example backend/.env
   python -m venv backend/.venv
   backend/.venv/Scripts/python.exe -m pip install -r backend/requirements-dev.txt
   ```

   กำหนด `DATABASE_URL` และ `SECRET_KEY` ใน `backend/.env` ตามเครื่องของคุณ เก็บคีย์และรหัสผ่านไว้นอก Git

2. ตรวจ SQL และสร้างตารางด้วย Alembic:

   ```powershell
   Push-Location backend
   .venv/Scripts/python.exe -m alembic upgrade head --sql
   .venv/Scripts/python.exe -m alembic upgrade head
   Pop-Location
   ```

3. ตรวจและเพิ่มข้อมูลไพ่ แล้วเริ่ม API:

   ```powershell
   backend/.venv/Scripts/python.exe -m database.seeds.seed --check-only
   backend/.venv/Scripts/python.exe -m database.seeds.seed
   Push-Location backend
   .venv/Scripts/python.exe -m uvicorn app.main:app --reload
   ```

4. เปิด terminal อีกหน้าต่างสำหรับ frontend:

   ```powershell
   cd frontend
   npm.cmd ci
   npm.cmd run dev
   ```

เปิด URL ที่ Vite แสดงใน terminal; API docs อยู่ที่ `http://127.0.0.1:8000/docs` และ health check ที่ `/api/health` ดูการตั้งค่า frontend เพิ่มเติมใน [frontend/.env.example](frontend/.env.example)

## ✦ ทดสอบและนำขึ้นเว็บ

จากโฟลเดอร์โปรเจกต์:

```powershell
backend/.venv/Scripts/python.exe -m pytest -q backend/tests
backend/.venv/Scripts/python.exe -m database.assets.validate
cd frontend
npm.cmd run build
```

การทดสอบ concurrency กับ MySQL/MariaDB ต้องใช้ฐานทดสอบแยกที่กำหนดไว้ตาม [คู่มือ backend](backend/README.md) ปัจจุบันยังไม่มีชุด frontend unit และ browser E2E tests ที่ตั้งค่าไว้

สำหรับการเผยแพร่ด้วย Docker, Render และ TiDB ให้ทำตาม [คู่มือ Render](docs/render-deployment.md) โดยรัน migration ก่อนอัปเดตแอป และตั้งค่า secrets ในระบบโฮสต์

## เอกสารเพิ่มเติม

- [โครงสร้างระบบ](docs/architecture.md) · [API](docs/api.md) · [ฐานข้อมูล](docs/database.md)
- [กติกาการอ่านไพ่](docs/tarot-rules.md) · [ที่มาและลิขสิทธิ์ภาพ](docs/asset-licenses.md) · [การนำขึ้นเว็บ](docs/deployment.md)
- [ร่างนโยบายความเป็นส่วนตัว](docs/privacy.md) · [สถานะการพัฒนา](docs/milestones.md)

---

✦ พัฒนาด้วยความสนุกและความตั้งใจในการเรียนรู้ ✦

**Programmer** · [Email](mailto:keattisaksari@gmail.com) · LINE: `boxigsl`
