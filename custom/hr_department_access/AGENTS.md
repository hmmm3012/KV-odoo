# hr_department_access

Giới hạn user theo phòng ban: `res.users.hr_authorized_department_ids` (chỉ `base.group_system` sửa).

- Danh sách rỗng = truy cập HR toàn công ty. Danh sách có dữ liệu = AND domain vào `ir.rule._compute_domain` (không viết rule nhóm có thể bị OR với domain `[(1, '=', 1)]`).
- Domain Odoo 19 phải dùng `hr.version` và `hr.attendance.overtime.line`, không `hr.contract`.
- `sudo()` giữ hành vi cũ cho portal punch và cron.
- Test: `tests/test_department_access.py`.
