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

    @api.model_create_multi
    def create(self, vals_list):
        products = super().create(vals_list)
        for product in products:
            self._create_bom_for_cfa_auger(product)
            self._create_bom_for_high_tensile_adapter(product)
        return products

    def _create_bom_for_high_tensile_adapter(self, product):
        """
        Create a BOM component for High Tensile Adapter
        """
        if product.product_tmpl_id.name != 'High Tensile Adapter':
            return

        components = self._get_high_tensile_adapter_components(product)
        reference = product.display_name
        self._create_bom_components(product, reference, components)

    def _get_high_tensile_adapter_components(self):
        p_name = product.product_tmpl_id.name
        attributes = {attr.attribute_id.name: attr.name for attr in product.product_template_attribute_value_ids}
        from_drive = attributes.get('From', '')
        to_drive = attributes.get('To', '')
        type = attributes.get('Type', '')
        reducer = attributes.get('Reducer', '')
        lift_lug = attributes.get('Lift Lug', '')
        customization = attributes.get('Customization', '')
        components = []

        _drives = self._get_high_tensile_drive_head(from_drive, to_drive, type)
        _base_plate = self._get_eb_base_plate(drive_head)
        stiff_ring = "" #TODO: create a function that returns a list of items
        liftlug = re.match(r'^\s*(\d+(?:\.\d+)?)', lift_lug)
        lift_lug_qty = int(liftlug.group(1)) if _lift_lug else 0.0
        _liftlug = (f'Lift lug', lift_lug_qty) 
        _reducer = (reducer, 1)
        components = [
            _drives,
            _base_plate,
            _reducer,
            _stiff_ring,
            _liftlug
        ]

        return components

    def _create_bom_for_extension_bar(self, product):
        """
        Create a BOM component for Extension Bar
        """
        if product.product_tmpl_id.name != 'Extension Bar':
            return

        components = self._get_extension_bar_components(product)
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

        if type == 'Telescopic Inner' and drive_head in inner_outer_items:
            components = self._get_eb_telescopic_inner_components(type, drive_head, length, center_tube, stubb, lift_lug)
        elif type == 'Telescopic Outer' and drive_head in inner_outer_items:
            components = self._get_eb_telescopic_outer_components(type, drive_head, length, center_tube, stubb, lift_lug)
        elif type == 'Rigid':
            components = self._get_eb_rigid_components(type, drive_head, length, center_tube, stubb, lift_lug)

        return components

    def _get_eb_telescopic_inner_components(self, type, drive_head, length, c_tube, stubb, lift_lug):
        center_tube = self._get_extension_bar_center_tube(type, c_tube, drive_head, stubb)
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
        center_tube = self._get_extension_bar_center_tube(type, c_tube, drive_head, stubb)
        gusset = self._get_extension_bar_center_tube_gusset(drive_head, c_tube)
        _lift_lug = re.match(r'^\s*(\d+(?:\.\d+)?)', lift_lug)
        lift_lug_qty = int(_lift_lug.group(1)) if _lift_lug else 0.0
        liftlug = (f'Lift lug', lift_lug_qty)
        lst = [
                (drive_head, 1),
                center_tube,
                (stubb, 1),
                (gusset, 1),
                liftlug
            ]
        components = [x for x in lst if x[0]]
        return components

    def _get_eb_rigid_components(self, type, drive_head, length, c_tube, stubb, lift_lug):
        d_head_ears = self._get_bp_dhead_ears(drive_head)
        center_tube = self._get_extension_bar_center_tube(type, c_tube, drive_head, stubb)
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
                (gusset, 1),
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
