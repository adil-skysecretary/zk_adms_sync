from odoo import models, fields


class HrAttendance(models.Model):
    _inherit = 'hr.attendance'

    # Extend both check-in and check-out modes
    in_mode = fields.Selection(
        selection_add=[('biometric', 'Biometric')],
        ondelete={'biometric': 'set default'}
    )

    out_mode = fields.Selection(
        selection_add=[('biometric', 'Biometric')],
        ondelete={'biometric': 'set default'}
    )