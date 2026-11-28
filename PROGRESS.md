# PROGRESS.md — Kiến Việt Odoo 19 harness

Nhật ký tiến độ giữa các phiên. Đây là nguồn sự thật cùng `feature_list.json`, không lấy trạng thái từ đoạn chat.

## Trạng thái hiện tại

- Nhánh: `19.0-upgrade` (local, không push)
- Việc đang mở (`in_progress`, WIP=1): không có (Pha 1–4 đã ghi evidence)
- Việc tiếp theo: nợ sản phẩm ngoài harness (portal chấm công, AccessError `hr.version`, PDF hợp đồng); CI unit-test chờ self-hosted runner — chưa push, chưa trigger Actions

## Nhật ký phiên

### 2026-11-28 — Giai đoạn 1: Khởi tạo và System of Record

- Đọc lại Page kế hoạch `5e856e1b-a8a9-4261-bb2f-0e80ddf16f79`.
- Khảo sát repo `/home/debian1/kv-odoo-19-upgrade/kv-custom-repo` trên nhánh `19.0-upgrade` (HEAD trước khi bắt đầu: `edc965a140a`).
- Xác nhận 4 module custom, 14 file unit test (0 test trong `kv_hr_contract`), stack 73 module đã cài, HTTP `127.0.0.1:8269/web/login` và `/attendance` trả 200.
- Nhóm quyền ghi đúng theo DB / XML (không dùng tên nhớ sai):
  - `hr.group_hr_user` — Officer: Manage all employees / Chuyên viên: Quản lý toàn bộ nhân viên
  - `hr_attendance_portal.group_hr_attendance_site_captain` — Department Captain / **Đội trưởng bộ phận** (không phải "Đội trưởng bãi")
  - `base.group_system` — Role / Administrator / Cài đặt
  - `AI Read Only` — có trong DB test (id 116) nhưng **không có xmlid** trong `ir_model_data`
- `.gitignore` gốc đang bỏ qua mọi file chấm (`.*`); đã thêm ngoại lệ cho thư mục `.cursor` để rule được commit.
- Artifact đã thêm: xem danh sách trong commit Giai đoạn 1.
- Fresh Session Test đạt lúc 2026-11-28 09:09 +07 (UTC+7):
  - `./init.sh` exit 0; lần nguội 10.512s, hai lần sau 0.912s / 0.819s (dưới 10s khi đã ấm)
  - `AGENTS.md` 50 dòng; mọi path trong AGENTS.md và `.cursor/rules` tồn tại
  - `python3 -m json.tool feature_list.json` hợp lệ
  - HTTP `127.0.0.1:8269/web/login` và `/attendance` = 200
- `harness-p1-system-of-record` chuyển `passing` / `passes: true` với evidence ở trên.

## Việc đã biết còn lại (chưa làm ở Pha 1)

- Giai đoạn 2: lệnh verify đầy đủ, DB template/tạm, linter bất biến, ruff, Makefile
- Giai đoạn 3: unit test `kv_hr_contract`, smoke menu/i18n, e2e, evaluator
- Giai đoạn 4: clean-state, QUALITY.md, CI


### 2026-11-28 — Giai đoạn 2: Phản hồi máy móc và môi trường cô lập

- Artifact: `scripts/agent-verify.sh`, `scripts/agent-reset-testdb.sh`, `scripts/xpath_check.py`, `scripts/check-odoo19-invariants.py`, `scripts/installed-modules-19.txt`, `pyproject.toml`, `Makefile`.
- Template DB `odoo_19_test_tpl` tạo bằng `pg_dump`/`psql` từ `odoo_19_test` (không ngắt kết nối, không restart container). Sau đó chạy `rehearsal-resanitize.sql` và `IS_TEMPLATE true`. `odoo_19_test` vẫn 342 MB / 73 module; HTTP `/web/login` = 200.
- `./scripts/agent-reset-testdb.sh --create` / `--drop` chỉ chấp nhận tên `odoo_19_agent_*`; từ chối `odoo_19_test`.
- Linter ruff (standalone `~/.local/bin/ruff` 0.17.6, `pyproject.toml` chọn E9+F, bỏ qua F401/F841 và F821 trong `custom/**/scripts/**`) và `check-odoo19-invariants.py` + xpath trên 73 module: PASS.
- Runtime `./scripts/agent-verify.sh` (DB tạm, filestore riêng, không publish cổng, không đụng `odoo_19_test`):
  - `kv_hr_contract`: PASS (0 unit test trong module — đúng hiện trạng; nâng cấp sạch)
  - `hr_department_access`: static PASS; runtime 0 failed, 1 error / 6 tests — `test_cannot_read_or_create_outside_department` AccessError khi tạo `hr.version` (record rule phòng ban lúc create employee). Đã thêm `hr.group_hr_contract_manager` vào user test nhưng lỗi vẫn còn (không phải thiếu ACL). Đây là lỗi sẵn có, không bịt PASS.
  - `hr_employee_kv`: static PASS; runtime 0 failed, 1 error / 19 tests — `TestIntroLetterTemplates.test_thanh_nien_docx_build` `ValueError: Invalid field 'gender' in 'hr.employee'` (sót Odoo 19).
  - `hr_attendance_portal`: static PASS; runtime 5 failed, 23 errors / 130 tests (khoảng 6 phút). Lỗi rải API/security/session/IP/concurrency/HTTP — tồn đọng port 19, sẽ xử lý sau, không sửa hàng loạt trong Pha 2.
- Host không có `lxml`/`python3-venv` (PEP 668). ruff cài bằng installer standalone. xpath chạy trong container `kv-odoo-19-test-odoo-1`.


### 2026-11-28 — Giai đoạn 3: Cổng kép, phạm vi và chống tuyên bố xong sớm

- `custom/kv_hr_contract/tests/test_contract_autonumber.py`: 7 test, `./scripts/agent-verify.sh kv_hr_contract` PASS (0 fail / 0 error). Số HĐ không hard-code. PDF HTTP bị 500 (`create_pdf` gọi `strftime` trên date=False); test chỉ khóa URL `/contracts/pdf/<id>`.
- `custom/hr_employee_kv/tests/test_menus_and_i18n.py` + sửa `test_intro_letter_templates.py` (`gender` → `sex`): `./scripts/agent-verify.sh hr_employee_kv` PASS (24 test, 0 fail / 0 error).
- E2E: không dùng Playwright (không có trong image `kv-odoo:19`, không cài browser trên server). `./scripts/e2e-smoke.sh` PASS (HTTP + kiểm file widget). `get_views`/menu nằm ở unit test.
- `docs/evaluator-rubric.md`, `docs/sprint-contract.md`. Pass-gate vẫn yêu cầu evidence; phiên viết code không tự chấm đạt.

### 2026-11-28 — Giai đoạn 4: Clean-state, CI và chống entropy

- `docs/QUALITY.md`, `docs/clean-state-checklist.md`, `docs/PR-REVIEW-PRODUCTION.md`, `session-handoff.md`.
- `scripts/cleanup.sh` (idempotent, EXIT 0): dọn `/tmp/kv-odoo-agent-*`, leftover `odoo_19_agent_*` nếu có, `__pycache__` dưới custom/scripts. Không đụng `odoo_19_test` / template / production.
- `scripts/check-i18n-vi.py` EXIT 0: `hr_department_access` và `kv_hr_contract` chưa có `i18n/vi.po` (nợ sẵn, không `--strict`).
- `scripts/check-doc-drift.py` EXIT 0 (113 path trong AGENTS/docs/rules).
- `.github/workflows/odoo19-ci.yml`: job `static` chạy được trên GitHub-hosted (ruff, lxml, xpath trên cây Odoo vendored). Job `odoo-tests` `if: false`, `runs-on: self-hosted` vì image `kv-odoo:19` chỉ có trên server công ty; **chưa đăng ký runner, chưa trigger GitHub Actions** (không push). Tương đương job static đã chạy local: PASS.
- `./init.sh` (gắn thêm i18n + doc-drift) và `./scripts/e2e-smoke.sh` đều EXIT 0. HTTP login 200.

Nợ sản phẩm còn lại (không thuộc harness): test `hr_attendance_portal` (5 fail + 23 error / 130), AccessError `hr.version` khi tạo NV trong `hr_department_access`, `create_pdf` 500 khi thiếu date.

