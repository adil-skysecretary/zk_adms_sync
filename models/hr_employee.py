from odoo import fields, models

class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    biometric_id = fields.Char(
        string='Biometric User ID',
        index=True,
        help="PIN / User ID registered on the physical biometric device"
    )
    biometric_device_id = fields.Many2one(
        'zk.biometric.device',
        string='Assigned Biometric Machine',
        help="Select the physical device assigned to this employee"
    )

class HrEmployeePublic(models.Model):
    _inherit = 'hr.employee.public'

    # You only need to define them as readonly here so the public profile can safely read them
    biometric_id = fields.Integer(string="Biometric ID", readonly=True)
    biometric_device_id = fields.Many2one('zk.biometric.device', string="Biometric Device", readonly=True)