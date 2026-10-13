import logging
from datetime import datetime
import pytz
from odoo import fields, http
from odoo.http import request

_logger = logging.getLogger(__name__)

DEFAULT_TIMEZONE = 'Asia/Riyadh'


class ZKTecoADMSController(http.Controller):

    # =========================================================================
    # HELPER: Get or Auto-Register Device & Track Last Ping / IP
    # =========================================================================
    def _get_or_create_device(self, device_sn):
        """Finds or auto-registers the physical machine and updates heartbeat info."""
        if not device_sn or device_sn == 'UNKNOWN_DEVICE':
            return False

        DeviceModel = request.env['zk.biometric.device'].sudo()
        device = DeviceModel.search([('serial_number', '=', device_sn)], limit=1)

        # Detect the machine's public/local IP address
        client_ip = request.httprequest.headers.get('X-Forwarded-For', request.httprequest.remote_addr)
        if client_ip and ',' in client_ip:
            client_ip = client_ip.split(',')[0].strip()

        vals = {
            'last_ping': fields.Datetime.now(),
            'ip_address': client_ip,
        }

        if not device:
            vals.update({
                'name': f'Machine {device_sn}',
                'serial_number': device_sn,
                'timezone': DEFAULT_TIMEZONE,
            })
            device = DeviceModel.create(vals)
            _logger.info("New Biometric Device Auto-Registered: %s (IP: %s)", device_sn, client_ip)
        else:
            device.write(vals)

        return device

    # =========================================================================
    # 1. Main Data Endpoint: Handles Handshakes (GET) and Data Push (POST)
    # =========================================================================
    @http.route('/iclock/cdata', type='http', auth='public', methods=['GET', 'POST'], csrf=False)
    def receive_cdata(self, **kwargs):
        device_sn = request.params.get('SN', 'UNKNOWN_DEVICE')
        table_type = request.params.get('table', '')

        # Auto-register device and refresh heartbeat
        device = self._get_or_create_device(device_sn)

        # --- INITIAL HANDSHAKE (GET) ---
        if request.httprequest.method == 'GET':
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

        # Attendance Push Handling
        if table_type == 'ATTLOG':
            _logger.info("Device %s pushing ATTLOG: %s", device_sn, raw_data)

            # Determine timezone dynamically from device record
            tz_str = device.timezone if (device and device.timezone) else DEFAULT_TIMEZONE
            try:
                device_tz = pytz.timezone(tz_str)
            except Exception:
                device_tz = pytz.timezone(DEFAULT_TIMEZONE)

            for line in raw_data.split('\n'):
                parts = line.split('\t')

                # Payload format: PIN \t Timestamp \t State \t VerifyType \t WorkCode \t Reserved
                if len(parts) >= 3:
                    badge_id = parts[0].strip()
                    timestamp_str = parts[1].strip()
                    punch_state = parts[2].strip()

                    try:
                        # 1. Dynamic Timezone Conversion (Device Local Time -> UTC)
                        naive_time = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
                        local_dt = device_tz.localize(naive_time)
                        punch_time_utc = local_dt.astimezone(pytz.utc).replace(tzinfo=None)

                        # 2. Find Employee: Matched by PIN AND Specific Device
                        Employee = request.env['hr.employee'].sudo()
                        employee = False

                        # Search using Many2one relational field if configured
                        if 'biometric_device_id' in Employee._fields:
                            employee = Employee.search([
                                ('biometric_id', '=', badge_id),
                                ('biometric_device_id.serial_number', '=', device_sn)
                            ], limit=1)

                        # Search using Char serial field if configured
                        if not employee and 'biometric_device_sn' in Employee._fields:
                            employee = Employee.search([
                                ('biometric_id', '=', badge_id),
                                ('biometric_device_sn', '=', device_sn)
                            ], limit=1)

                        # Fallback for single-machine environments (or unassigned devices)
                        if not employee:
                            employee = Employee.search([
                                '|', ('biometric_id', '=', badge_id), ('barcode', '=', badge_id)
                            ], limit=1)

                        # 3. Process Attendance or Log Warning
                        if employee:
                            self._process_smart_attendance(employee, punch_time_utc, punch_state)
                        else:
                            _logger.warning(
                                "Device %s: Skipped PIN %s (No Employee matching this PIN and Machine SN found in Odoo)",
                                device_sn, badge_id
                            )

                    except Exception as e:
                        _logger.error("Error processing line '%s' from Device %s: %s", line, device_sn, str(e))
        else:
            _logger.info("Device %s pushed unused table '%s'. Returning OK.", device_sn, table_type)

        # Always return 'OK' so the device clears pushed records from its memory
        return request.make_response("OK", [('Content-Type', 'text/plain')])

    # =========================================================================
    # ATTENDANCE LOGIC: Smart Toggle Check-in / Check-out
    # =========================================================================
    def _process_smart_attendance(self, employee, punch_time, punch_state):
        """Evaluates whether to check an employee in or out."""
        Attendance = request.env['hr.attendance'].sudo()

        last_punch = Attendance.search(
            [('employee_id', '=', employee.id)],
            order='check_in desc', limit=1
        )

        # Condition: Explicit Check-In ('0'), OR no open shift exists
        if punch_state == '0' or (not last_punch) or (last_punch and last_punch.check_out):
            if last_punch and last_punch.check_in == punch_time:
                return

            Attendance.create({
                'employee_id': employee.id,
                'check_in': punch_time,
                'in_mode': 'biometric',
            })

        # Condition: Explicit Check-Out ('1'), OR an open shift is pending
        elif punch_state == '1' or (last_punch and not last_punch.check_out):
            if last_punch.check_in != punch_time:
                last_punch.write({
                    'check_out': punch_time,
                    'out_mode': 'biometric',
                })

    # =========================================================================
    # 2. Heartbeat Endpoint: Updates Status and Dispatches Remote Commands
    # =========================================================================
    @http.route('/iclock/getrequest', type='http', auth='public', methods=['GET'], csrf=False)
    def device_heartbeat(self, **kwargs):
        device_sn = request.params.get('SN', '').strip()

        if device_sn:
            device = self._get_or_create_device(device_sn)

            # Check if there is a pending remote command (e.g., Clear Logs)
            if device and device.pending_command:
                command_payload = f"C:{device.id}:{device.pending_command}\n"
                device.write({'pending_command': False})  # Clear from queue
                _logger.info("Sent queued command to Device %s: %s", device_sn, command_payload.strip())
                return request.make_response(command_payload, [('Content-Type', 'text/plain')])

        return request.make_response("OK", [('Content-Type', 'text/plain')])

    # =========================================================================
    # 3. Command Response Endpoint: Receives Device Execution Confirmation
    # =========================================================================
    @http.route('/iclock/devicecmd', type='http', auth='public', methods=['GET', 'POST'], csrf=False)
    def device_cmd_response(self, **kwargs):
        """Catches acknowledgements sent back by the machine after running a command."""
        return request.make_response("OK", [('Content-Type', 'text/plain')])