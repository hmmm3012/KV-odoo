# Checklist review PR trước khi áp lên production

- [ ] Chỉ chứa thay đổi `custom/` / `scripts/` / harness; không có diff core `odoo/` `addons/`.
- [ ] Không có secret, dump, PII, ảnh CCCD thật.
- [ ] `./scripts/agent-verify.sh <module>` đã chạy trên DB tạm, evidence có trong PR / `feature_list.json`.
- [ ] XPath đã kiểm trên stack 73 module (không inherit `hr_timesheet` / `account` / `stock` / `project`).
- [ ] Quy ước Odoo 19: `hr.version`, `sex`, `models.Constraint`, `type=jsonrpc`.
- [ ] Dịch tiếng Việt cho chuỗi UI mới.
- [ ] Không lên production trước khi rehearsal trên `kv-odoo-19-test` ổn; không deploy sau 16:00 UTC+7 nếu có downtime.
- [ ] Runbook nâng cấp (`/home/debian1/kv-odoo-19-upgrade/UPGRADE-18-TO-19-RUNBOOK.md`) đã cập nhật nếu quy trình thay đổi.
