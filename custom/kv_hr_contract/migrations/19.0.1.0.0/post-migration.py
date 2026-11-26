"""Restore KV contract numbers after OpenUpgrade 18 -> 19.

OpenUpgrade's hr post-migration overwrites hr_version.name with the
employee name for every version, which wipes the "HD.<year>.<nnn>" numbers.
scripts/pre-openupgrade-kv.sql copies hr_contract.name into
kv_legacy_contract_name before the upgrade; the column survives the
hr_contract -> hr_version rename and is used here to put the numbers back.
"""
import logging

_logger = logging.getLogger(__name__)
LEGACY_LINK = "openupgrade_legacy_19_0_contract_id"


def _column_exists(cr, table, column):
    cr.execute(
        "SELECT 1 FROM information_schema.columns WHERE table_name=%s AND column_name=%s",
        (table, column),
    )
    return bool(cr.fetchone())


def migrate(cr, version):
    if not version:
        return
    if not _column_exists(cr, "hr_version", "kv_legacy_contract_name"):
        _logger.warning(
            "kv_hr_contract: kv_legacy_contract_name missing; contract numbers "
            "were not preserved (run scripts/pre-openupgrade-kv.sql first)."
        )
        return
    cr.execute(
        """
        UPDATE hr_version
           SET name = kv_legacy_contract_name
         WHERE kv_legacy_contract_name IS NOT NULL
        """
    )
    _logger.info("kv_hr_contract: restored %s contract numbers", cr.rowcount)
    if _column_exists(cr, "hr_version", LEGACY_LINK):
        # Versions created by OpenUpgrade for employees without a contract
        # got the employee name; they never had a contract number.
        cr.execute(
            f"""
            UPDATE hr_version
               SET name = NULL
             WHERE {LEGACY_LINK} IS NULL
               AND employee_id IS NOT NULL
            """
        )
        _logger.info("kv_hr_contract: cleared name on %s non-contract versions", cr.rowcount)
    cr.execute(
        """
        UPDATE hr_version
           SET contract_year = COALESCE(substring(name from '^HD\\.(\\d+)\\.\\d+$')::int, 0),
               contract_number = COALESCE(substring(name from '^HD\\.\\d+\\.(\\d+)$')::int, 0)
        """
    )
