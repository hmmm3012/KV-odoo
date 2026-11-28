# AGENTS.md — Kiến Việt Odoo 19

Repo custom HR cho Odoo 19 (`kv-custom-repo`, nhánh làm việc `19.0-upgrade`).
Mục tiêu không phải viết thật nhiều code, mà để phiên sau tiếp tục được mà không phải đoán.

Chỉ làm việc trong `custom/`, `scripts/` và các file harness ở gốc repo.
Không sửa core `odoo/` hay `addons/`.

## Khởi động phiên

1. Chạy `pwd`, xác nhận đúng thư mục gốc repo này.
2. Đọc `PROGRESS.md` (trạng thái đã kiểm chứng và bước tiếp theo).
3. Đọc `feature_list.json`, chọn đúng **một** mục ưu tiên cao nhất chưa xong (`WIP=1`).
4. Xem `git log --oneline -5` và `git status -sb`.
5. Chạy `./init.sh`.
6. Nếu kiểm tra nền đỏ: sửa nền trước, chưa làm tính năng mới.

## Ràng buộc cứng

- Không sửa core `odoo/` hay `addons/`. Không đụng production (`/home/debian1/KV-odoo`, compose `kv-odoo`, `hrmkienviet.ddns.net`) và không đụng staging Odoo 18 (`/home/debian1/KV-odoo-staging`, compose `kv-odoo-staging`).
- Không gây downtime server công ty từ 16:00 UTC+7 (giờ chấm công). Stack test `kv-odoo-19-test` / `odoo.psm.im` được phép làm trước mốc này, nhưng vẫn không đụng production.
- Không commit mật khẩu, API key, hay dữ liệu nhân sự thật / ảnh CCCD thật. Evidence chỉ lưu lệnh, kết quả và hash commit.
- Odoo 19: dùng `hr.version` (không còn `hr.contract`), field `sex` trên nhân viên (không ghi `gender`), `models.Constraint`, HTTP JSON `type="jsonrpc"`.
- Mọi view kế thừa phải được kiểm XPath trên đúng stack 73 module chỉ HR (đã gỡ `project`, `hr_timesheet`, `account`, `stock`).
- Chỉ một mục `in_progress` tại một thời điểm. Không đánh `passing` / `passes: true` khi chưa có evidence kiểm chứng.
- DB anh Minh test tay là `odoo_19_test` trên `odoo.psm.im`. Kiểm chứng đầy đủ chạy trên DB tạm. Không làm bẩn `odoo_19_test`. Nếu bắt buộc phải cập nhật DB đó, chạy lại `/home/debian1/kv-odoo-19-upgrade/scripts/rehearsal-resanitize.sql`.

## Bản đồ ngắn (chi tiết nằm ở docs/)

- `custom/hr_attendance_portal` — cổng `/attendance`, GPS/WiFi, PIN, kiosk, Đội trưởng bộ phận
- `custom/hr_employee_kv` — mã NV, CCCD (nút Tự nhập thông tin), badge, giấy GT, ẩn menu thừa, i18n
- `custom/hr_department_access` — giới hạn user theo phòng ban (`hr_authorized_department_ids`)
- `custom/kv_hr_contract` — số HĐ `HD.YYYY.NNN` trên `hr.version`, PDF `/contracts/pdf/<id>`
- Stack test: project Docker `kv-odoo-19-test`, image `kv-odoo:19`, cổng `127.0.0.1:8269`, DB tay `odoo_19_test`, 73 module chỉ HR

## Kiểm chứng

- Khởi động / kiểm tra nền: `./init.sh`
- Kiểm chứng đầy đủ theo module trên DB tạm: `./scripts/agent-verify.sh <ten_module>`
- Tạo/xóa DB tạm: `./scripts/agent-reset-testdb.sh --create` / `--drop <name>`

## Tài liệu chuyên đề (đọc khi đúng việc)

- `docs/ARCHITECTURE.md` — bản đồ 4 module custom và nhóm quyền
- `docs/ODOO19.md` — quy ước API / tương thích Odoo 19
- `docs/SAFETY.md` — ranh giới staging / production / DB test
- `.cursor/rules/odoo19-python.mdc`, `.cursor/rules/odoo19-views.mdc`, `.cursor/rules/odoo19-i18n.mdc`, `.cursor/rules/deploy-safety.mdc` — quy tắc theo glob
- `custom/<module>/AGENTS.md` — ràng buộc sát từng module
- `custom/docs/ACM_Agent_Operating_Guide v0.1.md` — hướng dẫn ACM cũ (tham khảo, không thay harness này)
- `feature_list.json` — nguồn chân lý về việc cần làm và evidence
- `PROGRESS.md` — nhật ký tiến độ giữa các phiên
- `docs/evaluator-rubric.md`, `docs/sprint-contract.md` — chấm tách biệt và hợp đồng sprint UI
- `scripts/e2e-smoke.sh` — smoke HTTP (không dùng Playwright)
- `scripts/agent-verify.sh`, `scripts/agent-reset-testdb.sh` — kiểm chứng đầy đủ trên DB tạm
- `docs/QUALITY.md`, `docs/clean-state-checklist.md`, `docs/PR-REVIEW-PRODUCTION.md`, `session-handoff.md`
- `scripts/cleanup.sh`, `scripts/check-i18n-vi.py`, `scripts/check-doc-drift.py`
- `.github/workflows/odoo19-ci.yml` — job static chạy được trên GitHub-hosted; job unit test cần self-hosted + image `kv-odoo:19` (hiện bị skip)
