# -*- coding: utf-8 -*-

import operator
import logging
from odoo import api, fields, models, _
from zk import ZK, const
from odoo.exceptions import ValidationError, UserError
from odoo.addons.hr_attendance_zktecho.models.biometric_device import BiomtericDeviceInfo
# from odoo.addons.fgp_base.models.method import POST_ADMIN_CHANNEL

_logger = logging.getLogger(__name__)

class TransferData(models.TransientModel):
    _name = "transfer.data"
    _description = 'Transfer Data Wizard'

    old_device_id = fields.Many2one('biomteric.device.info', string='From Device', required=True)
    # device_id = fields.Many2one('biomteric.device.info', string='To Device', required=True)
    device_ids = fields.Many2many('biomteric.device.info', string='To Device', required=True)
    employee_ids = fields.Many2many('employee.attendance.devices', string="Employees")

    def action_transfer(self):
        active_id = self.env['biomteric.device.info'].browse(self.env.context.get('active_id'))

        employee_ids = active_id.device_employee_ids.filtered(lambda r: r.employee_id.id != False)
        if self.employee_ids:
            employee_ids = self.employee_ids

        for rec in employee_ids:
            try:
                conn = active_id._connect_device()
                active_user_template = conn.get_user_template(uid=int(rec.attendance_id), temp_id=0)

                privilege = const.USER_DEFAULT
                if rec.access_type:
                    privilege = int(rec.access_type)


                if rec.new_biometric_id:
                    user_id = rec.new_biometric_id
                else:
                    user_id = int(rec.attendance_id)

                for device in self.device_ids:
                    new_conn = device._connect_device()
                    new_conn.set_user(uid=user_id, name=rec.name, privilege=privilege, password='', user_id=str(user_id), card=int(rec.card_number))

                    if active_user_template:
                        fingers = [active_user_template]
                        new_conn.save_user_template(user_id,fingers)

                    device.device_employee_ids.create(
                        {
                            'device_id': device.id,
                            'name': rec.name,
                            'employee_id': rec.employee_id.id,
                            'attendance_id': str(user_id),
                            'card_number': rec.card_number,
                            'access_type': rec.access_type
                        }
                    )

                # new_conn = self.device_id._connect_device()
                # new_conn.set_user(uid=user_id, name=rec.name, privilege=privilege, password='', user_id=str(user_id), card=int(rec.card_number))
                #
                # if active_user_template:
                #     fingers = [active_user_template]
                #     new_conn.save_user_template(user_id,fingers)
                #
                # self.device_id.device_employee_ids.create(
                #     {
                #         'device_id': self.device_id.id,
                #         'name': rec.name,
                #         'employee_id': rec.employee_id.id,
                #         'attendance_id': str(user_id)
                #     }
                # )

            except Exception as e:
                _logger.info(Warning(e))

                # POST_ADMIN_CHANNEL(self, "Data Transfer Unsuccessful", "<p>Data Transfer Unsuccessful:</p>"
                #                                                    "<p>The following error occured while moving data %s</p>" % e)

            conn.disconnect()
            new_conn.disconnect()

        # self.device_id.action_get_users

        return {
            'effect': {
                'fadeout': 'slow',
                'message': 'Data successfully transferred!',
                'type': 'rainbow_man',
            }
        }
