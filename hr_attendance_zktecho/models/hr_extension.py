# -*- coding: utf-8 -*-
import logging
from odoo import api, fields, models,_
from odoo.exceptions import ValidationError, UserError
from datetime import date, datetime, timedelta
_logger = logging.getLogger(__name__)
# from odoo.addons.fgp_base.models.method import POST_ADMIN_CHANNEL

class hrDraftAttendance(models.Model):
    _name = 'hr.draft.attendance'
    _description = 'Draft Attendance'
    # _inherit = ['portal.mixin','mail.thread', 'mail.activity.mixin']
    _inherit = ['portal.mixin', 'mail.thread.cc', 'mail.activity.mixin']
    _order = 'name desc'

    name = fields.Datetime('Datetime', required=False,tracking=True)
    date = fields.Date('Date', required=False,tracking=True)
    end_date = fields.Date('Date', required=False,tracking=True)
    day_name = fields.Char('Day',tracking=True)
    attendance_status = fields.Selection([('sign_in', 'Sign In'), ('sign_out', 'Sign Out'), ('sign_none', 'None')], 'Attendance State', required=True,tracking=True)
    employee_id = fields.Many2one(comodel_name='hr.employee', string='Employee',tracking=True)
    lock_attendance = fields.Boolean('Lock Attendance',tracking=True)
    biometric_attendance_id = fields.Integer(string='Biometric Attendance ID',tracking=True)
    is_missing = fields.Boolean('Missing', default=False,tracking=True)
    moved = fields.Boolean(default=False)
    moved_to = fields.Many2one(comodel_name='hr.attendance', string='Moved to HR Attendance')
    device_id = fields.Many2one(comodel_name='biomteric.device.info', string='Device')
    cron_activity = fields.Boolean(string="Cron Activity")

    def unlink(self):
        for rec in self:
            if rec.moved == True:
                if rec.moved_to:
                    raise UserError(_("You can`t delete Moved Attendance"))
        return super(hrDraftAttendance, self).unlink()

    def action_invalidate_log(self):
        for rec in self:
            rec.moved = True

    def action_force_sync(self):
        messages = ""
        for rec in self.sorted(key=lambda l: l.name):
            hr_attendance = self.env['hr.attendance']
            if rec.attendance_status == 'sign_in':
                vals = {
                    'employee_id': rec.employee_id.id,
                    'check_in': rec.name,
                }
                hr_attendance  = hr_attendance.sudo().create(vals)
            elif rec.attendance_status == 'sign_out':
                hr_attendance = hr_attendance.sudo().search(
                    [('employee_id', '=', rec.employee_id.id), ('check_out', '=', False)],limit=1)

                hr_attendance.sudo().write({'check_out': rec.name})

            if hr_attendance:
                # rec.moved = True
                rec.sudo().write({
                    'moved': True,
                    'moved_to': hr_attendance.id,
                })

                messages += "<p>%s <a href=# data-oe-model=%s data-oe-id=%d>%s</a></p>" % (rec.employee_id.name, rec._name, rec.id, rec.name)

        subject = "Force Sync Created"
        message = "<p>Force Sync Created for:</p>" + messages
        # POST_ADMIN_CHANNEL(self, subject, message)

    def action_mark_activity_done(self):
        for rec in self.activity_ids:
            if rec.user_id.id == self.env.user.id:
                rec.action_feedback("Done")

class HrEmployeeBase(models.AbstractModel):
    _inherit = "hr.employee.base"

    last_draft_attendance_id = fields.Many2one('hr.draft.attendance', compute='_compute_last_draft_attendance_id')
    attendance_devices = fields.One2many('employee.attendance.devices', 'employee_id', string='Attendance Devices')

    def _compute_last_draft_attendance_id(self):
        for employee in self:
            draft_atts = self.env['hr.draft.attendance'].search([('employee_id','=',employee.id)], order='name desc')
            employee.last_draft_attendance_id = draft_atts.ids

    @api.depends('last_draft_attendance_id.attendance_status', 'last_draft_attendance_id', 'last_attendance_id.check_in', 'last_attendance_id.check_out', 'last_attendance_id')
    def _compute_attendance_state(self):
        for employee in self:
            if employee.last_attendance_id and not self.env['hr.draft.attendance'].search([('moved_to','=',employee.last_attendance_id.id),
                                                                                           ('employee_id','=',employee.id)]):
                att = employee.last_attendance_id.sudo()
                employee.attendance_state = att and not att.check_out and 'checked_in' or 'checked_out'
            else:
                attendance_state = 'checked_out'
                if employee.last_draft_attendance_id and employee.last_draft_attendance_id.attendance_status == 'sign_in':
                    attendance_state = 'checked_in'
                employee.attendance_state = attendance_state

class EmployeeAttendanceDevices(models.Model):
    _name = 'employee.attendance.devices'
    _description = 'Employee Attendance Devices'
    _order = 'name'

    name = fields.Char(string='Name')
    employee_id = fields.Many2one(comodel_name='hr.employee', string='Employee')
    # location_id = fields.Many2one(related='employee_id.location_id', store=True)
    attendance_id = fields.Char("Biometric ID", required=True)
    device_id = fields.Many2one(comodel_name='biomteric.device.info', string='Biometric Device', required=True, ondelete='restrict')
    card_number = fields.Char(string="RFID Number")
    access_type = fields.Selection([('14','ADMIN'),
                                    ('0','USER')], string="Access")
    new_biometric_id = fields.Integer(string="New Biometric ID")
    active = fields.Boolean('Active', default=True)

    @api.constrains('attendance_id', 'device_id', 'name')
    def _check_unique_constraint(self):
        for rec in self:
            record = self.search([('attendance_id', '=', rec.attendance_id), ('device_id', '=', rec.device_id.id)])
            if len(record) > 1:
                raise ValidationError('Employee with Id ('+ str(rec.attendance_id)+') exists on Device ('+ str(rec.device_id.name)+') !')
            record = self.search([('name', '=', rec.employee_id.id), ('device_id', '=', rec.device_id.id)])
            if len(record) > 1:
                raise ValidationError('Configuration for Device ('+ str(rec.device_id.name)+') of Employee  ('+ str(rec.name.name)+') already exists!')

    def unlink(self):
        active_id = self.device_id
        try:
            conn = active_id._connect_device()
            for rec in self:
                conn.delete_user(uid=int(rec.attendance_id))
        except Exception as e:
            _logger.info(Warning(e))
        conn.disconnect()
        return super(EmployeeAttendanceDevices, self).unlink()
