# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError
import logging

from odoo.tools.populate import compute

_logger = logging.getLogger(__name__)


class PurchaseSale(models.Model):
    _inherit = 'purchase.order'

    sale_order_count = fields.Integer(string="Sale Order Count")
    beveling = fields.Char(string="Beveling", default="Total Beveling Charges")
    beveling_pcs = fields.Float(string="Total Pcs", compute="_compute_beveling_totals")
    beveling_qty = fields.Float(string="R ft", compute="_compute_beveling_totals")
    beveling_amount = fields.Float(string="Total Amount", compute="_compute_beveling_totals")
    sale_id = fields.Many2one('sale.order',string='Sale order')
    inventry_id = fields.Many2one('stock.picking')

    def button_confirm(self):
        super(PurchaseSale, self).button_confirm()
        for order in self:
            for line in order.order_line:
                _logger.info(f"Line Shape ID: {line.shape_id}, Shape ID Image: {line.shape_id_image}")
                stock_move = self.env['stock.move'].search([
                    ('purchase_line_id', '=', line.id),
                ], limit=1)

                if stock_move:
                    stock_move.write({
                        'org_length': line.org_length,
                        'org_width': line.org_width,
                        'unit': line.unit,
                        'shape_id': line.shape_id.id if line.shape_id else False,
                        'shape_id_image': line.shape_id.image if line.shape_id and line.shape_id.image else False,
                        'remarks': line.remarks,
                    })


    #
    # def action_view_picking(self):
    #
    #     po = self.env['stock.move'].default_get({
    #         'sale_id':self.sale_id.id,
    #     })
    # def action_view_picking(self):
    #     lines = [(0, 0, {
    #
    #     }) for rec in self.order_line]
    #
    #     po = self.env['purchase.order'].write({
    #
    #         'sale_id': self.sale_id.id,
    #         'order_line': lines
    #     })







    # def _prepare_sale_order_line(self, line):
    #     """
    #     Override the method to include custom fields from the quotation line to the sale order line.
    #     """
    #     Purchase_order_line_vals = super(PurchaseSale, self)._prepare_purchase_order_line(line)
    #
    #     # Include custom fields in sale order line
    #     Purchase_order_line_vals.update({
    #         'org_length': line.org_length,
    #         'org_width': line.org_width,
    #         'unit': line.unit,
    #         'shape_id': line.shape_id.id if line.shape_id else False,  # Correct ID is passed
    #         'shape_id_image': line.shape_id_image,
    #
    #     })
    #     return Purchase_order_line_vals

    @api.depends('order_line.unit', 'order_line.product_uom_qty', 'order_line.price_subtotal', 'order_line.shape_id')
    def _compute_beveling_totals(self):
        for order in self:
            total_pcs = 0.0
            total_qty = 0.0
            total_amount = 0.0
            for line in order.order_line:
                if line.shape_id:
                    sides = self._get_shape_sides(line.shape_id.sides)
                    length, width = self._calculate_dimensions(line, sides)
                    side_sum = length + width
                    if line.shape_id.extra_operations:
                        extra_charge = line.shape_id.extra_charge
                        if line.shape_id.extra_operations == "add":
                            side_sum = side_sum + extra_charge
                        elif line.shape_id.extra_operations == "sub":
                            side_sum = side_sum - extra_charge
                        elif line.shape_id.extra_operations == "mul":
                            side_sum = side_sum * extra_charge
                        elif line.shape_id.extra_operations == "divide":
                            if line.shape_id.extra_charge == 0:
                                raise UserError("Division by zero is not allowed in extra operations.")
                            side_sum = side_sum / extra_charge
                    quantity = (side_sum / 12) * line.unit

                    total_pcs += line.unit
                    total_qty += quantity
                    total_amount += quantity * line.shape_id.service_id.lst_price

            order.beveling_pcs = total_pcs
            order.beveling_qty = total_qty
            order.beveling_amount = total_amount

    def _get_shape_sides(self, sides_str):
        try:
            return list(map(int, sides_str.split(',')))
        except ValueError:
            raise UserError("Sides must be a comma-separated list of integers.")

    def _calculate_dimensions(self, line, sides):
        length = 0
        width = 0
        for side in sides:
            if side % 2 == 0:
                length += line.org_length
            else:
                width += line.org_width
        return length, width


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    org_length = fields.Float(string="Length")
    org_width = fields.Float(string="Width")
    unit = fields.Float(string="Pcs")
    product_uom_qty = fields.Float(string='Quantity', digits='Product Unit of Measure', required=True, default=0)
    shape_id = fields.Many2one(comodel_name='bracket.shapes', string="Shape")
    is_beveling = fields.Boolean()
    shape_id_image = fields.Binary(string="Image",related='shape_id.image')
    remarks = fields.Char(string='Remarks')
    amount = fields.Float(string='Amount',compute='_compute_discount_amount')
    taxes_amount = fields.Float(string='Taxes Amount', compute='_compute_taxes_id_amount')

    @api.depends('price_subtotal', 'taxes_id')
    def _compute_taxes_id_amount(self):
        for record in self:
            record.taxes_amount = (record.price_subtotal * (record.taxes_id.amount / 100)) if record.taxes_id else 0.0

    @api.depends('price_subtotal', 'discount')
    def _compute_discount_amount(self):
        for record in self:
            record.amount = -(record.price_subtotal * (record.discount / 100))


    @api.onchange('org_length', 'org_width', 'unit')
    def _onchange_length_width_qty(self):
        for rec in self:
            product_square = rec.org_length * rec.org_width * rec.unit
            if product_square != 0:
                rec.product_uom_qty = product_square / 144
            else:
                rec.product_uom_qty = product_square / 144

    def _prepare_invoice_line(self, **kwargs):
        # Call the original method to get default values
        invoice_line_vals = super(PurchaseOrderLine, self)._prepare_invoice_line(**kwargs)

        # Update with custom fields
        invoice_line_vals.update({
            'org_length': self.org_length,
            'org_width': self.org_width,
            'unit': self.unit,
            'shape_id': self.shape_id.id,
        })
        return invoice_line_vals


    def _prepare_stock_moves(self, picking):
        res = super(PurchaseOrderLine, self)._prepare_stock_moves(picking)
        for move in res:
            move.update({
                'org_length': self.org_length,
                'org_width': self.org_width,
                'unit': self.unit
            })
        return res







    #
    # def _add_beveling_line(self):
    #     for line in self:
    #         if line.shape_id:
    #             try:
    #                 sides = list(map(int, line.shape_id.sides.split(',')))
    #             except ValueError:
    #                 raise UserError("Sides must be a comma-separated list of integers.")
    #
    #             length = 0
    #             width = 0
    #
    #             for side in sides:
    #                 if side % 2 == 0:
    #                     length += line.org_length
    #                 else:
    #                     width += line.org_width
    #
    #             side_sum = length + width
    #             quantity = (side_sum / 12) * line.unit
    #             if not line.shape_id.service_id:
    #                 raise UserError("The selected shape does not have a linked product/service.")
    #             self.env['sale.order.line'].create({
    #                 'is_beveling': True,
    #                 'order_id': line.order_id.id,
    #                 'product_id': line.shape_id.service_id.id,
    #                 'org_length': line.org_length,
    #                 'org_width': line.org_width,
    #                 'unit': line.unit,
    #                 'product_uom_qty': quantity,
    #                 'price_unit': line.shape_id.service_id.lst_price,
    #             })
