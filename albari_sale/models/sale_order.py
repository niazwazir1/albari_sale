# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class SaleOrderShapeExt(models.Model):
    _inherit = 'sale.order'

    production_order_id = fields.Many2one('processing.production.order', string='Production Order')
    sale_order_count = fields.Integer(string="Sale Order Count")
    beveling = fields.Char(string="Beveling", default="Total Beveling Charges")
    beveling_pcs = fields.Float(string="Total Pcs", compute="_compute_beveling_totals")
    beveling_qty = fields.Float(string="R ft", compute="_compute_beveling_totals")
    beveling_amount = fields.Float(string="Total Amount", compute="_compute_beveling_totals")
    check_order = fields.Many2one('check.order', string="Check Order")
    processing_order_ids = fields.One2many(
        'processing.production.order', 'sale_id', string="Production Orders"
    )

    is_production_ready = fields.Boolean(
        string="Production Ready", store=True, default=False
    )

    # Boolean field to control the visibility of the delivery button
    # show_delivery_button = fields.Boolean(
    #     compute="_compute_show_delivery_button",
    #     store=True
    # )
    #
    # @api.depends('order_line.product_id')  # Adjust if required
    # def _compute_show_delivery_button(self):
    #     for order in self:
    #         processing_orders = self.env['processing.production.order'].search([
    #             ('sale_id', '=', order.id),
    #             ('status', '=', 'ready')  # Only when status is 'ready'
    #         ])
    #         order.show_delivery_button = bool(processing_orders)

    # @api.onchange('order_line')
    # def _onchange_methods_pcs(self):
    #     for order in self:
    #         order.beveling_pcs = sum(order.mapped('unit'))

    def action_confirm(self):
        res = super(SaleOrderShapeExt, self).action_confirm()

        for order in self:
            for line in order.order_line:
                # Find the corresponding stock move
                stock_move = self.env['stock.move'].search([
                    ('sale_line_id', '=', line.id),
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

        for rec in self:
            stock_delivery_vals = {
                'partner_id': rec.partner_id.id,
                'name': self.env['ir.sequence'].next_by_code('stock.check'),
                'order_id': rec.id,
                'state': 'draft',
                'check_order_id': [
                    (0, 0, {
                        'product_id': line.product_id.id,
                        'length': line.org_length,
                        'width': line.org_width,
                        'unit': line.unit,
                        'qty': line.product_uom_qty,
                        'shape_id': line.shape_id.id if line.shape_id else False,
                        'shape_id_image': line.shape_id.image if line.shape_id and line.shape_id.image else False,
                        # Related field works automatically
                        'remarks': line.remarks,
                    }) for line in rec.order_line
                ]
            }

            delivery = self.env['check.order'].create(stock_delivery_vals)
            rec.check_order = delivery.id

        return res

    def action_open_stock_check(self):

        self.ensure_one()
        if not self.check_order:
            raise ValidationError(_("No delivery record associated with this sale order."))

        return {
            'name': _('Delivery'),
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'check.order',
            'res_id': self.check_order.id,
            'target': 'current',
        }

    def _prepare_sale_order_line(self, line):
        """
        Override the method to include custom fields from the quotation line to the sale order line.
        """
        sale_order_line_vals = super(SaleOrderShapeExt, self)._prepare_sale_order_line(line)

        # Include custom fields in sale order line
        sale_order_line_vals.update({
            'org_length': line.org_length,
            'org_width': line.org_width,
            'unit': line.unit,
            'shape_id': line.shape_id.id,
        })
        return sale_order_line_vals

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

    # def stock_check_action(self):
    #     pass

    def action_create_purchase_orders(self):
        PurchaseOrder = self.env['purchase.order']
        PurchaseOrderLine = self.env['purchase.order.line']

        for order in self:
            purchase_order_vals = {
                'partner_id': self.env.user.company_id.partner_id.id,
                'sale_order_id': order.id,
                'order_line': []
            }

            for line in order.order_line:
                if line.product_id.qty_available <= 0:
                    purchase_line_vals = {
                        'product_id': line.product_id.id,
                        'name': line.product_id.name,
                        'product_qty': line.product_uom_qty,
                        'product_uom': line.product_uom.id,
                        'price_unit': line.product_id.standard_price,
                        'date_planned': fields.Date.today(),
                    }
                    purchase_order_vals['order_line'].append((0, 0, purchase_line_vals))

            if purchase_order_vals['order_line']:
                PurchaseOrder.create(purchase_order_vals)
            else:
                raise UserError(_('All products have sufficient stock. No purchase orders created.'))

    def action_view_purchase_orders(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Purchase Orders'),
            'view_mode': 'tree,form',
            'res_model': 'purchase.order',
            'domain': [('sale_order_id', '=', self.id)],
            'context': {'create': False},
        }

    def action_open_action_wizard(self):

        view_id = self.env.ref('albari_sale.view_sale_order_action_wizard_form').id
        return {
            'name': 'Stock Check',
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order.action.wizard',
            'view_mode': 'form',
            'target': 'new',
            'view_id': view_id,

        }


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    org_length = fields.Float(string="Length")
    org_width = fields.Float(string="Width")
    unit = fields.Float(string="Pcs")
    product_uom_qty = fields.Float(string='Quantity', digits='Product Unit of Measure', required=True, default=0)
    shape_id = fields.Many2one(comodel_name='bracket.shapes', string="Shape")
    is_beveling = fields.Boolean()
    shape_id_image = fields.Binary(string="Image", related='shape_id.image')
    remarks = fields.Char(string='Remarks')
    amount = fields.Float(string='Amount', compute='_compute_discount_amount')
    tax_amount = fields.Float(string='Tax Amount', compute='_compute_tax_id_amount')

    @api.depends('price_subtotal', 'tax_id')
    def _compute_tax_id_amount(self):
        for record in self:
            record.tax_amount = (record.price_subtotal * (record.tax_id.amount / 100)) if record.tax_id else 0.0

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
        invoice_line_vals = super(SaleOrderLine, self)._prepare_invoice_line(**kwargs)

        # Update with custom fields
        invoice_line_vals.update({
            'org_length': self.org_length,
            'org_width': self.org_width,
            'unit': self.unit,
            'shape_id': self.shape_id.id,
        })
        return invoice_line_vals
