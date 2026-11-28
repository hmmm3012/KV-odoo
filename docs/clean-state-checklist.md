# Clean-state checklist — kết thúc phiên

Phiên chỉ được coi là xong khi tất cả mục dưới đây đạt:

- [ ] `./init.sh` exit 0 (dưới 10 giây khi đã ấm).
- [ ] Cổng kiểm chứng liên quan đã chạy (`./scripts/agent-verify.sh <module>` và/hoặc `./scripts/e2e-smoke.sh`).
- [ ] `PROGRESS.md` và `feature_list.json` khớp trạng thái thật (không `passes: true` khi thiếu evidence).
- [ ] Không để việc dở chưa ghi; tối đa một mục `in_progress`.
- [ ] Không để file debug/tạm: chạy `./scripts/cleanup.sh` (idempotent).
- [ ] Không commit mật khẩu, `.env`, dump DB, hay PII/ảnh CCCD thật.
- [ ] Không đụng production / staging 18 / không làm bẩn `odoo_19_test`.
- [ ] Commit sạch trên `19.0-upgrade` (không push trừ khi được yêu cầu).
- [ ] Nếu phiên dài: cập nhật `session-handoff.md`.
