# PROGRESS.md — Kiến Việt Odoo 19 harness

Nhật ký tiến độ giữa các phiên. Đây là nguồn sự thật cùng `feature_list.json`, không lấy trạng thái từ đoạn chat.

## Trạng thái hiện tại

- Nhánh: `19.0-upgrade` (local, không push)
- Việc đang mở (`in_progress`, WIP=1): không có (Pha 1 đã passing)
- Việc tiếp theo: Giai đoạn 2 — `harness-p2-agent-verify`

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
