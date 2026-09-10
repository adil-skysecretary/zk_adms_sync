from odoo import fields, models

class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    biometric_id = fields.Char(
        string='Biometric Device ID',
        copy=False,
        index=True,
        help="User ID / PIN registered on the physical biometric device",
        groups="hr.group_hr_user"
    )