from odoo import api, fields, models
import re
from odoo.modules.module import get_module_resource
from odoo.exceptions import ValidationError
import logging
import math
_logger = logging.getLogger(__name__)


class ProductProduct(models.Model):
    _inherit = "product.product"

    @api.model_create_multi
    def create(self, vals_list):
        products = super().create(vals_list)
        for product in products:
            self._create_bom_for_extension_bar(product)
            self._create_bom_for_high_tensile_adapter(product)
            self._create_bom_for_cfa_auger(product)
        return products

    def _create_bom_for_cfa_auger(self, product):
        """
            Create a BOM component for CFA Auger
        """
        if product.product_tmpl_id.name != 'CFA Auger':
            return

        components = self._get_cfa_auger_components(product)

        if not components:
            return 

        reference = product.display_name
        self._create_cfa_bom_components(product, reference, components)

    def _get_cfa_auger_components(self, product):
        """
            param: product.template to get the product attributes 
            return: a list of items to create bom components 
        """
        components = []
        p_name = product.product_tmpl_id.name
        attributes = {attr.attribute_id.name: attr.name for attr in product.product_template_attribute_value_ids}
        cfa_type = attributes.get('CFA Type', '')
        lead_auger_type = attributes.get('Lead Auger Type', '')
        diameter = attributes.get('Auger Diameter', '')
        overall_length = attributes.get('Overall Length', '')
        drive_head = attributes.get('CFA Drive Head', '')

        center_tube = attributes.get('Centre Tube', '')
        inner_pipe = attributes.get('Inner Pipe', '')
        rotation = attributes.get('Rotation', '')
        teeth = attributes.get('Teeth', '')
        pilot = attributes.get('Pilot', '')
        
        lead_flight = attributes.get('>Lead Flight', '')
        carrier_flight = attributes.get('>Carrier Flight', '')
        coupling_flight = attributes.get('>Coupling Flight (N/A if same with carrier)', '')
        non_lead_flight = attributes.get('* NON-STOCKED Lead Flight', '')
        non_carrier_flight = attributes.get('* NON-STOCKED Carrier Flight', '')
        non_coupling_flight = attributes.get('* NON-STOCKED Coupling Flight (N/A if same with carrier)', '')

        if cfa_type == 'Lead':
            if lead_auger_type in ['Taper Rock', 'Dual Rock', 'Clay/Shale']:
                    components = self._get_cfa_dual_taper_rock(cfa_type, lead_auger_type, diameter, overall_length, drive_head, center_tube, inner_pipe, rotation, teeth, pilot, lead_flight, carrier_flight, coupling_flight, non_lead_flight, non_carrier_flight, non_coupling_flight)
            elif lead_auger_type in ['ZED 25mm', 'ZED 32mm', 'ZED 40mm', 'ZED 50mm']: 
                components = self._get_cfa_zed(cfa_type, lead_auger_type, diameter, overall_length, drive_head, center_tube, inner_pipe, rotation, teeth, pilot, lead_flight, carrier_flight, coupling_flight, non_lead_flight, non_carrier_flight, non_coupling_flight)
            elif lead_auger_type == 'Single Cut':
                components = self._get_cfa_single_cut(cfa_type, lead_auger_type, diameter, overall_length, drive_head, center_tube, inner_pipe, rotation, teeth, pilot, lead_flight, carrier_flight, coupling_flight, non_lead_flight, non_carrier_flight, non_coupling_flight)
            else:
                return []
        elif cfa_type == 'Intermediate':
            components = self._get_cfa_intermediate(cfa_type, lead_auger_type, diameter, overall_length, drive_head, center_tube, inner_pipe, rotation, teeth, pilot, lead_flight, carrier_flight, coupling_flight, non_lead_flight, non_carrier_flight, non_coupling_flight)
        else:
            # Extension (for couplings only)
            components = self._get_cfa_extension(cfa_type, lead_auger_type, diameter, overall_length, drive_head, center_tube, inner_pipe, rotation, teeth, pilot, lead_flight, carrier_flight, coupling_flight, non_lead_flight, non_carrier_flight, non_coupling_flight)
        return components

    def _get_cfa_dual_taper_rock(self, cfa_type, lead_type, diameter, overall_length, drive_head, center_tube, inner_pipe, rotation, teeth, pilot, lead_flight, carrier_flight, coupling_flight, non_lead_flight, non_carrier_flight, non_coupling_flight):
        # Get all items for at3
        ctube_at3 = self._get_cfa_coupling_ctube_at3(center_tube, inner_pipe)
        elbow = ctube_at3[0][0] # Get the elbow item for mapping of height 
        zed_center = "" # leave empty; only applicable for zed type
        base_coupling_at2 = self._get_cfa_coupling_dhead_at2(cfa_type, lead_type, drive_head, center_tube, inner_pipe, pilot, zed_center, elbow, overall_length)
        # Get the items & qty for lead, carrier, and coupling flights
        carrier_qty, coupling_qty = self._get_cfa_carrier_coupling_flight_qty(cfa_type, lead_flight, carrier_flight, coupling_flight, non_lead_flight, non_carrier_flight, non_coupling_flight, overall_length, drive_head)
        non_stock_flight = self._get_cfa_non_stock_flight(cfa_type, lead_type, diameter, center_tube, non_lead_flight, non_carrier_flight, non_coupling_flight, rotation, carrier_qty, coupling_qty)
        stock_flight = self._get_cfa_stock_flight(cfa_type, lead_type, diameter, lead_flight, carrier_flight, coupling_flight, carrier_qty, coupling_qty)
        # Return: Items for lead, carrier, and coupling flights
        non_or_stock_flights_at4 = self._get_cfa_non_or_stock_flights(non_stock_flight, stock_flight)
        # Get all the teeth and pilot items
        teeth_and_pilot_at5 = self._get_cfa_coupling_teeth_at5(diameter, center_tube, lead_type, teeth, pilot)

        # We combine all components based on lead type 
        combination = [
            *base_coupling_at2,
            *non_or_stock_flights_at4,
            *teeth_and_pilot_at5,
            *ctube_at3,
        ]

        # We filter components to exclude non-values
        components = [r for r in combination if r[0]]

        return components

    def _get_cfa_intermediate(self, cfa_type, lead_type, diameter, overall_length, drive_head, center_tube, inner_pipe, rotation, teeth, pilot, lead_flight, carrier_flight, coupling_flight, non_lead_flight, non_carrier_flight, non_coupling_flight):
        # Get all items for at3
        ctube_at3 = self._get_cfa_coupling_ctube_at3(center_tube, inner_pipe)
        elbow = ctube_at3[0][0] # Get the elbow item for mapping of height 
        zed_center = "" # leave empty; only applicable for zed type
        base_coupling_at2 = self._get_cfa_coupling_dhead_at2(cfa_type, lead_type, drive_head, center_tube, inner_pipe, pilot, zed_center, elbow, overall_length)
        # Get the items & qty for lead, carrier, and coupling flights
        carrier_qty, coupling_qty = self._get_cfa_carrier_coupling_flight_qty(cfa_type, lead_flight, carrier_flight, coupling_flight, non_lead_flight, non_carrier_flight, non_coupling_flight, overall_length, drive_head)
        non_stock_flight = self._get_cfa_non_stock_flight(cfa_type, lead_type, diameter, center_tube, non_lead_flight, non_carrier_flight, non_coupling_flight, rotation, carrier_qty, coupling_qty)
        stock_flight = self._get_cfa_stock_flight(cfa_type, lead_type, diameter, lead_flight, carrier_flight, coupling_flight, carrier_qty, coupling_qty)
        # Return: Items for lead, carrier, and coupling flights
        non_or_stock_flights_at4 = self._get_cfa_non_or_stock_flights(non_stock_flight, stock_flight)
        s_ring = ctube_at3[3] if len(ctube_at3) <= 2 else (None, 0)
        s_ring_lst = [s_ring]
        # We combine all components based on lead type 
        combination = [
            *base_coupling_at2,
            *non_or_stock_flights_at4,
            *s_ring_lst,
        ]

        # We filter components to exclude non-values
        components = [r for r in combination if r[0]]

        return components

    def _get_cfa_extension(self, cfa_type, lead_type, diameter, overall_length, drive_head, center_tube, inner_pipe, rotation, teeth, pilot, lead_flight, carrier_flight, coupling_flight, non_lead_flight, non_carrier_flight, non_coupling_flight):
        # Get all items for at3
        ctube_at3 = self._get_cfa_coupling_ctube_at3(center_tube, inner_pipe)
        elbow = ctube_at3[0][0] # Get the elbow item for mapping of height 
        zed_center = "" # leave empty; only applicable for zed type
        base_coupling_at2 = self._get_cfa_coupling_dhead_at2(cfa_type, lead_type, drive_head, center_tube, inner_pipe, pilot, zed_center, elbow, overall_length)
        # We combine all components based on lead type 
        s_ring = ctube_at3[3] if len(ctube_at3) <= 2 else (None, 0)
        s_ring_lst = [s_ring]

        combination = [
            *base_coupling_at2,
            *s_ring_lst,
        ]

        # We filter components to exclude non-values
        components = [r for r in combination if r[0]]

        return components

    def _get_cfa_zed(self, cfa_type, lead_type, diameter, overall_length, drive_head, center_tube, inner_pipe, rotation, teeth, pilot, lead_flight, carrier_flight, coupling_flight, non_lead_flight, non_carrier_flight, non_coupling_flight):
        # Get all items for at3
        ctube_at3 = self._get_cfa_coupling_ctube_at3(center_tube, inner_pipe)
        elbow = ctube_at3[0][0] # Get the elbow item for mapping of height 
        zed_center = "" # leave empty; only applicable for zed type
        base_coupling_at2 = self._get_cfa_coupling_dhead_at2(cfa_type, lead_type, drive_head, center_tube, inner_pipe, pilot, zed_center, elbow, overall_length)
        # Get the items & qty for lead, carrier, and coupling flights
        carrier_qty, coupling_qty = self._get_cfa_carrier_coupling_flight_qty(cfa_type, lead_flight, carrier_flight, coupling_flight, non_lead_flight, non_carrier_flight, non_coupling_flight, overall_length, drive_head)
        non_stock_flight = self._get_cfa_non_stock_flight(cfa_type, lead_type, diameter, center_tube, non_lead_flight, non_carrier_flight, non_coupling_flight, rotation, carrier_qty, coupling_qty)
        stock_flight = self._get_cfa_stock_flight(cfa_type, lead_type, diameter, lead_flight, carrier_flight, coupling_flight, carrier_qty, coupling_qty)
        # Return: lead, carrier, and coupling flights
        non_or_stock_flights_at4 = self._get_cfa_non_or_stock_flights(non_stock_flight, stock_flight)
        # Get all the teeth and pilot items
        teeth_and_pilot_at5 = self._get_cfa_coupling_teeth_at5(diameter, center_tube, lead_type, teeth, pilot)
        # Zed center items
        zed_center_at6 = self._get_cfa_zed_center_at6(center_tube, diameter)

        # We combine all components based on lead type 
        combination = [
            *base_coupling_at2,
            *non_or_stock_flights_at4,
            *teeth_and_pilot_at5,
            *ctube_at3,
            *zed_center_at6,
        ]

        # We filter components to exclude non-values
        components = [r for r in combination if r[0]]

        return components

    def _get_cfa_single_cut(self, cfa_type, lead_type, diameter, overall_length, drive_head, center_tube, inner_pipe, rotation, teeth, pilot, lead_flight, carrier_flight, coupling_flight, non_lead_flight, non_carrier_flight, non_coupling_flight):
        # Get all items for at3
        ctube_at3 = self._get_cfa_coupling_ctube_at3(center_tube, inner_pipe)
        elbow = ctube_at3[0][0] # Get the elbow item for mapping of height 
        zed_center = "" # leave empty; only applicable for zed type
        base_coupling_at2 = self._get_cfa_coupling_dhead_at2(cfa_type, lead_type, drive_head, center_tube, inner_pipe, pilot, zed_center, elbow, overall_length)
        # Get the items & qty for lead, carrier, and coupling flights
        carrier_qty, coupling_qty = self._get_cfa_carrier_coupling_flight_qty(cfa_type, lead_flight, carrier_flight, coupling_flight, non_lead_flight, non_carrier_flight, non_coupling_flight, overall_length, drive_head)
        non_stock_flight = self._get_cfa_non_stock_flight(cfa_type, lead_type, diameter, center_tube, non_lead_flight, non_carrier_flight, non_coupling_flight, rotation, carrier_qty, coupling_qty)
        stock_flight = self._get_cfa_stock_flight(cfa_type, lead_type, diameter, lead_flight, carrier_flight, coupling_flight, carrier_qty, coupling_qty)
        # Return: lead, carrier, and coupling flights
        non_or_stock_flights_at4 = self._get_cfa_non_or_stock_flights(non_stock_flight, stock_flight)
        # Get all the teeth and pilot items
        teeth_and_pilot_at5 = self._get_cfa_coupling_teeth_at5(diameter, center_tube, lead_type, teeth, pilot)
        dia = int(re.search(r"\d+\.?\d*", diameter).group())
        id_value = int(re.search(r'ID(\d+)', lead_flight).group(1)) if re.search(r'ID(\d+)', lead_flight) else ""
        profiling = [(f"Profiling - CFA Single Cut {dia}mm Diameter x Flight - OD280 ID{id_value} P330 T32 RH", 1)]
        # We combine all components based on lead type 
        combination = [
            *base_coupling_at2,
            *non_or_stock_flights_at4,
            *teeth_and_pilot_at5,
            *ctube_at3,
            *profiling,
        ]
        # We filter components to exclude non-values
        components = [r for r in combination if r[0]]
    
        return components

    def _create_bom_for_high_tensile_adapter(self, product):
        """
            Create a BOM component for High Tensile Adapter
        """
        if product.product_tmpl_id.name != 'High Tensile Adapter':
            return

        components = self._get_high_tensile_adapter_components(product)
        # raise ValidationError(f"tensile.. {components}")
        reference = product.display_name
        self._create_bom_components(product, reference, components)

    def _get_high_tensile_adapter_components(self, product):
        p_name = product.product_tmpl_id.name
        attributes = {attr.attribute_id.name: attr.name for attr in product.product_template_attribute_value_ids}
        from_drive = attributes.get('From', '')
        to_drive = attributes.get('To', '')
        type = attributes.get('Type', '')
        reducer = attributes.get('Reducer', '')
        lift_lug = attributes.get('Lift Lug', '')
        customization = attributes.get('Customization', '')
        components = []

        _drive1, _drive2 = self._get_high_tensile_drive_head(from_drive, to_drive, type)
        _base_plate = self._get_eb_base_plate(from_drive)
        _stiff_ring = self._get_stiffening_ring_for_tensile_adapter(from_drive, _drive2, type)
        liftlug = re.match(r'^\s*(\d+(?:\.\d+)?)', lift_lug)
        lift_lug_qty = int(liftlug.group(1)) if liftlug else 0.0
        _liftlug = (f'Lift lug', lift_lug_qty) 
        _reducer = (reducer, 1)
        _none = (None, 0)
        lst = [
            _drive1,
            _drive2,
            _base_plate or _none,
            _reducer or _none,
            _stiff_ring or _none,
            _liftlug or _none
        ]
        components = [x for x in lst if x[0]]
        return components

    def _create_bom_for_extension_bar(self, product):
        """
        Create a BOM component for Extension Bar
        """
        if product.product_tmpl_id.name != 'Extension Bar':
            return

        components = self._get_extension_bar_components(product)
        # raise ValidationError(f"bar.. {components}")
        reference = product.display_name
        self._create_bom_components(product, reference, components)

    def _get_extension_bar_components(self, product):
        p_name = product.product_tmpl_id.name
        attributes = {attr.attribute_id.name: attr.name for attr in product.product_template_attribute_value_ids}
        type = attributes.get('Type', '')
        drive_head = attributes.get('Drive Head', '')
        length = attributes.get('Length', '')
        center_tube = attributes.get('Centre Tube', '')
        stubb = attributes.get('Stub', '')
        lift_lug = attributes.get('Lift Lug', '')
        customization = attributes.get('Customization', '')
        components = []

        if type == 'Telescopic Inner':
            components = self._get_eb_telescopic_inner_components(type, drive_head, length, center_tube, stubb, lift_lug)
        elif type == 'Telescopic Outer':
            components = self._get_eb_telescopic_outer_components(type, drive_head, length, center_tube, stubb, lift_lug)
        elif type == 'Rigid':
            components = self._get_eb_rigid_components(type, drive_head, length, center_tube, stubb, lift_lug)

        return components

    def _get_eb_telescopic_inner_components(self, type, drive_head, length, c_tube, stubb, lift_lug):
        center_tube = self._get_extension_bar_center_tube(type, c_tube, drive_head, stubb, length)
        collar1 = 'Extension Bar Collar - 75mm' if c_tube == '4140 75mm square billet' else ''
        collar2 = 'Extension Bar Collar - 100mm' if c_tube == '4140 100mm square billet' else ''
        collar = collar1 if collar1 else collar2
        _lift_lug = re.match(r'^\s*(\d+(?:\.\d+)?)', lift_lug)
        lift_lug_qty = int(_lift_lug.group(1)) if _lift_lug else 0.0
        liftlug = (f'Lift lug', lift_lug_qty) 
        lst = [
                (drive_head, 1),
                center_tube,
                (collar, 1),
                liftlug
            ]
        components = [x for x in lst if x[0]]
        return components

    def _get_eb_telescopic_outer_components(self, type, drive_head, length, c_tube, stubb, lift_lug):
        center_tube = self._get_extension_bar_center_tube(type, c_tube, drive_head, stubb, length)
        gusset = self._get_extension_bar_center_tube_gusset(drive_head, c_tube)
        _lift_lug = re.match(r'^\s*(\d+(?:\.\d+)?)', lift_lug)
        lift_lug_qty = int(_lift_lug.group(1)) if _lift_lug else 0.0
        liftlug = (f'Lift lug', lift_lug_qty)
        lst = [
                (drive_head, 1),
                center_tube,
                (stubb, 1),
                gusset, 
                liftlug
            ]
        components = [x for x in lst if x[0]]
        return components

    def _get_eb_rigid_components(self, type, drive_head, length, c_tube, stubb, lift_lug):
        d_head_ears = self._get_bp_dhead_ears(drive_head)
        center_tube = self._get_extension_bar_center_tube(type, c_tube, drive_head, stubb, length)
        gusset = self._get_extension_bar_center_tube_gusset(drive_head, c_tube)
        base_plate = self._get_eb_base_plate(drive_head)
        collar1 = 'Extension Bar Collar - 75mm' if c_tube == '4140 75mm square billet' else ''
        collar2 = 'Extension Bar Collar - 100mm' if c_tube == '4140 100mm square billet' else ''
        collar = collar1 if collar1 else collar2
        _lift_lug = re.match(r'^\s*(\d+(?:\.\d+)?)', lift_lug)
        lift_lug_qty = int(_lift_lug.group(1)) if _lift_lug else 0.0
        liftlug = (f'Lift lug', lift_lug_qty)
        lst = [
                (drive_head, 1),
                (d_head_ears),
                center_tube,
                (stubb, 1),
                gusset,
                liftlug,
                (base_plate, 1)
            ]
        components = [x for x in lst if x[0]]
        return components

    def _get_eb_base_plate(self, drive_head):
        DRIVE_HEAD = {
            'Drive Head - 100mm Square': '100 Base Plate - 100mm Head',
            'Drive Head - 110mm Square': '190 Base Plate - 110mm Head',
            'Drive Head - 130mm Square': 'Base Plate - 130mm Head',
            'Drive Head - 130mm Square DIGGA': 'Base Plate - 130mm Head',
            'Drive Head - 150mm Square': 'Base Plate - 150mm Head',
            'Drive Head - 150mm Square IMT': 'Base Plate - 150mm Head',
            'Drive Head - 200mm Square Bauer': 'Base Plate - 200mm Head',
            'Drive Head - 200mm Square MAIT': 'Base Plate - 200mm Head'
        }
        return (DRIVE_HEAD.get(drive_head, ''), 1)

    def _get_extension_bar_center_tube(self, type, center_tube, drive_head, stubb, length):
        """Compute center tube quantity for Extension Bar based on type, drive head, and stub"""

        exclude_inner_tube = ['4140 75mm square billet', '4140 100mm square billet']
        DRIVE_HEAD_HEIGHTS = {
            'Drive Head - 75mm Square': 75,
            'Drive Head - 100mm Square': 100,
            'Drive Head - 110mm Square': 190,
            'Drive Head - 130mm Square': 130,
            'Drive Head - 130mm Square DIGGA': 130,
            'Drive Head - 150mm Square': 130,
            'Drive Head - 150mm Square IMT': 130,
            'Drive Head - 200mm Square Bauer': 190,
            'Drive Head - 200mm Square MAIT': 190,
        }
        STUB_HEIGHTS = {
            '75mm Square Extension Bar Stubb': 115,
            '100mm square Stubb': 150,
            '110mm Drive Stubb': 90,
            '130mm Square Stubb': 200,
            '130mm Stubb - Digga': 150,
            '150mm Stubb': 220,
            '150mm IMT Stubb': 215,
            '200mm Square Stubb': 350,
            '200mm MAIT Square Stub': 350,
        }
        length_str = re.search(r'(\d+(\.\d+)?)\s*m', length.lower())
        length_no = float(length_str.group(1)) if length_str else 0.0
        # Convert mm to meters
        head_height = DRIVE_HEAD_HEIGHTS.get(drive_head, 0) / 1000.0
        stub_height = STUB_HEIGHTS.get(stubb, 0) / 1000.0

        if type == 'Telescopic Inner' and center_tube in exclude_inner_tube:
            qty = length_no - head_height
            return (center_tube, round(qty, 2))

        elif type in ['Telescopic Outer', 'Rigid'] and center_tube not in exclude_inner_tube:
            qty = length_no - head_height - stub_height
            return (center_tube, round(qty, 2))

        else:
            return (None, 0)

    def _get_extension_bar_center_tube_gusset(self, drive_head, center_tube):
        """
        Returns the gusset component based on drive head and center shaft.
    
        Args:
            drive_head (str): The name of the drive head.
            centre_tube (str): The name of the center shaft.
    
        Returns:
            tuple: (component_name, quantity), e.g., ("Gusset - 130mm Drive 273mm Tube", 1)
        """
        dhead_100_110_mm = ['Drive Head - 100mm Square', 'Drive Head - 110mm Square']
        dhead_130_mm = ['Drive Head - 130mm Square', 'Drive Head - 130mm Square DIGGA']
        dhead_150_mm = ['Drive Head - 150mm Square', 'Drive Head - 150mm Square IMT']
        dhead_200_mm = ['Drive Head - 200mm Square Bauer', 'Drive Head - 200mm Square MAIT']
    
        gusset_map = {
            'dhead_100_110_mm': {
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
                'Pipe - OD168mm WT11mm': "Gusset - 100mm Drive 170mm Tube",
                'Pipe - OD219mm WT12.7mm': "Gusset - 100mm Drive 219mm Tube",
            },
            'dhead_130_mm': {
                'Hollow Bar - OD150mm ID120mm': "Gusset - 130mm Drive 150mm Tube",
                'Hollow Bar - OD152mm WT 26mm': "Gusset - 130mm Drive 150mm Tube",
                'Hollow Bar - OD152mm WT 33.5mm': "Gusset - 130mm Drive 150mm Tube",
                'Hollow Bar - OD168mm WT 21.5mm': "Gusset - 130mm Drive 170mm Tube",
                'Hollow Bar - OD168mm WT 29mm': "Gusset - 130mm Drive 170mm Tube",
                'Hollow Bar - OD170mm ID140mm': "Gusset - 130mm Drive 170mm Tube",
                'Hollow Bar - OD180 ID150': "Gusset - 130mm Drive 170mm Tube",
                'Hollow bar - OD200 ID150': "Gusset - 130mm Drive 170mm Tube",
                'Hollow Bar - OD219mm WT 25mm': "Gusset - 130mm Drive 219mm Tube",
                'Hollow bar - OD273mm WT14': "Gusset - 130mm Drive 273mm Tube",
                'Hollow Bar - OD273mm WT 25mm': "Gusset - 130mm Drive 273mm Tube",
                'Hollow Bar - OD273mm WT 32mm': "Gusset - 130mm Drive 273mm Tube",
                'Hollow Bar - OD323mm WT25mm': "Gusset - 130mm Drive 323mm Tube",
                'Hollow Bar - OD323mm WT30mm': "Gusset - 130mm Drive 323mm Tube",
                'Hollow Bar - OD356 ID306': "Gusset - 130mm Drive 323mm Tube",
                'Hollow bar - OD457mm T35mm': "Gusset - 130mm Drive 323mm Tube",
                'Hollow bar - OD457mm T25mm': "Gusset - 130mm Drive 323mm Tube",
                'Pipe - OD168mm WT11mm': "Gusset - 130mm Drive 170mm Tube",
                'Pipe - OD219mm WT12.7mm': "Gusset - 130mm Drive 219mm Tube",
                'Pipe - OD273mm WT12.7mm': "Gusset - 130mm Drive 273mm Tube",
                'Pipe - OD323mm WT12.7mm': "Gusset - 130mm Drive 323mm Tube",
                'Pipe - OD355mm WT12.7mm': "Gusset - 130mm Drive 323mm Tube",
                'Pipe - OD457mm WT15.9mm': "Gusset - 130mm Drive 323mm Tube",
            },
            'dhead_150_mm': {
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
                'Pipe - OD168mm WT11mm': "Gusset - 150mm Drive 170mm Tube",
                'Pipe - OD219mm WT12.7mm': "Gusset - 150mm Drive 170mm Tube",
                'Pipe - OD273mm WT12.7mm': "Gusset - 150mm Drive 273mm Tube",
                'Pipe - OD323mm WT12.7mm': "Gusset - 150mm Drive 273mm Tube",
                'Pipe - OD355mm WT12.7mm': "Gusset - 150mm Drive 273mm Tube",
                'Pipe - OD457mm WT15.9mm': "Gusset - 150mm Drive 273mm Tube",
            },
            'dhead_200_mm': {
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
                'Pipe - OD168mm WT11mm': "Gusset - 200mm Drive 170mm Tube",
                'Pipe - OD219mm WT12.7mm': "Gusset - 200mm Drive 170mm Tube",
                'Pipe - OD273mm WT12.7mm': "Gusset - 200mm Drive 273mm Tube",
                'Pipe - OD323mm WT12.7mm': "Gusset - 200mm Drive 273mm Tube",
                'Pipe - OD355mm WT12.7mm': "Gusset - 200mm Drive 273mm Tube",
                'Pipe - OD457mm WT15.9mm': "Gusset - 200mm Drive 273mm Tube",
            }
        }

        d_head = ''
        if drive_head in dhead_100_110_mm:
            d_head = 'dhead_100_110_mm'
        elif drive_head in dhead_130_mm:
            d_head = 'dhead_130_mm'
        elif drive_head in dhead_150_mm:
            d_head = 'dhead_150_mm'
        elif drive_head in dhead_200_mm:
            d_head = 'dhead_200_mm'
    
        gusset_label = gusset_map.get(d_head, {}).get(center_tube)
        return (gusset_label, 1) if gusset_label else (None, 0)

    def _get_high_tensile_drive_head(self, from_drive, to_drive, type):
        """
        Maps drive head combinations to actual component names based on a predefined dictionary.
    
        Args:
            from_drive (str): e.g. "XHD5 Coupling"
            to_drive (str): e.g. "HD4 Coupling"
            type (str): One of ["Female to Female", "Male to Male", "Female to Male", "Male to Female"]
    
        Returns:
            list of tuple: [(component_name, qty), ...]
        """
    
        female_map = {
            "3.5\" API Coupling": "3.5\" API Female coupling",
            "2\" Hex Coupling": "2\" Hex Coupling - Female",
            "3\" Hex Coupling": "3\" Hex Coupling - Female",
            "35TM Coupling": "35TM Coupling - Female",
            "53TM Coupling": "53TM Coupling - Female",
            "Carrendeena 5\" Coupling": "Carrendeena 5\" Coupling - Female",
            "Casagrande 5\" Coupling": "Casagrande 5\" Coupling - Female",
            "HD4 Coupling": "HD4 Coupling - Female",
            "HD5 Coupling": "HD5 Coupling - Female",
            "25XHD5 Coupling": "25XHD5 Coupling - Female",
            "XHD5 Coupling": "XHD5 Coupling - Female",
            "XHD5 Mini Coupling": "XHD5 Mini Coupling - Female",
            "Llamada Coupling": "Llamada Coupling - Female",
            "MAIT175 Coupling": "MAIT175 Coupling - Female",
            "MAIT200 Coupling": "MAIT200 Coupling - Female",
            "SW80 Coupling": "TB80/SW80 Coupling - Female",
            "SW110 Coupling": "SW110 Female Coupling",
            "SW150 EMDE Coupling": "SW150 Bauer Female Octagon Coupling",
            "SW150 Bauer Coupling": "SW150 EMDE Female",
            "SW175 Coupling": "SW175 Coupling - Female",
            "SW200 Coupling": "SW200 Female Coupling",
            "SW250 Coupling": "SW250 Female Coupling",
            "TB46 Coupling": "TB46 Coupling - Female",
            "65mm Round Drive": "Drive Head - 65mm Round",
            "65mm Square Drive": "Drive Head - 65mm Square",
            "75mm Square Drive": "Drive Head - 75mm Square",
            "100mm Square Drive": "Drive Head - 100mm Square",
            "110mm Square Drive": "Drive Head - 110mm Square",
            "130mm Square Drive": "Drive Head - 130mm Square",
            "130mm Square Drive DIGGA": "Drive Head - 130mm Square DIGGA",
            "150mm Square Drive": "Drive Head - 150mm Square",
            "150mm Square Drive IMT": "Drive Head - 150mm Square IMT",
            "200mm Square Drive Bauer": "Drive Head - 200mm Square Bauer",
            "200mm Square Drive MAIT": "Drive Head - 200mm Square MAIT",
            "150mm AT Hex": "Drive Head - 150mm AT Hex",
            "Terex 2.5\" Hex H250": "Terex Hex Hub Female 2.5\" (H250)"
        }
    
        male_map = {
            "3.5\" API Coupling": "3.5\" API Male coupling",
            "2\" Hex Coupling": "2\" Hex Coupling - Male Male Joiner",
            "3\" Hex Coupling": "3\" Hex Coupling - Male Male Joiner",
            "35TM Coupling": "35TM Coupling - Male",
            "53TM Coupling": "53TM Coupling - Male",
            "Carrendeena 5\" Coupling": "Carrendeena 5\" Coupling - Male",
            "Casagrande 5\" Coupling": "Casagrande 5\" Coupling - Male",
            "HD4 Coupling": "HD4 Coupling - Male",
            "HD5 Coupling": "HD5 Coupling - Male",
            "25XHD5 Coupling": "25XHD5 Coupling - Male",
            "XHD5 Coupling": "XHD5 Coupling - Male",
            "XHD5 Mini Coupling": "XHD5 Mini Coupling - Male",
            "Llamada Coupling": "Llamada Coupling - Male",
            "MAIT175 Coupling": "MAIT175 Coupling - Male",
            "MAIT200 Coupling": "MAIT200 Coupling - Male",
            "SW80 Coupling": "TB80/SW80 Coupling - Male",
            "SW110 Coupling": "SW110 Male Coupling",
            "SW150 EMDE Coupling": "SW150 Bauer Male Coupling",
            "SW150 Bauer Coupling": "SW150 EMDE Male",
            "SW175 Coupling": "SW175 Coupling - male",
            "SW200 Coupling": "SW200 Male Coupling",
            "SW250 Coupling": "SW250 Male Coupling",
            "TB46 Coupling": "TB46 Coupling - Male",
            "75mm Square Drive": "75mm Square Extension Bar Stubb",
            "100mm Square Drive": "100mm square Stubb",
            "110mm Square Drive": "110mm Drive Stubb",
            "130mm Square Drive": "130mm Stubb",
            "130mm Square Drive DIGGA": "130mm Stubb - Digga",
            "150mm Square Drive": "150mm Stubb",
            "150mm Square Drive IMT": "150mm IMT Stubb",
            "200mm Square Drive Bauer": "200mm Bauer Drive Stubb",
            "200mm Square Drive MAIT": "200mm MAIT Square Stub",
        }
    
        type_map = {
            'Female to Female': (female_map.get(from_drive), female_map.get(to_drive)),
            'Male to Male': (male_map.get(from_drive), male_map.get(to_drive)),
            'Female to Male': (female_map.get(from_drive), male_map.get(to_drive)),
            'Male to Female': (male_map.get(from_drive), female_map.get(to_drive)),
        }
    
        from_component, to_component = type_map.get(type, (None, None))
    
        result = []
        if from_component:
            result.append((from_component, 1))
        if to_component:
            result.append((to_component, 1))
    
        return result

    def _get_stiffening_ring_for_tensile_adapter(self, drive_from, drive_to, coupling_type):
        """
        Determines the correct stiffening ring component for high tensile adapters.
    
        Args:
            drive_from (str): e.g. "150mm Square Drive"
            drive_to (str): e.g. "130mm Stubb"
            coupling_type (str): e.g. "Female to Male", "Male to Male", etc.
    
        Returns:
            tuple or None: e.g. ('[75 Drive Stiffening Collar] Stiffening Ring - 130mm Stubb', 1)
        """
    
        stiffening_matrix = {
            '100mm Square Drive': {
                '75mm Stubb': True, '100mm Stubb': False, '110mm Stubb': False,
                '130mm Stubb': False, '150mm Stubb': False, '75mm Head': True,
            },
            '110mm Square Drive': {
                '75mm Stubb': True, '100mm Stubb': True, '110mm Stubb': False,
                '130mm Stubb': False, '150mm Stubb': False, '75mm Head': True,
            },
            '130mm Square Drive': {
                '75mm Stubb': True, '100mm Stubb': True, '110mm Stubb': True,
                '130mm Stubb': False, '150mm Stubb': False, '75mm Head': True,
            },
            '130mm Square Drive DIGGA': {
                '75mm Stubb': True, '100mm Stubb': True, '110mm Stubb': True,
                '130mm Stubb': False, '150mm Stubb': False, '75mm Head': True,
            },
            '150mm Square Drive': {
                '75mm Stubb': True, '100mm Stubb': True, '110mm Stubb': True,
                '130mm Stubb': True, '150mm Stubb': False, '75mm Head': True,
            },
            '150mm Square Drive IMT': {
                '75mm Stubb': True, '100mm Stubb': True, '110mm Stubb': True,
                '130mm Stubb': True, '150mm Stubb': True, '75mm Head': True,
            },
            '200mm Square Drive Bauer': {
                '75mm Stubb': True, '100mm Stubb': True, '110mm Stubb': True,
                '130mm Stubb': True, '150mm Stubb': True, '75mm Head': True,
            },
            '200mm Square Drive MAIT': {
                '75mm Stubb': True, '100mm Stubb': True, '110mm Stubb': True,
                '130mm Stubb': True, '150mm Stubb': True, '75mm Head': True,
            },
        }
    
        ring_label_map = {
            '75mm Stubb': 'Stiffening Ring - 75mm Stubb',
            '100mm Stubb': 'Stiffening Ring - 100mm Stubb',
            '110mm Stubb': 'Stiffening Ring - 110mm Stubb',
            '130mm Stubb': 'Stiffening Ring - 130mm Stubb',
            '150mm Stubb': 'Stiffening Ring - 150mm Stubb',
            '75mm Head': 'Stiffening Ring - 75mm Head',
        }
    
        available = stiffening_matrix.get(drive_from)
        if not available:
            return None
    
        # Preferred stub if 'Stubb' is explicitly mentioned in drive_to
        preferred_stub = None
        d_to, _ = drive_to
        if 'stubb' in d_to.lower():
            match = re.search(r'(\d{2,3})mm', d_to)
            if match:
                preferred_stub = f"{match.group(1)}mm Stubb"

        # Priority fallback order for stub selection
        drive2_priority_map = {
            'Female to Male': ['150mm Stubb', '130mm Stubb', '110mm Stubb', '100mm Stubb', '75mm Stubb'],
            'Male to Male': ['150mm Stubb', '130mm Stubb', '110mm Stubb', '100mm Stubb', '75mm Stubb'],
            'Female to Female': ['75mm Head'],
            'Male to Female': ['75mm Head'],
        }
        # If explicitly requested stub (e.g. 130mm Stubb) is available, return it
        if preferred_stub and available.get(preferred_stub):
            return (f"{ring_label_map[preferred_stub]}", 1)

        # Otherwise fallback to first available option in priority list
        for stub in drive2_priority_map.get(coupling_type, []):
            if available.get(stub):
                return (f"{ring_label_map[stub]}", 1)
    
        return None

    def _create_cfa_bom_components(self, product, reference, components):
        bom_lines = []
        attributes = {attr.attribute_id.name: attr.name for attr in product.product_template_attribute_value_ids}
        cfa_type = attributes.get('CFA Type', '')
        uom_meter = self.env.ref('uom.product_uom_meter', raise_if_not_found=False)
        unit = self.env.ref('uom.product_uom_unit', raise_if_not_found=False)

        for component_name, qty in components:
            uom = uom_meter if any(x in component_name for x in ['Hollow Bar', 'Pipe', 'Pilot Support']) else unit
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
        operation_ids = self._get_default_cfa_work_center(product, cfa_type)
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

    def _get_default_cfa_work_center(self, product, type):
        operations = []

        if type == 'Lead':
            operations = [
                {
                    'name': 'Flight Pressing',
                    'workcenter_id': 8,  # Flight Press
                    'time_mode': 'auto',
                    'time_cycle_manual': 0.0,
                },
                {
                    'name': 'Tacking',
                    'workcenter_id': 1,  # Tacking
                    'time_mode': 'auto',
                    'time_cycle_manual': 0.0,
                },
                {
                    'name': 'Flight Welding',
                    'workcenter_id': 11,  # Flight Welding
                    'time_mode': 'auto',
                    'time_cycle_manual': 0.0,
                },
                {
                    'name': 'Teeth Setting',
                    'workcenter_id': 12,  # Teeth Setting
                    'time_mode': 'auto',
                    'time_cycle_manual': 0.0,
                },
                {
                    'name': 'Teeth Welding',
                    'workcenter_id': 13,  # Teeth Welding
                    'time_mode': 'auto',
                    'time_cycle_manual': 0.0,
                }
            ]
        elif type == 'Intermediate':
            operations = [
                {
                    'name': 'Flight Pressing',
                    'workcenter_id': 8,  # Flight Press
                    'time_mode': 'auto',
                    'time_cycle_manual': 0.0,
                },
                {
                    'name': 'Tacking',
                    'workcenter_id': 1,  # Tacking
                    'time_mode': 'auto',
                    'time_cycle_manual': 0.0,
                },
                {
                    'name': 'Flight Welding',
                    'workcenter_id': 11,  # Flight Welding
                    'time_mode': 'auto',
                    'time_cycle_manual': 0.0,
                }
            ]
        else:
            operations = [
                {
                    'name': 'Tacking',
                    'workcenter_id': 1,  # Tacking
                    'time_mode': 'auto',
                    'time_cycle_manual': 0.0,
                },
                {
                    'name': 'Welding',
                    'workcenter_id': 4,  # Welding
                    'time_mode': 'auto',
                    'time_cycle_manual': 0.0,
                }
            ]

        operation_lines = [(0, 0, op) for op in operations]
        return operation_lines

    def _get_cfa_zed_center_at6(self, center_tube, diameter):
        dia = int(re.search(r"\d+\.?\d*", diameter).group())
        center_tube_map = {
            "Hollow Bar - OD150mm ID120mm ZED Centre 150mm": "ZED Centre 150mm",
            "Hollow Bar - OD152mm WT 26mm ZED Centre 150mm": "ZED Centre 150mm",
            "Hollow Bar - OD152mm WT 33.5mm ZED Centre 150mm": "ZED Centre 150mm",
            "Hollow Bar - OD168mm WT 21.5mm ZED Centre 168mm": "ZED Centre 168mm",
            "Hollow Bar - OD168mm WT 29mm ZED Centre 168mm": "ZED Centre 168mm",
            "Hollow Bar - OD170mm ID140mm ZED Centre 168mm": "ZED Centre 168mm",
            "Hollow Bar - OD219mm WT 25mm ZED Centre 219mm": "ZED Centre 219mm",
            "hollow bar - OD273mm WT14 ZED Centre 273mm": "ZED Centre 273mm",
            "Hollow Bar - OD273mm WT 25mm ZED Centre 273mm": "ZED Centre 273mm",
            "Hollow Bar - OD273mm WT 32mm ZED Centre 273mm": "ZED Centre 273mm",
            "Pipe - OD168mm WT11mm ZED Centre 168mm": "ZED Centre 168mm",
            "Pipe - OD219mm WT12.7mm ZED Centre 219mm": "ZED Centre 219mm",
            "Pipe - OD273mm WT12.7mm ZED Centre 273mm": "ZED Centre 273mm",
        }
        zed_center = [(center_tube_map.get(center_tube, ''), 1 )]
        zed_flight = [('ZED Flight Stiffener (Under 600mm)', 2)] if dia < 600 else [('ZED Flight Stiffener (600mm+)', 2)]

        return zed_center + zed_flight

    def _get_cfa_coupling_teeth_at5(self, diameter, center_tube, lead_type, teeth, pilot):
        """
            Return: a list of teeth items
        """
        dia = int(re.search(r"\d+\.?\d*", diameter).group())
        od_match = re.search(r'OD(\d+)', center_tube)
        c_tube_od = int(od_match.group(1)) if od_match else ''

        if lead_type in ['Dual Rock', 'Taper Rock']:
            return self._get_dual_taper_teeth(dia, teeth, pilot)
        elif lead_type in ['ZED 50mm', 'ZED 40mm', 'ZED 32mm', 'ZED 25mm']:
            return self._get_zed_teeth(dia, teeth, c_tube_od)
        elif lead_type == 'Clay/Shale':
            return self._get_clay_shale_teeth(dia, teeth, pilot)
        elif lead_type == 'Single Cut':
            return self._get_single_cut_teeth(dia, teeth, pilot)
        else:
            return (None, 0)

    def _get_single_cut_teeth(self, diameter, teeth, pilot):
        dia = diameter
        def _get_teeth_qty(od, mm):
            qty = (dia - od - 10) / mm
            return round(qty)

        teeth1_qty = _get_teeth_qty(150, 150)
        teeth2_qty = _get_teeth_qty(200, 116)
        
        teeth_map = {
            '38/30 BFZ162 Teeth': [
                ('BFZ162 (FZ70) 38/30mm step shank flat Teeth', teeth1_qty),
                ('Phaser Teeth Holder', teeth1_qty)
            ],
            'FZ54 Teeth': [
                ('FZ54 Mini Bauer Teeth', teeth2_qty),
                ('Mini Bauer Holder', teeth2_qty)
            ]
        }
        pilot_map = {
            '25mm Teeth Pilot': [
                ('Pilot Support - 75mm Square', 1),
                ('End Cap - Suit 75mm Square Pilot Support', 1),
                ('BTK03TB - 25mm Shank Teeth', 10),
                ('BHR167 - 25mm Round Tooth Holder', 6)
            ],
            '38/30 Teeth Pilot': [
                ('Rock Auger Pilot - 38/30mm Shank 100mm Square', 1),
                ('Pilot Support - 100mm Square', 1),
                ('End Cap - Suit 100mm Square Pilot Support', 1),
                ('BKH105TB - 38/30mm Shank Teeth', 10),
                ('BHR38 - 38/30mm Block Tooth Holder', 6)
            ]
        }

        _teeth = teeth_map.get(teeth, [])
        _pilot = pilot_map.get(pilot, [])

        return _teeth + _pilot

    def _get_clay_shale_teeth(self, diameter, teeth, pilot):
        dia = diameter
        def _get_teeth_qty(od, mm):
            qty = (dia - od - 10) / mm
            rounded = round(qty)
            return rounded if rounded % 2 == 0 else rounded + 1

        teeth1_qty = _get_teeth_qty(78, 80)
        teeth2_qty = _get_teeth_qty(150, 150)
        teeth3_qty = _get_teeth_qty(200, 116)
        
        teeth_map = {
            'AR150 Teeth': [
                ('AR150 Teeth', teeth1_qty),
                ('C87B Holder - suit AR150', teeth1_qty)
            ],
            '38/30 BFZ162 Teeth': [
                ('BFZ162 (FZ70) 38/30mm step shank flat Teeth', teeth2_qty),
                ('Phaser Teeth Holder', teeth2_qty)
            ],
            'FZ54 Teeth': [
                ('FZ54 Mini Bauer Teeth', teeth3_qty),
                ('Mini Bauer Holder', teeth3_qty)
            ]
        }
        pilot_map = {
            'Hex Auger Torque Fishtail Pilot': [
                    ('Auger Pilot - Hex Auger Torque Fishtail', 1),
                ('Pilot Support - Hex', 1),
                ('End Cap - Suit Hex Pilot Support', 1)
            ],
            '25mm Teeth Pilot': [
                ('Rock Auger Pilot - 25mm Shank 75mm square', 1),
                ('Pilot Support - 75mm Square', 1),
                ('End Cap - Suit 75mm Square Pilot Support', 1),
                ('BTK03TB - 25mm Shank Teeth', 4)
            ],
            '38/30 Teeth Pilot': [
                ('Rock Auger Pilot - 38/30mm Shank 100mm Square', 1),
                ('Pilot Support - 100mm Square', 1),
                ('End Cap - Suit 100mm Square Pilot Support', 1),
                ('BKH105TB - 38/30mm Shank Teeth', 4)
            ]
        }
        _teeth = teeth_map.get(teeth, [])
        _pilot = pilot_map.get(pilot, [])

        return _teeth + _pilot

    def _get_zed_teeth(self, diameter, teeth, c_tube_od):
        dia = diameter
        od = c_tube_od

        def _get_teeth_qty(mm):
            qty = (dia - od - 10) / mm * 2
            rounded = round(qty)
            return rounded if rounded % 2 == 0 else rounded + 1

        teeth_map = {
            '22mm BC05 Teeth': [
                ('BC05 - 22mm Shank Teeth BETEK', _get_teeth_qty(42)),
                ('BHR176 - 22mm Block Tooth Holder', _get_teeth_qty(42)),
                ('BA13 - Weld on Button Carbide', _get_teeth_qty(42) / 2)
            ],
            '25mm BTK03 Teeth': [
                ('BTK03TB - 25mm Shank Teeth', _get_teeth_qty(44)),
                ('BHR31 - 25mm Block Tooth Holder', _get_teeth_qty(44)),
                ('BA13 - Weld on Button Carbide', _get_teeth_qty(42) / 2)
            ],
            '38/30 BKH105 Teeth': [
                ('BKH105TB - 38/30mm Shank Teeth', _get_teeth_qty(66)),
                ('BHR38 - 38/30mm Block Tooth Holder', _get_teeth_qty(66)),
                ('BA13 - Weld on Button Carbide', _get_teeth_qty(42) / 2)
            ]
        }
        return teeth_map.get(teeth, [])

    def _get_dual_taper_teeth(self, dia, teeth, pilot):        
        def _get_teeth_qty(mm):
            qty = (dia - 70 - 10) / mm + 8
            rounded = round(qty)
            return rounded if rounded % 2 == 1 else rounded + 1

        teeth_map = {
            '19mm BK17 Teeth': [
                ('BSK17 - 19.4mm Shank Teeth', _get_teeth_qty(40)),
                ('BHR164 - 19.4mm Block Holder', _get_teeth_qty(40) - 4)
            ],
            '22mm BC86 Teeth': [
                ('BC86 - 22mm Shank Teeth BETEK', _get_teeth_qty(42)),
                ('BHR176 - 22mm Block Tooth Holder', _get_teeth_qty(42) - 4)
            ],
            '22mm BC05 Teeth': [
                ('BC05 - 22mm Shank Teeth BETEK', _get_teeth_qty(42)),
                ('BHR176 - 22mm Block Tooth Holder', _get_teeth_qty(42) - 4)
            ],
            '25mm BTK03 Teeth': [
                ('BTK03TB - 25mm Shank Teeth', _get_teeth_qty(44)),
                ('BHR31 - 25mm Block Tooth Holder', _get_teeth_qty(44) - 4)
            ],
            '38/30 BKH105 Teeth': [
                ('BKH105TB - 38/30mm Shank Teeth', _get_teeth_qty(66)),
                ('BHR38 - 38/30mm Block Tooth Holder', _get_teeth_qty(66) - 4)
            ]
        }
        pilot_map = {
            '19mm Teeth Pilot': [
                ('Rock Pilot suit 19mm Teeth 44mm Hex - RH / LH', 1),
                ('Pilot Support - Hex', 1),
                ('End Cap - Suit Hex Pilot Support', 1)
            ],
            '22mm Teeth Pilot': [
                ('Rock Pilot suit 22mm Teeth 44mm Hex - RH / LH', 1),
                ('Pilot Support - Hex', 1),
                ('End Cap - Suit Hex Pilot Support', 1)
            ],
            '25mm Teeth Pilot': [
                ('Rock Auger Pilot - 25mm Shank 75mm square', 1),
                ('Pilot Support - 75mm Square', 1),
                ('End Cap - Suit 75mm Square Pilot Support', 1)
            ],
            '38/30 Teeth Pilot': [
                ('Rock Auger Pilot - 38/30mm Shank 100mm Square', 1),
                ('Pilot Support - 100mm Square', 1),
                ('End Cap - Suit 100mm Square Pilot Support', 1)
            ]
        }
        _teeth = teeth_map.get(teeth, [])
        _pilot = pilot_map.get(pilot, [])

        return _teeth + _pilot
        

    def _get_cfa_coupling_ctube_at3(self, center_tube, inner_tube):
        """
            Return: list of items for Pipe Extension, Elbow, Spacer Ring, CFA Plug, CFA Holder
        """
        
        if center_tube == 'Hollow Bar - OD100mm ID80mm':
            return [
                ('75NB elbow - Xstrong long radius', 1),
            ]
        elif center_tube == 'Hollow Bar - OD110 ID70':
            return [
                ('75NB elbow - Xstrong long radius', 1),
            ]
        elif center_tube == 'Hollow Bar - OD128mm WT 11.5mm':
            return [
                ('75NB elbow - Xstrong long radius', 1),
                ('105mm CFA Plug', 1),
                ('105mm CFA Plug Holder', 1),
            ]
        elif center_tube == 'Hollow Bar - OD150mm ID120mm':
            return [
                ('75NB elbow - Xstrong long radius', 1),
                ('105mm CFA Plug', 1),
                ('105mm CFA Plug Holder', 1),
                ('Pipe Extension - Hollow Bar - OD150mm ID120mm', 1),
            ]
        elif center_tube == 'Hollow Bar - OD152mm WT 26mm':
            return [
                ('75NB elbow - Xstrong long radius', 1),
                ('Hollow Bar - OD150mm ID120mm', 0.25),
                ('105mm CFA Plug', 1),
                ('105mm CFA Plug Holder', 1)
            ]
        elif center_tube == 'Hollow Bar - OD152mm WT 33.5mm':
            return [
                ('75NB elbow - Xstrong long radius', 1),
                ('105mm CFA Plug', 1),
                ('105mm CFA Plug Holder', 1),
            ]
        elif center_tube == 'Hollow Bar - OD168mm WT 21.5mm':
            return [
                ('105NB elbow - Xstrong long radius', 1),
                ('Hollow Bar - OD170mm ID140mm', 0.25),
                ('105mm CFA Plug', 1),
                ('105mm CFA Plug Holder', 1)
            ]
        elif center_tube == 'Hollow Bar - OD168mm WT 29mm':
            return [
                ('105NB elbow - Xstrong long radius', 1),
                ('105mm CFA Plug', 1),
                ('105mm CFA Plug Holder', 1),
            ]
        elif center_tube == 'Hollow Bar - OD219mm WT 25mm' and inner_tube == 'Pipe - OD141mm WT6.6mm':
            return [
                ('125NB elbow - Xstrong long radius', 1),
                ('125mm CFA Plug', 1),
                ('125mm CFA Plug Holder', 1),
                ('273 CFA Spacer Ring (218mm OD 143mm ID 10mm)', 3),
            ]
        elif center_tube == 'Hollow Bar - OD273mm WT14' and inner_tube == 'Pipe - OD141mm WT6.6mm':
            return [
                ('125NB elbow - Xstrong long radius', 1),
                ('125mm CFA Plug', 1),
                ('125mm CFA Plug Holder', 1),
                ('273 CFA Spacer Ring (218mm OD 143mm ID 10mm)', 4),
            ]
        elif center_tube == 'Hollow Bar - OD273mm WT 25mm' and inner_tube == 'Pipe - OD141mm WT6.6mm':
            return [
                ('125NB elbow - Xstrong long radius', 1),
                ('125mm CFA Plug', 1),
                ('125mm CFA Plug Holder', 1),
                ('273 CFA Spacer Ring (218mm OD 143mm ID 10mm)', 6),
            ]
        elif center_tube == 'Hollow Bar - OD273mm WT 32mm' and inner_tube == 'Pipe - OD141mm WT6.6mm':
            return [
                ('125NB elbow - Xstrong long radius', 1),
                ('125mm CFA Plug', 1),
                ('125mm CFA Plug Holder', 1),
                ('273 CFA Spacer Ring (218mm OD 143mm ID 10mm)', 8),
            ]
        elif center_tube == 'Hollow Bar - OD323mm WT25mm' and inner_tube == 'Pipe - OD219mm WT 25mm':
            return [
                ('125NB elbow - Xstrong long radius', 1),
                ('125mm CFA Plug', 1),
                ('125mm CFA Plug Holder', 1),
                ('323 CFA Spacer Ring (270mm OD 143mm ID 10mm)', 10),
            ]
        elif center_tube == 'Hollow Bar - OD323mm WT30mm' and inner_tube == 'Pipe - OD219mm WT 25mm':
            return [
                ('125NB elbow - Xstrong long radius', 1),
                ('125mm CFA Plug', 1),
                ('125mm CFA Plug Holder', 1),
                ('323 CFA Spacer Ring (270mm OD 143mm ID 10mm)', 12),
            ]
        elif center_tube and inner_tube == 'Pipe - OD88.9mm WT5.4mm':
            return [
                ('75NB elbow - Xstrong long radius', 1),
            ]
        elif center_tube and inner_tube == 'Pipe - OD114mm WT6.0mm':
            return [
                ('105NB elbow - Xstrong long radius', 1),
                ('105mm CFA Plug ', 1),
                ('105mm CFA Plug Holder')
            ]
        elif center_tube and inner_tube == 'Hollow Bar - OD168mm WT 21.5mm ':
            return [
                ('125NB elbow - Xstrong long radius', 1),
                ('125mm CFA Plug', 1),
                ('125mm CFA Plug Holder', 1)
            ]
        else:
            return [(None, 0)]

    def _get_cfa_coupling_dhead_at2(self, cfa_type, lead_type, drive_head, center_tube, inner_tube, pilot_support, zed_center, elbow, overall_length):
        # Parse the pipe extension to get the length
        def _get_pipe_extension_length(center_tube):
            pipe_extension = ['Hollow Bar - OD152mm WT 26mm', 'Hollow Bar - OD168mm WT 21.5mm']
            if center_tube not in pipe_extension:
                return 0

            od_match = re.search(r'OD(\d+)', center_tube)
            id_match = re.search(r'ID(\d+)', center_tube)
            extension_length = 0
            if od_match and id_match:
                od = int(od_match.group(1))
                id_ = int(id_match.group(1))
                extension_length = (od - id_) / 2
            return extension_length

        # Return items for the base plate
        def _get_base_plate(dhead):
            base = ""
            if dhead == 'Drive Head - 100mm Square':
                base = 'Base Plate - 100mm Head'
            elif dhead == 'Drive Head - 130mm Square':
                base = 'Base Plate - 130mm Head'
            elif dhead == 'Drive Head - 130mm Square DIGGA':
                base = 'Base Plate - 130mm Head'
            else:
                base
            return base

        def _get_center_tube_qty(cfa_type, center_tube, o_length_mm, female_height, male_height, pilot_supp_height, b_plate, zed_cent_height):
            """
            Return center tube qty based on a formula.
            Final output is in meters (rounded up to 1 decimal place).
            """
            with_pipe_extension = ['Hollow Bar - OD152mm WT 26mm', 'Hollow Bar - OD168mm WT 21.5mm']
            excluded_lead_type = ['Dual Rock', 'Taper Rock', 'Clay/Shale', 'Single Cut']
        
            pipe_extension_length = 0
            if center_tube in with_pipe_extension:
                pipe_extension_length = _get_pipe_extension_length(center_tube)
        
            if cfa_type == 'Lead':
                if lead_type in excluded_lead_type:
                    base_subtract = female_height + pilot_supp_height
                else:
                    base_subtract = female_height + zed_cent_height
                c_qty = o_length_mm - base_subtract - pipe_extension_length - b_plate
            elif cfa_type == 'Intermediate':
                c_qty = o_length_mm - female_height - male_height - b_plate
            else:
                c_qty = o_length_mm - female_height - male_height
            # Convert to meters 
            c_qty_meters = round(c_qty / 1000.0, 2)
            return c_qty_meters

        def _get_inner_tube_qty(cfa_type, inner_tube, female_height, female_slot, male_height, male_slot, pilot_supp_height, zed_cent_height, elbow_height, b_plate, o_length_mm):
            """
            Return inner tube qty based on a formula.
            Final output is in meters (rounded up to 1 decimal place).
            """
            reg_lead_type = ['Dual Rock', 'Taper Rock', 'Clay/Shale', 'Single Cut']
        
            if cfa_type == 'Lead':
                if lead_type in reg_lead_type:
                    _logger.info(f"{o_length_mm}, {female_height}, {pilot_supp_height}, {elbow_height}, {b_plate}, {female_slot}")
                    in_qty = o_length_mm - female_height - pilot_supp_height - elbow_height - b_plate - female_slot
                else:
                    in_qty = o_length_mm - female_height - zed_cent_height - elbow_height - b_plate - female_slot
            elif cfa_type == 'Intermediate':
                in_qty = o_length_mm - female_height - male_height - b_plate - female_slot - male_slot
            else:
                in_qty = o_length_mm - female_height - male_height - female_slot - male_slot
        
            c_qty_meters = round(in_qty / 1000.0, 2)
            return c_qty_meters

        pilot_supp_map = {
            "Pilot Support - Hex": 75,
            "Pilot Support - 75mm Square": 70,
            "Pilot Support - 100mm Square": 100,
            "Pipe - OD101mm WT4.0mm": 70
        } 
        zed_center_map = {
            "ZED Centre 150mm": 133.5,
            "ZED Centre 168mm": 147.5,
            "ZED Centre 219mm": 163,
            "ZED Centre 273mm": 163
        }
        elbow_map = {
            "125NB elbow - Xstrong long radius": 260,
            "105NB elbow - Xstrong Long radius": 209,
            "90NB elbow - Xstrong Long radius": 184,
            "75NB elbow - Xxstrong Long radius": 158
        }
        base_plate_map = {
            "Drive Head - 100mm Square": 25,
            "Drive Head - 130mm Square": 32,
            "Drive Head - 130mm Square DIGGA": 32
        }
        female = self._get_cfa_female_coupling(drive_head)
        male = self._get_cfa_male_coupling(drive_head)

        # Get the height for overall length
        o_length = re.search(r'(\d+)\s*mm', overall_length)
        o_length_mm = int(o_length.group(1)) if o_length else 0

        # Get the height and slot for male and female
        female_height = female[1]
        female_slot = female[2]
        male_height = male[1]
        male_slot = male[2]

        # Get the height for pilot, zed, elbow, and drive head
        _pilot_support = ""
        if pilot_support in ['19mm Teeth Pilot', '22mm Teeth Pilot']:
            _pilot_support = 'Pilot Support - Hex'
        elif pilot_support == '25mm Teeth Pilot':
            _pilot_support = 'Pilot Support - 75mm Square'
        else:
            _pilot_support = 'Pilot Support - 100mm Square'
            
        pilot_supp = pilot_supp_map.get(_pilot_support, 0)
        zed_cent = zed_center_map.get(zed_center, 0)
        elbow = elbow_map.get(elbow, 0)
        b_plate = base_plate_map.get(drive_head, 0)

        # Get the qty of the center tube and the inner tube
        cent_tube_qty = _get_center_tube_qty(cfa_type, center_tube, o_length_mm, female_height, male_height, pilot_supp, b_plate, zed_cent)
        inn_tube_qty = _get_inner_tube_qty(cfa_type, inner_tube, female_height, female_slot, male_height, male_slot, pilot_supp, zed_cent, elbow, b_plate, o_length_mm)

        # list of item components
        _none = (None, 0)
        c_female = (female[0], 1)
        c_male = (male[0], 1) if cfa_type in ['Intermediate', 'Extension'] else _none
        base_plate = (_get_base_plate(drive_head), 1)
        cent_tube = (center_tube, cent_tube_qty)
        inn_tube = (inner_tube, inn_tube_qty)

        components = [
            c_female or _none,
            c_male,
            base_plate or _none,
            cent_tube or _none,
            inn_tube or _none
        ]
        return components

    def _get_cfa_female_coupling(self, drive_head):
        female_map = {
            "3.5\" API Coupling": ["3.5\" API Female coupling", 142, 0],
            "2\" Hex Coupling": ["2\" Hex Coupling - Female", 155, 0],
            "3\" Hex Coupling": ["3\" Hex Coupling - Female", 155, 0],
            "35TM Coupling": ["35TM Coupling - Female", 289, 15],
            "53TM Coupling": ["53TM Coupling - Female", 250, 15],
            "Carrendeena 5\" Coupling": ["Carrendeena 5\" Coupling - Female", 230, 0],
            "Casagrande 5\" Coupling": ["Casagrande 5\" Coupling - Female", 230, 15],
            "HD4 Coupling": ["HD4 Coupling - Female", 220, 0],
            "HD5 Coupling": ["HD5 Coupling - Female", 220, 0],
            "25XHD5 Coupling": ["25XHD5 Coupling - Female", 365, 15],
            "XHD5 Coupling": ["XHD5 Coupling - Female", 242, 15],
            "XHD5 Mini Coupling": ["XHD5 Mini Coupling - Female", 242, 15],
            "Llamada Coupling": ["Llamada Coupling - Female", 279, 0],
            "MAIT175 Coupling": ["MAIT175 Coupling - Female", 240, 15],
            "MAIT200 Coupling": ["MAIT200 Coupling - Female", 304, 15],
            "SW80 Coupling": ["TB80/SW80 Coupling - Female", 148, 0],
            "SW110 Coupling": ["SW110 Female Coupling", 170, 0],
            "SW150 EMDE Coupling": ["SW150 Bauer Female Octagon Coupling", 258, 0],
            "SW150 Bauer Coupling": ["SW150 EMDE Female", 225, 0],
            "SW175 Coupling": ["SW175 Coupling - Female", 415, 15],
            "SW200 Coupling": ["SW200 Female Coupling", 446, 15],
            "SW250 Coupling": ["SW250 Female Coupling", 585, 15],
            "TB46 Coupling": ["TB46 Coupling - Female", 250, 15],
            "Drive Head - 75mm Square": ["Drive Head - 75mm Square", 150, 0],
            "Drive Head - 100mm Square": ["Drive Head - 100mm Square", 175, 0],
            "Drive Head - 130mm Square": ["Drive Head - 130mm Square", 260, 0],
            "Drive Head - 130mm Square DIGGA": ["Drive Head - 130mm Square DIGGA", 260, 0]
        }
        return female_map.get(drive_head, [])

    def _get_cfa_male_coupling(self, drive_head):
        male_map = {
            "3.5\" API Coupling": ["3.5\" API Male coupling", 50, 0],
            "2\" Hex Coupling": ["2\" Hex Coupling - Male Male Joiner", 155, 0],
            "3\" Hex Coupling": ["3\" Hex Coupling - Male Male Joiner", 155, 0],
            "35TM Coupling": ["35TM Coupling - Male", 85, 15],
            "53TM Coupling": ["53TM Coupling - Male", 85, 15],
            "Carrendeena 5\" Coupling": ["Carrendeena 5\" Coupling - Male", 55, 0],
            "Casagrande 5\" Coupling": ["Casagrande 5\" Coupling - Male", 60, 15],
            "HD4 Coupling": ["HD4 Coupling - Male", 85, 0],
            "HD5 Coupling": ["HD5 Coupling - Male", 80, 0],
            "25XHD5 Coupling": ["25XHD5 Coupling - Male", 70, 15],
            "XHD5 Coupling": ["XHD5 Coupling - Male", 58.5, 15],
            "XHD5 Mini Coupling": ["XHD5 Mini Coupling - Male", 58, 15],
            "Llamada Coupling": ["Llamada Coupling - Male", 41, 0],
            "MAIT175 Coupling": ["MAIT175 Coupling - Male", 65, 15],
            "MAIT200 Coupling": ["MAIT200 Coupling - Male", 55, 15],
            "SW80 Coupling": ["TB80/SW80 Coupling - Male", 20, 0],
            "SW110 Coupling": ["SW110 Male Coupling", 35, 0],
            "SW150 EMDE Coupling": ["SW150 Bauer Male Coupling", 50, 0],
            "SW150 Bauer Coupling": ["SW150 EMDE Male", 100, 0],
            "SW175 Coupling": ["SW175 Coupling - male", 85, 15],
            "SW200 Coupling": ["SW200 Male Coupling", 145, 15],
            "SW250 Coupling": ["SW250 Male Coupling", 100, 15],
            "TB46 Coupling": ["TB46 Coupling - Male", 75, 15],
            "Drive Head - 75mm Square": ["75mm Square Adapter Stubb", 40, 0],
            "Drive Head - 100mm Square": ["100mm square Stubb", 50, 0],
            "Drive Head - 130mm Square": ["130mm Stubb", 40, 0],
            "Drive Head - 130mm Square DIGGA": ["130mm Square DIGGA", 40, 0]
        }
        return male_map.get(drive_head, [])

    def _get_cfa_non_stock_flight(self, cfa_type, lead_type, diameter, center_tube, non_le_flight, non_ca_flight, non_co_flight, rotation, carrier_qty, coupling_qty):
        """
        Returns a list of tuples (flight_string, quantity) for non-stock lead and carrier flights.
        """
        def _get_non_stock_flight(non_stock_flight, diameter, center_tube, rotation):
            """ Builds a non-stocked flight string from the given values."""
            if not non_stock_flight:
                return ""
            # Step 1: OD based on auger diameter
            od_value = f"OD{diameter - 10}"
            
            # Step 2: ID based on center_tube table
            od_match = re.search(r'OD(\d+)', center_tube)
            id_str = str(od_match.group(1)) if od_match else ''
            id_value = f"ID{id_str}"

            # Step 3-5: Parse non_stock_flight to get P, T, R
            pitch, thickness, turns = self._parse_flight_values(non_stock_flight)
            pitch = f"P{pitch}"
            thickness = f"T{thickness}"
            turns = f"R{turns}"

            # Setp 6: Rotation
            f_rotation = "RH" if rotation == 'Right Hand Rotation' else "LH"
            
            return f"Flight - {od_value} {id_value} {pitch} {thickness} {f_rotation} {turns} - Non-Stocked"

        # Build flight strings for lead, carrier, and coupling
        lead_flight_str = _get_non_stock_flight(non_le_flight, diameter, center_tube, rotation)
        carrier_flight_str = _get_non_stock_flight(non_ca_flight, diameter, center_tube, rotation)
        coupling_flight_str = _get_non_stock_flight(non_co_flight, diameter, center_tube, rotation)

        # Get the qty of the lead flight 
        lead_qty = self._get_cfa_lead_flight_qty(cfa_type, lead_type)
        
        _none = (None, 0)

        lst = [
            (lead_flight_str, lead_qty) or _none,
            (carrier_flight_str, carrier_qty) or _none,
            (coupling_flight_str, coupling_qty) or _none
        ]
        components = [r for r in lst if r[0]]
        return components

    def _get_cfa_stock_flight(self, cfa_type, lead_type, diameter, lead_flight, carrier_flight, coupling_flight, carrier_qty, coupling_qty):
        """
        Return a list of items for stock flight with qty
        """
        lead_qty = self._get_cfa_lead_flight_qty(cfa_type, lead_type)
        _none = (None, 0)
        
        lst = [
            (lead_flight, lead_qty) or _none,
            (carrier_flight, carrier_qty) or _none,
            (coupling_flight, coupling_qty) or _none
        ]
        component = [x for x in lst if x[0]]
        return component

    def _get_cfa_non_or_stock_flights(self, non_stock, stock):
        """
        Merge stock and non-stock flights, excluding any where the label is None.
        Returns only valid (non-None) entries.
        """
        stock = stock or []
        non_stock = non_stock or []

        result = []

        for item, qty in non_stock:
            if item:
                result.append((item, qty))

        for item, qty in stock:
            if item:
                result.append((item, qty))

        _logger.info(result)
        return result

    def _get_cfa_lead_flight_qty(self, cfa_type, lead_type):
        lead_qty = 0
        if cfa_type == 'Lead' and lead_type in ['Clay/Shale', 'Blade', 'Single Cut']:
            lead_qty = 1
        else:
            lead_qty = 2
        return lead_qty

    def _get_cfa_carrier_coupling_flight_qty(self, cfa_type, lead_flight, carrier_flight, coupling_flight, n_lead_flight, n_carrier_flight, n_coupling_flight, overall_length, drive_head):
        """ 
        We calculate the stock or non-stock carrier flight qty
        """
        def _get_pitch(res):
            p_match = re.search(r'P(\d+)', res)
            r_match = re.search(r'R(\d+\.\d+)', res)
            
            pitch = int(p_match.group(1)) if p_match else 1
            turns = float(r_match.group(1)) if r_match else 1
            
            return pitch, turns

        l_pitch = l_no_turn = ca_pitch = ca_no_turn = co_pitch = co_no_turn = 0

        # Prefer the most complete case first
        if coupling_flight and carrier_flight or coupling_flight and carrier_flight and (lead_flight or n_lead_flight):
            if lead_flight:
                l_pitch, l_no_turn = _get_pitch(lead_flight)
            else:
                l_pitch, l_no_turn = _get_pitch(n_lead_flight)
            co_pitch, co_no_turn = _get_pitch(coupling_flight)
            ca_pitch, ca_no_turn = _get_pitch(carrier_flight)
        
        # Then handle cases without coupling
        elif (lead_flight and carrier_flight):
            l_pitch, l_no_turn = _get_pitch(lead_flight)
            ca_pitch, ca_no_turn = _get_pitch(carrier_flight)
        
        elif (n_lead_flight and n_carrier_flight):
            l_pitch, l_no_turn = _get_pitch(n_lead_flight)
            ca_pitch, ca_no_turn = _get_pitch(n_carrier_flight)
        
        elif (lead_flight and n_carrier_flight):
            l_pitch, l_no_turn = _get_pitch(lead_flight)
            ca_pitch, ca_no_turn = _get_pitch(n_carrier_flight)
        
        elif (carrier_flight and n_lead_flight):
            l_pitch, l_no_turn = _get_pitch(n_lead_flight)
            ca_pitch, ca_no_turn = _get_pitch(carrier_flight)

        # Get the height of female coupling
        female = self._get_cfa_female_coupling(drive_head)
        female_height = female[1]

        co_qty = self._get_cfa_coflight_qty(female_height, co_pitch, co_no_turn, coupling_flight, n_coupling_flight)
        ca_qty = self._get_cfa_caflight_qty(cfa_type, l_pitch, l_no_turn, ca_pitch, ca_no_turn, co_qty, overall_length)

        return ca_qty, co_qty

    def _get_cfa_caflight_qty(self, cfa_type, l_pitch, l_no_turn, ca_pitch, ca_no_turn, co_qty, overall_length):
        ol_str = re.search(r'(\d+)\s*mm', overall_length)
        o_length = int(ol_str.group(1)) if ol_str else 0

        if cfa_type == "Lead":
            if ca_pitch * ca_no_turn != 0:
                qty = (o_length - (l_pitch * l_no_turn)) / (ca_pitch * ca_no_turn)
                qty = math.floor(qty * 2) / 2
                return qty
            return 0

        if cfa_type == 'Intermediate':
            if ca_pitch * ca_no_turn != 0:
                qty = (o_length / (ca_pitch * ca_no_turn)) - co_qty
                qty = math.ceil(qty * 2) / 2  # round-up to the nearest 0.5
                return qty
            return 0
    
        return 0

    def _get_cfa_coflight_qty(self, female_height, co_pitch, co_no_turn, coupling_flight, n_coupling_flight):
        if not coupling_flight and not n_coupling_flight:
            return 0

        qty = female_height / (co_pitch * co_no_turn)
        qty = round(qty * 2) / 2
        return qty
