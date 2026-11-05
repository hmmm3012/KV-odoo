# -*- coding: utf-8 -*-


def migrate(cr, version):
    """Rename final overtime status: hr_reviewed -> captain_reviewed (one-time)."""
    cr.execute(
        """
        UPDATE hr_attendance
           SET overtime_state = 'captain_reviewed'
         WHERE overtime_state = 'hr_reviewed'
        """
    )
    cr.execute(
        """
        UPDATE hr_attendance
           SET closed_from_overtime_state = 'captain_reviewed'
         WHERE closed_from_overtime_state = 'hr_reviewed'
        """
    )
    cr.execute(
        """
        UPDATE hr_attendance_overtime_case
           SET state = 'captain_reviewed'
         WHERE state = 'hr_reviewed'
        """
    )
    cr.execute(
        """
        UPDATE hr_attendance_overtime_case
           SET closed_from_state = 'captain_reviewed'
         WHERE closed_from_state = 'hr_reviewed'
        """
    )
