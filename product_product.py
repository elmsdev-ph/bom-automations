from odoo import api, fields, models
import csv
import re
from odoo.modules.module import get_module_resource
from odoo.exceptions import ValidationError
import logging
import math
_logger = logging.getLogger(__name__)


class ProductProduct(models.Model):
    _inherit = "product.product"

    is_different_price = fields.Boolean(default=False)
    different_price = fields.Float()

    @api.constrains('name')
    def _check_unique_name(self):
        for record in self:
            if self.search([('name', '=', record.name), ('id', '!=', record.id)]):
                raise ValidationError("The product name must be unique. The name '{}' already exists.".format(record.name))

    @api.depends('list_price', 'price_extra', 'different_price', 'is_different_price')
    @api.depends_context('uom')
    def _compute_product_lst_price(self):
        to_uom = None
        if 'uom' in self._context:
            to_uom = self.env['uom.uom'].browse(self._context['uom'])
        for product in self:
            list_price = product.list_price if not product.is_different_price else product.different_price
            if to_uom:
                list_price = product.uom_id._compute_price(list_price, to_uom)
            else:
                list_price = list_price
            product.lst_price = list_price + product.price_extra

    @api.onchange('lst_price', 'different_price', 'is_different_price')
    def _set_product_lst_price(self):
        for product in self:
            if self._context.get('uom'):
                value = self.env['uom.uom'].browse(self._context['uom'])._compute_price(product.lst_price, product.uom_id)
            else:
                value = product.lst_price
            value -= product.price_extra
            product.write({'list_price': value})

    def price_compute(self, price_type, uom=None, currency=None, company=None, date=False):
        company = company or self.env.company
        date = date or fields.Date.context_today(self)
        self = self.with_company(company)
        if price_type == 'standard_price':
            self = self.sudo()
        prices = dict.fromkeys(self.ids, 0.0)
        for product in self:
            price = product[price_type] or 0.0
            if product.is_different_price:
                price = product.different_price
            price_currency = product.currency_id
            if price_type == 'standard_price':
                price_currency = product.cost_currency_id
            if price_type == 'list_price':
                price += product.price_extra
                if self._context.get('no_variant_attributes_price_extra'):
                    price += sum(self._context.get('no_variant_attributes_price_extra'))
            if uom:
                price = product.uom_id._compute_price(price, uom)
            if currency:
                price = price_currency._convert(price, currency, company, date)
            prices[product.id] = price
        return prices

    def unlink(self):
        for product in self:
            # Find and unlink BOMs associated with this product variant
            boms = self.env['mrp.bom'].search([('product_id', '=', product.id)])
            if boms:
                boms.unlink()
        return super(ProductProduct, self).unlink()

    @api.model_create_multi
    def create(self, vals_list):
        products = super().create(vals_list)
        for product in products:
            self._create_bom_for_variant(product)
            self._create_tre_pipe(product)
            self._create_cleaning_bucket(product)
            self._create_drilling_barrel(product)
            self._create_bored_pile(product)
            self._create_pile_casing(product)
            self.send_product_variant_creation_email(product)
        return products

    def _create_pile_casing(self, product):
        """ Create a BOM automation for pile casing components """
        if product.product_tmpl_id.name != 'Pile Casing Stock':
            return

        reference = product.display_name
        components = self._get_pile_casing_components(product)
        attributes = {attr.attribute_id.name: attr.name for attr in product.product_template_attribute_value_ids}
        drive_band = attributes.get('1) Drive Band Size', '') or attributes.get('Drive Band Type (A)', '') or attributes.get('Drive Band Type (B)', '')
        shoe = attributes.get('2) Shoe Size', '') or attributes.get('Shoe Type (A)', '') or attributes.get('Shoe Type (B)', '')

        is_dband_shoe = True if drive_band or shoe else False

        if not components:
            return

        self._create_pcs_bom_components(product, reference, components, is_dband_shoe)

    def _create_pcs_bom_components(self, product, reference, components, is_dband_shoe):
        bom_lines = []
        uom_meter = self.env.ref('uom.product_uom_meter', raise_if_not_found=False)
        unit = self.env.ref('uom.product_uom_unit', raise_if_not_found=False)

        for component_name, qty in components:
            keywords = {'Permanent Casing', 'Hollow Bar', 'Flat Bar', 'Pipe'}
            uom = uom_meter if any(keyword in component_name for keyword in keywords) else unit
            component = self.env['product.product'].search([('name', '=', component_name)], limit=1)
            if not component:
                component = self.env['product.product'].create({
                    'name': component_name,
                    'type': 'consu',
                    'is_storable': True,
                    'uom_id': uom.id,
                })
            bom_lines.append((0, 0, {
                'product_id': component.id,
                'product_qty': qty,
                'product_uom_id': uom.id,
            }))
        operation_ids = self._get_default_pcs_work_center(product, is_dband_shoe)
        Mrp_bom = self.env['mrp.bom'].create({
            'code': reference,
            'product_tmpl_id': product.product_tmpl_id.id,
            'product_id': product.id,
            'product_qty': 1.0,
            'type': 'normal',
            'bom_line_ids': bom_lines,
            'operation_ids': operation_ids,
        })
        return Mrp_bom

    def _get_default_pcs_work_center(self, product, is_dband_shoe):
        if is_dband_shoe:
            return self.get_with_dband_pile_casing_operations()
        else:
            return self.get_without_dband_pile_casing_operations()

    def get_with_dband_pile_casing_operations(self):
        operations = [
            {
                'name': 'Rolling',
                'workcenter_id': 9,  # Plate Rollers - Rolling
                'time_mode': 'auto',
                'time_cycle_manual': 0.0,
            },
            {
                'name': 'Tacking',
                'workcenter_id': 1,  # Welding Bay - 1 (Trent)
                'time_mode': 'auto',
                'time_cycle_manual': 0.0,
            },
            {
                'name': 'Welding',
                'workcenter_id': 4,  # Welding Bay - 4 (Riley)
                'time_mode': 'auto',
                'time_cycle_manual': 0.0,
            }
        ]
        operation_lines = [(0, 0, op) for op in operations]
        return operation_lines

    def get_without_dband_pile_casing_operations(self):
        operations = [
            {
                'name': 'Tacking',
                'workcenter_id': 1,  # Welding Bay - 1 (Trent)
                'time_mode': 'auto',
                'time_cycle_manual': 0.0,
            },
            {
                'name': 'Welding',
                'workcenter_id': 4,  # Welding Bay - 4 (Riley)
                'time_mode': 'auto',
                'time_cycle_manual': 0.0,
            }
        ]
        operation_lines = [(0, 0, op) for op in operations]
        return operation_lines

    def _get_pile_casing_components(self, product):
        """
            param: product_template_attribute_value_ids; we retrieve all attribute values excluding N/A.
            return: a list of items & qty for pile casing component.
        """
        attributes = {attr.attribute_id.name: attr.name for attr in product.product_template_attribute_value_ids}
        casing_type = attributes.get('Casing Type', '')
        diameter = attributes.get('Inside Diameter', '')
        w_thickness = attributes.get('Wall Thickness', '')
        segment = attributes.get('Segment')
        c_length = attributes.get('Casing Length', '')

        d_band_size = attributes.get('1) Drive Band Size', '')
        d_band_type_a = attributes.get('Drive Band Type (A)', '')
        d_band_type_b = attributes.get('Drive Band Type (B)', '')

        shoe_size = attributes.get('2) Shoe Size')
        shoe_type_a = attributes.get('Shoe Type (A)')
        shoe_type_b = attributes.get('Shoe Type (B)')

        lock_type = attributes.get('Lock Type', '')
        lift_holes = attributes.get('Lift Holes')
        teeth = attributes.get('Teeth', '')
        no_of_teeth = attributes.get('No. of Teeth', '')
        customization = attributes.get('Customization', '')

        def _permanent_casing_combination(diameter, w_thickness):
            """
                return: formatted permanent casing string
            """
            od = 0
            wall = 0
            wall_str = 0

            od_match = re.search(r'(\d+)\s*mm', diameter, re.IGNORECASE)
            wt_match = re.search(r'(\d+(?:\.\d+)?)\s*mm', w_thickness, re.IGNORECASE)

            if od_match:
                od = int(od_match.group(1))
            if wt_match:
                wall_str = wt_match.group(1)
                wall = float(wt_match.group(1))
            od = od + ( 2 * wall)
            return f"Permanent Casing - OD{int(od)} WT{wall_str}"

        permanent_casing = _permanent_casing_combination(diameter, w_thickness)
        product_exist = self.env['product.template'].search([('name', '=', permanent_casing)], limit=1)

        od_match = re.search(r'(\d+)\s*mm', diameter or "", re.IGNORECASE)
        diameter_mm = str(od_match.group(1)) if od_match else ""

        if product_exist:
            return self._get_casing_component(casing_type, diameter, w_thickness, segment, c_length, d_band_size, d_band_type_a, d_band_type_b, no_of_teeth, shoe_size, shoe_type_a, shoe_type_b, lock_type, lift_holes, permanent_casing, teeth)
        else:
            raise ValidationError("Oops! Casing is not available, please review the selection")

    def _get_casing_component(self, casing_type, diameter, w_thickness, segment, c_length, d_band_size, d_band_type_a, d_band_type_b, no_of_teeth, shoe_size, shoe_type_a, shoe_type_b, lock_type, lift_holes, permanent_casing, teeth):
        # Extract numbers of attribute values
        casing_match = re.search(r"\d+\.?\d*", c_length)
        no_teeth_match = re.search(r"\d+\.?\d*", no_of_teeth)
        inside_dia = float(re.search(r"\d+\.?\d*", diameter).group())
        wall_thickness = float(re.search(r"\d+\.?\d*", w_thickness).group())

        # Qty for permanent casing and teeth attribute
        casing_qty = float(casing_match.group()) if casing_match else 0
        teeth_qty = int(no_teeth_match.group()) if no_teeth_match else 0

        def _get_dband_shoe_qty(type, inside_dia, wall_thickness, at_sizes):
            """
            Calculate the quantity (meter) of the ID aligned, OD aligned, and overlapped
            """
            # Handle case where sizes is None or empty - return early
            if not at_sizes:
                return 0.0

            attr_sizes = re.search(r"x(\d+)t", at_sizes)
            flat_bar_thickness = int(attr_sizes.group(1)) if attr_sizes else 0

            if type == 'id_align':
                total_id_aligned_db_mm = (inside_dia + flat_bar_thickness) * math.pi
                ia_mm_qty = round(total_id_aligned_db_mm / 1000, 2)
                return ia_mm_qty
            elif type == 'od_align':
                total_od_aligned_db_mm = (inside_dia + (wall_thickness * 2) - flat_bar_thickness) * math.pi
                oa_mm_qty = round(total_od_aligned_db_mm / 1000, 2)
                return oa_mm_qty
            else:
                total_overlapped_db_mm = (inside_dia + (wall_thickness * 2) + 6 + flat_bar_thickness) * math.pi
                ol_mm_qty = round(total_overlapped_db_mm / 1000, 2)
                return ol_mm_qty

        # Flat Bar items
        def _get_dband_shoe_sizes(size):
            attribute_size = re.search(r"(\d+)x(\d+)t", size)
            width = int(attribute_size.group(1)) if attribute_size else 0.0
            thickness = int(attribute_size.group(2)) if attribute_size else 0.0
            flat_bar = f"Flat Bar - {width}mm x {thickness}mm" if width and thickness else ""
            return flat_bar

        #flat_bar_dband = _get_dband_shoe_sizes(d_band_size)
        #flat_Bar_shoe = _get_dband_shoe_sizes(shoe_size)

        flat_bar_dband = _get_dband_shoe_sizes(d_band_size or "")
        flat_bar_shoe = _get_dband_shoe_sizes(shoe_size or "")

        pcs_name = "Profiling - Pile Casing Stock"

        if d_band_type_b == 'Profiled Drive Band' and shoe_type_b != 'Profiled Casing Shoe':

            parts = [casing_type, segment, diameter, w_thickness, d_band_size, d_band_type_a, lock_type, lift_holes]
            parts = [str(p) for p in parts if p is not None and p != '']
            profiling = f"{pcs_name} {', '.join(parts)}"

            standard = [(permanent_casing, casing_qty)]
            standard.extend([
                (profiling, 1)
            ])
            if shoe_size:
                type = 'id_align' if shoe_type_a == 'ID Aligned Casing Shoe' else 'od_align'
                fb_qty = _get_dband_shoe_qty(type, inside_dia, wall_thickness, shoe_size)

                standard.extend([
                    (flat_bar_shoe, fb_qty)
                ])
            if teeth:
                standard.extend([
                    ('BFZ318TB - Weld on Casing teeth', teeth_qty)
                ])
            return standard

        if shoe_type_b == 'Profiled Casing Shoe' and d_band_type_b != 'Profiled Drive Band':
            parts = [casing_type, segment, diameter, w_thickness, shoe_size, shoe_type_a]
            parts = [str(p) for p in parts if p is not None and p != '']
            profiling = f"{pcs_name} {', '.join(parts)}"

            standard = [(permanent_casing, casing_qty)]
            if d_band_size:
                type = 'id_align' if d_band_type_a == 'ID Aligned Drive Band' else 'ol'
                fb_qty = _get_dband_shoe_qty(type, inside_dia, wall_thickness, d_band_size)

                standard.extend([
                    (flat_bar_dband, fb_qty)
                ])
            standard.extend([
                    (profiling, 1)
                ])
            if teeth:
                standard.extend([
                    ('BFZ318TB - Weld on Casing teeth', teeth_qty)
                ])
            return standard

        if d_band_type_b == 'Profiled Drive Band' and shoe_type_b == 'Profiled Casing Shoe':
            parts = [casing_type, segment, diameter, w_thickness, d_band_size, d_band_type_a, shoe_size, shoe_type_a, lock_type, lift_holes]
            parts = [str(p) for p in parts if p is not None and p != '']
            profiling = f"{pcs_name} {', '.join(parts)}"

            standard = [(permanent_casing, casing_qty)]
            standard.extend([
                    (profiling, 1)
                ])
            if teeth:
                standard.extend([
                    ('BFZ318TB - Weld on Casing teeth', teeth_qty)
                ])
            return standard

        if not any([d_band_size, d_band_type_a, d_band_type_b, shoe_size, shoe_type_a, shoe_type_b]):
            standard = [(permanent_casing, casing_qty)]
            if teeth:
                standard.extend([
                    ('BFZ318TB - Weld on Casing teeth', teeth_qty)
                ])
            return standard

        # Drive band and shoe if not the same sizes, use a once flat bar item, otherwise show both
        SIZE_RE = re.compile(r'(?i)\b(\d+(?:\.\d+)?)\s*x\s*(\d+(?:\.\d+)?)\s*t\b')

        def parse_size(s: str):
            """Return (diameter_mm, thickness_mm) as floats, or None if not found."""
            m = SIZE_RE.search(s or '')
            return (float(m.group(1)), float(m.group(2))) if m else None

        def sizes_equal(a: str, b: str, dia_tol=0.0, thk_tol=0.0) -> bool:
            """
            Compare sizes with optional mm tolerances.
            dia_tol/thk_tol let you accept minor differences (e.g., 0.5 mm).
            """
            pa, pb = parse_size(a), parse_size(b)
            if not pa or not pb:
                return False
            (ad, at), (bd, bt) = pa, pb
            return abs(ad - bd) <= dia_tol and abs(at - bt) <= thk_tol

        has_same_size = sizes_equal(d_band_size, shoe_size)
        d_type = 'id_align' if d_band_type_a == 'ID Aligned Drive Band' else 'ol'
        s_type = 'id_align' if shoe_type_a == 'ID Aligned Casing Shoe' else 'od_align'

        fb_dband_qty = _get_dband_shoe_qty(d_type, inside_dia, wall_thickness, d_band_size)
        fb_shoe_qty = _get_dband_shoe_qty(s_type, inside_dia, wall_thickness, shoe_size)
        tot_fb_qty = fb_dband_qty + fb_shoe_qty

        if has_same_size:
            item_lst = [(permanent_casing, casing_qty)]        
            item_lst.extend([
                (flat_bar_dband, tot_fb_qty)
            ])
            if teeth:
                item_lst.extend([
                    ('BFZ318TB - Weld on Casing teeth', teeth_qty)
                ])
            return item_lst
        else:
            item_lst = [(permanent_casing, casing_qty)]
            if flat_bar_dband:
                item_lst.extend([
                    (flat_bar_dband, fb_dband_qty)
                ])
            if flat_bar_shoe:
                item_lst.extend([
                    (flat_bar_shoe, fb_shoe_qty)
                ])
            if teeth:
                item_lst.extend([
                    ('BFZ318TB - Weld on Casing teeth', teeth_qty)
                ])
            return item_lst

    def _create_bored_pile(self, product):
        """
        Create a BOM component for Bored Pile Auger
        """
        if product.product_tmpl_id.name != 'Bored Pile Auger':
            return

        reference = product.display_name
        components = self._get_bored_pile_component(product)
        _logger.info("bored pile components... %s", components)
        # raise ValidationError(f"This is bored... {components}")
        self._create_bom_components(product, reference, components)

    def _get_bored_pile_component(self, product):
        """
        param: product.template to get the product attributes 
        return: a list of items to create bom components 
        """
        components = []
        p_name = product.product_tmpl_id.name
        attributes = {attr.attribute_id.name: attr.name for attr in product.product_template_attribute_value_ids}
        type = attributes.get('Type', '')
        diameter = attributes.get('Auger Diameter', '')
        drive_head = attributes.get('Drive Head', '')
        overall_length = attributes.get('Overall Length', '')
        flighted_length = attributes.get('Flighted Length', '')
        rotation = attributes.get('Rotation', '')
        teeth = attributes.get('Teeth', '')
        reamer_teeth = attributes.get('Reamer Teeth')
        pilot = attributes.get('Pilot', '')
        center_tube = attributes.get('Centre Tube', '')
        lead_flight_od = attributes.get('Lead Flight OD', '')
        lead_flight_pt = attributes.get('Lead Flight Pitch', '')
        carrier_lead_flight_od = attributes.get('Carrier Flight OD', '')
        carrier_lead_flight_pt = attributes.get('Carrier Flight Pitch', '')
        override_bom = attributes.get('Override BOM', '')

        if type in ['Taper Rock', 'Dual Rock']:
            components = self._get_bp_dual_taper_rock(type, diameter, drive_head, overall_length, flighted_length, rotation, teeth, pilot, center_tube, lead_flight_od, lead_flight_pt, carrier_lead_flight_od, carrier_lead_flight_pt, override_bom)
        elif type == 'Triad Rock':
            components = self._get_bp_triad_rock(type, diameter, drive_head, overall_length, flighted_length, rotation, teeth, pilot, center_tube, lead_flight_od, lead_flight_pt, carrier_lead_flight_od, carrier_lead_flight_pt, override_bom)
        elif type in ['ZED 25mm', 'ZED 32mm', 'ZED 40mm', 'ZED 50mm']: 
            components = self._get_bp_zed(type, diameter, drive_head, overall_length, flighted_length, rotation, teeth, pilot, center_tube, lead_flight_od, lead_flight_pt, carrier_lead_flight_od, carrier_lead_flight_pt, override_bom)
        elif type == 'Clay/Shale':
            components = self._get_bp_clay_shale(type, diameter, drive_head, overall_length, flighted_length, rotation, teeth, pilot, center_tube, lead_flight_od, lead_flight_pt, carrier_lead_flight_od, carrier_lead_flight_pt, override_bom)
        else:
            # list of items for blade
            components = self._get_bp_blade(type, diameter, drive_head, overall_length, flighted_length, rotation, teeth, pilot, center_tube, lead_flight_od, lead_flight_pt, carrier_lead_flight_od, carrier_lead_flight_pt, override_bom)
        return components

    def _get_base_plate(self, dhead):
        exclude_dhead = {
            'Drive Head - 65mm Round', 'Drive Head - 65mm Square', 'Drive Head - 75mm Square',
            'Drive Head - 4" Lo Drill', 'Drive Head - 3" Hex', 'Drive Head - 2" Hex', 'Custom Head'
        }

        if dhead in exclude_dhead:
            return (None, 0)

        mapping = {
            'Drive Head - 100mm Square': 100,
            'Drive Head - 110mm Square': 110,
            'Drive Head - 130mm Square': 130,
            'Drive Head - 130mm Square DIGGA': 130,
            'Drive Head - 150mm Square': 150,
            'Drive Head - 150mm Square IMT': 150,
        }

        size = mapping.get(dhead, 200)
        return (f"Base Plate - {size}mm Head", 1)

    def _get_tube_guesset(self, drive_head, centre_tube):
        """
        Returns the gusset component based on drive head and center shaft.
        
        Args:
            drive_head (str): The name of the drive head.
            centre_tube (str): The name of the center shaft.
        
        Returns:
            tuple or None: A tuple like ("Gusset - 100mm Drive 150mm Tube", 1) or None if not applicable.
        """
        dhead_100_110_mm = ['Drive Head - 100mm Square', 'Drive Head - 110mm Square']
        dhead_130_mm = ['Drive Head - 130mm Square', 'Drive Head - 130mm Square DIGGA']
        dhead_150_mm = ['Drive Head - 150mm Square', 'Drive Head - 150mm Square IMT']
        dhead_200_mm = ['Drive Head - 200mm Square Bauer', 'Drive Head - 200mm Square MAIT']

        gusset_map = {
            'dhead_100_110_mm': {
                # Hollow Bars
                'Hollow Bar - OD128mm WT 11.5mm': "Gusset - 100mm Drive 150mm Tube",
                'Hollow Bar - OD150mm ID120mm': "Gusset - 100mm Drive 150mm Tube",
                'Hollow Bar - OD152mm WT 26mm': "Gusset - 100mm Drive 150mm Tube",
                'Hollow Bar - OD152mm WT 33.5mm': "Gusset - 100mm Drive 150mm Tube",
                'Hollow Bar - OD168mm WT 21.5mm': "Gusset - 100mm Drive 170mm Tube",
                'Hollow Bar - OD168mm WT 29mm': "Gusset - 100mm Drive 170mm Tube",
                'Hollow Bar - OD170mm ID140mm': "Gusset - 100mm Drive 170mm Tube",
                'Hollow Bar - OD180 ID150': "Gusset - 100mm Drive 170mm Tube",
                'Hollow bar - OD200 ID150': "Gusset - 100mm Drive 170mm Tube",
                'Hollow Bar - OD219mm WT 25mm': "Gusset - 100mm Drive 219mm Tube",
                # Pipes
                'Pipe - OD168mm WT6.4mm': "Gusset - 100mm Drive 170mm Tube",
                'Pipe - OD168mm WT4.8mm': "Gusset - 100mm Drive 170mm Tube",
                'Pipe - OD168mm WT11mm': "Gusset - 100mm Drive 170mm Tube",
                'Pipe - OD177mm WT 8mm': "Gusset - 100mm Drive 170mm Tube",
                'Pipe - OD219mm WT8.2mm': "Gusset - 100mm Drive 219mm Tube",
                'Pipe - OD219mm WT6.4mm': "Gusset - 100mm Drive 219mm Tube",
                'Pipe - OD219mm WT12.7mm': "Gusset - 100mm Drive 219mm Tube",
            },
            'dhead_130_mm': {
                # Hollow Bars
                'Hollow Bar - OD150mm ID120mm': "Gusset - 130mm Drive 150mm Tube",
                'Hollow Bar - OD152mm WT 26mm': "Gusset - 130mm Drive 150mm Tube",
                'Hollow Bar - OD152mm WT 33.5mm': "Gusset - 130mm Drive 150mm Tube",
                'Hollow Bar - OD168mm WT 21.5mm': "Gusset - 130mm Drive 170mm Tube",
                'Hollow Bar - OD168mm WT 29mm': "Gusset - 130mm Drive 170mm Tube",
                'Hollow Bar - OD170mm ID140mm': "Gusset - 130mm Drive 170mm Tube",
                'Hollow Bar - OD180 ID150': "Gusset - 130mm Drive 170mm Tube",
                'Hollow bar - OD200 ID150': "Gusset - 130mm Drive 170mm Tube",
                'Hollow Bar - OD219mm WT 25mm': "Gusset - 130mm Drive 219mm Tube",
                'hollow bar - OD273mm WT14': "Gusset - 130mm Drive 273mm Tube",
                'Hollow Bar - OD273mm WT 25mm': "Gusset - 130mm Drive 273mm Tube",
                'Hollow Bar - OD273mm WT 32mm': "Gusset - 130mm Drive 273mm Tube",
                'Hollow Bar - OD323mm WT25mm': "Gusset - 130mm Drive 323mm Tube",
                'Hollow Bar - OD323mm WT30mm': "Gusset - 130mm Drive 323mm Tube",
                'Hollow Bar - OD356 ID306': "Gusset - 130mm Drive 323mm Tube",
                'Hollow bar - OD457mm T35mm': "Gusset - 130mm Drive 323mm Tube",
                'Hollow bar - OD457mm T25mm': "Gusset - 130mm Drive 323mm Tube",
                # Pipes
                'Pipe - OD168mm WT6.4mm': "Gusset - 130mm Drive 170mm Tube",
                'Pipe - OD168mm WT4.8mm': "Gusset - 130mm Drive 170mm Tube",
                'Pipe - OD168mm WT11mm': "Gusset - 130mm Drive 170mm Tube",
                'Pipe - OD177mm WT 8mm': "Gusset - 130mm Drive 170mm Tube",
                'Pipe - OD219mm WT8.2mm': "Gusset - 130mm Drive 219mm Tube",
                'Pipe - OD219mm WT6.4mm': "Gusset - 130mm Drive 219mm Tube",
                'Pipe - OD219mm WT12.7mm': "Gusset - 130mm Drive 219mm Tube",
                'Pipe - OD273mm WT9.3mm': "Gusset - 130mm Drive 273mm Tube",
                'Pipe - OD273mm WT6.4mm': "Gusset - 130mm Drive 273mm Tube",
                'Pipe - OD273mm WT12.7mm': "Gusset - 130mm Drive 273mm Tube",
                'Pipe - OD323mm WT9.75mm': "Gusset - 130mm Drive 323mm Tube",
                'Pipe - OD323mm WT9.5mm': "Gusset - 130mm Drive 323mm Tube",
                'Pipe - OD323mm WT6.4mm': "Gusset - 130mm Drive 323mm Tube",
                'Pipe - OD323mm WT12.7mm': "Gusset - 130mm Drive 323mm Tube",
                'Pipe - OD355 WT9.5mm': "Gusset - 130mm Drive 323mm Tube",
                'Pipe - OD355mm WT12.7mm': "Gusset - 130mm Drive 323mm Tube",
                'Pipe - 406mm 9.5mm WT': "Gusset - 130mm Drive 323mm Tube",
                'Pipe - OD406mm WT12.7mm': "Gusset - 130mm Drive 323mm Tube",
                'Pipe - OD457mm WT9.5mm': "Gusset - 130mm Drive 323mm Tube",
                'Pipe - OD457mm WT15.9mm': "Gusset - 130mm Drive 323mm Tube",
            },
            'dhead_150_mm': {
                # Hollow Bars
                'Hollow Bar - OD150mm ID120mm': "Gusset - 150mm Drive 150mm Tube",
                'Hollow Bar - OD152mm WT 26mm': "Gusset - 150mm Drive 150mm Tube",
                'Hollow Bar - OD152mm WT 33.5mm': "Gusset - 150mm Drive 150mm Tube",
                'Hollow Bar - OD168mm WT 21.5mm': "Gusset - 150mm Drive 170mm Tube",
                'Hollow Bar - OD168mm WT 29mm': "Gusset - 150mm Drive 170mm Tube",
                'Hollow Bar - OD170mm ID140mm': "Gusset - 150mm Drive 170mm Tube",
                'Hollow Bar - OD180 ID150': "Gusset - 150mm Drive 170mm Tube",
                'Hollow bar - OD200 ID150': "Gusset - 150mm Drive 170mm Tube",
                'Hollow Bar - OD219mm WT 25mm': "Gusset - 150mm Drive 170mm Tube",
                'Hollow bar - OD273mm WT14': "Gusset - 150mm Drive 273mm Tube",
                'Hollow Bar - OD273mm WT 25mm': "Gusset - 150mm Drive 273mm Tube",
                'Hollow Bar - OD273mm WT 32mm': "Gusset - 150mm Drive 273mm Tube",
                'Hollow Bar - OD323mm WT25mm': "Gusset - 150mm Drive 273mm Tube",
                'Hollow Bar - OD323mm WT30mm': "Gusset - 150mm Drive 273mm Tube",
                'Hollow Bar - OD356 ID306': "Gusset - 150mm Drive 273mm Tube",
                'Hollow bar - OD457mm T35mm': "Gusset - 150mm Drive 273mm Tube",
                'Hollow bar - OD457mm T25mm': "Gusset - 150mm Drive 273mm Tube",
                # Pipes
                'Pipe - OD168mm WT6.4mm': "Gusset - 130mm Drive 170mm Tube",
                'Pipe - OD168mm WT4.8mm': "Gusset - 130mm Drive 170mm Tube",
                'Pipe - OD168mm WT11mm': "Gusset - 130mm Drive 170mm Tube",
                'Pipe - OD177mm WT 8mm': "Gusset - 130mm Drive 170mm Tube",
                'Pipe - OD219mm WT8.2mm': "Gusset - 130mm Drive 219mm Tube",
                'Pipe - OD219mm WT6.4mm': "Gusset - 130mm Drive 219mm Tube",
                'Pipe - OD219mm WT12.7mm': "Gusset - 130mm Drive 219mm Tube",
                'Pipe - OD273mm WT9.3mm': "Gusset - 150mm Drive 273mm Tube",
                'Pipe - OD273mm WT6.4mm': "Gusset - 150mm Drive 273mm Tube",
                'Pipe - OD273mm WT12.7mm': "Gusset - 150mm Drive 273mm Tube",
                'Pipe - OD323mm WT9.75mm': "Gusset - 150mm Drive 273mm Tube",
                'Pipe - OD323mm WT9.5mm': "Gusset - 150mm Drive 273mm Tube",
                'Pipe - OD323mm WT6.4mm': "Gusset - 150mm Drive 273mm Tube",
                'Pipe - OD323mm WT12.7mm': "Gusset - 150mm Drive 273mm Tube",
                'Pipe - OD355 WT9.5mm': "Gusset - 150mm Drive 273mm Tube",
                'Pipe - OD355mm WT12.7mm': "Gusset - 150mm Drive 273mm Tube",
                'Pipe - 406mm 9.5mm WT': "Gusset - 150mm Drive 273mm Tube",
                'Pipe - OD406mm WT12.7mm': "Gusset - 150mm Drive 273mm Tube",
                'Pipe - OD457mm WT9.5mm': "Gusset - 150mm Drive 273mm Tube",
                'Pipe - OD457mm WT15.9mm': "Gusset - 150mm Drive 273mm Tube",
            },
            'dhead_200_mm': {
                # Hollow Bars
                'Hollow Bar - OD168mm WT 21.5mm': "Gusset - 200mm Drive 170mm Tube",
                'Hollow Bar - OD168mm WT 29mm': "Gusset - 200mm Drive 170mm Tube",
                'Hollow Bar - OD170mm ID140mm': "Gusset - 200mm Drive 170mm Tube",
                'Hollow Bar - OD180 ID150': "Gusset - 200mm Drive 170mm Tube",
                'Hollow bar - OD200 ID150': "Gusset - 200mm Drive 170mm Tube",
                'Hollow Bar - OD219mm WT 25mm': "Gusset - 200mm Drive 170mm Tube",
                'Hollow bar - OD273mm WT14': "Gusset - 200mm Drive 273mm Tube",
                'Hollow Bar - OD273mm WT 25mm': "Gusset - 200mm Drive 273mm Tube",
                'Hollow Bar - OD273mm WT 32mm': "Gusset - 200mm Drive 273mm Tube",
                'Hollow Bar - OD323mm WT25mm': "Gusset - 200mm Drive 273mm Tube",
                'Hollow Bar - OD323mm WT30mm': "Gusset - 200mm Drive 273mm Tube",
                'Hollow Bar - OD356 ID306': "Gusset - 200mm Drive 273mm Tube",
                'Hollow bar - OD457mm T35mm': "Gusset - 200mm Drive 273mm Tube",
                'Hollow bar - OD457mm T25mm': "Gusset - 200mm Drive 273mm Tube",
                # Pipes
                'Pipe - OD168mm WT6.4mm': "Gusset - 200mm Drive 170mm Tube",
                'Pipe - OD168mm WT4.8mm': "Gusset - 200mm Drive 170mm Tube",
                'Pipe - OD168mm WT11mm': "Gusset - 200mm Drive 170mm Tube",
                'Pipe - OD177mm WT 8mm': "Gusset - 200mm Drive 170mm Tube",
                'Pipe - OD219mm WT8.2mm': "Gusset - 200mm Drive 170mm Tube",
                'Pipe - OD219mm WT6.4mm': "Gusset - 200mm Drive 170mm Tube",
                'Pipe - OD219mm WT12.7mm': "Gusset - 200mm Drive 170mm Tube",
                'Pipe - OD273mm WT9.3mm': "Gusset - 200mm Drive 273mm Tube",
                'Pipe - OD273mm WT6.4mm': "Gusset - 200mm Drive 273mm Tube",
                'Pipe - OD273mm WT12.7mm': "Gusset - 200mm Drive 273mm Tube",
                'Pipe - OD323mm WT9.75mm': "Gusset - 200mm Drive 273mm Tube",
                'Pipe - OD323mm WT9.5mm': "Gusset - 200mm Drive 273mm Tube",
                'Pipe - OD323mm WT6.4mm': "Gusset - 200mm Drive 273mm Tube",
                'Pipe - OD323mm WT12.7mm': "Gusset - 200mm Drive 273mm Tube",
                'Pipe - OD355 WT9.5mm': "Gusset - 200mm Drive 273mm Tube",
                'Pipe - OD355mm WT12.7mm': "Gusset - 200mm Drive 273mm Tube",
                'Pipe - 406mm 9.5mm WT': "Gusset - 200mm Drive 273mm Tube",
                'Pipe - OD406mm WT12.7mm': "Gusset - 200mm Drive 273mm Tube",
                'Pipe - OD457mm WT9.5mm': "Gusset - 200mm Drive 273mm Tube",
                'Pipe - OD457mm WT15.9mm': "Gusset - 200mm Drive 273mm Tube",
            }
        }

        # Support for shared mapping between similar drive heads
        d_head = ''
        if drive_head in dhead_100_110_mm:
            d_head = 'dhead_100_110_mm'
        elif drive_head in dhead_130_mm:
            d_head = 'dhead_130_mm'
        elif drive_head in dhead_150_mm:
            d_head = 'dhead_150_mm'
        elif drive_head in dhead_200_mm:
            d_head = 'dhead_200_mm'

        gusset_label = gusset_map.get(d_head, {}).get(centre_tube)

        return (gusset_label, 1) if gusset_label else (None, 0)

    def _get_zed_center_component_map(self, center_tube):
        zed_center_mapping = {
            'Hollow Bar - OD150mm ID120mm': "ZED Centre 150mm",
            'Hollow Bar - OD152mm WT 26mm': "ZED Centre 150mm",
            'Hollow Bar - OD152mm WT 33.5mm': "ZED Centre 150mm",
            'Hollow Bar - OD168mm WT 21.5mm': "ZED Centre 168mm",
            'Hollow Bar - OD168mm WT 29mm': "ZED Centre 168mm",
            'Hollow Bar - OD170mm ID140mm': "ZED Centre 168mm",
            'Hollow Bar - OD219mm WT 25mm': "ZED Centre 219mm",
            'hollow bar - OD273mm WT14': "ZED Centre 273mm",
            'Hollow Bar - OD273mm WT 25mm': "ZED Centre 273mm",
            'Hollow Bar - OD273mm WT 32mm': "ZED Centre 273mm",
            'Pipe - OD168mm WT11mm': "ZED Centre 168mm",
            'Pipe - OD219mm WT12.7mm': "ZED Centre 219mm",
            'Pipe - OD273mm WT12.7mm': "ZED Centre 273mm"
        }
        return zed_center_mapping.get(center_tube, "")

    def _get_center_tube_zed(self, overall_length, drive_head, center_tube, zed_center):
        """
            return a component for center tube items and qty based on zed type
        """
        match = re.search(r'\d+', overall_length)
        o_length = int(match.group()) if match else 0
        drive_head_map = {
            "Drive Head - 65mm Round": [100],
            "Drive Head - 65mm Square": [100],
            "Drive Head - 75mm Square": [150],
            "Drive Head - 100mm Square": [175, 25],
            "Drive Head - 110mm Square": [240, 25],
            "Drive Head - 130mm Square": [260, 32],
            "Drive Head - 130mm Square DIGGA": [260, 32],
            "Drive Head - 150mm Square": [260, 32],
            "Drive Head - 150mm Square IMT": [260, 32],
            "Drive Head - 200mm Square Bauer": [475, 32],
            "Drive Head - 200mm Square MAIT": [345, 32],
            "Drive Head - 4\" Lo Drill": [332, 25],
            "Drive Head - 3\" Hex": [155],
            "Drive Head - 2\" Hex": [135]
        }
        drive_head_num = drive_head_map.get(drive_head, 0)
        drive_head_height = drive_head_num[0]
        drive_head_base_plate = drive_head_num[1]
        zed_height_map = {
            "ZED Centre 150mm": round((o_length - drive_head_height - drive_head_base_plate - 133.5) / 1000, 2),
            "ZED Centre 168mm": round((o_length - drive_head_height - drive_head_base_plate - 147.5) / 1000, 2),
            "ZED Centre 219mm": round((o_length - drive_head_height - drive_head_base_plate - 163) / 1000, 2),
            "ZED Centre 273mm": round((o_length - drive_head_height - drive_head_base_plate - 163) / 1000, 2)
        }
        return (center_tube, zed_height_map.get(zed_center, 0))

    def _get_center_tube(self, overall_length, drive_head, center_tube, pilot_supp):
        pilot_support = pilot_supp[0] if pilot_supp else ""
        match = re.search(r'\d+', overall_length)
        o_length = int(match.group()) if match else 0

        pilot_support_map = {
            "Pilot Support - Hex": 75,
            "Pilot Support - 75mm Square": 70,
            "Pilot Support - 100mm Square": 100,
            "Pipe - OD101mm WT4.0mm": 70,
        }
        MM_TO_M = 1000
        pilot_offset = pilot_support_map.get(pilot_support, 0)

        drive_head_map = {
            "Drive Head - 65mm Round": round((o_length - 100 - pilot_offset) / MM_TO_M, 2),
            "Drive Head - 65mm Square": round((o_length - 100 - pilot_offset) / MM_TO_M, 2),
            "Drive Head - 75mm Square": round((o_length - 150 - pilot_offset) / MM_TO_M, 2),
            "Drive Head - 100mm Square": round((o_length - 175 - 25 - pilot_offset) / MM_TO_M, 2),
            "Drive Head - 110mm Square": round((o_length - 240 - 25 - pilot_offset) / MM_TO_M, 2),
            "Drive Head - 130mm Square": round((o_length - 260 - 32 - pilot_offset) / MM_TO_M, 2),
            "Drive Head - 130mm Square DIGGA": round((o_length - 260 - 32 - pilot_offset) / MM_TO_M, 2),
            "Drive Head - 150mm Square": round((o_length - 260 - 32 - pilot_offset) / MM_TO_M, 2),
            "Drive Head - 150mm Square IMT": round((o_length - 260 - 32 - pilot_offset) / MM_TO_M, 2),
            "Drive Head - 200mm Square Bauer": round((o_length - 457 - 32 - pilot_offset) / MM_TO_M, 2),
            "Drive Head - 200mm Square MAIT": round((o_length - 345 - 32 - pilot_offset) / MM_TO_M, 2),
            "Drive Head - 4\" Lo Drill": round((o_length - 332 - 25 - pilot_offset) / MM_TO_M, 2),
            "Drive Head - 3\" Hex": round((o_length - 155 - pilot_offset) / MM_TO_M, 2),
            "Drive Head - 2\" Hex": round((o_length - 135 - pilot_offset) / MM_TO_M, 2),
        }
        return (center_tube, drive_head_map.get(drive_head, 0))

    def _get_flight_brace_components(self, dhead, carrier_lead_flight_od, carrier_lead_flight_pt):
        """
        return: flight brace components
            exclude: Not applicable to 65mm, 75mm, 100mm, 110mm, 4" Lo Drill, 3" Hex, 2" Hex and Custom Heads
        """
        exclude_dhead = {
            'Drive Head - 65mm Round', 'Drive Head - 65mm Square', 'Drive Head - 75mm Square',
            'Drive Head - 100mm Square', 'Drive Head - 110mm Square', 'Drive Head - 4" Lo Drill',
            'Drive Head - 3" Hex', 'Drive Head - 2" Hex', 'Custom Head'
        }

        if dhead in exclude_dhead:
            return []

        fb_qty = 1 if carrier_lead_flight_od and carrier_lead_flight_pt else 2
        return {
            (0, 750): (None, 0),
            (750, 900): ("750mm flight brace 180mm long", fb_qty),
            (900, 1050): ("900mm Flight brace 230mm long", fb_qty),
            (1050, 1200): ("1050mm flight brace 280mm long", fb_qty),
            (1200, 1350): ("1200mm Flight Brace 330mm long", fb_qty),
            (1350, 5000): ("1350mm+ flight brace 480mm long", fb_qty),
        }

    def _get_carrier_flight_qty(self, type, lead_flight, carrier_flight, flighted_length):
        """ 
            We calculate the qty for carrier flight
        """
        flight_length = re.findall(r'\d+', flighted_length)[0]
        flight_length_num = int(flight_length)

        def _get_pitch(res):
            """
                We parse the flights to get the pitch and the number of turns
            """
            p_match = re.search(r'P(\d+)', res)
            r_match = re.search(r'R(\d+\.\d+)', res)

            pitch = int(p_match.group(1)) if p_match else 0
            turns = float(r_match.group(1)) if r_match else 1
    
            return pitch, turns

        l_pitch = l_no_turn = c_pitch = c_no_turn = 0
        if lead_flight or carrier_flight:
            l_pitch, l_no_turn = _get_pitch(lead_flight or "")
            c_pitch, c_no_turn = _get_pitch(carrier_flight or "")

            qty = self._get_cflight_qty(type, flight_length_num, l_pitch, l_no_turn, c_pitch, c_no_turn)
            return qty
        return 0

    def _get_cflight_qty(self, type, flight_length_num, lead_pitch, l_no_turn, carrier_pitch, c_no_turn):
        auger_type = ['Dual Rock', 'Taper Rock', 'ZED 25mm', 'ZED 32mm', 'ZED 40mm', 'ZED 50mm']
        qty = 0

        # Validate to avoid ZeroDivisionError
        denominator = carrier_pitch * c_no_turn
        if denominator == 0:
            _logger.warning(f"Division by zero prevented for type={type}. carrier_pitch={carrier_pitch}, c_no_turn={c_no_turn}")
            return 0
    
        try:
            if type in auger_type:
                qty = (flight_length_num - (lead_pitch * l_no_turn)) / denominator
            elif type in ['Clay/Shale', 'Blade']:
                _logger.info(f"Clay/Blade type calculation: flight_length_num={flight_length_num}, lead_pitch={lead_pitch}, l_no_turn={l_no_turn}, carrier_pitch={carrier_pitch}, c_no_turn={c_no_turn}")
                qty = (flight_length_num - (lead_pitch * l_no_turn)) / denominator * 2
            elif type in ['Triad Rock']:
                qty = (flight_length_num - (lead_pitch * l_no_turn * 0.4)) / denominator
            else:
                qty = 0
    
            qty = math.ceil(qty * 2) / 2
            return qty
    
        except Exception as e:
            _logger.exception(f"Unexpected error in _get_cflight_qty for type={type}: {e}")
            return 0

    def _find_flight_id(self, base_od):
        Product = self.env['product.product']

        candidates = []
        for tolerance in range(0, 6):
            candidates.append(base_od + tolerance)

        flights = Product.search([
            ('name', 'like', 'Flight -'),
        ])

        valid_ids = []
        for p in flights:
            m = re.search(r'ID(\d+)', p.name)
            if m:
                pid = int(m.group(1))
                if pid in candidates:
                    valid_ids.append(pid)
        return min(valid_ids) if valid_ids else None

    def _get_flight_combination(self, flight_pt, flight_od, diameter, center_tube, rotation):
        """
        Builds a non-stocked flight string from the given values.

        Args:
            flight PT (str): PT
            flight OD (str): OD
            diameter (int): Auger diameter
            center_tube (str): Center tube description
            rotation (str): 'RH' or 'LH'

        Returns:
            str: Formatted non-stocked flight string
        """
        def _parse_flight_values(flight_pt):
            """
            Extract pitch, thickness, and optionally turns from a flight string.
            """
            pitch = thickness = turns = 0
    
            # Look for Pitch (P...), Thickness (T...), and Turns (R...)
            p_match = re.search(r'P(\d+)', flight_pt)
            t_match = re.search(r'T(\d+)', flight_pt)
            r_match = re.search(r'R(\d+\.\d+)', flight_pt)
    
            if p_match:
                pitch = int(p_match.group(1))
            if t_match:
                thickness = int(t_match.group(1))
            if r_match:
                turns_num = float(r_match.group(1))
                turns = turns_num if turns_num > 1 else 0
            return pitch, thickness, turns

        if not flight_pt and not flight_od:
            return ""
        # OD based on auger diameter
        od_value = f"OD{diameter - 20}" if diameter < 1500 else f"OD{diameter - 30}"

        # ID based on center_tube table
        flight_od = 0
        od_match = re.search(r'OD(\d+)', center_tube)
        mm_match = re.search(r'-\s*(\d+)', center_tube)

        if od_match:
            flight_od = int(od_match.group(1))
        if mm_match:
            flight_od = int(mm_match.group(1))

        pitch, thickness, turns = _parse_flight_values(flight_pt)

        # Get the smallest ID of the available flights
        flight_id = self._find_flight_id(flight_od)
        # Combine flight attribute name
        od_value = f"OD{diameter - 20}" if diameter < 1500 else f"OD{diameter - 30}"
        id_value = f"ID{str(flight_id)}"
        pitch = f"P{pitch}"
        thickness = f"T{thickness}"
        f_rotation = "RH" if rotation == 'Right Hand Rotation' else "LH"
        turns = f"R{turns}" if turns > 1 else ""

        return f"Flight - {od_value} {id_value} {pitch} {thickness} {f_rotation} {turns}"

    def _get_lead_or_carrier_flight(self, type, diameter, center_tube, l_pt, l_od, c_pt, c_od, rotation, flighted_length, override_bom):
        """
        Returns a list of tuples (flight_string, quantity) for lead and carrier flights.
        """
        # Build flight strings
        lead_flight = self._get_flight_combination(l_pt, l_od, diameter, center_tube, rotation)
        carrier_flight = self._get_flight_combination(c_pt, c_od, diameter, center_tube, rotation)

        def _check_flights(flight):
            return self.env['product.product'].search_count([
                ('name', '=', flight)
            ]) > 0

        _lead = _check_flights(lead_flight)
        _carrier = _check_flights(carrier_flight)

        flight = ""
        if not _lead and not _carrier:
            flight = "Lead Flight & Carrier Flights"
        if not _lead:
            flight = "Lead Flight"
        if not _carrier:
            flight = "Carrier Flight"

        if not _lead or not _carrier and not override_bom:
            raise ValidationError(f"Opss! {flight} is not available, please review the selection or Override BOM.")

        # Compute the carrier qty
        carrier_qty = self._get_carrier_flight_qty(type, lead_flight, carrier_flight, flighted_length)

        if type == "Triad Rock":
            lead_qty = 3 if diameter > 650 else 1
        else:
            lead_qty = 2

        _none = (None, 0)
        lst = [
            (lead_flight, lead_qty) if _lead and override_bom or _lead and not override_bom else _none,
            (carrier_flight, carrier_qty) if _carrier and override_bom or _carrier and not override_bom else _none
        ]
        return lst

    def _get_stock_lead_carrier_flight(self, auger_type, diameter, lead_flight, carrier_flight, flighted_length, carrier_qty):
        """
        Return a list of items for stock flight with qty
        """
        if auger_type == "Triad Rock":
            lead_qty = 3 if diameter > 650 else 1
        else:
            lead_qty = 2

        return [
            (lead_flight or None, lead_qty if lead_flight else 0),
            (carrier_flight or None, carrier_qty if carrier_flight else 0)
        ]
    
    def _get_non_or_stock_flights(self, non_stock, stock):
        """
        Returns a list with two tuples:
        - First tuple: first valid non-stock flight or ('', 0)
        - Second tuple: first valid stock flight or ('', 0)
        """
        empty = ("", 0)

        # Get first valid non-stock item
        non_item = next(((item, qty) for item, qty in (non_stock or []) if item), empty)

        # Get first valid stock item
        stock_item = next(((item, qty) for item, qty in (stock or []) if item), empty)

        return (non_item, stock_item)

    def _get_pilot_support_od(self, pilot):
        # Pilot Support - Hex  78mm Pilot Support OD
        # Pilot Support - 75mm Square  150mm Pilot Support OD
        # Pilot Support - 100mm Square  200mm Pilot Support OD
        pilot_support = {
            'Pilot Support - Hex': 78,
            'Pilot Support - 75mm Square': 150,
            'Pilot Support - 100mm Square': 200
        }
        return pilot_support.get(pilot, 0)

    def _get_teeth_qty(self, diameter, mm1, mm2, mm3):
        qty = ((diameter - mm1 - mm2) / mm3) + 8
        # Round up to the nearest integer first
        qty = round(qty)
        # If even, add 1 to make it odd
        if qty % 2 == 0:
            qty += 1
        return qty

    def _get_teeth_dual_taper_rock(self, diameter, teeth, pilot):
        TEETH_CONFIG = {
            '19.4mm BSK17 Teeth': {
                'divisor': 40,
                'parts': [
                    'BSK17 - 19.4mm Shank Teeth',
                    'BHR164 - 19.4mm Block Holder',
                ]
            },
            '22mm BC86 Teeth': {
                'divisor': 42,
                'parts': [
                    'BC86TB - TEBCO 22mm Teeth',
                    'BHR176 - 22mm Block Tooth Holder',
                ]
            },
            '22mm BC05 Teeth': {
                'divisor': 42,
                'parts': [
                    'BC05TB - 22mm Shank Teeth',
                    'BHR176 - 22mm Block Tooth Holder',
                ]
            },
            '25mm BTK03 Teeth w/ Flat Back Holder': {
                'divisor': 44,
                'parts': [
                    'BTK03TB - 25mm Shank Teeth',
                    'TB25 - 25mm Flat Back Holder',
                ]
            },
            '25mm BTK03 Teeth w/ Block Holder': {
                'divisor': 44,
                'parts': [
                    'BTK03TB - 25mm Shank Teeth',
                    'BHR31 - 25mm Block Tooth Holder',
                ]
            },
            '38/30 BKH105 Teeth': {
                'divisor': 66,
                'parts': [
                    'BKH105TB - 38/30mm Shank Teeth',
                    'BHR38 - 38/30mm Block Tooth Holder',
                ]
            },
        }
        PILOT_CONFIG = {
            '19.4mm Teeth Pilot': [
                ('Rock Pilot suit 19mm Teeth 44mm Hex - RH / LH', 1),
                ('Pilot Support - Hex', 1),
                ('End Cap - Suit Hex Pilot Support', 1),
            ],
            '22mm Teeth Pilot': [
                ('Rock Pilot suit 22mm Teeth 44mm Hex - RH / LH', 1),
                ('Pilot Support - Hex', 1),
                ('End Cap - Suit Hex Pilot Support', 1),
            ],
            '25mm Teeth Pilot': [
                ('Rock Auger Pilot - 25mm Shank 75mm square', 1),
                ('Pilot Support - 75mm Square', 1),
                ('End Cap - Suit 75mm Square Pilot Support', 1),
            ],
            '38/30 Teeth Pilot': [
                ('Rock Auger Pilot - 38/30mm Shank 100mm Square', 1),
                ('Pilot Support - 100mm Square', 1),
                ('End Cap - Suit 100mm Square Pilot Support', 1),
            ],
        }
        teeth_config = TEETH_CONFIG.get(teeth)
        pilot_parts = PILOT_CONFIG.get(pilot, [])
        pilot_support = pilot_parts[1][0] if pilot_parts else ""
        pilot_support_od = self._get_pilot_support_od(pilot_support)

        offset = 20 if diameter < 1500 else 30
        result = []

        if teeth_config:
            teeth_qty = self._get_teeth_qty(
                diameter,
                pilot_support_od,
                offset,
                teeth_config['divisor']
            )
            
            result.extend([
                (teeth_config['parts'][0], teeth_qty),
                (teeth_config['parts'][1], teeth_qty - 4),
            ])
            
        result.extend(pilot_parts)
        
        return result

    def _get_teeth_qty_even(self, diameter, mm1, mm2, mm3):
        qty = ((diameter - mm1 - mm2) / mm3) * 2
        qty = int(round(qty / 2.0) * 2)  # Round to nearest even
        return qty

    def _get_teeth_zed(self, diameter, center_tube, teeth):
        # Parse to get the OD number of the center tube
        od_match = re.search(r'OD(\d+)', center_tube)
        center_tube_od = int(od_match.group(1)) if od_match else 0

        ZED_TEETH_CONFIG = {
            '22mm BC05 Teeth': {
                'divisor': 42,
                'parts': [
                    'BC05TB - 22mm Shank Teeth',
                    'BHR176 - 22mm Block Tooth Holder',
                ]
            },
            '25mm BTK03 Teeth w/ Flat Back Holder': {
                'divisor': 44,
                'parts': [
                    'BTK03TB - 25mm Shank Teeth',
                    'TB25 - 25mm Flat Back Holder',
                ]
            },
            '25mm BTK03 Teeth w/ Block Holder': {
                'divisor': 44,
                'parts': [
                    'BTK03TB - 25mm Shank Teeth',
                    'BHR31 - 25mm Block Tooth Holder',
                ]
            },
            '38/30 BKH105 Teeth': {
                'divisor': 66,
                'parts': [
                    'BKH105TB - 38/30mm Shank Teeth',
                    'BHR38 - 38/30mm Block Tooth Holder',
                ]
            },
        }

        teeth_config = ZED_TEETH_CONFIG.get(teeth)
        result = []
        if teeth_config:
            offset = 20 if diameter < 1500 else 30
            
            teeth_qty = self._get_teeth_qty_even(
                diameter,
                center_tube_od,
                offset,
                teeth_config['divisor']
            )
            
            weld_qty = int(round(teeth_qty / 2))
            
            result.extend([
                (teeth_config['parts'][0], teeth_qty),
                (teeth_config['parts'][1], teeth_qty),
                ('BA13 - Weld on Button Carbide', weld_qty),
            ])

        # ZED Flight Stiffener (always added)
        stiffener = [(
            ('ZED Flight Stiffener (Under 600mm)', 2)
            if diameter < 600 else
            ('ZED Flight Stiffener (600mm+)', 2)
        )]
        result.extend(stiffener)
        return result

    def _get_teeth_qty_triad(self, diameter, mm1, mm2, mm3):
        qty = ((diameter - mm1 - mm2) / mm3) * 3 + 4
        qty = round(qty)  # Round to nearest whole number
        return qty
    
    def _get_teeth_triad_rock(self, diameter, teeth, pilot):
        TRIAD_ROCK_TEETH_CONFIG = {
                '22mm BC86 Teeth': {
                    'divisor': 84,
                    'parts': [
                        'BC86TB - TEBCO 22mm Teeth',
                        'BHR176 - 22mm Block Tooth Holder',
                    ]
                },
            }
        TRIAD_ROCK_PILOT_CONFIG = {
                '22mm Teeth Pilot': [
                    ('Rock Pilot suit 22mm Teeth 44mm Hex - RH / LH', 1),
                    ('Pilot Support - Hex', 1),
                    ('End Cap - Suit Hex Pilot Support', 1),
                ],
            }

        teeth_config = TRIAD_ROCK_TEETH_CONFIG.get(teeth)
        pilot_parts = TRIAD_ROCK_PILOT_CONFIG.get(pilot, [])

        pilot_support = pilot_parts[1][0] if len(pilot_parts) > 1 else ""
        pilot_support_od = self._get_pilot_support_od(pilot_support)

        offset = 20 if diameter < 1500 else 30
        result = []
        if teeth_config:
            teeth_qty = self._get_teeth_qty_triad(
                diameter,
                pilot_support_od,
                offset,
                teeth_config['divisor']
            )
            
            result.extend([
                (teeth_config['parts'][0], teeth_qty),
                (teeth_config['parts'][1], teeth_qty - 4),
            ])

        result.extend(pilot_parts)
        return result
        
    def _get_teeth_clay_shale(self, diameter, teeth, pilot):
        pilot_support_od_ar150 = 78  # for AR150 (D<300)

        CLAY_SHALE_TEETH_CONFIG = {
            'AR150 Teeth': {
                'teeth': 'AR150 Teeth',
                'gauge_teeth': None,
            },
            'AR150 Teeth w/ Gauge Teeth': {
                'teeth': 'AR150 Teeth',
                'gauge_teeth': [
                    ('BC05TB - 22mm Shank Teeth', 2),
                    ('BHR176 - 22mm Block Tooth Holder', 2),
                ],
            },
            '38/30 BFZ162 Teeth': {
                'divisor': 75,
                'parts': [
                    'BFZ162 (FZ70) 38/30mm step shank flat Teeth',
                    'Phaser Teeth Holder',
                ],
            },
            'FZ54 Teeth': {
                'divisor': 58,
                'parts': [
                    'FZ54 Mini Bauer Teeth',
                    'Mini Bauer Holder',
                ],
            },
        }
        
        CLAY_SHALE_DIAMETER_CONFIG = {
            300: {'teeth_qty': 4, 'holder': '300mm Clay Shale Teeth Holder'},
            400: {'teeth_qty': 8, 'holder': '400mm Clay Shale Teeth Holder'},
            450: {'teeth_qty': 8, 'holder': '450mm Clay Shale Teeth Holder'},
            600: {'teeth_qty': 12, 'holder': '600mm Clay Shale Teeth Holder'},
        }
        
        CLAY_SHALE_PILOT_CONFIG = {
            'Hex Auger Torque Fishtail Pilot': {
                'parts': [
                    ('Auger Pilot - Hex Auger Torque Fishtail', 1),
                    ('Pilot Support - Hex', 1),
                    ('End Cap - Suit Hex Pilot Support', 1),
                ],
                'teeth_3': None,
            },
            '19.4mm Teeth Pilot': {
                'parts': [
                    ('Rock Pilot suit 19mm Teeth 44mm Hex - RH / LH', 1),
                    ('Pilot Support - Hex', 1),
                    ('End Cap - Suit Hex Pilot Support', 1),
                ],
                'teeth_3': ('BSK17 - 19.4mm Shank Teeth', 4),
            },
            '22mm Teeth Pilot': {
                'parts': [
                    ('Rock Pilot suit 22mm Teeth 44mm Hex - RH / LH', 1),
                    ('Pilot Support - Hex', 1),
                    ('End Cap - Suit Hex Pilot Support', 1),
                ],
                'teeth_3': ('BC86TB - TEBCO 22mm Teeth', 4),
            },
            '25mm Teeth Pilot': {
                'parts': [
                    ('Rock Auger Pilot - 25mm Shank 75mm square', 1),
                    ('Pilot Support - 75mm Square', 1),
                    ('End Cap - Suit 75mm Square Pilot Support', 1),
                ],
                'teeth_3': ('BTK03TB - 25mm Shank Teeth', 4),
            },
            '38/30 Teeth Pilot': {
                'parts': [
                    ('Rock Auger Pilot - 38/30mm Shank 100mm Square', 1),
                    ('Pilot Support - 100mm Square', 1),
                    ('End Cap - Suit 100mm Square Pilot Support', 1),
                ],
                'teeth_3': ('BKH105TB - 38/30mm Shank Teeth', 4),
            },
            'Blade Auger Fishtail Pilot': {
                'parts': [
                    ('Blade Auger Fishtail Pilot', 1),
                    ('Pipe - OD101mm WT4.0mm', 0.25),
                ],
                'teeth_3': None,
            },
        }
        teeth_config = CLAY_SHALE_TEETH_CONFIG.get(teeth)
        pilot_config = CLAY_SHALE_PILOT_CONFIG.get(pilot, {})
        parts = pilot_config.get('parts', [])

        # raise ValidationError(pilot_config)
        pilot_support = parts[1][0] if len(parts) > 1 else ""
        pilot_support_od = self._get_pilot_support_od(pilot_support)
        result = []

        # Handle BFZ162 and FZ54 teeth (for "All" diameters)
        if teeth in ['38/30 BFZ162 Teeth', 'FZ54 Teeth']:
            teeth_qty = self._get_teeth_qty_even(
                diameter,
                pilot_support_od,
                20,
                teeth_config['divisor']
            )
            result = [
                (teeth_config['parts'][0], teeth_qty),
                (teeth_config['parts'][1], teeth_qty),
            ]
            result.extend(pilot_config.get('parts', []))
            return result
        
        # Handle AR150 Teeth
        if diameter < 300:
            # D<300: formula-based qty
            teeth_qty = self._get_teeth_qty_even(
                diameter,
                pilot_support_od_ar150,
                20,
                40
            )
            result = [
                ('AR150 Teeth', teeth_qty),
                ('C87B Holder - suit AR150', teeth_qty),
            ]
        elif diameter in CLAY_SHALE_DIAMETER_CONFIG:
            # Fixed diameter config (300, 400, 450, 600)
            diameter_config = CLAY_SHALE_DIAMETER_CONFIG[diameter]
            result = [
                ('AR150 Teeth', diameter_config['teeth_qty']),
                (diameter_config['holder'], 2),
            ]
            
            # Add gauge teeth if applicable
            # if teeth_config.get('gauge_teeth'):
            #     result.extend(teeth_config['gauge_teeth'])
        else:
            return []

        # Add pilot parts
        result.extend(pilot_config.get('parts', []))
        
        # Add teeth 3 from pilot config
        if pilot_config.get('teeth_3'):
            result.extend(pilot_config['teeth_3'])
        
        return result
    
    def _get_teeth_blade(self, diameter, teeth, pilot):
        BLADE_TEETH_CONFIG = {
                'Blade Teeth': {
                    'gauge_teeth': None,
                },
                'Blade Teeth w/ Gauge Teeth': {
                    'gauge_teeth': [
                        ('BC05TB - 22mm Shank Teeth', 2),
                        ('BHR176 - 22mm Block Tooth Holder', 2),
                    ],
                },
            }
        BLADE_DIAMETER_CONFIG = {
                300: {
                    'teeth': '300mm Hardfaced Blade Teeth',
                    'holder': '300mm Blade Holder',
                },
                400: {
                    'teeth': '400mm Hardfaced Blade Teeth',
                    'holder': '400mm Blade Holder',
                },
                450: {
                    'teeth': '450mm Hardfaced Blade Teeth',
                    'holder': '450mm Blade Holder',
                },
            }  
        BLADE_PILOT_CONFIG = {
            'Blade Auger Fishtail Pilot': [
                ('Blade Auger Fishtail Pilot', 1),
                ('Pipe - OD101mm WT4.0mm', 0.25),
            ],
            'Hex Auger Torque Fishtail Pilot': [
                ('Auger Pilot - Hex Auger Torque Fishtail', 1),
                ('Pilot Support - Hex', 1),
                ('End Cap - Suit Hex Pilot Support', 1),
            ],
        }

        teeth_config = BLADE_TEETH_CONFIG.get(teeth)
        diameter_config = BLADE_DIAMETER_CONFIG.get(diameter)
        pilot_parts = BLADE_PILOT_CONFIG.get(pilot, [])

        # Initialize with defaults
        teeth_part = None
        tooth_holder = None
        pilot_part = None
        pilot_support = None
        end_cap = None

        if diameter_config:
            teeth_part = (diameter_config['teeth'], 2)
            tooth_holder = (diameter_config['holder'], 2)

        # if teeth_config and teeth_config.get('gauge_teeth'):
        #     gauge_teeth = teeth_config['gauge_teeth']

        if pilot_parts:
            pilot_part = pilot_parts[0] if len(pilot_parts) > 0 else None
            pilot_support = pilot_parts[1] if len(pilot_parts) > 1 else None
            end_cap = pilot_parts[2] if len(pilot_parts) > 2 else None

        return teeth_part, tooth_holder, pilot_part, pilot_support, end_cap

    def _get_pilot_support(self, items):
        if not items:
            return None

        keywords = ['Pilot Support', 'Pipe - OD101mm WT4.0mm']
        for item in items:
            if not item or len(item) < 2 or not item[0]:
                continue
            if any(kw in item[0] for kw in keywords):
                return item[0]
        return None  # No keyword match found

    def _get_bp_dual_taper_rock(self, type, diameter, drive_head, overall_length, flighted_length, rotation, teeth, pilot, center_tube, lead_flight_od, lead_flight_pt, carrier_lead_flight_od, carrier_lead_flight_pt, override_bom):
        d_number = re.findall(r'\d+', diameter)[0]
        diameter = int(d_number)

        d_head_75mm = "Drive Head - 75mm Square"
        h_bar_od150 = "Hollow Bar - OD150mm ID120mm"
        stiffening_ring = "Stiffening Ring - 75mm Head" if drive_head == d_head_75mm and center_tube == h_bar_od150 else ""

        base_plate = self._get_base_plate(drive_head)
        tube_gusset = self._get_tube_guesset(drive_head, center_tube)
        fb_components = self._get_flight_brace_components(drive_head, carrier_lead_flight_od, carrier_lead_flight_pt)
        flight_brace = self._get_range_per_diameter(fb_components, diameter) if fb_components else []
        l_flight, c_flight = self._get_lead_or_carrier_flight(type, diameter, center_tube, lead_flight_pt, lead_flight_od, carrier_lead_flight_pt, carrier_lead_flight_od, rotation, flighted_length, override_bom)

        fb_item, fb_qty = flight_brace if flight_brace else (None, 0)
        stiffening = (stiffening_ring, 1) if stiffening_ring else (None, 0) 
        teeth_dual_taper = self._get_teeth_dual_taper_rock(diameter, teeth, pilot) or []

        pilot_support = self._get_pilot_support(teeth_dual_taper)
        _center_tube = self._get_center_tube(overall_length, drive_head, center_tube, pilot_support)
        _none = (None, 0)

        components = [
            (drive_head, 1),
            stiffening,
            base_plate,
            tube_gusset,
            (fb_item, fb_qty),
            _center_tube or _none,
            l_flight,
            c_flight,
        ]
        # raise ValidationError(f"test {teeth_dual_taper}")
        components.extend(teeth_dual_taper)
        # exclude none values
        components = [c for c in components if c and len(c) >= 2 and c[0] and c[1]]
        return components

    def _get_bp_triad_rock(self, type, diameter, drive_head, overall_length, flighted_length, rotation, teeth, pilot, center_tube, lead_flight_od, lead_flight_pt, carrier_lead_flight_od, carrier_lead_flight_pt, override_bom):
        d_number = re.findall(r'\d+', diameter)[0]
        diameter = int(d_number)

        l_flight, c_flight = self._get_lead_or_carrier_flight(type, diameter, center_tube, lead_flight_pt, lead_flight_od, carrier_lead_flight_pt, carrier_lead_flight_od, rotation, flighted_length, override_bom)
        teeth_triad_rock = self._get_teeth_triad_rock(diameter, teeth, pilot) or []

        pilot_support = self._get_pilot_support(teeth_triad_rock)
        _center_tube = self._get_center_tube(overall_length, drive_head, center_tube, pilot_support)
        _none = (None, 0)

        components = [
            (drive_head, 1),
            _center_tube or _none,
            l_flight,
            c_flight,
        ]
        components.extend(teeth_triad_rock)
        # exclude none values
        components = [c for c in components if c and len(c) >= 2 and c[0] and c[1]]
        return components

    def _get_bp_zed(self, type, diameter, drive_head, overall_length, flighted_length, rotation, teeth, pilot, center_tube, lead_flight_od, lead_flight_pt, carrier_lead_flight_od, carrier_lead_flight_pt, override_bom):
        d_number = re.findall(r'\d+', diameter)[0]
        diameter = int(d_number)

        pilot_support = "None"
        d_head_75mm = "Drive Head - 75mm Square"
        h_bar_od150 = "Hollow Bar - OD150mm ID120mm"
        stiffening_ring = "Stiffening Ring - 75mm Head" if drive_head == d_head_75mm and center_tube == h_bar_od150 else ""

        base_plate = self._get_base_plate(drive_head)
        tube_gusset = self._get_tube_guesset(drive_head, center_tube)
        fb_components = self._get_flight_brace_components(drive_head, carrier_lead_flight_od, carrier_lead_flight_pt)
        flight_brace = self._get_range_per_diameter(fb_components, diameter) if fb_components else []
        fb_item, fb_qty = flight_brace if flight_brace else (None, 0)

        l_flight, c_flight = self._get_lead_or_carrier_flight(type, diameter, center_tube, lead_flight_pt, lead_flight_od, carrier_lead_flight_pt, carrier_lead_flight_od, rotation, flighted_length, override_bom)
        zed_centre = self._get_zed_center_component_map(center_tube)
        _center_tube = self._get_center_tube_zed(overall_length, drive_head, center_tube, zed_centre)
        teeth_zed = self._get_teeth_zed(diameter, center_tube, teeth) or []

        stiffening = (stiffening_ring, 1) if stiffening_ring else (None, 0)
        teeth_brace = ('ZED Auger Teeth Brace', 2)
        _none = (None, 0)

        components = [
            (drive_head, 1),
            stiffening, 
            base_plate,
            tube_gusset,
            (fb_item, fb_qty),
            _center_tube or _none,
            l_flight,
            c_flight,
            teeth_brace,
            (zed_centre, 1)
        ]
        components.extend(teeth_zed)
        # exclude none e.g (None, (None, 0), ('', 0))
        components = [c for c in components if c and len(c) >= 2 and c[0] and c[1]]

        return components

    def _get_bp_clay_shale(self, type, diameter, drive_head, overall_length, flighted_length, rotation, teeth, pilot, center_tube, lead_flight_od, lead_flight_pt, carrier_lead_flight_od, carrier_lead_flight_pt, override_bom):
        d_number = re.findall(r'\d+', diameter)[0]
        diameter = int(d_number)

        d_head_75mm = "Drive Head - 75mm Square"
        h_bar_od150 = "Hollow Bar - OD150mm ID120mm"
        stiffening_ring = "Stiffening Ring - 75mm Head" if drive_head == d_head_75mm and center_tube == h_bar_od150 else ""

        base_plate = self._get_base_plate(drive_head)
        tube_gusset = self._get_tube_guesset(drive_head, center_tube)

        l_flight, c_flight = self._get_lead_or_carrier_flight(type, diameter, center_tube, lead_flight_pt, lead_flight_od, carrier_lead_flight_pt, carrier_lead_flight_od, rotation, flighted_length, override_bom)
        teeth_clay_shale = self._get_teeth_clay_shale(diameter, teeth, pilot) or []

        pilot_support = self._get_pilot_support(teeth_clay_shale)
        _center_tube = self._get_center_tube(overall_length, drive_head, center_tube, pilot_support)

        stiffening = (stiffening_ring, 1) if stiffening_ring else (None, 0) 
        _none = (None, 0)

        components = [
            (drive_head, 1),
            stiffening,
            base_plate,
            tube_gusset,
            _center_tube or _none,
            l_flight,
            c_flight
        ]
        components.extend(teeth_clay_shale)
        # exclude none values
        components = [c for c in components if c and len(c) >= 2 and c[0] and c[1]]

        return components

    def _get_bp_blade(self, type, diameter, drive_head, overall_length, flighted_length, rotation, teeth, pilot, center_tube, lead_flight_od, lead_flight_pt, carrier_lead_flight_od, carrier_lead_flight_pt, override_bom):
        d_number = re.findall(r'\d+', diameter)[0]
        diameter = int(d_number)

        l_flight, c_flight = self._get_lead_or_carrier_flight(type, diameter, center_tube, lead_flight_pt, lead_flight_od, carrier_lead_flight_pt, carrier_lead_flight_od, rotation, flighted_length, override_bom)
        teeth_blade = self._get_teeth_blade(diameter, teeth, pilot)

        pilot_support = self._get_pilot_support(teeth_blade)
        _center_tube = self._get_center_tube(overall_length, drive_head, center_tube, pilot_support)
        _none = (None, 0)

        components = [
            (drive_head, 1),
            _center_tube or _none,
            l_flight,
            c_flight
        ]
        components.extend(teeth_blade)
        # exclude none values
        # raise ValidationError("This is blade...")
        components = [c for c in components if c and len(c) >= 2 and c[0] and c[1]]
        return components

    def _create_drilling_barrel(self, product):
        reference = product.display_name
        if product.product_tmpl_id.name == 'Drilling Barrel':
            components = self._create_drilling_barrel_component(product)
            # create bom components for tremie pipe
            self._create_bom_components(product, reference, components)

    def _create_drilling_barrel_component(self, product):
        components = []
        p_name = product.product_tmpl_id.name
        # product attributes values
        attributes = {attr.attribute_id.name: attr.name for attr in product.product_template_attribute_value_ids}
        dia = attributes.get('Diameter', '')
        b_height = attributes.get('Barrel Height', '')
        d_head = attributes.get('Drive Head', '')
        type = attributes.get('Opening Type', '')
        no_blade = attributes.get('No. of Blade', '')
        db_type = attributes.get('Type', '')
        custom = attributes.get('Customization', '')
        front_end = attributes.get('Front End', '')
        teeth = attributes.get('Teeth', '')

        if type == 'Plunger & Handle':
            components = self._get_db_plunger_handler(p_name, dia, b_height, type, no_blade, d_head, db_type, custom, front_end, teeth)
        elif type == 'Plunger':
            components = self._get_db_plunger(p_name, dia, b_height, type, no_blade, d_head, db_type, custom, front_end, teeth)
        elif type == 'Handle':
            components = self._get_db_handle(p_name, dia, b_height, type, no_blade, d_head, db_type, custom, front_end, teeth)
        return components

    def _get_db_handle(self, p_name, dia, b_height, type, no_blade, d_head, db_type, custom, front_end, teeth):
        d_number = re.findall(r'\d+', dia)[0]
        x_head = d_head or ""
        head_matches = re.findall(r'\d+', x_head)
        head = head_matches[0] if head_matches else ""

        height_matches = re.findall(r'\d+', b_height)
        height = height_matches[0] if height_matches else 0

        dia_number = int(d_number)

        components_map = self._components_db_mapping()
        components = self._get_range_per_diameter(components_map, dia_number)

        combination = self._get_prof_combination_for_cb_db(d_head, db_type)
        pf_combination = f" - {combination}" if combination else ""

        prof_combination = f"{p_name} {dia} x {b_height} - {type} - {no_blade} - {custom} - {front_end} - {teeth} {pf_combination}"
        gusset_d_head = self._get_gusset_combination(d_head, head)
        gusset_label = "- Clean & Drill Barrel" if d_head not in ["Custom head", "Amazng Head"] else ""
        gusset = f"Gusset {gusset_d_head} x {d_number}mm Diameter {gusset_label}"
        drive_head = self._get_drive_head(d_head)
        d_head_digga = "Drive Head EARS - 130mm Square" if d_head == "130mm Square Head" else ""
        drive_head_ears = "Drive Head EARS - 130mm Square DIGGA" if d_head == "130mm Digga Square Head" else d_head_digga
        drive_head_ears_qty = 2 if d_head == "130mm Square Head" else 4
        drill_pivot_kit = self._get_drill_pivot_kit(db_type, d_head, dia_number)

        hinge_comp3 = self._get_hinge_db_component3()
        hinge_comp3_lst = self._get_range_per_diameter(hinge_comp3, dia_number)
        if hinge_comp3_lst:
            hinge_c3, hengi_c3_qty = hinge_comp3_lst
        else:
            hinge_c3, hengi_c3_qty = None, None

        handle_bar_qty = self._get_db_handle_bar_qty(height, dia_number)
        wear_pads = "Barrel Wear Pads"
        wear_qty = self.round_to_nearest_even((((dia_number - 40) * 3.142) * 2) / 200)
        pcf1 = self._get_db_pcf1(dia_number)
        pcf2 = self._get_pcf2(dia_number)
        hollow_bar_extension = self._get_hollow_bar_extension(db_type, d_head, dia_number, front_end)
        zed_centre = self._get_zed_centre(hollow_bar_extension, front_end)

        rock_components = self._get_teeth_rock_components(drill_pivot_kit, dia_number, teeth, no_blade)
        clay_components = self._get_teeth_clay_components(drill_pivot_kit, dia_number, teeth, no_blade)
        taper_components = self._get_teeth_taper_components(drill_pivot_kit, dia_number, teeth, no_blade)
        zed_components = self._get_zed_frontend_components(drill_pivot_kit, dia_number, teeth, no_blade)

        drilling_arrow_head = ""
        if dia_number < 350:
            drilling_arrow_head = "Arrow Head - Small"
        elif 350 <= dia_number < 1600:
            drilling_arrow_head = "Arrow Head - Medium"
        else:
            drilling_arrow_head = "Arrow Head - Large"

        # Return the list of components with quantities
        hinge_comp1 = hinge_comp2 = handle_bar = locking_comp1 = locking_comp2 = None
        if components:
            hinge_comp1, hinge_comp2, handle_bar, locking_comp1, locking_comp2 = components
        # List of all possible components with their values
        possible_components = [
            (f"Profiling - {prof_combination}", 1.0) if prof_combination else None,
            (gusset, 4) if gusset else None,
            (drive_head, 1) if drive_head else None,
            (drive_head_ears, drive_head_ears_qty) if drive_head_ears else None,
            (drill_pivot_kit, 1) if drill_pivot_kit else None,
            (hinge_comp1, 1) if hinge_comp1 else None,
            (hinge_comp2, 2) if hinge_comp2 else None,
            (hinge_c3, hengi_c3_qty) if hinge_c3 else None,
            (handle_bar, handle_bar_qty) if handle_bar and handle_bar_qty else None,
            (locking_comp1, 3) if locking_comp1 else None,
            (locking_comp2, 3) if locking_comp2 else None,
            (drilling_arrow_head, 1),
            (wear_pads, wear_qty) if wear_pads else None,
            pcf1 if pcf1 and pcf1 else None,
            pcf2 if pcf2 and pcf2[0] else None,
        ]
        if hollow_bar_extension and front_end in ['Taper Rock Front End', 'ZED Front End']:
            possible_components.append((hollow_bar_extension, 1))

        possible_components.append((zed_centre, 1) if zed_centre else None)
        # Filter out None values and create the final components list
        components = [component for component in possible_components if component]
        # Extend with rock_components
        if front_end == 'Rock Front End':
            components.extend(rock_components)
        elif front_end == 'Clay Front End':
            components.extend(clay_components)
        elif front_end == 'Taper Rock Front End':                                                                                                                                                                                                        
            components.extend(taper_components)
        elif front_end == 'ZED Front End':
            components.extend(zed_components)

        return components

    def _get_db_handle_bar_qty(self, d_height, d_number):
        def mm_to_meters(mm):
            return mm / 1000

        qty = 0
        height = int(d_height)
        if d_number < 350:
            qty = mm_to_meters(height) + 0.5
        elif 350 <= d_number < 400:
            qty = mm_to_meters(height) + 0.635
        elif 400 <= d_number < 500:
            qty = mm_to_meters(height) + 0.67
        else:
            qty = mm_to_meters(height) + 0.5
        return qty

    def _get_db_plunger(self, p_name, dia, b_height, type, no_blade, d_head, db_type, custom, front_end, teeth):
        d_number = re.findall(r'\d+', dia)[0]
        x_head = d_head or ""
        head_matches = re.findall(r'\d+', x_head)
        head = head_matches[0] if head_matches else ""
        dia_number = int(d_number)

        components_map = {
            (0, 400): ("35mm Hinge - 75mm Long", "35mm Hinge - Bush"),
            (400, 500): ("35mm Hinge - 110mm Long", "35mm Hinge - Bush"),
            (500, 550): ("45mm Hinge - 180mm Long", "45mm Hinge - Bush"),
            (550, 650): ("45mm Hinge - 180mm Long", "45mm Hinge - Bush"),
            (650, 800): ("45mm Hinge - 240mm Long", "45mm Hinge - Bush"),
            (800, 1050): ("45mm Hinge - 320mm long", "45mm Hinge - Bush"),
            (1050, 1400): ("60mm Hinge - 250mm long", "60mm Hinge - Bush"),
            (1400, 1850): ("60mm Hinge - 400mm long", "60mm Hinge - Bush"),
            (1850, 2000): ("100mm Hinge - 450mm long", "100mm Hinge - Bush"),
            (2000, 2500): ("100mm Hinge - 450mm long", "100mm Hinge - Bush"),
            (2500, 5000): ("100mm Hinge - 550mm long", "100mm Hinge - Bush"),
        }
        components = self._get_range_per_diameter(components_map, dia_number)

        combination = self._get_prof_combination_for_cb_db(d_head, db_type)
        pf_combination = f" - {combination}" if combination else ""

        prof_combination = f"{p_name} {dia} x {b_height} - {type} - {no_blade} - {custom} - {front_end} - {teeth} {pf_combination}"
        gusset_d_head = self._get_gusset_combination(d_head, head)
        gusset_label = "- Clean & Drill Barrel" if d_head not in ["Custom head", "Amazng Head"] else ""
        gusset = f"Gusset {gusset_d_head} x {d_number}mm Diameter {gusset_label}"
        drive_head = self._get_drive_head(d_head)
        d_head_digga = "Drive Head EARS - 130mm Square" if d_head == "130mm Square Head" else ""
        drive_head_ears = "Drive Head EARS - 130mm Square DIGGA" if d_head == "130mm Digga Square Head" else d_head_digga
        drive_head_ears_qty = 2 if d_head == "130mm Square Head" else 4
        drill_pivot_kit = self._get_drill_pivot_kit(db_type, d_head, dia_number)

        hinge_comp3 = self._get_hinge_db_plunger_comp3()
        hinge_comp3_lst = self._get_range_per_diameter(hinge_comp3, dia_number)
        if hinge_comp3_lst:
            hinge_c3, hengi_c3_qty = hinge_comp3_lst
        else:
            hinge_c3, hengi_c3_qty = None, None

        plunger_bar = self._get_plunger_bar(d_head, dia_number)
        plunger_bar_qty = self._get_plunger_bar_qty(dia_number)
        plunger_bush = "Plunger Bush - 110mm OD 75mm ID - 100mm long"
        plunger_spring = "Plunger Spring"
        plunger_end_cap = "Plunger End Cap"
        bolt = "Hex Bolt - M30 x 130mm GR10.9"
        nut = "Nut - M30 Coneloc"
        wear_pads = "Barrel Wear Pads"
        wear_qty = self.round_to_nearest_even((((dia_number - 40) * 3.142) * 2) / 200)
        pcf1 = self._get_db_pcf1(dia_number)
        pcf2 = self._get_pcf2(dia_number)
        hollow_bar_extension = self._get_hollow_bar_extension(db_type, d_head, dia_number, front_end)
        zed_centre = self._get_zed_centre(hollow_bar_extension, front_end)
        rock_components = self._get_teeth_rock_components(drill_pivot_kit, dia_number, teeth, no_blade)
        clay_components = self._get_teeth_clay_components(drill_pivot_kit, dia_number, teeth, no_blade)
        taper_components = self._get_teeth_taper_components(drill_pivot_kit, dia_number, teeth, no_blade)
        zed_components = self._get_zed_frontend_components(drill_pivot_kit, dia_number, teeth, no_blade)
        drilling_arrow_head = ""
        if dia_number < 350:
            drilling_arrow_head = "Arrow Head - Small"
        elif 350 <= dia_number < 1600:
            drilling_arrow_head = "Arrow Head - Medium"
        else:
            drilling_arrow_head = "Arrow Head - Large"

        plung_qty = 0
        b_n_qty = 0
        if dia_number >= 1850:
            plung_qty = 2
            b_n_qty = 6
        else:
            plung_qty = 1
            b_n_qty = 3

        # Return the list of components with quantities
        hinge_comp1 = hinge_comp2 = None
        if components:
            hinge_comp1, hinge_comp2 = components
        # List of all possible components with their values
        possible_components = [
            (f"Profiling - {prof_combination}", 1.0) if prof_combination else None,
            (gusset, 4) if gusset else None,
            (drive_head, 1) if drive_head else None,
            (drive_head_ears, drive_head_ears_qty) if drive_head_ears else None,
            (drill_pivot_kit, 1) if drill_pivot_kit else None,
            (hinge_comp1, 1) if hinge_comp1 else None,
            (hinge_comp2, 2) if hinge_comp2 else None,
            (hinge_c3, hengi_c3_qty) if hinge_c3 else None,
            (plunger_bar, plunger_bar_qty) if plunger_bar else None,
            (plunger_bush, plung_qty) if plunger_bush else None,
            (plunger_spring, plung_qty) if plunger_spring else None,
            (plunger_end_cap, plung_qty) if plunger_end_cap else None,
            (bolt, b_n_qty),
            (nut, b_n_qty),
            (wear_pads, wear_qty) if wear_pads else None,
            pcf1 if pcf1 and pcf1 else None,
            pcf2 if pcf2 and pcf2[0] else None,
        ]
        if hollow_bar_extension and front_end in ['Taper Rock Front End', 'ZED Front End']:
            possible_components.append((hollow_bar_extension, 1))

        possible_components.append((zed_centre, 1) if zed_centre else None)
        # Filter out None values and create the final components list
        components = [component for component in possible_components if component]
        # Extend with rock_components
        if front_end == 'Rock Front End':
            components.extend(rock_components)
        elif front_end == 'Clay Front End':
            components.extend(clay_components)
        elif front_end == 'Taper Rock Front End':
            components.extend(taper_components)
        elif front_end == 'ZED Front End':
            components.extend(zed_components)
        return components

    def _get_gusset_combination(self, d_head, head):
        gusset_d_head = ""

        if d_head == '4" Lo Drill Head':
            gusset_d_head = '4" Lo Drill'
        elif d_head == "Custom head":
            gusset_d_head = "Custom Head"
        elif d_head == "130mm Square Head":
            gusset_d_head = "130mm Square Drive"
        elif d_head == "130mm Digga Square Head":
            gusset_d_head = "130mm Digga Drive"
        elif d_head == "150mm Square Head":
            gusset_d_head = "150mm Drive"
        elif d_head == "150mm IMT Square Head":
            gusset_d_head = "150mm IMT Drive"
        elif d_head == "200mm Bauer Square Head":
            gusset_d_head = "200mm Bauer Drive"
        elif d_head == "200mm Mait Square Head":
            gusset_d_head = "200mm Mait Drive"
        else:
            gusset_d_head = f"{head}mm Drive"

        return gusset_d_head

    def _get_hollow_bar_extension(self, db_type, d_head, dia, front_end):
        item = ""
        if db_type in ['Lightweight', 'Standard']:
            if d_head in ["75mm Square Head", "100mm Square Head", "110mm Square Head", '4" Lo Drill Head'] and dia >= 1:
                item = "Hollow Bar - OD152mm WT 33.5mm"
            elif d_head in ["200mm Bauer Square Head", "200mm Mait Square Head"] and dia < 800:
                item = "Hollow Bar - OD152mm WT 33.5mm"
            elif d_head in ["130mm Digga Square Head", "130mm Square Head", "150mm Square Head", "150mm IMT Square Head"] and dia < 1000:
                item = "Hollow Bar - OD152mm WT 33.5mm"
            elif d_head in ["200mm Bauer Square Head", "200mm Mait Square Head"] and 800 <= dia < 2100:
                item = "Hollow Bar - OD200 ID150" if front_end == "Taper Rock Front End" else "Hollow Bar - OD219mm WT 25mm"
            elif d_head in ["130mm Digga Square Head", "130mm Square Head", "150mm Square Head", "150mm IMT Square Head"] and dia >= 1000:
                item = "Hollow Bar - OD200 ID150" if front_end == "Taper Rock Front End" else "Hollow Bar - OD219mm WT 25mm"
            elif d_head in ["200mm Bauer Square Head", "200mm Mait Square Head"] and dia >= 2100:
                item = "Hollow Bar - OD273mm WT 25mm"

        elif db_type == 'Heavy Duty':
            if d_head in ["75mm Square Head", "100mm Square Head", "110mm Square Head", '4" Lo Drill Head'] and dia >= 1:
                item = "Hollow Bar - OD152mm WT 33.5mm"
            elif d_head in ["130mm Digga Square Head", "130mm Square Head", "150mm Square Head", "150mm IMT Square Head"] and dia < 900:
                item = "Hollow Bar - OD152mm WT 33.5mm"
            elif d_head in ["130mm Digga Square Head", "130mm Square Head", "150mm Square Head", "150mm IMT Square Head"] and dia >= 900:
                item = "Hollow Bar - OD200 ID150" if front_end == "Taper Rock Front End" else "Hollow Bar - OD219mm WT 25mm"
            elif d_head in ["200mm Bauer Square Head", "200mm Mait Square Head"] and 800 <= dia < 2100:
                item = "Hollow Bar - OD200 ID150" if front_end == "Taper Rock Front End" else "Hollow Bar - OD219mm WT 25mm"
            elif d_head in ["200mm Bauer Square Head", "200mm Mait Square Head"] and dia >= 2100:
                item = "Hollow Bar - OD273mm WT 25mm"
            elif d_head in ["200mm Bauer Square Head", "200mm Mait Square Head"] and dia < 800:
                item = "Hollow Bar - OD152mm WT 33.5mm"

        return item

    def _get_hinge_db_plunger_comp3(self):
        return {
            (0, 400): ("4140 Bright Bar - 35mm",  0.14),
            (400, 500): ("4140 Bright Bar - 35mm", 0.17),
            (500, 550): ("4140 Bright Bar - 45mm", 0.26),
            (550, 650): ("4140 Bright Bar - 45mm", 0.26),
            (650, 800): ("4140 Bright Bar - 45mm", 0.32),
            (800, 1050): ("4140 Bright Bar - 45mm", 0.40),
            (1050, 1400): ("4140 Bright Bar - 60mm", 0.41),
            (1400, 1850): ("4140 Bright Bar - 60mm", 0.56),
            (1850, 2000): ("4140 Bright Bar - 100mm", 1.15),
            (2000, 2500): ("4140 Bright Bar - 100mm", 1.15),
            (2500, 5000): ("4140 Bright Bar - 100mm", 1.25),
        }

    def _get_hinge_db_component3(self):
        return {
            (0, 350): ("4140 Bright Bar - 35mm",  0.14),
            (500, 550): ("4140 Bright Bar - 45mm", 0.26),
            (550, 650): ("4140 Bright Bar - 45mm", 0.26),
            (650, 800): ("4140 Bright Bar - 45mm", 0.32),
            (800, 1050): ("4140 Bright Bar - 45mm", 0.40),
            (1050, 1400): ("4140 Bright Bar - 60mm", 0.41),
            (1400, 1600): ("4140 Bright Bar - 60mm", 0.56),
            (1600, 1850): ("4140 Bright Bar - 60mm", 0.56),
            (1850, 2000): ("4140 Bright Bar - 100mm", 1.15),
            (2000, 2500): ("4140 Bright Bar - 100mm", 1.15),
            (2500, 5000): ("4140 Bright Bar - 100mm", 1.25),
        }

    def _get_db_plunger_handler(self, p_name, dia, b_height, type, no_blade, d_head, db_type, custom, front_end, teeth):
        d_number = re.findall(r'\d+', dia)[0]
        x_head = d_head or ""
        head_matches = re.findall(r'\d+', x_head)
        head = head_matches[0] if head_matches else ""

        height_matches = re.findall(r'\d+', b_height)
        height = height_matches[0] if height_matches else 0

        dia_number = int(d_number)

        components_map = self._components_db_mapping()
        components = self._get_range_per_diameter(components_map, dia_number)

        combination = self._get_prof_combination_for_cb_db(d_head, db_type)
        pf_combination = f" - {combination}" if combination else ""

        prof_combination = f"{p_name} {dia} x {b_height} - {type} - {no_blade} - {custom} - {front_end} - {teeth} {pf_combination} "
        gusset_d_head = self._get_gusset_combination(d_head, head)
        gusset_label = "- Clean & Drill Barrel" if d_head not in ["Custom head", "Amazng Head"] else ""
        gusset = f"Gusset {gusset_d_head} x {d_number}mm Diameter {gusset_label}"
        drive_head = self._get_drive_head(d_head)
        d_head_digga = "Drive Head EARS - 130mm Square" if d_head == "130mm Square Head" else ""
        drive_head_ears = "Drive Head EARS - 130mm Square DIGGA" if d_head == "130mm Digga Square Head" else d_head_digga
        drive_head_ears_qty = 2 if d_head == "130mm Square Head" else 4
        drill_pivot_kit = self._get_drill_pivot_kit(db_type, d_head, dia_number)

        hinge_comp3 = self._get_hinge_db_component3()
        hinge_comp3_lst = self._get_range_per_diameter(hinge_comp3, dia_number)
        if hinge_comp3_lst:
            hinge_c3, hengi_c3_qty = hinge_comp3_lst
        else:
            hinge_c3, hengi_c3_qty = None, None

        handle_bar_qty = self._get_handle_bar_qty(height, dia_number)
        plunger_bar = self._get_plunger_bar(d_head, dia_number)
        plunger_bush = "Plunger Bush - 110mm OD 75mm ID - 100mm long"
        plunger_spring = "Plunger Spring"
        plunger_end_cap = "Plunger End Cap"
        wear_pads = "Barrel Wear Pads"
        wear_qty = self.round_to_nearest_even((((dia_number - 40) * 3.142) * 2) / 200)
        pcf1 = self._get_db_pcf1(dia_number)
        pcf2 = self._get_pcf2(dia_number)
        hollow_bar_extension = self._get_hollow_bar_extension(db_type, d_head, dia_number, front_end)
        zed_centre = self._get_zed_centre(hollow_bar_extension, front_end)
        rock_components = self._get_teeth_rock_components(drill_pivot_kit, dia_number, teeth, no_blade)
        clay_components = self._get_teeth_clay_components(drill_pivot_kit, dia_number, teeth, no_blade)
        taper_components = self._get_teeth_taper_components(drill_pivot_kit, dia_number, teeth, no_blade)
        zed_components = self._get_zed_frontend_components(drill_pivot_kit, dia_number, teeth, no_blade)
        drilling_arrow_head = ""
        if dia_number < 350:
            drilling_arrow_head = "Arrow Head - Small"
        elif 350 <= dia_number < 1600:
            drilling_arrow_head = "Arrow Head - Medium"
        else:
            drilling_arrow_head = "Arrow Head - Large"

        # Return the list of components with quantities
        hinge_comp1 = hinge_comp2 = handle_bar = locking_comp1 = locking_comp2 = None
        if components:
            hinge_comp1, hinge_comp2, handle_bar, locking_comp1, locking_comp2 = components
        # List of all possible components with their values
        possible_components = [
            (f"Profiling - {prof_combination}", 1.0) if prof_combination else None,
            (gusset, 4) if gusset else None,
            (drive_head, 1) if drive_head else None,
            (drive_head_ears, drive_head_ears_qty) if drive_head_ears else None,
            (drill_pivot_kit, 1) if drill_pivot_kit else None,
            (hinge_comp1, 1) if hinge_comp1 else None,
            (hinge_comp2, 2) if hinge_comp2 else None,
            (hinge_c3, hengi_c3_qty) if hinge_c3 else None,
            (handle_bar, handle_bar_qty) if handle_bar and handle_bar_qty else None,
            (locking_comp1, 3) if locking_comp1 else None,
            (locking_comp2, 3) if locking_comp2 else None,
            (drilling_arrow_head, 1) if drilling_arrow_head else None,
            (plunger_bar, 1) if plunger_bar else None,
            (plunger_bush, 1) if plunger_bush else None,
            (plunger_spring, 1) if plunger_spring else None,
            (plunger_end_cap, 1) if plunger_end_cap else None,
            (wear_pads, wear_qty) if wear_pads else None,
            pcf1 if pcf1 and pcf1 else None,
            pcf2 if pcf2 and pcf2[0] else None,
        ]
        if hollow_bar_extension and front_end in ['Taper Rock Front End', 'ZED Front End']:
            possible_components.append((hollow_bar_extension, 1))

        possible_components.append((zed_centre, 1) if zed_centre else None)
        # Filter out None values and create the final components list
        components = [component for component in possible_components if component]
        # Extend with rock_components
        if front_end == 'Rock Front End':
            components.extend(rock_components)
        elif front_end == 'Clay Front End':
            components.extend(clay_components)
        elif front_end == 'Taper Rock Front End':
            components.extend(taper_components)
        elif front_end == 'ZED Front End':
            components.extend(zed_components)
        return components

    def _get_zed_centre(self, hollow_bar, front_end):
        if front_end != 'ZED Front End':
            return None

        zed_centre_map = {
            "Hollow Bar - OD152mm WT 33.5mm": "ZED Centre 150mm",
            "Hollow Bar - OD219mm WT 25mm": "ZED Centre 219mm",
            "Hollow Bar - OD273mm WT 25mm": "ZED Centre 273mm",
        }

        return zed_centre_map.get(hollow_bar)

    def _get_pivot_kit_head_od(self, pivot_kit):
        mm = 0
        if pivot_kit == "Drilling Barrel Pivot Kit - 90mm":
            mm = 150
        elif pivot_kit == "Drilling Barrel Pivot Kit - 120mm":
            mm = 200
        elif pivot_kit == "Drilling Barrel Pivot Kit - 160mm":
            mm = 270
        return mm

    def _get_zed_frontend_components(self, pivot_kit, diameter, teeth, no_blade):
        mm = self._get_pivot_kit_head_od(pivot_kit)
        if teeth == "22mm Teeth":
            qty = round((diameter - mm - 40) / 42 * 2)
            qty = qty if qty % 2 == 0 else qty + 1
            comp1 = [
                ("BC86 - 22mm Shank Teeth BETEK", qty),
                ("BHR176 - 22mm Block Tooth Holder", qty),
            ]
            if diameter < 750:
                comp1.append(("ZED Flight Stiffener (Under 600mm)", 2))
            else:
                comp1.append(("ZED Flight Stiffener (600mm+)", 2))
            return comp1

        elif teeth == "25mm teeth":
            qty = round((diameter - mm - 40) / 44  * 2)
            qty = qty if qty % 2 == 0 else qty + 1
            comp1 = [
                ("BTK03TB - 25mm Shank Teeth", qty),
                ("BHR31 - 25mm Block Tooth Holder", qty),
                ("ZED Auger Teeth Brace", 2),
            ]
            if diameter < 750:
                comp1.append(("ZED Flight Stiffener (Under 600mm)", 2))
            else:
                comp1.append(("ZED Flight Stiffener (600mm+)", 2))
            return comp1

        elif teeth == "38/30 Teeth":
            qty = round((diameter - mm - 40) / 66 * 2)
            # Ensure qty is an odd number
            qty = qty if qty % 2 == 0 else qty + 1

            comp1 = [
                ("BKH105TB - 38/30mm Shank Teeth", qty),
                ("BHR38 - 38/30mm Block Tooth Holder", qty),
                ("ZED Auger Teeth Brace", 2),
            ]
            if diameter < 750:
                comp1.append(("ZED Flight Stiffener (Under 600mm)", 2))
            else:
                comp1.append(("ZED Flight Stiffener (600mm+)", 2))
            return comp1

        else:
            return []

    def _get_teeth_taper_components(self, pivot_kit, diameter, teeth, no_blade):
        if teeth == "22mm Teeth":
            qty = round((diameter - 78 - 40) / 42 + 4)
            qty = qty if qty % 2 != 0 else qty - 1
            tooth_qty = qty - 4
            return [
                ("BC86 - 22mm Shank Teeth BETEK", qty),
                ("BHR176 - 22mm Block Tooth Holder", tooth_qty),
                ("Rock Pilot suit 22mm Teeth 44mm Hex - RH", 1),
                ("Pilot Support - Hex", 1)
            ]
        elif teeth == "25mm teeth":
            qty = round((diameter - 150 - 40) / 44 + 4)
            qty = qty if qty % 2 != 0 else qty - 1
            tooth_qty = qty - 4
            return [
                ("BTK03TB - 25mm Shank Teeth", qty),
                ("BHR31 - 25mm Block Tooth Holder", tooth_qty),
                ("Rock Auger Pilot - 25mm Shank 75mm square", 1),
                ("Pilot Support - 75mm Square", 1)
            ]
        elif teeth == "38/30 Teeth":
            qty = round((diameter - 200 - 40) / 66 + 4)
            qty = qty if qty % 2 != 0 else qty - 1
            tooth_qty = qty - 4
            return [
                ("BKH105TB - 38/30mm Shank Teeth", qty),
                ("BHR38 - 38/30mm Block Tooth Holder", tooth_qty),
                ("Rock Auger Pilot - 38/30mm Shank 100mm Square", 1),
                ("Pilot Support - 100mm Square", 1)
            ]
        else:
            return []

    def _get_teeth_clay_components(self, pivot_kit, diameter, teeth, no_blade):
        qty = 0
        if teeth == "BFZ162 teeth":
            if no_blade == "Dual Blade":
                qty = (diameter - 200 - 40) // 75
                qty = qty if qty % 2 != 0 else qty - 1 # round down to the nearest odd number
            else:  # Single Blade
                qty = (diameter - 200 - 40) // 150  # round down to the nearest whole number

            return [
                ("BFZ162 (FZ70) 38/30mm step shank flat Teeth", qty),
                ("BKH105TB - 38/30mm Shank Teeth", 4),
                ("Phaser Teeth Holder", qty),
                ("Rock Auger Pilot - 38/30mm Shank 100mm Square", 1),
                ("Pilot Support - 100mm Square", 1)
            ]
        elif teeth == "FZ54 teeth":
            if no_blade == "Dual Blade":
                qty = (diameter - 150 - 40) // 58
                qty = qty if qty % 2 != 0 else qty - 1
            else:
                qty = (diameter - 150 - 40) // 116
            return [
                ("FZ54 Mini Bauer Teeth", qty),
                ("BTK03TB - 25mm Shank Teeth ", 4),
                ("Mini Bauer Holder", qty),
                ("Rock Auger Pilot - 25mm Shank 75mm square", 1),
                ("Pilot Support - 75mm Square ", 1)
            ]
        return []

    def _get_teeth_rock_components(self, pivot_kit, diameter, teeth, no_blade):
        # mm = self._get_pivot_kit_head_od(pivot_kit)
        qty = 0
        if teeth == "22mm Teeth":
            if no_blade == "Dual Blade":
                qty = (diameter - 78 - 40) // 43 + 4
                qty = qty if qty % 2 != 0 else qty - 1
            else:
                qty = (diameter - 78 - 40) // 86 + 4

            tooth_qty = qty - 4
            return [
                ("BC86 - 22mm Shank Teeth BETEK", qty),
                ("BHR174 - 22mm Round Tooth Holder", tooth_qty),
                ("Rock Pilot suit 22mm Teeth 44mm Hex - RH", 1),
                ("Pilot Support - Hex", 1)
            ]
        elif teeth == "25mm teeth":
            if no_blade == "Dual Blade":
                qty = (diameter - 150 - 40) // 50 + 4
                qty = qty if qty % 2 != 0 else qty - 1
            else:
                qty = (diameter - 150 - 40) // 100 + 4

            tooth_qty = qty - 4
            return [
                ("BTK03TB - 25mm Shank Teeth", qty),
                ("BHR167 - 25mm Round Tooth Holder", tooth_qty),
                ("Rock Auger Pilot - 25mm Shank 75mm square", 1),
                ("Pilot Support - 75mm Square", 1)
            ]
        elif teeth == "38/30 Teeth":
            qty = 0
            if no_blade == "Dual Blade":
                qty = (diameter - 200 - 40) // 74 + 4
                qty = qty if qty % 2 != 0 else qty - 1
            else:
                qty = (diameter - 200 - 40) // 148 + 4

            tooth_qty = qty - 4
            return [
                ("BKH105TB - 38/30mm Shank Teeth", qty),
                ("TB38R - 38/30 Shank Round Holder", tooth_qty),
                ("Rock Auger Pilot - 38/30mm Shank 100mm Square", 1),
                ("Pilot Support - 100mm Square", 1)
            ]
        else:
            return []

    def _get_db_pcf1(self, diameter):
        qty = self.convert_mm(((diameter - 40) * 2) - 300)
        if diameter >= 2000:
            return ("200mm PFC - Parallel Flange Channel", qty)
        else:
            return None

    def _components_db_mapping(self):
        # Map of diameter ranges to corresponding components
        return {
            (0, 350): ("35mm Hinge - 75mm Long", "35mm Hinge - Bush", "4140 Bright Bar - 25mm", "26mm Locking Handle Washers / Bush", "25mm Locking Handle Washers / Bush"),
            (350, 400): ("35mm Hinge - 75mm Long", "35mm Hinge - Bush", "4140 Bright Bar - 35mm", "36mm Locking Handle Washers / Bush", "35mm Locking Handle Washers / Bush"),
            (400, 500): ("35mm Hinge - 110mm Long", "35mm Hinge - Bush", "4140 Bright Bar - 35mm", "36mm Locking Handle Washers / Bush", "35mm Locking Handle Washers / Bush"),
            (500, 550): ("45mm Hinge - 180mm Long", "45mm Hinge - Bush", "4140 Bright Bar - 35mm", "36mm Locking Handle Washers / Bush", "35mm Locking Handle Washers / Bush"),
            (550, 650): ("45mm Hinge - 180mm Long", "45mm Hinge - Bush", "4140 Bright Bar - 35mm", "36mm Locking Handle Washers / Bush", "35mm Locking Handle Washers / Bush"),
            (650, 800): ("45mm Hinge - 240mm Long", "45mm Hinge - Bush", "4140 Bright Bar - 35mm", "36mm Locking Handle Washers / Bush", "35mm Locking Handle Washers / Bush"),
            (800, 1050): ("45mm Hinge - 320mm long", "45mm Hinge - Bush", "4140 Bright Bar - 35mm", "36mm Locking Handle Washers / Bush", "35mm Locking Handle Washers / Bush"),
            (1050, 1400): ("60mm Hinge - 250mm long", "60mm Hinge - Bush", "4140 Bright Bar - 35mm", "36mm Locking Handle Washers / Bush", "35mm Locking Handle Washers / Bush"),
            (1400, 1600): ("60mm Hinge - 400mm long", "60mm Hinge - Bush", "4140 Bright Bar - 35mm", "36mm Locking Handle Washers / Bush", "35mm Locking Handle Washers / Bush"),
            (1600, 1850): ("60mm Hinge - 400mm long", "60mm Hinge - Bush", "4140 Bright bar - 50mm", "51mm Locking Handle Washers / Bush", "50mm Locking Handle Washers / Bush"),
            (1850, 2000): ("100mm Hinge - 450mm long", "100mm Hinge - Bush", "4140 Bright bar - 50mm", "51mm Locking Handle Washers / Bush", "50mm Locking Handle Washers / Bush"),
            (2000, 2500): ("100mm Hinge - 450mm long", "100mm Hinge - Bush", "4140 Bright bar - 50mm", "51mm Locking Handle Washers / Bush", "50mm Locking Handle Washers / Bush"),
            (2500, 5000): ("100mm Hinge - 550mm long", "100mm Hinge - Bush", "4140 Bright bar - 50mm", "51mm Locking Handle Washers / Bush", "50mm Locking Handle Washers / Bush"),
        }

    def _get_drill_pivot_kit(self, cb_type, d_head, dia):
        item = ""
        if cb_type in ['Lightweight', 'Standard']:
            if d_head in ["75mm Square Head", "100mm Square Head", "110mm Square Head", '4" Lo Drill Head'] and dia >= 1:
                item = "Drilling Barrel Pivot Kit - 90mm"
            elif d_head in ["200mm Mait Square Head", "200mm Bauer Square Head", "Custom head"] and dia < 800:
                item = "Drilling Barrel Pivot Kit - 90mm"
            elif d_head in ["130mm Square Head", "130mm Digga Square Head", "150mm IMT Square Head", "150mm Square Head"] and dia < 1000:
                item = "Drilling Barrel Pivot Kit - 90mm"
            elif d_head in ["130mm Square Head", "130mm Digga Square Head", "150mm IMT Square Head", "150mm Square Head"] and dia >= 1000:
                item = "Drilling Barrel Pivot Kit - 120mm"
            elif d_head in ["200mm Bauer Square Head", "200mm Mait Square Head", "Custom head"] and 800 <= dia < 2100:
                item = "Drilling Barrel Pivot Kit - 120mm"
            elif d_head in ["200mm Bauer Square Head", "200mm Mait Square Head", "Custom head"] and dia >= 2100:
                item = "Drilling Barrel Pivot Kit - 160mm"

        elif cb_type == 'Heavy Duty':
            if d_head in ["75mm Square Head", "100mm Square Head", "110mm Square Head", '4" Lo Drill Head'] and dia >= 1:
                item = "Drilling Barrel Pivot Kit - 90mm"
            elif d_head in ["200mm Bauer Square Head", "200mm Mait Square Head", "Custom head"] and dia < 800:
                item = "Drilling Barrel Pivot Kit - 90mm"
            elif d_head in ["130mm Square Head", "130mm Digga Square Head", "150mm IMT Square Head", "150mm Square Head"] and dia < 900:
                item = "Drilling Barrel Pivot Kit - 90mm"
            elif d_head in ["130mm Square Head", "130mm Digga Square Head", "150mm IMT Square Head", "150mm Square Head"] and dia >= 900:
                item = "Drilling Barrel Pivot Kit - 120mm"
            elif d_head in ["200mm Bauer Square Head", "200mm Mait Square Head", "Custom head"] and 800 <= dia < 2100:
                item = "Drilling Barrel Pivot Kit - 120mm"
            elif d_head in ["200mm Bauer Square Head", "200mm Mait Square Head", "Custom head"] and dia >= 2100:
                item = "Drilling Barrel Pivot Kit - 160mm"

        return item
    # START of cleaning bucket
    def _create_cleaning_bucket(self, product):
        reference = product.display_name
        if product.product_tmpl_id.name == 'Cleaning Bucket':
            components = self._get_cleaning_bucket_components(product)
            # create bom components for tremie pipe
            self._create_bom_components(product, reference, components)

    def _get_cleaning_bucket_components(self, product):
        components = []
        p_name = product.product_tmpl_id.name
        # product attributes values
        attributes = {attr.attribute_id.name: attr.name for attr in product.product_template_attribute_value_ids}
        dia = attributes.get('Diameter', '')
        b_height = attributes.get('Barrel Height', '')
        d_head = attributes.get('Drive Head', '')
        type = attributes.get('Opening Type', '')
        no_blade = attributes.get('No. of Blade', '')
        cb_type = attributes.get('Type', '')
        custom = attributes.get('Customization', '')

        if type == 'Plunger & Handle':
            components = self._get_cb_plunger_handler(p_name, dia, b_height, type, no_blade, d_head, cb_type, custom)
        elif type == "Plunger":
            components = self._get_cb_plunger(p_name, dia, b_height, type, no_blade, d_head, cb_type, custom)
        elif type == "Handle":
            components = self._get_cb_handle(p_name, dia, b_height, type, no_blade, d_head, cb_type, custom)
        return components

    def _get_range_per_diameter(self, components_map, dia_number):
        components = None
        selected_range = None
        # Iterate over ranges and find the most specific matching range
        for (min_d, max_d), component_set in components_map.items():
            if min_d <= dia_number < max_d:
                # Check if the current range is more specific (smaller range)
                if selected_range is None or (max_d - min_d) < (selected_range[1] - selected_range[0]):
                    components = component_set
                    selected_range = (min_d, max_d)
            # Handle cases where dia_number >= 2500
            if dia_number >= 2500 and (min_d == 0 and max_d == 2500):
                components = component_set
                selected_range = (min_d, max_d)
        return components

    def _get_cb_handle(self, p_name, dia, b_height, type, no_blade, d_head, cb_type, custom):
        d_number = re.findall(r'\d+', dia)[0]
        x_head = d_head or ""
        head_matches = re.findall(r'\d+', x_head)
        head = head_matches[0] if head_matches else ""

        height_matches = re.findall(r'\d+', b_height)
        height = height_matches[0] if height_matches else 0

        dia_number = int(d_number)

        components_map = self._components_cb_mapping()
        components = self._get_range_per_diameter(components_map, dia_number)
        
        b_wear_pads = "Barrel Wear Pads"
        combination = self._get_prof_combination_for_cb_db(d_head, cb_type)
        pf_combination = f" - {combination}" if combination else ""

        prof_combination = f"{p_name} {dia} x {b_height} - {type} - {no_blade} - {custom} {pf_combination}"
        gusset_d_head = self._get_gusset_combination(d_head, head)
        gusset_label = "- Clean & Drill Barrel" if d_head not in ["Custom head", "Amazng Head"] else ""
        gusset = f"Gusset {gusset_d_head} x {d_number}mm Diameter {gusset_label}"
        drive_head = self._get_drive_head(d_head)
        d_head_digga = "Drive Head EARS - 130mm Square" if d_head == "130mm Square Head" else ""
        drive_head_ears = "Drive Head EARS - 130mm Square DIGGA" if d_head == "130mm Digga Square Head" else d_head_digga
        drive_head_ears_qty = 2 if d_head == "130mm Square Head" else 4
        pivot_kit = self._get_pivot_kit(cb_type, d_head, dia_number)

        hinge_comp3 = self._get_hinge_cb_component3()
        hinge_comp3_lst = self._get_range_per_diameter(hinge_comp3, dia_number)
        if hinge_comp3_lst:
            hinge_c3, hengi_c3_qty = hinge_comp3_lst
        else:
            hinge_c3, hengi_c3_qty = None, None

        handle_bar_qty = self._get_hinge_handle_bar_qty(height, dia_number)
        wear_pads = "Barrel Wear Pads"
        wear_qty = self.round_to_nearest_even((((dia_number - 30) * 3.142) * 2) / 200)
        pcf1 = self._get_pcf1(dia_number)
        pcf2 = self._get_pcf2(dia_number)

        cleaning_arrow_head = ""
        if dia_number < 350:
            cleaning_arrow_head = "Arrow Head - Small"
        elif 350 <= dia_number < 1600:
            cleaning_arrow_head = "Arrow Head - Medium"
        else:
            cleaning_arrow_head = "Arrow Head - Large"

        # Return the list of components with quantities
        if components:
            hinge_comp1, hinge_comp2, handle_bar, locking_comp1, locking_comp2 = components

        # List of all possible components with their values
        possible_components = [
            (f"Profiling - {prof_combination}", 1.0) if prof_combination else None,
            (gusset, 4) if gusset else None,
            (drive_head, 1) if drive_head else None,
            (drive_head_ears, drive_head_ears_qty) if drive_head_ears else None,
            (pivot_kit, 1) if pivot_kit else None,
            (hinge_comp1, 1) if hinge_comp1 else None,
            (hinge_comp2, 2) if hinge_comp2 else None,
            (hinge_c3, hengi_c3_qty) if hinge_c3 else None,
            (handle_bar, handle_bar_qty) if handle_bar and handle_bar_qty else None,
            (locking_comp1, 3) if locking_comp1 else None,
            (locking_comp2, 3) if locking_comp2 else None,
            (cleaning_arrow_head, 1) if cleaning_arrow_head else None,
            (wear_pads, wear_qty) if wear_pads else None,
            pcf1 if pcf1 and pcf1[0] else None,
            pcf2 if pcf2 and pcf2[0] else None
        ]

        # Filter out None values and create the final components list
        components = [component for component in possible_components if component]

        return components

    def _get_hinge_handle_bar_qty(self, d_height, d_number):
        def mm_to_meters(mm):
            return mm / 1000

        qty = 0
        height = int(d_height)
        if d_number < 350:
            qty = mm_to_meters(height) + 0.5
        elif 350 <= d_number < 400:
            qty = mm_to_meters(height) + 0.635
        elif 400 <= d_number < 500:
            qty = mm_to_meters(height) + 0.67
        else:
            qty = mm_to_meters(height) + 0.5
        return qty

    def _get_cb_plunger(self, p_name, dia, b_height, type, no_blade, d_head, cb_type, custom):
        d_number = re.findall(r'\d+', dia)[0]
        x_head = d_head or ""
        head_matches = re.findall(r'\d+', x_head)
        head = head_matches[0] if head_matches else ""

        dia_number = int(d_number)
        components_map = {
            (0, 400): ("35mm Hinge - 75mm Long", "35mm Hinge - Bush"),
            (400, 500): ("35mm Hinge - 110mm Long", "35mm Hinge - Bush"),
            (500, 550): ("45mm Hinge - 180mm Long", "45mm Hinge - Bush"),
            (550, 650): ("45mm Hinge - 180mm Long", "45mm Hinge - Bush"),
            (650, 800): ("45mm Hinge - 240mm Long", "45mm Hinge - Bush"),
            (800, 1500): ("45mm Hinge - 320mm long", "45mm Hinge - Bush"),
            (1500, 1850): ("60mm Hinge - 400mm long", "60mm Hinge - Bush"),
            (1850, 2000): ("100mm Hinge - 450mm long", "100mm Hinge - Bush"),
            (2000, 2500): ("100mm Hinge - 450mm long", "100mm Hinge - Bush"),
            (2500, 5000): ("100mm Hinge - 550mm long", "100mm Hinge - Bush"),
        }
        components = self._get_range_per_diameter(components_map, dia_number)

        b_wear_pads = "Barrel Wear Pads"
        dia_number = int(d_number)
        combination = self._get_prof_combination_for_cb_db(d_head, cb_type)
        pf_combination = f" - {combination}" if combination else ""

        prof_combination = f"{p_name} {dia} x {b_height} - {type} - {no_blade} - {custom} {pf_combination}"
        gusset_d_head = self._get_gusset_combination(d_head, head)
        gusset_label = "- Clean & Drill Barrel" if d_head not in ["Custom head", "Amazng Head"] else ""
        gusset = f"Gusset {gusset_d_head} x {d_number}mm Diameter {gusset_label}"
        drive_head = self._get_drive_head(d_head)
        d_head_digga = "Drive Head EARS - 130mm Square" if d_head == "130mm Square Head" else ""
        drive_head_ears = "Drive Head EARS - 130mm Square DIGGA" if d_head == "130mm Digga Square Head" else d_head_digga
        drive_head_ears_qty = 2 if d_head == "130mm Square Head" else 4
        pivot_kit = self._get_pivot_kit(cb_type, d_head, dia_number)

        hinge_comp3 = self._get_hinge_cb_plunger_component3()
        hinge_comp3_lst = self._get_range_per_diameter(hinge_comp3, dia_number)
        if hinge_comp3_lst:
            hinge_c3, hengi_c3_qty = hinge_comp3_lst
        else:
            hinge_c3, hengi_c3_qty = None, None

        plunger_bar = self._get_plunger_bar(d_head, dia_number)
        plunger_bar_qty = self._get_plunger_bar_qty(dia_number)
        plunger_bush = "Plunger Bush - 110mm OD 75mm ID - 100mm long"
        plunger_spring = "Plunger Spring"
        plunger_end_cap = "Plunger End Cap"
        bolt = "Hex Bolt - M30 x 130mm GR10.9"
        nut = "Nut - M30 Coneloc"
        wear_pads = "Barrel Wear Pads"
        wear_qty = self.round_to_nearest_even((((dia_number - 30) * 3.142) * 2) / 200)
        pfc1 = self._get_pcf1(dia_number)
        pfc2 = self._get_pcf2(dia_number)

        plung_qty = 0
        b_n_qty = 0
        if dia_number >= 1850:
            plung_qty = 2
            b_n_qty = 6
        else:
            plung_qty = 1
            b_n_qty = 3

        # Return the list of components with quantities
        hinge_comp1 = hinge_comp2 = None
        if components:
            hinge_comp1, hinge_comp2 = components
        # List of all possible components with their values
        possible_components = [
            (f"Profiling - {prof_combination}", 1.0) if prof_combination else None,
            (gusset, 4) if gusset else None,
            (drive_head, 1) if drive_head else None,
            (drive_head_ears, drive_head_ears_qty) if drive_head_ears else None,
            (pivot_kit, 1) if pivot_kit else None,
            (hinge_comp1, 1) if hinge_comp1 else None,
            (hinge_comp2, 2) if hinge_comp2 else None,
            (hinge_c3, hengi_c3_qty) if hinge_c3 else None,
            (plunger_bar, plunger_bar_qty) if plunger_bar else None,
            (plunger_bush, plung_qty) if plunger_bush else None,
            (plunger_spring, plung_qty) if plunger_spring else None,
            (plunger_end_cap, plung_qty) if plunger_end_cap else None,
            (bolt, b_n_qty) if bolt else None,
            (nut, b_n_qty) if nut else None,
            (wear_pads, wear_qty) if wear_pads else None,
            pfc1 if pfc1 and pfc1[0] else None,
            pfc2 if pfc2 and pfc2[0] else None
        ]
        # Filter out None values and create the final components list
        components = [component for component in possible_components if component]

        return components

    def _get_hinge_cb_plunger_component3(self):
        return {
            (0, 400): ("4140 Bright Bar - 35mm",  0.14),
            (400, 500): ("4140 Bright Bar - 45mm", 0.17),
            (500, 550): ("4140 Bright Bar - 45mm", 0.26),
            (550, 650): ("4140 Bright Bar - 45mm", 0.26),
            (650, 800): ("4140 Bright Bar - 45mm", 0.32),
            (800, 1500): ("4140 Bright Bar - 60mm", 0.40),
            (1500, 1850): ("4140 Bright Bar - 60mm", 0.56),
            (1850, 2000): ("4140 Bright Bar - 100mm", 1.15),
            (2000, 2500): ("4140 Bright Bar - 100mm", 1.15),
            (2500, 5000): ("4140 Bright Bar - 100mm", 1.25),
        }

    def _get_cb_plunger_handler(self, p_name, dia, b_height, type, no_blade, d_head, cb_type, custom):
        d_number = re.findall(r'\d+', dia)[0]
        x_head = d_head or ""
        head_matches = re.findall(r'\d+', x_head)
        head = head_matches[0] if head_matches else ""

        height_matches = re.findall(r'\d+', b_height)
        height = height_matches[0] if height_matches else 0

        dia_number = int(d_number)

        components_map = self._components_cb_mapping()
        components = self._get_range_per_diameter(components_map, dia_number)

        # components = components_map.get(d_number, None)
        b_wear_pads = "Barrel Wear Pads"
        dia_number = int(d_number)

        combination = self._get_prof_combination_for_cb_db(d_head, cb_type)
        pf_combination = f" - {combination}" if combination else ""
        _logger.warning("combination: %s", combination)

        prof_combination = f"{p_name} {dia} x {b_height} - {type} - {no_blade} - {custom} {pf_combination}"
        gusset_d_head = self._get_gusset_combination(d_head, head)
        gusset_label = "- Clean & Drill Barrel" if d_head not in ["Custom head", "Amazng Head"] else ""
        gusset = f"Gusset {gusset_d_head} x {d_number}mm Diameter {gusset_label}"
        drive_head = self._get_drive_head(d_head)
        d_head_digga = "Drive Head EARS - 130mm Square" if d_head == "130mm Square Head" else ""
        drive_head_ears = "Drive Head EARS - 130mm Square DIGGA" if d_head == "130mm Digga Square Head" else d_head_digga
        drive_head_ears_qty = 2 if d_head == "130mm Square Head" else 4
        pivot_kit = self._get_pivot_kit(cb_type, d_head, dia_number)

        hinge_comp3 = self._get_hinge_cb_component3()
        hinge_comp3_lst = self._get_range_per_diameter(hinge_comp3, dia_number)
        if hinge_comp3_lst:
            hinge_c3, hengi_c3_qty = hinge_comp3_lst
        else:
            hinge_c3, hengi_c3_qty = None, None

        handle_bar_qty = self._get_handle_bar_qty(height, dia_number)
        plunger_bar = self._get_plunger_handler_bar(d_head, dia_number)
        plunger_bush = "Plunger Bush - 110mm OD 75mm ID - 100mm long"
        plunger_spring = "Plunger Spring"
        plunger_end_cap = "Plunger End Cap"
        wear_pads = "Barrel Wear Pads"
        wear_qty = self.round_to_nearest_even((((dia_number - 30) * 3.142) * 2) / 200)
        pcf1 = self._get_pcf1(dia_number)
        pcf2 = self._get_pcf2(dia_number)

        cleaning_arrow_head = ""
        if dia_number < 350:
            cleaning_arrow_head = "Arrow Head - Small"
        elif 350 <= dia_number < 1600:
            cleaning_arrow_head = "Arrow Head - Medium"
        else:
            cleaning_arrow_head = "Arrow Head - Large"

        hinge_comp1 = hinge_comp2 = handle_bar = locking_comp1 = locking_comp2 = None
        if components:
            hinge_comp1, hinge_comp2, handle_bar, locking_comp1, locking_comp2 = components

        # List of all possible components with their values
        possible_components = [
            (f"Profiling - {prof_combination}", 1.0) if prof_combination else None,
            (gusset, 4) if gusset else None,
            (drive_head, 1) if drive_head else None,
            (drive_head_ears, drive_head_ears_qty) if drive_head_ears else None,
            (pivot_kit, 1) if pivot_kit else None,
            (hinge_comp1, 1) if hinge_comp1 else None,
            (hinge_comp2, 2) if hinge_comp2 else None,
            (hinge_c3, hengi_c3_qty) if hinge_c3 else None,
            (handle_bar, handle_bar_qty) if handle_bar and handle_bar_qty else None,
            (locking_comp1, 3) if locking_comp1 else None,
            (locking_comp2, 3) if locking_comp2 else None,
            (cleaning_arrow_head, 1) if cleaning_arrow_head else None,
            (plunger_bar, 1) if plunger_bar else None,
            (plunger_bush, 1) if plunger_bush else None,
            (plunger_spring, 1) if plunger_spring else None,
            (plunger_end_cap, 1) if plunger_end_cap else None,
            (wear_pads, wear_qty) if wear_pads else None,
            pcf1 if pcf1 and pcf1[0] else None,
            pcf2 if pcf2 and pcf2[0] else None
        ]
        
        # Filter out None values and create the final components list
        components = [component for component in possible_components if component]

        return components

    def convert_mm(self, mm):
        return mm / 1000

    def _get_pcf1(self, diameter):
        qty = self.convert_mm(((diameter - 30) * 2) - 300)
        if diameter >= 2000:
            return ("200mm PFC - Parallel Flange Channel", qty)
        else:
            return None

    def _get_pcf2(self, diameter):
        qty = self.convert_mm(diameter - 240)
        if 2000 <= diameter < 2500:
            return ("250mm PFC - Parallel Flange Channel", qty)
        elif diameter >= 2500:
            return ("300mm PFC - Parallel Flange Channel", qty)
        else:
            return None

    def _components_cb_mapping(self):
        # Map of diameter ranges to corresponding components
        return {
            (0, 350): ("35mm Hinge - 75mm Long", "35mm Hinge - Bush", "4140 Bright Bar - 25mm", "26mm Locking Handle Washers / Bush", "25mm Locking Handle Washers / Bush"),
            (350, 400): ("35mm Hinge - 75mm Long", "35mm Hinge - Bush", "4140 Bright Bar - 35mm", "36mm Locking Handle Washers / Bush", "35mm Locking Handle Washers / Bush"),
            (400, 500): ("35mm Hinge - 110mm Long", "35mm Hinge - Bush", "4140 Bright Bar - 35mm", "36mm Locking Handle Washers / Bush", "35mm Locking Handle Washers / Bush"),
            (500, 550): ("45mm Hinge - 180mm Long", "45mm Hinge - Bush", "4140 Bright Bar - 35mm", "36mm Locking Handle Washers / Bush", "35mm Locking Handle Washers / Bush"),
            (550, 650): ("45mm Hinge - 180mm Long", "45mm Hinge - Bush", "4140 Bright Bar - 35mm", "36mm Locking Handle Washers / Bush", "35mm Locking Handle Washers / Bush"),
            (650, 800): ("45mm Hinge - 240mm Long", "45mm Hinge - Bush", "4140 Bright Bar - 35mm", "36mm Locking Handle Washers / Bush", "35mm Locking Handle Washers / Bush"),
            (800, 1500): ("45mm Hinge - 320mm long", "45mm Hinge - Bush", "4140 Bright Bar - 35mm", "36mm Locking Handle Washers / Bush", "35mm Locking Handle Washers / Bush"),
            (1500, 1600): ("60mm Hinge - 400mm long", "60mm Hinge - Bush", "4140 Bright Bar - 35mm", "36mm Locking Handle Washers / Bush", "35mm Locking Handle Washers / Bush"),
            (1600, 1850): ("60mm Hinge - 400mm long", "60mm Hinge - Bush", "4140 Bright bar - 50mm", "51mm Locking Handle Washers / Bush", "50mm Locking Handle Washers / Bush"),
            (1850, 2000): ("100mm Hinge - 450mm long", "100mm Hinge - Bush", "4140 Bright bar - 50mm", "51mm Locking Handle Washers / Bush", "50mm Locking Handle Washers / Bush"),
            (2000, 2500): ("100mm Hinge - 450mm long", "100mm Hinge - Bush", "4140 Bright bar - 50mm", "51mm Locking Handle Washers / Bush", "50mm Locking Handle Washers / Bush"),
            (2500, 5000): ("100mm Hinge - 550mm long", "100mm Hinge - Bush", "4140 Bright bar - 50mm", "51mm Locking Handle Washers / Bush", "50mm Locking Handle Washers / Bush"),
        }

    def _get_plunger_handler_bar(self, d_head, dia_number):
        bar = ""
        if d_head in ["75mm Square Head", "100mm Square Head", "110mm Square Head", '4" Lo Drill Head'] and dia_number >= 1:
            bar = "Plunger Bars - 550mm Tongue & grooved one end + M24 thread"
        elif d_head in ["130mm Square Head", "130mm Digga Square Head", "150mm Square Head", "150mm IMT Square Head", "200mm Mait Square Head"] and dia_number < 900:
            bar = "Plunger Bars - 550mm Tongue & grooved one end + M24 thread"
        elif d_head in ["130mm Square Head", "130mm Digga Square Head", "150mm Square Head", "150mm IMT Square Head"] and dia_number >= 900:
            bar = "Plunger Bars - 650mm Tongue & grooved one end + M24 thread"
        elif d_head in ["200mm Bauer Square Head"] and dia_number < 900:
            bar = "Plunger Bars - 650mm Tongue & grooved one end + M24 thread"
        elif d_head in ["200mm Bauer Square Head", "200mm Mait Square Head"] and dia_number >= 900:
            bar = "Plunger Bars - 750mm Tongue & grooved one end + M24 thread"
        return bar

    def _get_plunger_bar(self, d_head, dia_number):
        bar = ""
        if d_head in ["75mm Square Head", "100mm Square Head", "110mm Square Head", '4" Lo Drill Head'] and dia_number >= 1:
            bar = "Plunger Bars - 550mm Tongue & grooved one end + M24 thread"
        elif d_head in ["130mm Square Head", "130mm Digga Square Head", "150mm Square Head", "150mm IMT Square Head", "200mm Mait Square Head"] and dia_number < 900:
            bar = "Plunger Bars - 550mm Tongue & grooved one end + M24 thread"
        elif d_head in ["130mm Square Head", "130mm Digga Square Head", "150mm Square Head", "150mm IMT Square Head"] and dia_number >= 900:
            bar = "Plunger Bars - 650mm Tongue & grooved one end + M24 thread"
        elif d_head in ["200mm Bauer Square Head", "Custom head"] and dia_number < 900:
            bar = "Plunger Bars - 650mm Tongue & grooved one end + M24 thread"
        elif d_head in ["200mm Bauer Square Head", "200mm Mait Square Head"] and dia_number >= 900:
            bar = "Plunger Bars - 750mm Tongue & grooved one end + M24 thread"
        return bar

    def _get_plunger_bar_qty(self, dia_number):
        qty = 0
        if dia_number < 1850:
            qty = 1
        else:
            qty = 2   
        return qty

    def _get_drive_head(self, d_head):
        drive_head = ""
        if d_head == "75mm Square Head":
            drive_head = "Drive Head - 75mm Square"
        elif d_head == "100mm Square Head":
            drive_head = "Drive Head - 100mm Square"
        elif d_head == "110mm Square Head":
            drive_head = "Drive Head - 110mm Square"
        elif d_head == "130mm Square Head":
            drive_head = "Drive Head - 130mm Square"
        elif d_head == "130mm Digga Square Head":
            drive_head = "Drive Head - 130mm Square DIGGA"
        elif d_head == "150mm Square Head":
            drive_head = "Drive Head - 150mm Square"
        elif d_head == "150mm IMT Square Head":
            drive_head = "Drive Head - 150mm Square IMT"
        elif d_head == "200mm Bauer Square Head":
            drive_head = "Drive Head - 200mm Square Bauer"
        elif d_head == "200mm Mait Square Head":
            drive_head = "Drive Head - 200mm Square MAIT"
        elif d_head == '4" Lo Drill Head':
            drive_head = 'Drive Head - 4" Lo Drill'
        return drive_head

    def _get_pivot_kit(self, cb_type, d_head, dia):
        item = ""

        # Lightweight conditions
        drive_head = ["75mm Square Head", "100mm Square Head", "110mm Square Head", "130mm Square Head", "150mm Square Head", "200mm Square Head", '4" Lo Drill Head']
        if cb_type == 'Lightweight':
            if (d_head in ["75mm Square Head", "100mm Square Head", "110mm Square Head", '4" Lo Drill Head']) and dia < 550:
                item = "Cleaning Bucket Pivot Kit - 60mm"
            elif (d_head in ["130mm Square Head", "130mm Digga Square Head", "150mm Square Head", '150mm IMT Square Head']) and dia < 450:
                    item = "Cleaning Bucket Pivot Kit - 60mm"
            elif d_head in ["75mm Square Head", "100mm Square Head", "110mm Square Head", '4" Lo Drill Head'] and 550 <= dia < 800:
                item = "Cleaning Bucket Pivot Kit - 80mm"
            elif d_head in ["130mm Square Head", "130mm Digga Square Head", "150mm Square Head", '150mm IMT Square Head'] and 450 <= dia < 550:
                item = "Cleaning Bucket Pivot Kit - 80mm"
            elif d_head in ["75mm Square Head", "100mm Square Head", "110mm Square Head", '4" Lo Drill Head'] and dia >= 800:
                item = "Cleaning Bucket Pivot Kit - 90mm"
            elif d_head in ["130mm Square Head", "130mm Digga Square Head", "150mm Square Head", '150mm IMT Square Head'] and dia >= 550:
                item = "Cleaning Bucket Pivot Kit - 90mm"
            elif d_head in ["Custom head", "200mm Bauer Square Head", "200mm Mait Square Head"] and dia < 1300:
                item = "Cleaning Bucket Pivot Kit - 90mm"

        # Standard conditions
        elif cb_type == 'Standard':
            if d_head == "75mm Square Head" and dia < 550:
                item = "Cleaning Bucket Pivot Kit - 60mm"
            elif d_head in ["100mm Square Head", "110mm Square Head", '4" Lo Drill Head'] and dia < 500:
                item = "Cleaning Bucket Pivot Kit - 60mm"
            elif d_head in ["130mm Square Head", "130mm Digga Square Head", "150mm Square Head", '150mm IMT Square Head'] and dia < 450:
                item = "Cleaning Bucket Pivot Kit - 60mm"
            elif d_head == "75mm Square Head" and 550 <= dia < 800:
                item = "Cleaning Bucket Pivot Kit - 80mm"
            elif d_head in ["100mm Square Head", "110mm Square Head", '4" Lo Drill Head'] and 500 <= dia < 650:
                item = "Cleaning Bucket Pivot Kit - 80mm"
            elif d_head in ["130mm Square Head", "130mm Digga Square Head", "150mm Square Head", '150mm IMT Square Head'] and 450 <= dia < 550:
                item = "Cleaning Bucket Pivot Kit - 80mm"

            elif d_head == "75mm Square Head" and dia >= 800:
                item = "Cleaning Bucket Pivot Kit - 90mm"
            elif d_head in ["100mm Square Head", "110mm Square Head", '4" Lo Drill Head'] and dia >= 650:
                item = "Cleaning Bucket Pivot Kit - 90mm"
            elif d_head in ["130mm Square Head", "130mm Digga Square Head", "150mm Square Head", '150mm IMT Square Head'] and dia >= 550:
                item = "Cleaning Bucket Pivot Kit - 90mm"
            elif d_head in ["200mm Bauer Square Head", "200mm Mait Square Head"] and dia < 1300:
                item = "Cleaning Bucket Pivot Kit - 90mm"

        # Heavy Duty conditions
        elif cb_type == 'Heavy Duty':
            if d_head == "75mm Square Head" and dia < 550:
                item = "Cleaning Bucket Pivot Kit - 60mm"
            elif d_head == "75mm Square Head" and 550 <= dia < 800:
                item = "Cleaning Bucket Pivot Kit - 80mm"
            elif d_head in ["100mm Square Head", "110mm Square Head", "130mm Square Head", "130mm Digga Square Head", "150mm Square Head", '4" Lo Drill Head', '150mm IMT Square Head'] and dia < 500:
                item = "Cleaning Bucket Pivot Kit - 80mm"
            elif d_head == "75mm Square Head" and dia >= 800:
                item = "Cleaning Bucket Pivot Kit - 90mm"
            elif d_head in ["100mm Square Head", "110mm Square Head", "130mm Square Head", "130mm Digga Square Head", "150mm Square Head", '4" Lo Drill Head', '150mm IMT Square Head'] and dia >= 500:
                item = "Cleaning Bucket Pivot Kit - 90mm"
            elif d_head in  ["200mm Mait Square Head", "200mm Bauer Square Head"] and dia < 1300:
                item = "Cleaning Bucket Pivot Kit - 90mm"

        # General conditions for 120mm and 160mm kits
        if cb_type in ['Lightweight', 'Standard', 'Heavy Duty']:
            if d_head in ["200mm Bauer Square Head", "200mm Mait Square Head"] and 1300 <= dia < 2500:
                item = "Cleaning Bucket Pivot Kit - 120mm"
            elif d_head in ["200mm Bauer Square Head", "200mm Mait Square Head"] and dia >= 2500:
                item = "Cleaning Bucket Pivot Kit - 160mm"
        return item

    def _get_handle_bar_qty(self, d_height, d_number):
        def mm_to_meters(mm):
            return mm / 1000
    
        qty = 0
        height = int(d_height)
        if d_number < 350:
            qty = mm_to_meters(height) + 0.1
        elif 350 <= d_number < 400:
            qty = mm_to_meters(height) + 0.235
        elif 400 <= d_number < 500:
            qty = mm_to_meters(height) + 0.27
        else:
            qty = mm_to_meters(height) + 0.1
        return qty

    def _get_hinge_cb_component3(self):
        return {
            (0, 350): ("4140 Bright Bar - 35mm",  0.14),
            (500, 550): ("4140 Bright Bar - 45mm", 0.26),
            (550, 650): ("4140 Bright Bar - 45mm", 0.26),
            (650, 800): ("4140 Bright Bar - 45mm", 0.32),
            (800, 1500): ("4140 Bright Bar - 45mm", 0.40),
            (1500, 1600): ("4140 Bright Bar - 60mm", 0.56),
            (1600, 1850): ("4140 Bright Bar - 60mm", 0.56),
            (1850, 2000): ("4140 Bright Bar - 100mm", 1.15),
            (2000, 2500): ("4140 Bright Bar - 100mm", 1.15),
            (2500, 5000): ("4140 Bright Bar - 100mm", 1.25),
        }

    def round_to_nearest_even(self, number):
        rounded_number = round(number)

        if rounded_number % 2 != 0:
            # Round up or down to the nearest even number based on proximity
            if number - rounded_number >= 0:
                return rounded_number + 1  # round up to the next even number
            else:
                return rounded_number - 1  # round down to the previous even number
        return rounded_number

    def _get_prof_combination_for_cb_db(self, drive_head, type):
        if drive_head == '75mm Square Head' and type == 'Lightweight':
            return '75mm Lightweight'
        
        elif (drive_head == '75mm Square Head' and type == 'Standard') or \
            (drive_head == '100mm Square Head' and type == 'Lightweight') or \
            (drive_head == '110mm Square Head' and type == 'Lightweight'):
            return '75mm Standard, 100mm Lightweight, 110mm Lightweight'
        
        elif (drive_head == '75mm Square Head' and type == 'Heavy Duty') or \
            (drive_head == '100mm Square Head' and type == 'Standard') or \
            (drive_head == '110mm Square Head' and type == 'Standard') or \
            (drive_head == '130mm Square Head' and type == 'Lightweight') or \
            (drive_head == '130mm Digga Square Head' and type == 'Lightweight') or \
            (drive_head == '150mm IMT Square Head' and type == 'Lightweight') or \
            (drive_head == '150mm Square Head' and type == 'Lightweight'):
            return '75mm Heavy Duty, 100mm Standard, 110mm Standard, 130mm Lightweight, 150mm Lightweight'
        
        elif (drive_head == '100mm Square Head' and type == 'Heavy Duty') or \
            (drive_head == '110mm Square Head' and type == 'Heavy Duty') or \
            (drive_head == '130mm Square Head' and type == 'Standard') or \
            (drive_head == '130mm Digga Square Head' and type == 'Standard') or \
            (drive_head == '150mm IMT Square Head' and type == 'Standard') or \
            (drive_head == '150mm Square Head' and type == 'Standard') or \
            (drive_head == '200mm Mait Square Head' and type == 'Lightweight') or \
            (drive_head == '200mm Bauer Square Head' and type == 'Lightweight'):
            return '100mm Heavy Duty, 110mm Heavy Duty, 130mm Standard, 150mm Standard, 200mm Lightweight'
        
        elif (drive_head == '130mm Square Head' and type == 'Heavy Duty') or \
            (drive_head == '130mm Digga Square Head' and type == 'Heavy Duty') or \
            (drive_head == '150mm Square Head' and type == 'Heavy Duty') or \
            (drive_head == '150mm IMT Square Head' and type == 'Heavy Duty') or \
            (drive_head == '200mm Mait Square Head' and type == 'Standard') or \
            (drive_head == '200mm Bauer Square Head' and type == 'Standard'):
            return '130mm Heavy Duty, 150mm Heavy Duty, 200mm Standard'

        elif (drive_head == '200mm Bauer Square Head' and type == 'Heavy Duty') or \
            (drive_head == '200mm Mait Square Head' and type == 'Heavy Duty'):
            return '200mm Heavy Duty'

        elif type == "Lightweight" and drive_head == '4" Lo Drill Head':
            return '4" Lo Drill Lightweight'
        elif type == "Standard" and drive_head == '4" Lo Drill Head':
            return '4" Lo Drill Standard'
        elif type == "Heavy Duty" and drive_head == '4" Lo Drill Head':
            return '4" Lo Drill Heavy Duty'

        elif type == "Lightweight" and drive_head == 'Custom head':
            return 'Custom Head Lightweight'
        elif type == "Standard" and drive_head == 'Custom head':
            return 'Custom Head Standard'
        elif type == "Heavy Duty" and drive_head == 'Custom head':
            return 'Custom Head Heavy Duty'

        # If no combination found, return empty
        return ''

    def _create_tre_pipe(self, product):
        reference = product.display_name
        if product.product_tmpl_id.name == 'Tremie Pipe Trial':
            components = self._get_tre_pipe_components(product)
            # create bom components for tremie pipe
            self._create_bom_components(product, reference, components)

    def _get_tre_pipe_components(self, product):
        p_name = product.product_tmpl_id.name
        # product attributes values
        attributes = {attr.attribute_id.name: attr.name for attr in product.product_template_attribute_value_ids}
        type = attributes.get('Type_TP', '')
        tp_length = attributes.get('Length_TP', '')
        tp_diameter = attributes.get('Diameter_TP', '')
        tp_size = attributes.get('Pipe Size_TP', '')
        components = []
        if type == 'Intermediate':
            components = self._get_tp_intermediate(tp_length, tp_diameter, tp_size)
        else:
            if type == 'Lead Section':
                components = self._get_tp_lead_section(tp_length, tp_diameter, tp_size)
        return components

    def _get_tp_intermediate(self, tp_length, tp_diameter, tp_size):
        l_number = re.findall(r'\d+\.\d+|\d+', tp_length)[0]
        d_number = re.findall(r'\d+', tp_diameter)[0]

        tc_female = f'{d_number} "Tremie Coupling - Female' 
        tc_male = f'{d_number} "Tremie Coupling - Male  '
        c3_qty = self._get_c3_qty(l_number, d_number )
        components = [
                (f"{tc_female}", 1),
                (f"{tc_male}", 1),
                (f"{tp_size}", c3_qty)
            ]
        return components 

    def _get_tp_lead_section(self, tp_length, tp_diameter, tp_size):
        l_number = re.findall(r'\d+\.\d+|\d+', tp_length)[0]
        d_number = re.findall(r'\d+', tp_diameter)[0]
        l = float(l_number)
        d = int(d_number)

        c3_qty = l - 0.10
        lead_c1 = '4" Tremie Coupling - Female' 
        lead_c2 = '105mm CFA Plug Holder'
        lead_c3 = tp_size

        tc_female = f'{d_number} "Tremie Coupling - Female' 
        components = []
        c2_qty = 0.00
        if d == 6:
            c2_qty += l - 0.10
        else:
            c2_qty += l - 0.16

        if tp_diameter == '4" Diameter':
            components = [
                    (f"{lead_c1}", 1),
                    (f"{lead_c2}", 1),
                    (f"{lead_c3}", c3_qty)
                ]
        else:
            components = [
                    (f"{tc_female}", 1),
                    (f"{lead_c3}", c2_qty)
                ]
        return components
    
    def _get_c3_qty(self, leng, dia):
        d = int(dia)
        l = float(leng)
        qty = 0.00
        if d == 4:
            qty += l - 0.13
        elif d == 6:
            qty += l - 0.10
        elif d == 8:
            qty += l - 0.19
        elif d == 10 or d == 12:
            qty += l - 0.20
        else:
            qty
            
        return qty

    def _create_bom_for_variant(self, product):
        """
            - Automatically generate bom for variants when a product created
            - Set default MO components & operations
            - Calculate component qty based on diameter for teeth attribute
        """
        parent_product_names = ['Core Barrel']
        
        if product.product_tmpl_id.name in parent_product_names:
            # Check if a BoM already exists for this product variant
            existing_bom = self.env['mrp.bom'].search([('product_id', '=', product.id)], limit=1)
            if existing_bom:
                return
                
            attributes = {attr.attribute_id.name: attr.name for attr in product.product_template_attribute_value_ids}
    
            diameter = attributes.get('Diameter', '')
            height = attributes.get('Height-A', '')
            drive_head = attributes.get('Drive Head', '')
            teeth = attributes.get('Teeth', '')
            customization = attributes.get('Customization', '')
            type = attributes.get('Type', '')

            # Get the numeric value of drive attribute e.g 22mm 
            drive_head_attr = self._extract_numeric_value(drive_head)
            
            # Use the name_get method to get the formatted name for bom reference
            reference = product.display_name

            # Calculate the teeth qty based on diameter 
            teeth_data = self._load_teeth_data('core_barrel_teeth_qty.csv')
            component_qty = self._compute_number_of_teeth(attributes, diameter, teeth_data)
            prod_qty = component_qty if component_qty > 0 else 1

            # Drive head combination
            drive_head_name = ''
            if drive_head == '75mm Square Head':
                drive_head_name = 'Drive Head - 75mm Square'
            elif drive_head == '100mm Square Head':
                drive_head_name = 'Drive Head - 100mm Square'
            elif drive_head == '110mm Square Head':
                drive_head_name = 'Drive Head - 110mm Square'
            elif drive_head == '130mm Square Head':
                drive_head_name = 'Drive Head - 130mm Square'
            elif drive_head == '150mm Square Head':
                drive_head_name = 'Drive Head - 150mm Square'
            elif drive_head == '150mm IMT Square Head':
                drive_head_name = 'Drive Head - 150mm Square IMT'
            elif drive_head == '200mm Bauer Square Head':
                drive_head_name = 'Drive Head - 200mm Square Bauer'
            elif drive_head == '200mm Mait Square Head':
                drive_head_name = 'Drive Head - 200mm Square MAIT'
            elif drive_head == '130mm Digga Square Head':
                drive_head_name = 'Drive Head - 130mm Square DIGGA'
            else: 
                drive_head_name

            # Profiling combination
            combination = ''
            if drive_head == '100mm Square Head' and type == 'Heavy Duty' or \
                drive_head == '110mm Square Head' and type == 'Heavy Duty' or \
                drive_head == '130mm Square Head' and type == 'Standard' or \
                drive_head == '130mm Digga Square Head' and type == 'Standard' or \
                drive_head == '150mm Square Head' and type == 'Standard' or \
                drive_head == '150mm IMT Square Head' and type == 'Standard' or \
                drive_head == '200mm Bauer Square Head' and type == 'Lightweight' or \
                drive_head == '200mm Mait Square Head' and type == 'Lightweight':
                combination = '100mm Heavy Duty, 110mm Heavy Duty, 130mm Standard, 150mm Standard, 200mm Lightweight'
            elif drive_head == '130mm Square Head' and type == 'Heavy Duty' or \
                drive_head == '130mm Digga Square Head' and type == 'Heavy Duty' or \
                drive_head == '150mm Square Head' and type == 'Heavy Duty' or \
                drive_head == '150mm IMT Square Head' and type == 'Heavy Duty' or \
                drive_head == '200mm Bauer Square Head' and type == 'Standard' or \
                drive_head == '200mm Mait Square Head' and type == 'Standard':
                combination = '130mm Heavy Duty, 150mm Heavy Duty, 200mm Standard'
            elif drive_head == '200mm Bauer Square Head' and type == 'Heavy Duty' or \
                drive_head == '200mm Mait Square Head' and type == 'Heavy Duty':
                combination = '200mm Heavy Duty'
            elif drive_head == '75mm Square Head' and type == 'Lightweight': 
                combination = '75mm Lightweight'
            elif drive_head == '75mm Square Head' and type == 'Standard' or \
                drive_head == '100mm Square Head' and type == 'Lightweight' or \
                drive_head == '110mm Square Head' and type == 'Lightweight': 
                combination = '75mm Standard, 100mm Lightweight, 110mm Lightweight'
            elif drive_head == '75mm Square Head' and type == 'Heavy Duty' or \
                drive_head == '100mm Square Head' and type == 'Standard' or \
                drive_head == '110mm Square Head' and type == 'Standard' or \
                drive_head == '130mm Square Head' and type == 'Lightweight' or \
                drive_head == '130mm Digga Square Head' and type == 'Lightweight' or \
                drive_head == '150mm Square Head' and type == 'Lightweight' or \
                drive_head == '150mm IMT Square Head' and type == 'Lightweight': 
                combination = '75mm Heavy Duty, 100mm Standard, 110mm Standard, 130mm Lightweight, 150mm Lightweight'
            else:
                combination

            # Teeth attribute values
            teeth_attr = ''
            if teeth == '22mm Teeth' or teeth == '22mm Extra Teeth':
                teeth_attr = '22mm' 
            elif teeth == '25mm Teeth' or teeth == '25mm Extra Teeth':
                teeth_attr = '25mm'
            elif teeth == '38/30 Teeth':
                teeth_attr = '38/20mm'
            elif teeth == 'CJ2 Teeth':
                teeth_attr = 'CJ2'
            elif teeth == 'WS20 Teeth':
                teeth_attr = 'WS20'

            prof_combination = f"{product.product_tmpl_id.name} {diameter}, {height}, {teeth}, {customization} - {combination}"
            # List of components for core barrel 
            components = [
                (f"Profiling - {prof_combination}", 1.0),
                (f"{drive_head_name}", 1.0),
                (f"40x8 Flat Bar - Hardfaced Wear Strip", 1.0),
                (f"12mm Round Bar - Miniflights", 1.0),
            ]
            # Find the index of the 1st component
            index = next(i for i, component in enumerate(components) if component == (f"Profiling - {prof_combination}", 1.0))
            gusset_label = "Core Barrel 22mm Teeth" if teeth in ['22mm Extra Teeth', '22mm Teeth'] else "Core Barrel"
            components.insert(index + 1, (f"Gusset {drive_head_attr} Drive x {diameter} - {gusset_label}", 4.0))

            # Find the index of the 2nd component
            index = next(i for i, component in enumerate(components) if component == (f"{drive_head_name}", 1.0))

            # Insert new components based on attributes
            if drive_head == '130mm Digga Square Head':
                components.insert(index + 1, (f"Drive Head EARS - 130mm Square DIGGA", 4.0))
            elif drive_head == '130mm Square Head':
                components.insert(index + 1, (f"Drive Head EARS - 130mm Square", 2.0))
            if teeth == 'CJ2/WS20 Combo Teeth':
                components.insert(index + 1, (f"CJ2 Teeth", 1.0))
                components.insert(index + 1, (f"CJ2 Tooth Holder", 1.0))
                components.insert(index + 1, (f"WS20 Teeth", 4.0))
                components.insert(index + 1, (f"WS20 Tooth Holder", 4.0))
            else:    
                components.insert(index + 1, (f"{self._get_detault_teeth_combination(teeth_attr, 1)}", prod_qty))
                components.insert(index + 1, (f"{self._get_detault_teeth_combination(teeth_attr, 0)}", prod_qty))
                
            # Create new bom and set default values 
            self._create_bom_components(product, reference, components)

    def _create_bom_components(self, product, reference, components):
        bom_lines = []
        uom_meter = self.env.ref('uom.product_uom_meter', raise_if_not_found=False)
        unit = self.env.ref('uom.product_uom_unit', raise_if_not_found=False)

        for component_name, qty in components:
            keywords = {'Permanent Casing', 'Hollow Bar', 'Flat Bar', 'Pipe', 'Parallel Flange Channel', 'Bright Bar'}
            uom = uom_meter if any(keyword in component_name for keyword in keywords) else unit
            component = self.env['product.product'].search([('name', '=', component_name)], limit=1)
            if not component:
                component = self.env['product.product'].create({
                    'name': component_name,
                    'type': 'consu',
                    'is_storable': True,
                    'uom_id': uom.id,
                })
            bom_lines.append((0, 0, {
                'product_id': component.id,
                'product_qty': qty,
                'product_uom_id': uom.id,
            }))
        operation_ids = self._get_default_work_center(product)
        Mrp_bom = self.env['mrp.bom'].create({
            'code': reference,
            'product_tmpl_id': product.product_tmpl_id.id,
            'product_id': product.id,
            'product_qty': 1.0,
            'type': 'normal',
            'bom_line_ids': bom_lines,
            'operation_ids': operation_ids,
        })
        return Mrp_bom

    def _get_default_work_center(self, product):
        if product.name == "Tremie Pipe Trial":
            return self.get_default_tp_operations()
        if product.name == "Cleaning Bucket":
            return self.get_default_cb_operations()
        if product.name == "Drilling Barrel":
            return self.get_default_db_operations()
        if product.name == "Pile Casing Stock":
            return self.get_default_pile_casing_operations()
        if product.name == "Bored Pile Auger":
            return self.get_default_bp_auger_operations()
        if product.name == "High Tensile Adapter":
            return self.get_default_hta_operations()
        else:
            return self.get_default_operations()

    def get_default_hta_operations(self):
        operations = [
            {
                'name': 'Tacking',
                'workcenter_id': 1,  # Welding Bay - 1 (Trent)
                'time_mode': 'auto',
                'time_cycle_manual': 0.0,
            },
            {
                'name': 'Welding',
                'workcenter_id': 4,  # Welding Bay - 4 (Shayne)
                'time_mode': 'auto',
                'time_cycle_manual': 0.0,
            }
        ]
        operation_lines = [(0, 0, op) for op in operations]
        return operation_lines

    def get_default_pile_casing_operations(self):
        operations = [
            {
                'name': 'Rolling',
                'workcenter_id': 9,  # Plate Rollers - Rolling
                'time_mode': 'auto',
                'time_cycle_manual': 0.0,
            },
            {
                'name': 'Tacking',
                'workcenter_id': 1,  # Welding Bay - 1 (Trent)
                'time_mode': 'auto',
                'time_cycle_manual': 0.0,
            },
            {
                'name': 'Welding',
                'workcenter_id': 4,  # Welding Bay - 4 (Shayne)
                'time_mode': 'auto',
                'time_cycle_manual': 0.0,
            }
        ]
        operation_lines = [(0, 0, op) for op in operations]
        return operation_lines
        
    def get_default_bp_auger_operations(self):
        operations = [
            {
                'name': 'Tacking',
                'workcenter_id': 1,  # Welding Bay - 1 (Trent)
                'time_mode': 'auto',
                'time_cycle_manual': 0.0,
            },
            {
                'name': 'Flight Welding',
                'workcenter_id': 5,  # Welding Bay - 5 (Nick)
                'time_mode': 'auto',
                'time_cycle_manual': 0.0,
            },
            {
                'name': 'Teeth Setting',
                'workcenter_id': 2,  # Welding Bay - 2 (Eretz)
                'time_mode': 'auto',
                'time_cycle_manual': 0.0,
            },
            {
                'name': 'Teeth Welding',
                'workcenter_id': 3,  # Welding Bay - 3 (Jimmy)
                'time_mode': 'auto',
                'time_cycle_manual': 0.0,
            },
            {
                'name': 'HEAD Setting',
                'workcenter_id': 1,  # Welding Bay - 1 (Trent)
                'time_mode': 'auto',
                'time_cycle_manual': 0.0,
            },
            {
                'name': 'HEAD Welding',
                'workcenter_id': 3,  # Welding Bay - 3 (Jimmy)
                'time_mode': 'auto',
                'time_cycle_manual': 0.0,
            }
        ]
        operation_lines = [(0, 0, op) for op in operations]
        return operation_lines
        
    def get_default_db_operations(self):
        operations = [
            {
                'name': 'Rolling',
                'workcenter_id': 9,  # Plate Rollers - Rolling
                'time_mode': 'auto',
                'time_cycle_manual': 0.0,
            },
            {
                'name': 'Tacking',
                'workcenter_id': 1,  # Welding Bay - 1 (Trent)
                'time_mode': 'auto',
                'time_cycle_manual': 0.0,
            },
            {
                'name': 'Welding',
                'workcenter_id': 5,  # Welding Bay - 5 (Nick)
                'time_mode': 'auto',
                'time_cycle_manual': 0.0,
            },
            {
                'name': 'Teeth Setting',
                'workcenter_id': 2,  # Welding Bay - 2 (Eretz)
                'time_mode': 'auto',
                'time_cycle_manual': 0.0,
            },
            {
                'name': 'Teeth Welding',
                'workcenter_id': 3,  # Welding Bay - 3 (Jimmy)
                'time_mode': 'auto',
                'time_cycle_manual': 0.0,
            },
            {
                'name': 'HEAD Setting',
                'workcenter_id': 1,  # Welding Bay - 1 (Trent)
                'time_mode': 'auto',
                'time_cycle_manual': 0.0,
            },
            {
                'name': 'HEAD Welding',
                'workcenter_id': 3,  # Welding Bay - 3 (Jimmy)
                'time_mode': 'auto',
                'time_cycle_manual': 0.0,
            }
        ]
        operation_lines = [(0, 0, op) for op in operations]
        return operation_lines

    def get_default_tp_operations(self):
        # Define default operations for Core Barrels
        operations = [
            {
                'name': 'Tacking',
                'workcenter_id': 1,  # Welding Bay - 1 (Trent)
                'time_mode': 'auto',
                'time_cycle_manual': 0.0,
            },
            {
                'name': 'Welding',
                'workcenter_id': 5,  # Welding Bay - 5 (Nick)
                'time_mode': 'auto',
                'time_cycle_manual': 0.0,
            }
        ]
        operation_lines = [(0, 0, op) for op in operations]
        return operation_lines

    def get_default_cb_operations(self):
        # Define default operations for Core Barrels
        operations = [
            {
                'name': 'Rolling',
                'workcenter_id': 9,  # Plate Rollers - Rolling
                'time_mode': 'auto',
                'time_cycle_manual': 0.0,
            },
            {
                'name': 'Tacking',
                'workcenter_id': 1,  # Welding Bay - 1 (Trent)
                'time_mode': 'auto',
                'time_cycle_manual': 0.0,
            },
            {
                'name': 'Barrel Welding',
                'workcenter_id': 4,  # Welding Bay - 4 (Shayne)
                'time_mode': 'auto',
                'time_cycle_manual': 0.0,
            }
        ]
        operation_lines = [(0, 0, op) for op in operations]
        return operation_lines

    def get_default_operations(self):
        # Define default operations for Core Barrels
        operations = [
            {
                'name': 'Rolling',
                'workcenter_id': 9,  # Plate Rollers - Rolling
                'time_mode': 'auto',
                'time_cycle_manual': 0.0,
            },
            {
                'name': 'Tacking',
                'workcenter_id': 1,  # Welding Bay - 1 (Trent)
                'time_mode': 'auto',
                'time_cycle_manual': 0.0,
            },
            {
                'name': 'Core Barrel Welding',
                'workcenter_id': 4,  # Welding Bay - 4 (Shayne)
                'time_mode': 'auto',
                'time_cycle_manual': 0.0,
            }
        ]
        operation_lines = [(0, 0, op) for op in operations]
        return operation_lines
    
    def _get_detault_teeth_combination(self, attr, num):
        code = ''
        if attr == '22mm':
            code = 'BC05TB - 22mm Shank Teeth' if num > 0 else 'BHR174 - 22mm Round Tooth Holder'
        elif attr == '25mm':
            code = 'BTK03TB - 25mm Shank Teeth' if num > 0 else 'BHR167 - 25mm Round Tooth Holder'
        elif attr == '38/20mm':
            code = 'BKH105TB - 38/30mm Shank Teeth' if num > 0 else '38/30mm Round Tooth Holder'
        elif attr == 'CJ2':
            code = 'CJ2 Teeth' if num > 0 else 'CJ2 Tooth Holder'
        elif attr == 'WS20':
            code = 'WS20 Teeth' if num > 0 else 'WS20 Tooth Holder'
        else:
            code = 'unknown'
        return code

    def _extract_numeric_value(self, attribute_string):
        match = re.search(r'\d+mm', attribute_string)
        if match:
            return match.group()
        return None
    
    def _load_teeth_data(self, filename):
        filepath = get_module_resource('general_ledger', 'data', filename)
        data = {}
        with open(filepath, mode='r') as file:
            csv_reader = csv.DictReader(file)
            for row in csv_reader:
                diameter = int(row['Diameter'])
                data[diameter] = {
                    '22mm_teeth': int(row['22mm_teeth']),
                    '22mm_extra_teeth': int(row['22mm_extra_teeth']),
                    '25mm_teeth': int(row['25mm_teeth']),
                    '25mm_extra_teeth': int(row['25mm_extra_teeth']),
                    '38_30_teeth': int(row['38_30_teeth']),
                }
        return data

    def _get_teeth_for_diameter(self, dia, teeth_type, teeth_data):
        if dia in teeth_data:
            return teeth_data[dia].get(teeth_type, 0)
        
        # Initialize closest_diameter to handle cases where dia is smaller than any key
        closest_diameter = None
        sorted_diameters = sorted(teeth_data.keys())
        
        for d in sorted_diameters:
            if dia < d:
                break
            closest_diameter = d
        
        # If closest_diameter is still None, dia is smaller than the smallest key in teeth_data
        if closest_diameter is None:
            closest_diameter = sorted_diameters[0]
        
        return teeth_data[closest_diameter].get(teeth_type, 0)

    def _compute_number_of_teeth(self, attributes, diameter, teeth_data):
        teeth_attribute = attributes.get('Teeth', '')
        teeth_type = self._normalize_attribute(teeth_attribute)
        dia_numeric = self._extract_diameter(diameter)
        if dia_numeric is not None:
            return self._get_teeth_for_diameter(dia_numeric, teeth_type, teeth_data)
        return 0

    def _normalize_attribute(self, attribute):
        # Normalize the attribute string by removing extra spaces and converting to lowercase
        return re.sub(r'\s+', ' ', attribute).strip().lower().replace(' ', '_').replace('/', '_')

    def _extract_diameter(self, diameter_string):
        # Use regular expression to find all numeric parts in the string
        match = re.search(r'\d+', diameter_string)
        if match:
            return int(match.group())
        return None
    
    def send_product_variant_creation_email(self, product):
        # Fetch the web base URL from system parameters
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')

        # Get the email template
        template_id = self.env.ref('general_ledger.product_variant_creation_email_template')
        
        if template_id:
            # Send the email with base_url in the context
            template_id.with_context(base_url=base_url).sudo().send_mail(product.id, force_send=True, email_values={
                'email_from': 'notifications@tebcoptyltd.odoo.com', 
                'email_to': 'von@tebco.com.au'
            })
