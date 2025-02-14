# -*- coding: utf-8 -*-

from odoo import models, fields, api


class BracketShapes(models.Model):
    _name = 'bracket.shapes'


    name = fields.Char(string="Name", required=True)
    image = fields.Binary()
    shape_image = fields.Binary()
    service_id = fields.Many2one(comodel_name="product.product", string="product/Service")
    shape_type = fields.Selection(string="Shape Type", selection =[('circle', 'Circle'),
                                                         ('square', 'Square'), ('rectangle', 'Rectangle'),
                                                         ('triangle_right', 'Triangle Right'),
                                                         ('triangle_equilateral', 'Triangle Equilateral'),])
    operation_intent = fields.Selection(string="Calculation", selection=[('area', 'Area'),
                                                                  ('parameters', 'Parameters')])
    sides = fields.Char(string="Sides")
    extra_operations = fields.Selection(string="Extra Calculations", selection=[('add', 'Addition'),
                                                                  ('sub', 'Subtraction'), ('mul', 'Multiplication'),
                                                                  ('divide', 'Divide')])
    extra_charge = fields.Float(string="Extra Charges")