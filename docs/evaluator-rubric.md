# Evaluator rubric — Odoo 19 Kiến Việt

Phiên viết code (generator) không tự chấm đạt. Một lượt chấm riêng đọc rubric này, `feature_list.json`, log `./scripts/agent-verify.sh`, và diff.

Chấm mỗi mục 0–2 (0 = không đạt, 1 = một phần, 2 = đạt). Chỉ nhận việc khi không có điểm 0 và các cổng bắt buộc đã có evidence.

| Tiêu chí | 2 | 0 |
| --- | --- | --- |
| Đúng hành vi | Đúng phạm vi WIP=1, đúng Odoo 19 (`hr.version`, `sex`, `jsonrpc`) | Sai model/field, phá menu/quyền, hoặc làm ngoài mục đang mở |
| Kiểm chứng | `./scripts/agent-verify.sh <module>` (và e2e/HTTP nếu đụng view/JS) đã chạy, evidence ghi rõ lệnh và kết quả | Chỉ nhìn code; bỏ qua test đỏ; đánh `passes: true` không có evidence |
| Kỷ luật phạm vi | Chỉ sửa `custom/` / `scripts/` / file harness; không đụng production / staging 18 / `odoo_19_test` | Có thay đổi core, hostname production, hoặc ghi DB tay |
| Chịu restart | `./init.sh` vẫn xanh; phiên sau đọc `PROGRESS.md` + `feature_list.json` là làm tiếp được | Để việc dở không ghi, hoặc nền init đỏ |
| Dễ bảo trì | Có test/linter cho bất biến mới; thông báo lỗi chỉ cách sửa | Logic chỉ sống trong chat; xpath/test bỏ sót |
| Sẵn sàng bàn giao | Commit sạch, không secret/PII, PROGRESS khớp thật | Commit lẫn dump/mật khẩu, hoặc báo xong khi test còn đỏ mà không nói |

Khi test sản phẩm còn đỏ từ trước (ví dụ portal chấm công), evaluator phải ghi rõ số fail/error, không được gộp thành "verify PASS".
