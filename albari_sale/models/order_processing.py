from odoo import models, fields, api
from odoo.exceptions import UserError


class CustomProductionOrder(models.Model):
    _name = 'processing.production.order'
    _description = 'Custom Production Order'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        string="Production Order",
        required=True,
        copy=False,
        default=lambda self: self.env['ir.sequence'].next_by_code('custom.production.order')
    )
    date = fields.Datetime(
        string="Date"
    )
    company_id = fields.Many2one('res.company', string='Company', required=True,
                                 default=lambda self: self.env.company.id,
                                 help='The default company for this user.', )
    purchase_id = fields.Many2one('purchase.order', string='Purchase Order')
    sale_id = fields.Many2one('sale.order', string='sale order')
    sale_order_id = fields.Many2one(
        'sale.order',
        string="Sale Order",
        store=True,
        readonly=True
    )
    partner_id = fields.Many2one(
        comodel_name='res.partner', string='Customer', readonly=True
    )
    processing_line_id = fields.One2many('order.processing.line', 'production_order_id')

    status = fields.Selection([
        ('new', 'New'),
        ('in_progress', 'In Progress'),
        ('quality', 'Quality Check'),
        ('ready', 'Ready')

    ], string="Status", default='new')

    def action_set_new(self):
        self.status = 'new'

    def action_set_in_progress(self):
        self.status = 'in_progress'

    def action_set_ready(self):
        for rec in self.sale_id:
            rec.is_production_ready = True
        self.status = 'ready'

    def action_quality(self):
        self.status = 'quality'

    def action_set_cancel(self):
        pass


class SaleOrderLine(models.Model):
    _name = 'order.processing.line'

    product_id = fields.Many2one(
        comodel_name='product.product'
    )
    org_length = fields.Float(string="Length")
    org_width = fields.Float(string="Width")
    unit = fields.Float(string="Pcs")
    qty = fields.Float(string="SQFT")
    shape_id = fields.Many2one(comodel_name='bracket.shapes', string="Shape")
    shape_id_image = fields.Binary(string="Image")
    remarks = fields.Char(string='Remarks')

    production_order_id = fields.Many2one(
        comodel_name='processing.production.order',
        string="Production Order"
    )
