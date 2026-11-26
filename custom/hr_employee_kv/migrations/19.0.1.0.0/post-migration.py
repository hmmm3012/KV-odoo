"""Fix hr.version state for archived employees after OpenUpgrade 18 -> 19.

OpenUpgrade's hr post-migration copies hr_employee.active into every
hr_version row, so all versions (incl. ex-contracts) of archived employees
become archived. Odoo 19 then cannot find a current version for them
(_compute_current_version_id searches active versions only) and their form
shows an empty department/job/contract. In Odoo 19 archiving an employee
does not archive its versions, so re-activate them and set
current_version_id like Odoo does (latest date_version <= today, else first).
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    cr.execute(
        """
        UPDATE hr_version v
           SET active = true
          FROM hr_employee e
         WHERE v.employee_id = e.id
           AND NOT e.active
           AND NOT v.active
        """
    )
    _logger.info("hr_employee_kv: re-activated %s versions of archived employees", cr.rowcount)
    cr.execute(
        """
        UPDATE hr_employee e
           SET current_version_id = sub.version_id
          FROM (
                SELECT DISTINCT ON (v.employee_id) v.employee_id, v.id AS version_id
                  FROM hr_version v
                 WHERE v.active AND v.employee_id IS NOT NULL
                 ORDER BY v.employee_id,
                          (v.date_version <= current_date) DESC,
                          CASE WHEN v.date_version <= current_date THEN v.date_version END DESC NULLS LAST,
                          v.date_version, v.id
               ) sub
         WHERE e.id = sub.employee_id
           AND e.current_version_id IS NULL
        """
    )
    _logger.info("hr_employee_kv: set current_version_id on %s employees", cr.rowcount)
