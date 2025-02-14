from odoo import models, fields, api


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    org_length = fields.Float(string="Length")
    org_width = fields.Float(string="Width")
    unit = fields.Float(string="Pcs")
    shape_id = fields.Many2one(comodel_name='bracket.shapes', string="Shape")
    shape_id_image = fields.Binary(string="Image")




    