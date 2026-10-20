# HR Attendance Portal

Odoo 18 Community addon that lets employees check in and out **without Odoo user accounts**.

Employees open `/attendance` on a phone, sign in with **employee code + PIN**, and punch with GPS. Shared workplace devices keep using Odoo's standard kiosk URL. Both paths write `hr.attendance` through the same validation, locking, and audit logic.

## What was reused

- `hr.employee` identity, including `emp_code` from `hr_employee_kv` (fallback: `barcode`)
- `hr.employee.pin` as the HR-facing PIN field (digits only, already on the employee form)
- `hr.attendance` for check-in/out, GPS coordinates, IP, browser, and mode
- `_attendance_action_change()` to create/close attendance rows
- Standard kiosk (`/hr_attendance/<company-token>`) for shared devices
- Attendance officer/manager groups for HR review

The browser never talks to PostgreSQL. The frontend never receives a privileged technical account. Public routes only call `sudo()` after PIN or session checks, and only for that employee.

## Employee login

1. Open `/attendance`
2. Enter employee code (`emp_code` or badge ID) and PIN
3. Allow GPS
4. Check in / check out

Wrong employee codes and wrong PINs return the same error: `invalid_credentials`.

## PIN storage and rotation

Odoo Community stores `hr.employee.pin` in plaintext so the stock kiosk and POS cashier switch keep working. This addon also writes a **pbkdf2-sha512** hash to `attendance_pin_hash` whenever the PIN is set. The portal verifies the hash. PINs are never returned to the frontend and never written to audit events.

**Reset / rotate a PIN**

1. HR opens the employee form (Officer or User rights)
2. Enter a new numeric PIN in **Attendance PIN**
3. Save
4. The hash is rotated and existing portal sessions for that employee are revoked
5. Temporary lockouts expire on their own; they are never permanent

## GPS and workplaces

Workplaces (`hr.attendance.location`) hold coordinates and an allowed radius. Do not put coordinates in controllers.

Default company policies (Attendances settings):

| Situation | Default |
| --- | --- |
| Missing GPS on a personal device | Reject |
| GPS accuracy worse than the workplace limit | Needs review |
| Outside the allowed radius | Needs review |
| No workplace configured | Needs review |
| Punch photo with no detectable face | Needs review |
| Face check library unavailable | Needs review |
| Kiosk without GPS | Allowed (device is assumed to be on site) |

Needs-review punches still create `hr.attendance` and appear under **Attendances → Exceptions & Audit**.

Punch photos on personal devices are checked for **at least one face** using OpenCV YuNet (see `requirements.txt`). A still with no face defaults to Needs Review. This is presence only, not identity matching or anti-spoofing.

## Shared kiosk

Use the existing company kiosk URL. Enable **Employee PIN Identification** in Attendances settings. This addon intercepts barcode and manual kiosk punches so they:

- verify PIN with the hashed verifier
- take an advisory lock per employee
- write an audit event
- revoke the kiosk session after the punch so the next person cannot reuse it

## Rate limits

Failed PIN attempts are counted per employee code (hashed) and per IP. After the configured threshold the employee or IP is locked **temporarily** (1 / 5 / 15 minutes). Unauthenticated requests cannot permanently disable check-in.

## HR screens

- Attendances → **Exceptions & Audit**
- Attendances → **Workplaces**
- Attendances → **Kiosk Devices**
- Attendance form: workplace, GPS accuracy, review status, event history
- Settings → Attendances → **Attendance Portal**
