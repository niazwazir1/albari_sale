from odoo import models, fields, api, _


class CheckSaleOrder(models.Model):
    _name = "check.order"

    name = fields.Char(string='Name')
    partner_id = fields.Many2one("res.partner", string="customer", readonly=True)
    check_order_id = fields.One2many('stock.check.line', 'check_order_id')
    order_id = fields.Many2one('sale.order', string='sale order')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('random', 'Random'),
        ('order_processing', 'Order Processing'),
        ('purchase_order', 'Purchase Order'),
        ('combo', 'Combo'),
        ('cancel', 'Cancel')

    ], string='state')

    po_id = fields.Many2one('purchase.order')
    production_order_id = fields.Many2one('processing.production.order')
    date = fields.Date(string='Date')



    def action_processing(self):
        return {
            'name': _('Delivery'),
            'type': 'ir.actions.act_window',
            'view_mode': 'tree,form',
            'res_model': 'processing.production.order',
            'res_id': self.production_order_id.id,
            'target': 'current',
        }

    def action_draft(self):
        self.state = 'draft'

    def action_random(self):
        lines = [(0, 0, {
            'product_id': rec.product_id.id,
            'org_length': rec.length,
            'org_width': rec.width,
            'unit': rec.unit,
            'qty': rec.qty,
            'shape_id': rec.shape_id.id if rec.shape_id else False,  # Correct ID is passed
            'shape_id_image': rec.shape_id_image,
            'remarks':rec.remarks
        }) for rec in self.check_order_id]

        po = self.env['processing.production.order'].create({
            'partner_id': self.partner_id.id,
            'sale_id': self.order_id.id,
            'processing_line_id': lines
        })
        self.state = 'random'

    def action_cancel(self):
        self.state = 'cancel'

    def action_purchase_order(self):
        lines = [(0, 0, {
            'product_id': rec.product_id.id,
            'org_length': rec.length,
            'org_width': rec.width,
            'unit': rec.unit,
            'product_qty': rec.qty,
            'shape_id': rec.shape_id.id if rec.shape_id else False,  # Correct ID is passed
            'shape_id_image': rec.shape_id_image,
            'remarks': rec.remarks,

        }) for rec in self.check_order_id]

        po = self.env['purchase.order'].create({
            'partner_id': self.partner_id.id,
            'sale_id': self.order_id.id,
            'order_line': lines
        })

        self.po_id = po.id
        self.state = 'purchase_order'

    def action_order_processing(self):
        lines = [(0, 0, {
            'product_id': rec.product_id.id,
            'qty': rec.qty,
            'org_length': rec.length,
            'org_width': rec.width,
            'unit': rec.unit,
            'shape_id': rec.shape_id.id if rec.shape_id else False,  # Correct ID is passed
            'shape_id_image': rec.shape_id_image,
            'remarks': rec.remarks,

        }) for rec in self.check_order_id]

        po = self.env['processing.production.order'].create({
            'partner_id': self.partner_id.id,
            'sale_id': self.order_id.id,
            'processing_line_id': lines
        })
        self.state = 'order_processing'

    def confirm_combo(self):
        operation_types = ['order_processing', 'purchase_order', 'random']

        order_processing_lines = []  # ✅ Merge 'order_processing' & 'random'
        purchase_order_lines = []

        for op_type in operation_types:
            # ✅ Filter only relevant records for this operation type (avoid duplicate processing)
            filtered_records = self.check_order_id.filtered(lambda rec: rec.operation_type == op_type)

            if not filtered_records:
                continue  # If no records for this type, skip iteration

            if op_type in ['order_processing', 'random']:
                order_processing_lines += [(0, 0, {
                    'product_id': rec.product_id.id,
                    'qty': rec.qty,  # ✅ Uses `qty`
                    'org_length': rec.length,
                    'org_width': rec.width,
                    'unit': rec.unit,
                    'shape_id': rec.shape_id.id if rec.shape_id else False,  # Correct ID is passed
                    'shape_id_image': rec.shape_id_image,
                    'remarks': rec.remarks,

                }) for rec in filtered_records]

            elif op_type == 'purchase_order':
                purchase_order_lines += [(0, 0, {
                    'product_id': rec.product_id.id,
                    'product_uom_qty': rec.qty,  # ✅ Uses `product_uom_qty`
                    'org_length': rec.length,
                    'org_width': rec.width,
                    'unit': rec.unit,
                    'product_qty': rec.qty,
                    'shape_id': rec.shape_id.id if rec.shape_id else False,  # Correct ID is passed
                    'shape_id_image': rec.shape_id_image,
                    'remarks': rec.remarks,

                }) for rec in filtered_records]

        # ✅ Create only ONE order for both 'order_processing' & 'random'
        if order_processing_lines:
            self.env['processing.production.order'].create({
                'partner_id': self.partner_id.id,
                'sale_id': self.order_id.id,
                'status': 'new',
                'processing_line_id': order_processing_lines  # ✅ One order for both types
            })

        # ✅ Purchase order remains separate
        if purchase_order_lines:
            self.po_id.create({
                'partner_id': self.partner_id.id,
                'sale_id': self.order_id.id,
                'order_line': purchase_order_lines
            })

        self.state = 'combo'


class SaleOrderActionWizard(models.Model):
    _name = 'stock.check.line'
    _description = 'Sale Order Action Wizard'
    check_order_id = fields.Many2one('check.order', string='Check Order')
    product_id = fields.Many2one(
        comodel_name='product.product'
    )
    length = fields.Float(string="Length")
    width = fields.Float(string="Width")
    unit = fields.Float(string="Pcs")
    qty = fields.Float(string="SQFT")
    shape_id = fields.Many2one(comodel_name='bracket.shapes', string="Shape")
    shape_id_image = fields.Binary(string="Image")
    remarks = fields.Char(string='Remarks')
    operation_type = fields.Selection([
        ('random', 'Random'),
        ('order_processing', 'Order Processing'),
        ('purchase_order', 'Purchase Order'),
        ('combo', 'Combo')
    ], string='operation_type', )
