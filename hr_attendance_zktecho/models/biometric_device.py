# -*- coding: utf-8 -*-

import datetime
import logging
import socket
import pytz
_logger = logging.getLogger('biometric_device')

from pytz import timezone, all_timezones
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT
from zk import ZK, const
from zk.exception import ZKErrorResponse, ZKNetworkError
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError
from socket import timeout
# from odoo.addons.fgp_base.models.method import POST_ADMIN_CHANNEL
# from ..pyzk.zk.finger import Finger

class BiomtericDeviceInfo(models.Model):
    _name = 'biomteric.device.info'
    _description = 'Biomteric Device Info'
    _inherit = ['mail.thread']

    name = fields.Char(string='Device', required=True)
    ipaddress = fields.Char(string='IP Address', required=True)
    portnumber = fields.Integer(string='Port', required=True)
    fetch_days = fields.Integer('Attendance Fetching Limit (days)', default=-1)
    action = fields.Selection(selection=[('sign_in','Sign In'),('sign_out','Sign Out'),('both','All')], string='Action', default='sign_in', required=True)
    time_zone = fields.Selection('_tz_get', string='Timezone', required=True, default=lambda self: self.env.user.tz or 'UTC')
    password = fields.Char('Device Password')
    protocol = fields.Selection(selection=[('tcp', 'TCP'), ('udp', 'UDP')], string='Connection Protocol', required=True, default='tcp')
    ommit_ping = fields.Boolean(string='Ommit Ping', default=False)
    api_type = fields.Selection(selection=[('legacy', 'Legacy API'), ('new', 'New API')], string='API Type', default='new')
    sign_in = fields.Char('Sign In Parameters', required=True, default='0,2,4')
    sign_out = fields.Char('Sign Out Parameters', required=True, default='1,3,5')
    time_out = fields.Integer('Connection Time Out', default=60)
    device_employee_ids = fields.One2many('employee.attendance.devices','device_id',string="Device Employees")
    sequence_id = fields.Many2one('ir.sequence', string="Sequence", ondelete='cascade', default=lambda self: self.env.ref('hr_attendance_zktecho.biometric_user_sequence'))
    private_ipaddress = fields.Char(string='Private IP')
    active = fields.Boolean(string="Active", default=True)
    zk_model = fields.Char(string="Model")
    zk_record_count = fields.Integer(string="Device Records")
    zk_record_count_cap = fields.Integer(string="Device Records Cap")
    zk_record_rate = fields.Float(string="Device Records Rate", compute='compute_record_rate')
    exclude_sync = fields.Boolean(string="Exclude Sync", help="Exclude Logs to be sync in attendance logs")
    device_datetime = fields.Datetime(string="Device DateTime")
    # cron_id = fields.Many2one('ir.cron', string="Cron", default= lambda self: self.env.ref('hr_attendance_zktecho.biometric_attendances').id)
    code = fields.Char(string="Code")

    @api.model
    def _tz_get(self):
        return [(x, x) for x in all_timezones]

    @api.constrains('ipaddress', 'portnumber')
    def _check_unique_constraint(self):
        self.ensure_one()
        record = self.search([('ipaddress', '=', self.ipaddress), ('portnumber', '=', self.portnumber)])
        if len(record) > 1:
            raise ValidationError('Device already exists with IP ('+str(self.ipaddress)+') and port ('+str(self.portnumber)+')!')

    @api.returns('self', lambda value: value.id)
    def copy(self, default=None):
        default = dict(default or {})
        default['name'] = _("%s (copy)") % (self.name or '')
        default['ipaddress'] = _("%s (copy)") % (self.ipaddress or '')
        default['portnumber'] = self.portnumber
        return super(BiomtericDeviceInfo, self).copy(default)

    def _connect_device(self):
        _logger.info('Connecting...')

        conn = None
        password = self.password or 0
        force_udp = False
        if self.protocol == 'udp':
            force_udp = True
        zk = ZK(self.ipaddress, port=self.portnumber, timeout=self.time_out, password=password, force_udp=force_udp,
                ommit_ping=self.ommit_ping)

        try:
            conn = zk.connect()
            conn.disable_device()
            conn.enable_device()
        except ZKNetworkError as e:
            subject = "Connection Error"
            if e.args[0] == "can't reach device (ping %s)" % self.ipaddress:
                message = "can't reach device (ping %s), make sure the device is powered on and connected to the network" % self.ipaddress
                # POST_ADMIN_CHANNEL(self, subject, message)
                raise Warning(message)
            else:
                # POST_ADMIN_CHANNEL(self, subject, e)
                raise Warning(e)

        except ZKErrorResponse as e:
            subject = "Connection Error"
            if e.args[0] == 'Unauthenticated':
                message = "Unable to connect (Authentication Failure), Kindly supply correct password for the device."
                # POST_ADMIN_CHANNEL(self, subject, message)
                raise Warning(message)
            else:
                # POST_ADMIN_CHANNEL(self, subject, e)
                raise Warning(e)

        except timeout:
            subject = "Connection Error"
            # POST_ADMIN_CHANNEL(self, subject, "Connection timed out, make sure the device is turned on and not blocked by the Firewall")
            raise Warning("Connection timed out, make sure the device is turned on and not blocked by the Firewall")
        except Exception as e:
            subject = "Connection Error"
            message = e
            # POST_ADMIN_CHANNEL(self, subject, message)
            raise Warning(e)
        finally:
            if conn:
                return conn

    @api.depends('zk_record_count','zk_record_count_cap')
    def compute_record_rate(self):
        for rec in self:
            if rec.zk_record_count and rec.zk_record_count_cap:
                rec.zk_record_rate = (rec.zk_record_count / rec.zk_record_count_cap) * 100
            else:
                rec.zk_record_rate = 0

    @api.model
    def fetch_attendance(self,devices):
        'Scheduled action function'

        # context = self.sudo().env.context
        # param = context.get('params')

        machines = self.search([('code','in',devices)])
        for machine in machines:
            machine.download_attendance_oldapi()

    def test_connection_device(self):
        force_udp = False
        zk = ZK('192.168.100.150', port=4370, timeout=5, password=0, force_udp=False, ommit_ping=False)
        try:
            # connect to device
            conn = zk.connect()
            # disable device, this method ensures no activity on the device while the process is run
            conn.disable_device()
            # another commands will be here!
            # Example: Get All Users
            users = conn.get_users()
            for user in users:
                privilege = 'User'
                if user.privilege == const.USER_ADMIN:
                    privilege = 'Admin'
                print('+ UID #{}'.format(user.uid))
                print('  Name       : {}'.format(user.name))
                print('  Privilege  : {}'.format(privilege))
                print('  Password   : {}'.format(user.password))
                print('  Group ID   : {}'.format(user.group_id))
                print('  User  ID   : {}'.format(user.user_id))

            # Test Voice: Say Thank You
            conn.test_voice()
            # re-enable device after all commands already executed
            conn.enable_device()
        except Exception as e:
            print("Process terminate : {}".format(e))
        finally:
            if conn:
                conn.connect()

    def download_attendance_oldapi(self):
        hr_attendance = self.env['hr.draft.attendance']
        bunch_seconds = self.env['ir.config_parameter'].sudo().get_param(
            'hr_attendance_zktecho.duplicate_punches_seconds')

        _logger.info('Fetching attendance')
        if self.fetch_days >= 0:
            now_datetime = datetime.datetime.strptime(datetime.datetime.now().strftime('%Y-%m-%d'), '%Y-%m-%d')
            prev_datetime = now_datetime - datetime.timedelta(days=self.fetch_days)
            curr_date = prev_datetime.date()
        else:
            curr_date = datetime.datetime.strptime('1950-01-01', '%Y-%m-%d').date()

        conn = None
        password = self.password or 0
        force_udp = False
        if self.protocol == 'udp':
            force_udp = True
        zk = ZK(self.ipaddress, port=self.portnumber, timeout=self.time_out, password=password, force_udp=force_udp,
                ommit_ping=self.ommit_ping)

        try:
            conn = zk.connect()
            conn.disable_device()

            conn.read_sizes()
            self.zk_record_count = conn.records
            self.zk_record_count_cap = conn.rec_cap

            attendance = conn.get_attendance()
            conn.enable_device()
            if (attendance):
                if self.fetch_days > 0:
                    now_datetime = conn.get_time()
                    prev_datetime = now_datetime - datetime.timedelta(days=self.fetch_days)
                    curr_date = prev_datetime.date()

                attendance_logs = []
                for lattendance in attendance:
                    if curr_date <= lattendance.timestamp.date():

                        local_timezone = timezone(self.time_zone)
                        local_date = local_timezone.localize(lattendance.timestamp).astimezone(timezone('UTC'))
                        atten_time = datetime.datetime.strftime(local_date, DEFAULT_SERVER_DATETIME_FORMAT)
                        att_id = lattendance.user_id or ''
                        employees = self.env['employee.attendance.devices'].search(
                            [('attendance_id', '=', att_id), ('device_id', '=', self.id)])
                        try:
                            punch_flag = lattendance.punch
                            if self.api_type == 'legacy':
                                punch_flag = lattendance.status

                            if self.action == 'both':
                                if str(punch_flag) in list(self.sign_in):
                                    action = 'sign_in'
                                elif str(punch_flag) in list(self.sign_out):
                                    action = 'sign_out'
                                else:
                                    action = 'sign_none'
                            else:
                                action = self.action
                            if action != False:
                                if not employees.employee_id.id:
                                    _logger.info('No Employee record found to be associated with User ID: ' + str(
                                        att_id) + ' on Finger Print Mahcine')
                                    continue
                                atten_ids = hr_attendance.search(
                                    [('employee_id', '=', employees.employee_id.id), ('name', '=', atten_time)])
                                atten_time = now_datetime = datetime.datetime.strptime(atten_time,
                                                                                       DEFAULT_SERVER_DATETIME_FORMAT)

                                time_with_seconds = atten_time - datetime.timedelta(seconds=float(bunch_seconds))
                                duplicated_recs = hr_attendance.search([('employee_id', '=', employees.employee_id.id),
                                                                        ('name', '>', time_with_seconds),
                                                                        ('name', '<=', atten_time)])
                                if duplicated_recs:
                                    continue
                                if atten_ids:
                                    _logger.info(
                                        'Attendance For Employee' + str(employees.employee_id.name) + 'on Same time Exist')
                                    atten_ids.write({'name': atten_time,
                                                     'employee_id': employees.employee_id.id,
                                                     'date': lattendance.timestamp.date(),
                                                     'attendance_status': action,
                                                     'day_name': lattendance.timestamp.strftime('%A')})
                                else:
                                    atten_id = hr_attendance.create({'name': atten_time,
                                                                     'employee_id': employees.employee_id.id,
                                                                     'date': lattendance.timestamp.date(),
                                                                     'attendance_status': action,
                                                                     'day_name': lattendance.timestamp.strftime('%A'),
                                                                     'device_id': self.id
                                                                     })
                                    attendance_logs.append(atten_id)

                                    _logger.info('Creating Draft Attendance Record: ' + str(atten_id) + 'For ' + str(
                                        employees.employee_id.name))
                        except Exception as e:
                            # POST_ADMIN_CHANNEL(self, e, e)
                            _logger.error('Exception' + str(e))
                    else:
                        _logger.warning('Skip attendance because its before the threshold ' + str(curr_date))

                # POST_ADMIN_CHANNEL(self, "Biometric Logs Successfully Downloaded!",
                #                    '%s: Biometric logs successfully downloaded: %s records' % (self.name,len(attendance_logs)))
            else:
                _logger.warning('No attendance Data to Fetch')
        except ZKNetworkError as e:
            subject = "Connection Error"
            if e.args[0] == "can't reach device (ping %s)" % self.ipaddress:
                message = "can't reach device (ping %s), make sure the device is powered on and connected to the network" % self.ipaddress
                # POST_ADMIN_CHANNEL(self, subject, message)
                raise Warning(message)
            else:
                # POST_ADMIN_CHANNEL(self, subject, e)
                raise Warning(e)

        except ZKErrorResponse as e:
            subject = "Connection Error"
            if e.args[0] == 'Unauthenticated':
                message = "Unable to connect (Authentication Failure), Kindly supply correct password for the device."
                # POST_ADMIN_CHANNEL(self, subject, message)
                raise Warning(message)
            else:
                # POST_ADMIN_CHANNEL(self, subject, e)
                raise Warning(e)

        except timeout:
            subject = "Connection Error"
            # POST_ADMIN_CHANNEL(self, subject,
            #                    "Connection timed out, make sure the device is turned on and not blocked by the Firewall")
            raise Warning("Connection timed out, make sure the device is turned on and not blocked by the Firewall")
        except Exception as e:
            subject = "Connection Error"
            message = e
            # POST_ADMIN_CHANNEL(self, subject, message)
            raise Warning(e)
        finally:
            if conn:
                return conn
        return True

    def clear_attendance_device(self):
        conn = self._connect_device()

        # self.download_attendance_oldapi()
        _logger.info('Clear attendance...')
        conn.clear_attendance()

        conn.disconnect()

        return {
            'effect': {
                'fadeout': 'slow',
                'message': 'Biometric logs cleared!',
                'type': 'rainbow_man',
            }
        }

    def action_restart_device(self):
        conn = self._connect_device()
        conn.restart()
        conn.disconnect()

    def action_get_users(self):
        conn = self._connect_device()
        _logger.info('Get users...')

        users = conn.get_users()
        employee_ids = []
        for user in users:
            # template = conn.get_user_template(uid=user.uid, temp_id=0)
            # fingers = []
            # fingers.append(template)
            #
            # conn.save_user_template(2,fingers)

            employee_device_obj = self.env['employee.attendance.devices']

            existing_employee_id = employee_device_obj.search([('attendance_id', '=', user.uid), ('device_id', '=', self.id)])
            if existing_employee_id:
                existing_employee_id.sudo().write({
                    'name': user.name,
                    'card_number': str(user.card),
                    'access_type': str(user.privilege)
                })

            else:
                employee_id = employee_device_obj.sudo().create({
                    'device_id': self.id,
                    'name': user.name,
                    'attendance_id': str(user.uid),
                    'card_number': str(user.card),
                    'access_type': str(user.privilege)
                })

                employee_ids.append(employee_id)
        conn.disconnect()

        body = "<p>%s: Biometric users successfully downloaded: %s records </p>" % (self.name,len(employee_ids))
        for emp in employee_ids:
            body += "<p>%s</p>" % (emp.name)
        # POST_ADMIN_CHANNEL(self, "Biometric Users Successfully Downloaded!",body)

        return {
            'effect': {
                'fadeout': 'slow',
                'message': 'Biometric users downloaded!',
                'type': 'rainbow_man',
            }
        }

    def action_sync_attendance(self):
        sync_days = self.env['ir.config_parameter'].sudo().get_param(
            'hr_attendance_zktecho.sync_days')

        if not sync_days:
            sync_days = self.env.company.sync_days

        # date_from = (datetime.datetime.today().date()).strftime('%Y-%m-01 00:00:00')
        # date_to = (datetime.datetime.today().date()).strftime('%Y-%m-%d 23:59:00')

        date_to = datetime.datetime.today().date()
        date_from = date_to - datetime.timedelta(days=int(sync_days))

        hr_attendance_draft = self.env['hr.draft.attendance']
        hr_attendance = self.env['hr.attendance']

        employees = hr_attendance_draft.search([('moved', '=', False), ]).mapped('employee_id')

        for employee in employees:
            log_ids = hr_attendance_draft.search([('employee_id', '=', employee.id),
                                                  ('attendance_status', '!=', 'sign_none'),
                                                  ('date', '>=', date_from),
                                                  ('date', '<=', date_to),
                                                  ('moved', '=', False),
                                                  ('device_id.exclude_sync', '=', False),
                                                  ], order='name asc')

            for log in log_ids.sorted(key=lambda l: l.name):
                attendance_id = False
                try:
                    previous_attendance_id = hr_attendance.search([('employee_id','=',employee.id)],order='check_in desc', limit=1)

                    if previous_attendance_id:
                        if not previous_attendance_id.check_out:
                            previous_attendance_id.write({
                                'check_out': log.name
                            })
                            attendance_id = previous_attendance_id
                        else:
                            val = {
                                'employee_id': employee.id,
                                'check_in': log.name,
                            }
                            attendance_id = hr_attendance.create(val)

                    else:
                        val = {
                            'employee_id': employee.id,
                            'check_in': log.name,
                        }
                        attendance_id = hr_attendance.create(val)

                    log.write({
                        'moved': True,
                        'moved_to': attendance_id
                    })
                except Exception as e:
                    log.write({
                        'moved': True,
                        'moved_to': attendance_id
                    })

                    # POST_ADMIN_CHANNEL(self, "Logs Sync Unsuccessful", "<p>Logs Sync Unsuccessful:</p>"
                    #                                                    "<p>The following error occured while moving attendances %s</p>" % e)
                    # if log:
                    #     self.action_sync_attendance_eod(log,e)

        if self:
            return {
                'effect': {
                    'fadeout': 'slow',
                    'message': 'Biometric logs successfully synced!',
                    'type': 'rainbow_man',
                }
            }

    def action_sync_attendance_eod(self,draft_attendance_id,error):
        # log_ids = self.env['hr.draft.attendance'].sudo().search([('moved', '=', False),
        #                               ('cron_activity', '=', False), ])
        log_ids = draft_attendance_id

        for rec in log_ids:
            if not rec.cron_activity:
                partner_ids = rec.device_id.message_follower_ids.mapped('partner_id')
                for partner in partner_ids:
                    user_id = self.env['res.users'].sudo().search([('partner_id', '=', partner.id)])
                    if user_id:
                        rec.activity_schedule(
                            activity_type_id=self.env.ref('mail.mail_activity_data_todo').id,
                            summary="Fix employee attendance",
                            note="Synced but it needs to  be fixed. Biometric log <a href=# data-oe-model=%s data-oe-id=%d>%s</a>. "
                                 "%s" % (rec._name, rec.id, rec.name, error),
                            user_id=user_id.id,
                            date_deadline=rec.date
                        )
                rec.cron_activity = True

    def action_transfer_data_biometric(self):
        action = {
            "type": "ir.actions.act_window",
            "view_mode": "form",
            "name": _("Transfer Data"),
            "res_model": "transfer.data",
            "context": {
                'default_old_device_id': self.id,
            },
            "target": "new",
        }
        return action

    def action_get_device_info(self):
        conn = self._connect_device()
        _logger.info('Get Device Info...')

        self.zk_model = conn.get_device_name()
        self.private_ipaddress = conn.get_network_params().get('ip')

        conn.read_sizes()
        self.zk_record_count = conn.records
        self.zk_record_count_cap = conn.rec_cap

        user_tz = pytz.timezone(self.env.context.get('tz') or 'UTC')

        device_datetime = conn.get_time()
        with_timezone = user_tz.localize(device_datetime)

        self.device_datetime = with_timezone.astimezone(pytz.utc).replace(tzinfo=None)
        conn.disconnect()



        return {
            'effect': {
                'fadeout': 'slow',
                'message': 'Biometric Device details updated',
                'type': 'rainbow_man',
            }
        }

    def action_update_datetime(self):
        conn = self._connect_device()
        user_tz = pytz.timezone(self.env.context.get('tz') or 'UTC')

        newtime = self.device_datetime.astimezone(user_tz).replace(tzinfo=None)
        conn.set_time(newtime)

        conn.disconnect()

        return {
            'effect': {
                'fadeout': 'slow',
                'message': 'Biometric Device DateTime updated',
                'type': 'rainbow_man',
            }
        }

    def action_check_biometric_port(self):
        machines = self.search([])
        for machine in machines:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            result = sock.connect_ex((machine.ipaddress, machine.portnumber))
            # if result != 0:
                # POST_ADMIN_CHANNEL(self, "Port Closed", "<p>Port Closed:</p>"
                #                                                    "<p> %s</p>" % machine.ipaddress)
            sock.close()



    # @api.model
    # def create(self, vals):
    #     sequence_id = self.env['ir.sequence'].create({
    #         'name': '%s Biometric User Sequence' % vals.get('name'),
    #         'code': 'biometric.user.sequence.%s' % vals.get('name').replace(' ','.'),
    #         'padding': 6,
    #         'implementation': 'no_gap',
    #         'number_next_actual': 100,
    #     })
    #     vals.update({
    #         'sequence_id': sequence_id.id
    #     })
    #     return super(BiomtericDeviceInfo, self).create(vals)

