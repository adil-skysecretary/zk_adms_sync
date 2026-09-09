import logging
from datetime import datetime
import pytz
from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

# Set to the timezone where the physical biometric machine is located
DEVICE_TIMEZONE = pytz.timezone('Asia/Riyadh')


class ZKTecoADMSController(http.Controller):

    # 1. Main Data Endpoint: Handles Handshakes (GET) and Data Push (POST)
    @http.route('/iclock/cdata', type='http', auth='public', methods=['GET', 'POST'], csrf=False)
    def receive_cdata(self, **kwargs):
        # Capture query parameters sent by the device
        device_sn = request.params.get('SN', 'UNKNOWN_DEVICE')
        table_type = request.params.get('table', '')

        # --- INITIAL HANDSHAKE (GET) ---
        if request.httprequest.method == 'GET':
            # When the device first connects, it asks the server for settings.
            # 'Realtime=1' tells the device to push punches instantly.
            handshake_response = (
                "GET OPTION FROM: {}\n"
                "ErrorDelay=60\n"
                "Delay=30\n"
                "TransTimes=00:00;14:00\n"
                "TransInterval=1\n"
                "TransFlag=1111000000\n"
                "Realtime=1\n"
                "Encrypt=0"
            ).format(device_sn)

            _logger.info("Device %s connected. Sending handshake.", device_sn)
            return request.make_response(handshake_response, [('Content-Type', 'text/plain')])

        # --- DATA PUSH (POST) ---
        raw_data = request.httprequest.data.decode('utf-8').strip()

        if not raw_data:
            return request.make_response("OK", [('Content-Type', 'text/plain')])

        # Only process Attendance Logs (ignore OPERLOG or BIODATA pushes for now)
        if table_type == 'ATTLOG':
            _logger.info("Device %s pushing ATTLOG: %s", device_sn, raw_data)

            for line in raw_data.split('\n'):
                parts = line.split('\t')

                # Payload format: PIN \t Timestamp \t State \t VerifyType \t WorkCode \t Reserved
                if len(parts) >= 3:
                    badge_id = parts[0].strip()
                    timestamp_str = parts[1].strip()
                    punch_state = parts[2].strip()

                    try:
                        # 1. Timezone Conversion (Device Local Time -> Odoo UTC)
                        naive_time = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
                        local_dt = DEVICE_TIMEZONE.localize(naive_time)
                        punch_time_utc = local_dt.astimezone(pytz.utc).replace(tzinfo=None)

                        # 2. Find Employee by PIN
                        employee = request.env['hr.employee'].sudo().search([
                            '|', ('biometric_id', '=', badge_id), ('barcode', '=', badge_id)
                        ], limit=1)

                        if employee:
                            self._process_smart_attendance(employee, punch_time_utc, punch_state)
                        else:
                            _logger.warning("Device %s: Skiped PIN %s (No Employee Found in Odoo)", device_sn, badge_id)

                    except Exception as e:
                        _logger.error("Error processing line '%s' from Device %s: %s", line, device_sn, str(e))
        else:
            _logger.info("Device %s pushed unused table '%s'. Returning OK.", device_sn, table_type)

        # Always return 'OK' so the device clears the pushed records from its memory
        return request.make_response("OK", [('Content-Type', 'text/plain')])

    def _process_smart_attendance(self, employee, punch_time, punch_state):
        """ Evaluates whether to check an employee in or out. """
        Attendance = request.env['hr.attendance'].sudo()

        # Get the employee's most recent attendance record
        last_punch = Attendance.search(
            [('employee_id', '=', employee.id)],
            order='check_in desc', limit=1
        )

        # ZKTeco States: '0' = Check-In, '1' = Check-Out.
        # Fallback: If device doesn't enforce states, we toggle based on Odoo's last record.

        # Condition: If state is explicitly Check-In ('0'), OR there is no open shift
        if punch_state == '0' or (not last_punch) or (last_punch and last_punch.check_out):
            # Prevent duplicate check-ins at the exact same time
            if last_punch and last_punch.check_in == punch_time:
                return

            Attendance.create({
                'employee_id': employee.id,
                'check_in': punch_time,
            })

        # Condition: If state is explicitly Check-Out ('1'), OR a shift is currently open
        elif punch_state == '1' or (last_punch and not last_punch.check_out):
            # Prevent closing a shift at the exact same second it was opened
            if last_punch.check_in != punch_time:
                last_punch.write({'check_out': punch_time})

    # 2. Heartbeat Endpoint
    @http.route('/iclock/getrequest', type='http', auth='public', methods=['GET'], csrf=False)
    def device_heartbeat(self, **kwargs):
        # The device pings this to see if Odoo has any commands for it. We return OK to keep it online.
        return request.make_response("OK", [('Content-Type', 'text/plain')])