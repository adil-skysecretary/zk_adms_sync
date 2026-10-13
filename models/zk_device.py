from odoo import fields, models, api
from datetime import timedelta
import pytz


class ZkBiometricDevice(models.Model):
    _name = 'zk.biometric.device'
    _description = 'Biometric Machine'
    _rec_name = 'name'

    name = fields.Char(string='Device Name', required=True)
    serial_number = fields.Char(string='Serial Number (SN)', required=True, index=True)
    ip_address = fields.Char(string='Last Known IP', readonly=True)

    # Feature 1: Timezone per device
    timezone = fields.Selection(
        selection=lambda self: [(tz, tz) for tz in pytz.all_timezones],
        string='Device Timezone',
        default='Asia/Riyadh',
        required=True
    )

    # Feature 2: Online/Offline Status Tracking
    last_ping = fields.Datetime(string='Last Ping (Heartbeat)', readonly=True)
    state = fields.Selection([
        ('online', 'Online'),
        ('offline', 'Offline')
    ], string='Status', compute='_compute_state')

    # Feature 3: Command Queueing (Clear Logs)
    pending_command = fields.Char(string='Pending ADMS Command', readonly=True)

    @api.depends('last_ping')
    def _compute_state(self):
        for device in self:
            if device.last_ping and device.last_ping >= fields.Datetime.now() - timedelta(minutes=5):
                device.state = 'online'
            else:
                device.state = 'offline'

    # def action_clear_device_logs(self):
    #     """ Queues a command to clear the physical device's attendance logs """
    #     for device in self:
    #         # ADMS command syntax to clear attendance logs
    #         device.pending_command = "DATA UPDATE INFO \t CLEAR LOG"