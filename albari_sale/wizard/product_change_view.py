from odoo import models, fields, api


class WizardProductChange(models.TransientModel):
    _name = 'wizard.product.change'
    _description = 'Change Product in Order Lines'

    order_line_ids = fields.Many2many(
        'sale.order.line',
        string="Order Lines Product",
        domain="[('order_id', '=', context.get('active_id'))]"
    )

    # Field for selecting a new product
    product_id = fields.Many2one('product.product', string="New Product")

    custom_price = fields.Float(string="New Price")


    def action_wizard_done(self):
        for wizard in self:
            if wizard.product_id:
                for order_line in wizard.order_line_ids:
                    # Update product details for each selected order line
                    order_line.product_id = wizard.product_id.id
                    order_line.name = wizard.product_id.name
                    # order_line.price_unit = wizard.product_id.list_price
                    order_line.product_uom = wizard.product_id.uom_id
                    order_line.price_unit = wizard.custom_price if wizard.custom_price else wizard.product_id.list_price

