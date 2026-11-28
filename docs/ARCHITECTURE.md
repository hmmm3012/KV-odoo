# Kiến trúc — Odoo 19 Kiến Việt (custom HR)

Trạng thái khảo sát ngày 28/11/2026 trên nhánh `19.0-upgrade`, DB test `odoo_19_test` (73 module `installed`). Chỉ mô tả code và dữ liệu đã kiểm trên stack test, không mô tả production.

## Bố cục repo

- Gốc `kv-custom-repo` là cây Odoo 19 đầy đủ (`odoo/`, `addons/`) cộng phần custom.
- Agent **chỉ sửa** `custom/`, `scripts/`, và file harness ở gốc (`AGENTS.md`, `docs/`, `init.sh`, `feature_list.json`, `PROGRESS.md`, `.cursor/rules/`).
- Không sửa core `odoo/` hay `addons/`.
- Script nâng cấp rehearsal (không thuộc repo harness): `/home/debian1/kv-odoo-19-upgrade/scripts/` (gồm `q.sh`, bản `xpath_check.py` cũ, `rehearsal-resanitize.sql`).
- Compose test: `/home/debian1/kv-odoo-19-upgrade/docker-compose.yml`, project `kv-odoo-19-test`, mount `kv-custom-repo/custom` vào `/opt/odoo-custom`.

## Bốn module custom

### `hr_attendance_portal`

Cổng chấm công `/attendance` (mã NV + PIN, không cần tài khoản Odoo), GPS/WiFi (IP công cộng), ảnh chấm công, kiosk dùng chung, workplaces, audit. Ghi `hr.attendance` sau khi kiểm PIN/session.

- Nhóm riêng: `hr_attendance_portal.group_hr_attendance_site_captain` (EN: Department Captain, VI: **Đội trưởng bộ phận**). Chỉ đọc nhân viên/chấm công trong phòng được ủy quyền, không tạo/sửa/xóa.
- Test: 9 file trong `custom/hr_attendance_portal/tests/` (`test_attendance_api`, concurrency, geofence, public IP, security, session, timesheet, department_structure, face_pipeline).
- README hiện có (`custom/hr_attendance_portal/README.md`) vẫn mở đầu bằng "Odoo 18"; module trên nhánh này đã port lên 19 (`cd8608e4b13` và các commit sau).

### `hr_employee_kv`

Mở rộng nhân viên: mã NV, ảnh CCCD, nút **Tự nhập thông tin** (ưu tiên QR, fallback OCR; không tự chạy lúc upload), badge, giấy giới thiệu, ẩn menu Thảo luận/Lịch, override tiếng Việt (tab **Hợp đồng & Lương**).

- Model/parser: `custom/hr_employee_kv/models/models.py`, `custom/hr_employee_kv/models/id_card_qr.py`, `custom/hr_employee_kv/models/id_card_ocr.py`. Parser được phép trả khóa dict nội bộ `gender`; `_id_card_fields()` map sang `sex` trước khi ghi `hr.employee`.
- Views: `custom/hr_employee_kv/views/hr_employee_views.xml`, `custom/hr_employee_kv/views/hide_unused_menus.xml`, OWL widget `custom/hr_employee_kv/static/src/id_card_autofill.js`.
- Test: 4 file (`test_badge`, `test_id_card_ocr`, `test_id_card_qr`, `test_intro_letter_templates`).

### `hr_department_access`

Thêm `res.users.hr_authorized_department_ids` (chỉ Settings / `base.group_system` sửa được). Khi danh sách không rỗng, Python AND thêm domain vào `ir.rule._compute_domain` cho `hr.employee`, `hr.attendance`, `hr.version`, ... để quyền Administrator không OR phá hạn chế. Danh sách rỗng = truy cập toàn công ty.

- Test: `custom/hr_department_access/tests/test_department_access.py`.

### `kv_hr_contract`

Đánh số hợp đồng `HD.YYYY.NNN` trên `hr.version` (Odoo 19 đã gộp `hr.contract` vào `hr.version`). Đổi lương / tạo version cùng hợp đồng giữ số cũ; gia hạn (đổi `contract_date_start`) cấp số mới. PDF: route `/contracts/pdf/<int:contract_id>` (`auth="user"`).

- Test trong repo: **0 file**. Bản shell rollback (không phải TransactionCase) nằm ngoài repo tại `/home/debian1/kv-odoo-19-upgrade/tests/test_contract_autonumber.py` — sẽ chuyển thành unit test ở Giai đoạn 3, không hard-code số thứ tự phụ thuộc dữ liệu DB tay.

## Nhóm quyền thật (đã đối chiếu XML + DB test)

| Vai trò thường gọi | XMLID / ghi chú | Tên EN | Tên VI trên DB test |
| --- | --- | --- | --- |
| Người dùng nội bộ | `base.group_user` | Internal User | Người dùng Nội bộ |
| Quyền truy cập | `base.group_erp_manager` | Access Rights | Quyền truy cập |
| Admin / Cài đặt | `base.group_system` | Role / Administrator | Cài đặt |
| Nhân sự (Officer) | `hr.group_hr_user` | Officer: Manage all employees | Chuyên viên: Quản lý toàn bộ nhân viên |
| Quản trị HR | `hr.group_hr_manager` | Administrator | Quản trị viên |
| Đội trưởng bộ phận | `hr_attendance_portal.group_hr_attendance_site_captain` | Department Captain | Đội trưởng bộ phận |
| AI Read Only | **Không có xmlid** trong `ir_model_data`. Có trong DB test (id 116), comment "Read-only access for AI assistant". | AI Read Only | (chưa dịch) |
| Chấm công — đọc của mình | `hr_attendance.group_hr_attendance_own_reader` | User: Read his own attendances | Người dùng: Đọc chấm công của chính mình |
| Chấm công — officer | `hr_attendance.group_hr_attendance_officer` | Officer: Manage attendances | Người phụ trách: Quản lý chấm công |
| Ngày nghỉ — officer | `hr_holidays.group_hr_holidays_user` | Officer: Manage all requests | Người phụ trách: Quản lý tất cả đơn |

Lưu ý: hội thoại đôi lúc gọi "Đội trưởng bãi". Tên trên hệ thống là **Đội trưởng bộ phận**. Không bịa xmlid cho nhóm AI Read Only.

## Stack đã cài (73 module, chỉ HR)

Đã gỡ `project`, `project_todo`, `hr_timesheet`, `account`, `stock`, `spreadsheet_dashboard`, `l10n_vn`, ... Menu gốc Thảo luận (`mail`) và Lịch (`calendar`) **ẩn bằng view** trong `hr_employee_kv` (không gỡ được: `mail` là nền, `calendar` là dependency của `hr_holidays`).

Menu chính hiện còn: Liên hệ, Nhân viên, Chấm công, Ngày nghỉ, Ứng dụng, Cài đặt.

Một số module phụ vẫn installed vì bị kéo theo HR (ví dụ `payment`, `product`, `sales_team`, `sms`, `spreadsheet`) — không phải app người dùng đang xài. Khi inherit view, kiểm XPath trên đúng 73 module này, không giả định `account` / `stock` / `project` / `hr_timesheet` còn tồn tại.

## Ranh giới

Xem `docs/SAFETY.md`. Kiểm chứng runtime: `./init.sh` (nền). Lệnh verify đầy đủ trên DB tạm sẽ được thêm ở Giai đoạn 2.
