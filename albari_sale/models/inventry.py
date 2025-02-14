from reportlab.lib.validators import inherit

import logging

_logger = logging.getLogger(__name__)


from odoo import models,fields,api


class Inventry(models.Model):
    _inherit = 'stock.picking'

    inherit_id = fields.Many2one('sale.order', string='Sale Seq', related='purchase_id.sale_id')
    purchase_id = fields.Many2one('purchase.order')
    production_id = fields.Many2one('processing.production.order')

    @api.model
    def create(self, vals):
        res = super(Inventry, self).create(vals)

        if res.origin:  # Checking if there is an origin (linked to PO)
            purchase_order = self.env['purchase.order'].search([('name', '=', res.origin)], limit=1)
            if purchase_order and purchase_order.sale_id:
                res.sale_id = purchase_order.sale_id.id
        return res

    def button_validate(self):
        self.ensure_one()

        _logger.debug("Purchase ID: %s", self.purchase_id)
        _logger.debug("Inherit ID (Sale Order Reference): %s", self.inherit_id)

        # Ensure this order is linked to a Sale Order through inherit_id
        if self.inherit_id:
            sale_id = self.inherit_id  # Sale order ka reference jo inventory field inherit_id mein hai
            _logger.debug("Processing linked Sale Order ID: %s", sale_id.id)

            # Check if an existing processing order is linked to the same sale_id
            processing_order = self.env['processing.production.order'].search([
                ('sale_id', '=', sale_id.id)
            ], limit=1)

            _logger.debug("Existing Processing Order found: %s", processing_order)

            # Prepare the processing lines
            lines = []
            for rec in self.move_ids_without_package:
                _logger.debug("Processing Record: %s, Length: %s, Width: %s, Qty: %s",
                              rec.product_id.name, rec.org_length, rec.org_width, rec.quantity)

                if rec.org_length and rec.org_width and rec.quantity:  # Ensure all fields are populated
                    lines.append((0, 0, {
                        'product_id': rec.product_id.id,
                        'qty': rec.quantity,
                        'org_length': rec.org_length,
                        'org_width': rec.org_width,
                        'unit': rec.unit,
                        'shape_id': rec.shape_id.id if rec.shape_id else False,
                        'shape_id_image': rec.shape_id.image if rec.shape_id and rec.shape_id.image else False,
                        'remarks': rec.remarks

                    }))
                else:
                    _logger.warning("Missing values for product: %s", rec.product_id.name)

            _logger.debug("Lines to Append: %s", lines)

            if processing_order:
                _logger.debug("Appending lines to existing Processing Order: %s", processing_order.id)
                processing_order.write({'processing_line_id': lines})
                _logger.debug("Updated existing Processing Order.")
            else:
                processing_order = self.env['processing.production.order'].create({
                    'partner_id': self.partner_id.id,
                    'sale_id': sale_id.id,  # Link with the sale order
                    'processing_line_id': lines
                })
                _logger.debug("Created new Processing Order: %s", processing_order.id)

        else:
            _logger.debug("This purchase order is not linked to a Sale Order. Skipping processing.")

        return super(Inventry, self).button_validate()


class StockMove(models.Model):

    _inherit = 'stock.move'

    org_length = fields.Float(string="Length")
    org_width = fields.Float(string="Width")
    unit = fields.Float(string="Pcs")
    shape_id = fields.Many2one(comodel_name='bracket.shapes', string="Shape")
    shape_id_image = fields.Binary(string="Image",related='shape_id.image')
    remarks = fields.Char(string='Remarks')
    purchase_line_id = fields.Many2one('purchase.order.line')




