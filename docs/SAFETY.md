# An toàn môi trường — Odoo 19 Kiến Việt

Bất biến này phải được tôn trọng bằng hành động, không chỉ bằng lời nhắc. Linter (Giai đoạn 2) sẽ bắt hostname production và sửa ngoài `custom/` / `scripts/`.

## Ba môi trường (không được nhầm)

| Môi trường | Đường dẫn / compose | Domain / cổng | Được phép làm gì |
| --- | --- | --- | --- |
| Production Odoo 18 | `/home/debian1/KV-odoo`, compose `kv-odoo` | `hrmkienviet.ddns.net`, `127.0.0.1:8069` | **Không** đụng, restart, chạy lệnh, sửa file, hay query ghi. |
| Staging Odoo 18 | `/home/debian1/KV-odoo-staging`, compose `kv-odoo-staging` | (cổng `127.0.0.1:8169`) | **Không** đụng trong công việc harness 19. |
| Test Odoo 19 | `/home/debian1/kv-odoo-19-upgrade`, compose `kv-odoo-19-test` | `odoo.psm.im`, `127.0.0.1:8269` / `8272` | Được làm việc. Image `kv-odoo:19`. DB tay: `odoo_19_test`. |

`init.sh` (và lệnh verify đầy đủ ở Giai đoạn 2) chỉ *đọc* hoặc tạo DB tạm trên project `kv-odoo-19-test`. Không gọi `docker compose` với project `kv-odoo` hay `kv-odoo-staging`.

## Mốc 16:00 UTC+7

Không gây downtime server công ty từ 16:00 UTC+7 (giờ nhân sự chấm công trên production). Stack test `kv-odoo-19-test` có thể làm việc trước mốc này, nhưng **production vẫn tuyệt đối không đụng** bất kỳ giờ nào.

## Bảo vệ `odoo_19_test`

- Đây là DB anh Minh dùng để test tay trên `odoo.psm.im`.
- Không chạy `-u`, `--test-enable`, uninstall, hay script ghi vào `odoo_19_test` trừ khi anh Minh yêu cầu rõ. Kiểm chứng đầy đủ dùng DB tạm clone từ template (Giai đoạn 2).
- Nếu buộc phải cập nhật `odoo_19_test` (ví dụ nâng cấp module theo yêu cầu), chạy lại `/home/debian1/kv-odoo-19-upgrade/scripts/rehearsal-resanitize.sql` để tắt cron, mail server, fetchmail và giữ `web.base.url=https://odoo.psm.im`.
- Stack test đã đặt `ODOO_MAX_CRON_THREADS=0`.

## Bí mật và dữ liệu cá nhân

- Không commit mật khẩu, API key, file `.env`, dump DB, ảnh CCCD thật, hay dữ liệu nhân sự thật.
- Test chỉ dùng dữ liệu tổng hợp (nhân viên giả, ảnh QR/OCR mẫu).
- Evidence trong `feature_list.json` / `PROGRESS.md` chỉ lưu lệnh, kết quả (PASS/FAIL, số test), và hash commit — không lưu PII.

## Git

- Làm việc trên nhánh local `19.0-upgrade`.
- Không `git push` trừ khi anh Minh yêu cầu rõ ràng.
- `.gitignore` gốc bỏ qua mọi file chấm (`.*`) trừ một số ngoại lệ; ngoại lệ `.cursor` đã được thêm để commit rule harness.
