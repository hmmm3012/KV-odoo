import logging
from datetime import date
import re
from odoo import _, api, fields, models
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
import base64
from odoo.http import request
from odoo import http
from io import BytesIO

_logger = logging.getLogger(__name__)


class KVHRContract(models.Model):
    _inherit = "hr.contract"
    _description = "KV HR Contract"

    contract_year = fields.Integer(compute="_compute_contract_parts", store=True)
    contract_number = fields.Integer(compute="_compute_contract_parts", store=True)
    # contract_period = fields.Char(string="Thời han hợp đồng", required=True)

    @api.depends("name")
    def _compute_contract_parts(self):
        for record in self:
            # Regular expression to match the format "HD.2024.1"
            matches = re.match(r"HD\.(\d+)\.(\d+)$", record.name)
            if matches:
                record.contract_year = int(matches.group(1))
                record.contract_number = int(matches.group(2))
            else:
                # Default/fallback values if the name doesn't match the expected format
                record.contract_year = 0
                record.contract_number = 0

    def check_report(self):
        _logger.info("clicked button")
        pass

    def default_get(self, fields_list):
        # _logger.info("default_get has been called")
        defaults = super(KVHRContract, self).default_get(fields_list)
        defaults["name"] = self._compute_default_name()
        return defaults

    def _compute_default_name(self):
        default = self.get_latest_contract_name()
        return default

    def get_latest_contract_name(self):
        contracts = self.env["hr.contract"].search(
            [("contract_year", "=", 2025)], order="contract_number desc", limit=1
        )
        if contracts:
            formatted_number = "{:03}".format(contracts[0].contract_number + 1)
        else :
            formatted_number = "001"       
        return "HD.2025." + formatted_number

    def generate_pdf_action(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_url",
            "url": f"/contracts/pdf/{self.id}",
            "target": "new",
        }
