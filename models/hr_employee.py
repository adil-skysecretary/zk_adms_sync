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
    biometric_device_sn = fields.Char(
        string='Machine Serial Number (SN)',
        copy=False,
        index=True,
        help="The Serial Number of the physical machine this employee uses. Found in the device URL (SN=...).",
        groups="hr.group_hr_user"
    )