from datetime import datetime
import logging
import pytz
from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)
DEVICE_TIMEZONE = pytz.timezone('Asia/Riyadh')

class ZKTecoADMSController(http.Controller):

    @http.route('/iclock/cdata', type='http', auth='public', methods=['GET', 'POST'], csrf=False)
    def receive_attendance_data(self, **kwargs):
        if request.httprequest.method == 'GET':
            return request.make_response("OK", [('Content-Type', 'text/plain')])

        raw_data = request.httprequest.data.decode('utf-8')
        _logger.info("Raw Biometric Push: %s", raw_data)

        if not raw_data:
            return request.make_response("OK", [('Content-Type', 'text/plain')])

        for line in raw_data.strip().split('\n'):
            parts = line.split('\t')
            if len(parts) >= 2:
                badge_id = parts[0].strip()
                timestamp_str = parts[1].strip()

                try:
                    naive_time = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
                    punch_time = DEVICE_TIMEZONE.localize(naive_time).astimezone(pytz.utc).replace(tzinfo=None)

                    employee = request.env['hr.employee'].sudo().search(
                        ['|', ('pin', '=', badge_id), ('barcode', '=', badge_id)], limit=1
                    )
                    if employee:
                        last_punch = request.env['hr.attendance'].sudo().search(
                            [('employee_id', '=', employee.id)], order='check_in desc', limit=1
                        )
                        if last_punch and not last_punch.check_out:
                            if last_punch.check_in != punch_time:
                                last_punch.sudo().write({'check_out': punch_time})
                        else:
                            request.env['hr.attendance'].sudo().create({
                                'employee_id': employee.id,
                                'check_in': punch_time,
                            })
                    else:
                        _logger.warning("Employee with PIN %s not found", badge_id)
                except Exception as e:
                    _logger.error("Error processing punch line '%s': %s", line, str(e))

        return request.make_response("OK", [('Content-Type', 'text/plain')])

    @http.route('/iclock/getrequest', type='http', auth='public', methods=['GET'], csrf=False)
    def device_heartbeat(self, **kwargs):
        return request.make_response("OK", [('Content-Type', 'text/plain')])