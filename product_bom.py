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

        attributes = {attr.attribute_id.name: attr.name for attr in product.product_template_attribute_value_ids}

        cfa_type = attributes.get('Type', '')
        lead_type = attributes.get('Lead Auger', '')
        diameter = attributes.get('Auger Diameter', '')
        drive_head = attributes.get('CFA Drive Head', '')
        o_length = attributes.get('Length', '')
        rotation = attributes.get('Rotation', '')
        teeth = attributes.get('Teeth', '')
        pilot = attributes.get('Pilot', '')

        centre_tube = attributes.get('Centre Tube', '')
        inner_tube = attributes.get('Inner Tube', '')

        l_flight_od = attributes.get('Lead Flight OD', '')
        l_flight_pt = attributes.get('Lead Flight Pitch', '')
        c_flight_od = attributes.get('Carrier Flight OD', '')
        c_flight_pt = attributes.get('Carrier Flight Pitch', '')
        coupling_flight_id = attributes.get('Coupling Flight ID', '')
        override_bom  = attributes.get('Override BOM', '')

        diameter = int(re.search(r"\d+\.?\d*", diameter).group())

        if cfa_type == 'Lead':
            if lead_type in ['Taper Rock', 'Dual Rock', 'Clay/Shale']:
                components = self._get_cfa_dual_taper_rock(cfa_type, lead_type, diameter, drive_head, o_length, rotation, teeth, pilot, centre_tube, inner_tube, l_flight_od, l_flight_pt, c_flight_od, c_flight_pt, coupling_flight_id, override_bom)
            elif lead_type in ['ZED 25mm', 'ZED 32mm', 'ZED 40mm', 'ZED 50mm']:
                components = self._get_cfa_zed(cfa_type, lead_type, diameter, drive_head, o_length, rotation, teeth, pilot, centre_tube, inner_tube, l_flight_od, l_flight_pt, c_flight_od, c_flight_pt, coupling_flight_id, override_bom)
            elif lead_type == 'Single Cut':
                components = self._get_cfa_single_cut(cfa_type, lead_type, diameter, drive_head, o_length, rotation, teeth, pilot, centre_tube, inner_tube, l_flight_od, l_flight_pt, c_flight_od, c_flight_pt, coupling_flight_id, override_bom)
            else:
                return []
        elif cfa_type == 'Intermediate':
            components = self._get_cfa_intermediate(cfa_type, lead_type, diameter, drive_head, o_length, rotation, teeth, pilot, centre_tube, inner_tube, l_flight_od, l_flight_pt, c_flight_od, c_flight_pt, coupling_flight_id, override_bom)
        else:
            # Extension (for couplings only)
            components = self._get_cfa_extension(cfa_type, lead_type, diameter, drive_head, o_length, rotation, teeth, pilot, centre_tube, inner_tube, l_flight_od, l_flight_pt, c_flight_od, c_flight_pt, coupling_flight_id)
        return components

    def _get_cfa_dual_taper_rock(self, cfa_type, lead_type, diameter, drive_head, o_length, rotation, teeth, pilot, centre_tube, inner_tube, l_flight_od, l_flight_pt, c_flight_od, c_flight_pt, coupling_flight_id, override_bom):
        # Get all items for at3
        ctube_at3 = self._get_cfa_coupling_ctube_at3(centre_tube, inner_tube)
        # Get the elbow item for mapping of inner tube height
        elbow = ctube_at3[0][0] if ctube_at3 else ''
        zed_center = "" # leave empty; only applicable for zed type
        base_coupling_at2 = self._get_cfa_coupling_dhead_at2(cfa_type, lead_type, drive_head, centre_tube, inner_tube, pilot, zed_center, elbow, o_length)
        # Return: Items for lead, carrier, and coupling flights w/ qty
        cfa_stock_flights_at4 = self._get_cfa_lead_ca_co_flights(cfa_type, lead_type, diameter, centre_tube, l_flight_od, l_flight_pt, c_flight_od, c_flight_pt, coupling_flight_id, rotation, o_length, drive_head, override_bom)
        # Get all the teeth and pilot items
        teeth_and_pilot_at5 = self._get_cfa_coupling_teeth_at5(diameter, centre_tube, lead_type, teeth, pilot)

        # We combine all components based on lead type
        combination = [
            *base_coupling_at2,
            *cfa_stock_flights_at4,
            *teeth_and_pilot_at5,
            *ctube_at3,
        ]

        # We filter components to exclude non-values
        components = [r for r in combination if r[0]]

        return components

    def _get_cfa_intermediate(self, cfa_type, lead_type, diameter, drive_head, o_length, rotation, teeth, pilot, centre_tube, inner_tube, l_flight_od, l_flight_pt, c_flight_od, c_flight_pt, coupling_flight_id, override_bom):
        # Get all items for at3
        ctube_at3 = self._get_cfa_coupling_ctube_at3(centre_tube, inner_tube)
        elbow = ctube_at3[0][0] if ctube_at3 else ''  # Get the elbow item for mapping of inner tube height
        zed_center = "" # leave empty; only applicable for zed type
        base_coupling_at2 = self._get_cfa_coupling_dhead_at2(cfa_type, lead_type, drive_head, centre_tube, inner_tube, pilot, zed_center, elbow, o_length)
        # Return: Items for lead, carrier, and coupling flights w/ qty
        cfa_stock_flights_at4 = self._get_cfa_lead_ca_co_flights(cfa_type, lead_type, diameter, centre_tube, l_flight_od, l_flight_pt, c_flight_od, c_flight_pt, coupling_flight_id, rotation, o_length, drive_head, override_bom)
        s_ring = ctube_at3[3] if len(ctube_at3) <= 2 else (None, 0)
        s_ring_lst = [s_ring]
        # We combine all components based on lead type
        combination = [
            *base_coupling_at2,
            *cfa_stock_flights_at4,
            *s_ring_lst,
        ]

        # We filter components to exclude non-values
        components = [r for r in combination if r[0]]

        return components

    def _get_cfa_extension(self, cfa_type, lead_type, diameter, drive_head, o_length, rotation, teeth, pilot, centre_tube, inner_tube, l_flight_od, l_flight_pt, c_flight_od, c_flight_pt, coupling_flight_id):
        # Get all items for at3
        ctube_at3 = self._get_cfa_coupling_ctube_at3(centre_tube, inner_tube)
        elbow = ctube_at3[0][0] if ctube_at3 else ''# Get the elbow item for mapping of inner tube height
        zed_center = "" # leave empty; only applicable for zed type
        base_coupling_at2 = self._get_cfa_coupling_dhead_at2(cfa_type, lead_type, drive_head, centre_tube, inner_tube, pilot, zed_center, elbow, o_length)
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

    def _get_cfa_zed(self, cfa_type, lead_type, diameter, drive_head, o_length, rotation, teeth, pilot, centre_tube, inner_tube, l_flight_od, l_flight_pt, c_flight_od, c_flight_pt, coupling_flight_id, override_bom):
        # Get all items for at3
        ctube_at3 = self._get_cfa_coupling_ctube_at3(centre_tube, inner_tube)
        elbow = ctube_at3[0][0] if ctube_at3 else ''  # Get the elbow item for mapping of inner tube height
        # Zed center items
        zed_center_at6 = self._get_cfa_zed_center_at6(centre_tube, diameter)
        zed_center = zed_center_at6[0][0] if zed_center_at6 else ''
        base_coupling_at2 = self._get_cfa_coupling_dhead_at2(cfa_type, lead_type, drive_head, centre_tube, inner_tube, pilot, zed_center, elbow, o_length)
        # Return: Items for lead, carrier, and coupling flights w/ qty
        cfa_stock_flights_at4 = self._get_cfa_lead_ca_co_flights(cfa_type, lead_type, diameter, centre_tube, l_flight_od, l_flight_pt, c_flight_od, c_flight_pt, coupling_flight_id, rotation, o_length, drive_head, override_bom)
        # Get all the teeth and pilot items
        teeth_and_pilot_at5 = self._get_cfa_coupling_teeth_at5(diameter, centre_tube, lead_type, teeth, pilot)
        # We combine all components based on lead type
        combination = [
            *base_coupling_at2,
            *cfa_stock_flights_at4,
            *teeth_and_pilot_at5,
            *ctube_at3,
            *zed_center_at6,
        ]
        # We filter components to exclude non-values
        components = [r for r in combination if r[0]]

        return components

    def _get_cfa_single_cut(self, cfa_type, lead_type, diameter, drive_head, o_length, rotation, teeth, pilot, centre_tube, inner_tube, l_flight_od, l_flight_pt, c_flight_od, c_flight_pt, coupling_flight_id, override_bom):
        # Get all items for at3
        ctube_at3 = self._get_cfa_coupling_ctube_at3(centre_tube, inner_tube)
        elbow = ctube_at3[0][0] if ctube_at3 else ''  # Get the elbow item for mapping of inner tube height
        zed_center = "" # leave empty; only applicable for zed type
        base_coupling_at2 = self._get_cfa_coupling_dhead_at2(cfa_type, lead_type, drive_head, centre_tube, inner_tube, pilot, zed_center, elbow, o_length)
        # Return: Items for lead, carrier, and coupling flights w/ qty
        cfa_stock_flights_at4 = self._get_cfa_lead_ca_co_flights(cfa_type, lead_type, diameter, centre_tube, l_flight_od, l_flight_pt, c_flight_od, c_flight_pt, coupling_flight_id, rotation, o_length, drive_head, override_bom)
        # Get all the teeth and pilot items
        teeth_and_pilot_at5 = self._get_cfa_coupling_teeth_at5(diameter, centre_tube, lead_type, teeth, pilot)

        id_value = ""
        # dia = int(re.search(r"\d+\.?\d*", diameter).group())
        dia = diameter
        id_match = re.search(r'OD(\d+)', centre_tube)
        if id_match:
            id_value = int(id_match.group(1))

        profiling = [(f"Profiling - CFA Single Cut {dia}mm Diameter x Flight - OD280 ID{id_value} P330 T32 RH", 1)]
        # We combine all components based on lead type
        combination = [
            *base_coupling_at2,
            *cfa_stock_flights_at4,
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
        attributes = {attr.attribute_id.name: attr.name for attr in product.product_template_attribute_value_ids}
        from_drive = attributes.get('From', '')
        to_drive = attributes.get('To', '')
        type = attributes.get('Type', '')
        reducer = attributes.get('Reducer', '')
        lift_lug = attributes.get('Lift Lug', '')

        components = []

        _drive1, _drive2, _base_plate = self._get_high_tensile_drive_head(from_drive, to_drive, type)
        _stiff_ring = self._get_stiffening_ring_for_tensile_adapter(_drive1, _drive2, type)
        liftlug = re.match(r'^\s*(\d+(?:\.\d+)?)', lift_lug)
        lift_lug_qty = int(liftlug.group(1)) if liftlug else 0.0
        _liftlug = ('Lift lug', lift_lug_qty) if lift_lug else (None, 0)
        c_reducer = self._get_hta_reducer(reducer)
        _reducer = (c_reducer, 1)
        _none = (None, 0)
        lst = [
            _drive1,
            _drive2,
            _base_plate or _none,
            _reducer or _none,
            _stiff_ring or _none,
            _liftlug
        ]
        components = [x for x in lst if x[0]]
        return components

    def _get_hta_reducer(self, reducer):
        reducer_map = {
            'Reducer - 4" to 2"': 'Reducer - 4" to 2"',
            'Reducer - 5" to 4"': 'Internal reducer funnel 5" to 4"',
            'Reducer - 250NB to 100NB': 'Concentric reducer - 250NB to 100NB NB',
            'Reducer - 350NB to 200NB': 'Concentric reducer - 350 NB to 200 NB',
            'Reducer - 500NB to 300NB': 'Concentric reducer - 500 NB to 300 NB',
        }
        return reducer_map.get(reducer, '')

    def _get_hta_base_plate(self, drive_head):
        base_plate_map = {
            'Drive Head - 75mm Square': '',
            'Drive Head - 100mm Square': 'Base Plate - 100mm Head',
            'Drive Head - 110mm Square': 'Base Plate - 110mm Head',
            'Drive Head - 130mm Square': 'Base Plate - 130mm Head',
            'Drive Head - 130mm Square DIGGA': 'Base Plate - 130mm Head',
            'Drive Head - 150mm Square': 'Base Plate - 150mm Head',
            'Drive Head - 150mm Square IMT': 'Base Plate - 150mm Head',
            'Drive Head - 200mm Square Bauer': 'Base Plate - 200mm Head',
            'Drive Head - 200mm Square MAIT': 'Base Plate - 200mm Head',
        }
        return base_plate_map.get(drive_head, '')

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
        attributes = {attr.attribute_id.name: attr.name for attr in product.product_template_attribute_value_ids}
        type = attributes.get('Type', '')
        drive_head = attributes.get('Drive', '')
        adaptor = attributes.get('Adaptor', '')
        f_female = attributes.get('Female to Female', '')
        m_male = attributes.get('Male to Male', '')
        center_tube = attributes.get('Centre Tube', '')
        length = attributes.get('Length', '')
        # stubb = attributes.get('Stub', '')
        lift_lug = attributes.get('Lift Lug', '')

        components = []

        if type == 'Telescopic Inner':
            components = self._get_eb_telescopic_inner_components(type, drive_head, adaptor, f_female, m_male, center_tube, length, lift_lug)
        elif type == 'Telescopic Outer':
            components = self._get_eb_telescopic_outer_components(type, drive_head, adaptor, f_female, m_male, center_tube, length, lift_lug)
        else:
            components = self._get_eb_rigid_components(type, drive_head, adaptor, f_female, m_male, center_tube, length, lift_lug)

        return components

    def _get_eb_telescopic_inner_components(self, type, drive_head, adaptor, f_female, m_male, center_tube, length, lift_lug):
        _drive_head = self._get_eb_drive_head(drive_head)
        _center_tube_stub_bp = self._get_extension_bar_center_tube_at2(type, center_tube, drive_head, f_female, m_male, length, adaptor)
        lift_lug = re.match(r'^\s*(\d+(?:\.\d+)?)', lift_lug)
        lift_lug_qty = int(lift_lug.group(1)) if lift_lug else 0.0
        _liftlug = (f'Lift lug', lift_lug_qty) if lift_lug else (None, 0)
        _collar = self._get_eb_collar(center_tube)
        lst = [
            _drive_head,
            *_center_tube_stub_bp,
            (_collar, 1),
            _liftlug
        ]
        components = [x for x in lst if x[0]]
        return components

    def _get_eb_telescopic_outer_components(self, type, drive_head, adaptor, f_female, m_male, center_tube, length, lift_lug):
        _drive_head = self._get_eb_drive_head(drive_head)
        _center_tube_stub_bp = self._get_extension_bar_center_tube_at2(type, center_tube, drive_head, f_female, m_male, length, adaptor)
        _dhead = _drive_head[0] if _drive_head else '' # drive head item
        _gusset = self._get_extension_bar_center_tube_gusset(_dhead, center_tube)
        lift_lug = re.match(r'^\s*(\d+(?:\.\d+)?)', lift_lug)
        lift_lug_qty = int(lift_lug.group(1)) if lift_lug else 0.0
        _liftlug = (f'Lift lug', lift_lug_qty) if lift_lug else (None, 0)
        lst = [
                _drive_head,
                *_center_tube_stub_bp,
                _gusset,
                _liftlug
            ]
        components = [x for x in lst if x[0]]
        return components

    def _get_eb_rigid_components(self, type, drive_head, adaptor, f_female, m_male, center_tube, length, lift_lug):
        """
            return: list of items for dhead, base plate, stub and gusset
        """
        def _get_mm_size(str):
            fm_str = re.search(r'(\d+)mm', str)
            number = int(fm_str.group(1)) if fm_str else 0
            return number

        f_female_mm = _get_mm_size(f_female)
        d_head_mm = _get_mm_size(drive_head)

        _drive_head = self._get_eb_drive_head(drive_head)
        _drive_head_1 = _drive_head[0] if _drive_head else ''  # Drive head item
        _drive_head_2 = self._get_drive_head_from_female(f_female)

        _dhead_qty = 1 if f_female and _drive_head_1 != _drive_head_2 or not f_female else 2
        _dhead = (_drive_head_1, _dhead_qty) if not m_male else (None, 0)

        _center_tube_stub_bp = self._get_extension_bar_center_tube_at2(type, center_tube, drive_head, f_female, m_male, length, adaptor)

        _gusset = self._get_extension_bar_center_tube_gusset(_drive_head_1, center_tube)
        _gusset_name = _gusset[0] if _gusset else ''  # Gusset item
        _gusset_qty = 1 if f_female and _drive_head_1 != _drive_head_2 and f_female_mm != d_head_mm or not f_female else 2
        _gusset_1 = (_gusset_name, _gusset_qty) if _gusset_name and not m_male else (None, 0)

        # raise ValidationError(f"{_gusset_1} {_gusset_name}, {_drive_head_1}")
        gusset_2_dhead = self._get_eb_female_gusset_dhead(f_female)
        _gusset_2 = self._get_extension_bar_center_tube_gusset(gusset_2_dhead, center_tube)

        lift_lug = re.match(r'^\s*(\d+(?:\.\d+)?)', lift_lug)
        lift_lug_qty = int(lift_lug.group(1)) if lift_lug else 0.0
        _liftlug = ("Lift lug", lift_lug_qty) if lift_lug else (None, 0)

        lst = [
                _dhead,
                *_center_tube_stub_bp,
                _liftlug
            ]

        if type != 'Telescopic Inner' and not m_male:
            item = [_gusset_1]
            if f_female_mm != d_head_mm:
                item.extend([_gusset_2])
            lst.extend(item)

        components = [x for x in lst if x[0]]
        return components

    def _get_eb_collar(self, centre):
        centre_tube = {
            "4140 75mm square billet": "Extension Bar Collar - 75mm",
            "4140 100mm square billet": "Extension Bar Collar - 100mm"
        }
        return centre_tube.get(centre, '')

    def _get_eb_drive_head(self, drive_head):
        DRIVE_HEAD = {
            '75mm Square Drive': 'Drive Head - 75mm Square',
            '100mm Square Drive': 'Drive Head - 100mm Square',
            '110mm Square Drive': 'Drive Head - 110mm Square',
            '130mm Square Drive': 'Drive Head - 130mm Square',
            '130mm Square Digga Drive': 'Drive Head - 130mm Square DIGGA',
            '150mm Square Drive': 'Drive Head - 150mm Square',
            '150mm Square IMT Drive': 'Drive Head - 150mm Square IMT',
            '200mm Square Bauer Drive': 'Drive Head - 200mm Square Bauer',
            '200mm Square MAIT Drive': 'Drive Head - 200mm Square MAIT'
        }
        return (DRIVE_HEAD.get(drive_head, ''), 1)

    def _get_eb_female_gusset_dhead(self, female):
        """
        param: female_female attribute
        return: find the drive head based on the female attribute for gusset 2
        """
        F_FEMALE = {
            'to 75mm Square Drive (Female to Female)': 'Drive Head - 75mm Square',
            'to 100mm Square Drive (Female to Female)': 'Drive Head - 100mm Square',
            'to 110mm Square Drive (Female to Female)': 'Drive Head - 110mm Square',
            'to 130mm Square Drive (Female to Female)': 'Drive Head - 130mm Square',
            'to 130mm Square Digga Drive (Female to Female)': 'Drive Head - 130mm Square DIGGA',
            'to 150mm Square Drive (Female to Female)': 'Drive Head - 150mm Square',
            'to 150mm Square IMT Drive (Female to Female)': 'Drive Head - 150mm Square IMT',
            'to 200mm Square Bauer Drive (Female to Female)': 'Drive Head - 200mm Square Bauer',
            'to 200mm Square MAIT Drive (Female to Female)': 'Drive Head - 200mm Square MAIT',
        }
        return F_FEMALE.get(female, '')

    def _get_eb_male_stub_dhead(self, male):
        """
        param: male_male attribute
        return: find the drive head based on the male attribute for stub 2
        """
        M_MALE = {
            'to 75mm Square Drive (Male to Male)': 'Drive Head - 75mm Square',
            'to 100mm Square Drive (Male to Male)': 'Drive Head - 100mm Square',
            'to 110mm Square Drive (Male to Male)': 'Drive Head - 110mm Square',
            'to 130mm Square Drive (Male to Male)': 'Drive Head - 130mm Square',
            'to 130mm Square Digga Drive (Male to Male)': 'Drive Head - 130mm Square DIGGA',
            'to 150mm Square Drive (Male to Male)': 'Drive Head - 150mm Square',
            'to 150mm Square IMT Drive (Male to Male)': 'Drive Head - 150mm Square IMT',
            'to 200mm Square Bauer Drive (Male to Male)': 'Drive Head - 200mm Square Bauer',
            'to 200mm Square MAIT Drive (Male to Male)': 'Drive Head - 200mm Square MAIT',
        }
        return M_MALE.get(male, '')

    def _get_drive_head_from_female(self, female):
            if not female or female == 'N/A' or 'Custom' in female:
                return ''
            # Extract everything between "to " and " Drive"
            match = re.search(r'to\s+(.+?)\s+Drive', female)
            digga_item = ['to 130mm Square Digga Drive (Female to Female)']
            if female in digga_item:
                return "Drive Head - 130mm Square DIGGA"
            if match:
                return f"Drive Head - {match.group(1)}"
            return ''

    def _get_extension_bar_center_tube_at2(self, type, center_tube, drive_head, f_female, m_male, length, adaptor):
        """Compute center tube quantity for Extension Bar based on type, drive head, and stub"""

        def _get_mm_number(str):
            fm_str = re.search(r'(\d+)mm', str)
            number = int(fm_str.group(1)) if fm_str else 0
            return number

        # list of heights [dh_height, bp_thikness, stub_height]
        DRIVE_HEAD_HEIGHTS = {
            '75mm Square Drive': [150, 0, 40],
            '100mm Square Drive': [175, 25, 50],
            '110mm Square Drive': [240, 25, 40],
            '130mm Square Drive': [260, 32, 40],
            '130mm Square Digga Drive': [260, 32, 40],
            '150mm Square Drive': [260, 32, 60],
            '150mm Square IMT Drive': [260, 32, 60],
            '200mm Square Bauer Drive': [457, 32, 60],
            '200mm Square MAIT Drive': [345, 32, 60],
        }
        # mapping of items for base plate and stub
        BASE_PLATE = {
            '100mm Square Drive': 'Base Plate - 100mm Head',
            '110mm Square Drive': 'Base Plate - 110mm Head',
            '130mm Square Drive': 'Base Plate - 130mm Head',
            '130mm Square Digga Drive': 'Base Plate - 130mm Head',
            '150mm Square Drive': 'Base Plate - 150mm Head',
            '150mm Square IMT Drive': 'Base Plate - 150mm Head',
            '200mm Square Bauer Drive': 'Base Plate - 200mm Head',
            '200mm Square MAIT Drive': 'Base Plate - 200mm Head ',
        }
        STUB = {
            'to 75mm Square Stub': '75mm Square Extension Bar Stubb',
            'to 100mm Square Stub': '100mm square Stubb',
            'to 110mm Square Stub': '110mm Drive Stubb',
            'to 130mm Square Stub': '130mm Stubb',
            'to 130mm Square Digga Stub': '130mm Stubb - Digga',
            'to 150mm Square Stub': '150mm Drive Stub',
            'to 150mm Square IMT Stub': '150mm IMT Stub',
            'to 200mm Square Bauer Stub': '200mm Bauer Drive Stubb',
            'to 200mm Square MAIT Stub': '200mm MAIT Square Stub'
        }
        STUB_DHEAD = {
            '75mm Square Drive': '75mm Square Extension Bar Stubb',
            '100mm Square Drive': '100mm square Stubb',
            '110mm Square Drive': '110mm Drive Stubb',
            '130mm Square Drive': '130mm Stubb',
            '130mm Square Digga Drive': '130mm Stubb - Digga',
            '150mm Square Drive': '150mm Drive Stub',
            '150mm Square IMT Drive': '150mm IMT Stub',
            '200mm Square Bauer Drive': '200mm Bauer Drive Stubb',
            '200mm Square MAIT Drive': '200mm MAIT Square Stub'
        }
        # mapping of stub item and height
        STUB_2 = {
            'to 75mm Square Drive (Male to Male)': ['75mm Square Extension Bar Stubb', 40],
            'to 100mm Square Drive (Male to Male)': ['100mm square Stubb', 50],
            'to 110mm Square Drive (Male to Male)': ['110mm Drive Stubb', 40],
            'to 130mm Square Drive (Male to Male)': ['130mm Stubb', 40],
            'to 130mm Square Digga Drive (Male to Male)': ['130mm Stubb - Digga', 40],
            'to 150mm Square Drive (Male to Male)': ['150mm Drive Stub', 60],
            'to 150mm Square IMT Drive (Male to Male)': ['150mm IMT Stub', 60],
            'to 200mm Square Bauer Drive (Male to Male)': ['200mm Bauer Drive Stubb', 60],
            'to 200mm Square MAIT Drive (Male to Male)': ['200mm MAIT Square Stub', 60],
        }
        # mapping of female head and base plate
        DH_BP_2 = {
            'to 75mm Square Drive (Female to Female)': [150, 0],
            'to 100mm Square Drive (Female to Female)': [175, 25],
            'to 110mm Square Drive (Female to Female)': [240, 25],
            'to 130mm Square Drive (Female to Female)': [260, 32],
            'to 130mm Square Digga Drive (Female to Female)': [260, 32],
            'to 150mm Square Drive (Female to Female)': [260, 32],
            'to 150mm Square IMT Drive (Female to Female)': [260, 32],
            'to 200mm Square Bauer Drive (Female to Female)': [457, 32],
            'to 200mm Square MAIT Drive (Female to Female)': [345, 32],
        }
        _drive_head = self._get_eb_drive_head(drive_head)
        _drive_head_1 = _drive_head[0] if _drive_head else ''  # Drive head item
        _drive_head_2 = self._get_drive_head_from_female(f_female)

        d_head = DRIVE_HEAD_HEIGHTS.get(drive_head, [])
        length_str = re.search(r'(\d+(\.\d+)?)\s*m', length.lower())
        length_no = float(length_str.group(1)) if length_str else 0.0

        # Find the mm size of Female Female and Drive
        f_female_no = _get_mm_number(f_female)
        d_head_no = _get_mm_number(drive_head)

        # Convert mm to meters for head, base, stub
        head_height = d_head[0] / 1000.0 if d_head else 0
        base_height = d_head[1] / 1000.0 if d_head else 0
        stub_height = d_head[2] / 1000.0 if d_head else 0

        Dh_bp_2 = DH_BP_2.get(f_female, [])
        Stub_2 = STUB_2.get(m_male, [])
        Base_plate = BASE_PLATE.get(drive_head, '')
        Stub = STUB.get(adaptor, '')
        Stub_dhead = STUB_DHEAD.get(drive_head, '')

        # Find the heights
        dhead_2 = Dh_bp_2[0] / 1000.0 if f_female else 0  # drive head 2
        bp_2 = Dh_bp_2[1] / 1000.0 if f_female else 0  # base plate 2
        stub_2 = Stub_2[1] / 1000.0 if m_male else 0  # stub 2

        tube_qty = 0
        if type == 'Telescopic Inner':
            tube_qty = length_no - head_height
        elif type == 'Telescopic Outer':
            tube_qty = length_no - head_height - stub_height
        else:
            if f_female and not m_male:
                tube_qty = length_no - head_height - dhead_2 - base_height - bp_2
            elif m_male and not f_female:
                tube_qty = length_no - stub_height - stub_2
            else:
                tube_qty = length_no - head_height - stub_height - base_height

        _dhead_stub_2 = self._get_eb_male_stub_dhead(m_male)
        _base_plate_2 = f"Base Plate - {f_female_no}mm Head" 

        _none = (None, 0)
        _centre_tube = center_tube if center_tube else ''
        _base_plate = Base_plate if Base_plate else ''  # base plate
        _stub = Stub if Stub else ''  # stub

        components = [
            (_centre_tube, round(tube_qty, 2)) or _none,
        ]
        b_plate_qty = 2 if f_female else 1
        stub_qty = 2 if m_male else 1

        if type == 'Rigid':
            if f_female and f_female_no != d_head_no and not m_male:
                b_plate_qty = 1
                lst = [
                    (_base_plate_2, 1) or _none
                ]
                components.extend(lst)
            if not m_male:
                components.extend(
                    [(_base_plate, b_plate_qty) or _none,]
                )
            if f_female and _drive_head_1 != _drive_head_2 and not m_male:
                lst = [
                    (_drive_head_2, 1) or _none,
                ]
                components.extend(lst)
            if m_male and _drive_head_1 != _dhead_stub_2:
                stub_qty = 1
                stub_2 = Stub_2[0] if Stub_2 else ''
                lst = [(stub_2, 1) or _none]
                components.extend(lst)

        if type != 'Telescopic Inner' and not f_female:
            if adaptor:
                lst = [(_stub, 1) or _none]
                components.extend(lst)
            else:
                lst = [(Stub_dhead, stub_qty) or _none]
                components.extend(lst)
        return components

    def _get_extension_bar_center_tube_gusset(self, drive_head, center_tube):
        """
        Returns the gusset component based on drive head and center shaft.
        Args:
            drive_head (str): The name of the drive head.
            center_tube (str): The name of the center shaft.
        Returns:
            tuple: (component_name, quantity), e.g., ("Gusset - 130mm Drive 273mm Tube", 1)
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
                'Hollow bar - OD273mm WT14': "Gusset - 130mm Drive 273mm Tube",
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
                # Pipes (smaller pipes use 130mm gussets)
                'Pipe - OD168mm WT6.4mm': "Gusset - 130mm Drive 170mm Tube",
                'Pipe - OD168mm WT4.8mm': "Gusset - 130mm Drive 170mm Tube",
                'Pipe - OD168mm WT11mm': "Gusset - 130mm Drive 170mm Tube",
                'Pipe - OD177mm WT 8mm': "Gusset - 130mm Drive 170mm Tube",
                'Pipe - OD219mm WT8.2mm': "Gusset - 130mm Drive 219mm Tube",
                'Pipe - OD219mm WT6.4mm': "Gusset - 130mm Drive 219mm Tube",
                'Pipe - OD219mm WT12.7mm': "Gusset - 130mm Drive 219mm Tube",
                # Larger pipes use 150mm gussets
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
            "4\" Hex Coupling": "4\" Hex Coupling - Female",
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
            "4\" Hex Coupling": "4\" Hex Coupling - Male Male Joiner",
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
            "150mm Square Drive": "150mm Stub",
            "150mm Square Drive IMT": "150mm IMT Stub",
            "200mm Square Drive Bauer": "200mm Bauer Drive Stubb",
            "200mm Square Drive MAIT": "200mm MAIT Square Stub",
        }

        ff_fdrive = self._get_mm_number(female_map.get(from_drive))
        ff_tdrive = self._get_mm_number(female_map.get(to_drive))
        ff_dhead = ""
        if ff_fdrive > ff_tdrive:
            ff_dhead = female_map.get(from_drive)
        else:
            ff_dhead = female_map.get(to_drive)

        type_map = {
            'Female to Female': (female_map.get(from_drive), female_map.get(to_drive), self._get_hta_base_plate(ff_dhead)),
            'Male to Male': (male_map.get(from_drive), male_map.get(to_drive), ''),
            'Female to Male': (female_map.get(from_drive), male_map.get(to_drive), self._get_hta_base_plate(female_map.get(from_drive))),
            'Male to Female': (male_map.get(from_drive), female_map.get(to_drive), self._get_hta_base_plate(female_map.get(to_drive))),
        }

        from_component, to_component, base_plate = type_map.get(type, (None, None, None))

        result = []
        _none = (None, 0)

        result.append((from_component, 1) if from_component else _none)
        result.append((to_component, 1) if to_component else _none)
        result.append((base_plate, 1) if base_plate else _none)
        return result

    def _get_mm_number(self, str):
        fm_str = re.search(r'(\d+)mm', str)
        number = int(fm_str.group(1)) if fm_str else 0
        return number

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
            'Drive Head - 100mm Square': {
                '75mm Stubb': True, '100mm Stubb': False, '110mm Stubb': False,
                '130mm Stubb': False, '150mm Stubb': False, '75mm Head': True,
            },
            'Drive Head - 110mm Square': {
                '75mm Stubb': True, '100mm Stubb': True, '110mm Stubb': False,
                '130mm Stubb': False, '150mm Stubb': False, '75mm Head': True,
            },
            'Drive Head - 130mm Square': {
                '75mm Stubb': True, '100mm Stubb': True, '110mm Stubb': True,
                '130mm Stubb': False, '150mm Stubb': False, '75mm Head': True,
            },
            'Drive Head - 130mm Square DIGGA': {
                '75mm Stubb': True, '100mm Stubb': True, '110mm Stubb': True,
                '130mm Stubb': False, '150mm Stubb': False, '75mm Head': True,
            },
            'Drive Head - 150mm Square': {
                '75mm Stubb': True, '100mm Stubb': True, '110mm Stubb': True,
                '130mm Stubb': True, '150mm Stubb': False, '75mm Head': True,
            },
            'Drive Head - 150mm Square IMT': {
                '75mm Stubb': True, '100mm Stubb': True, '110mm Stubb': True,
                '130mm Stubb': True, '150mm Stubb': True, '75mm Head': True,
            },
            'Drive Head - 200mm Square Bauer': {
                '75mm Stubb': True, '100mm Stubb': True, '110mm Stubb': True,
                '130mm Stubb': True, '150mm Stubb': True, '75mm Head': True,
            },
            'Drive Head - 200mm Square MAIT': {
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

        stub_item = ""
        drive = ""
        if coupling_type == 'Female to Male':
            stub_item = drive_to[0] if drive_to else ""
            drive = drive_from[0] if drive_from else ""

        if coupling_type == 'Male to Female':
            stub_item = drive_from[0] if drive_from else ""
            drive = drive_to[0] if drive_to else ""

        available = stiffening_matrix.get(drive)
        dhead_75 = self._get_mm_number(drive)

        if dhead_75 == 75:
            return (f"{ring_label_map['75mm Head']}", 1)

        if not available:
            return None

        # Preferred stub if 'Stubb' is explicitly mentioned in drive_to
        preferred_stub = None
        if 'stubb' in stub_item.lower() or 'stub' in stub_item.lower():
            match = re.search(r'(\d{2,3})mm', stub_item)
            if match:
                preferred_stub = f"{match.group(1)}mm Stubb"

        if preferred_stub and available.get(preferred_stub):
            return (f"{ring_label_map[preferred_stub]}", 1)

        return (None, 0)

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

    def _get_cfa_coupling_teeth_at5(self, diameter, center_tube, lead_type, teeth, pilot):
        """
            Return: a list of teeth items
        """
        # dia = int(re.search(r"\d+\.?\d*", diameter).group())
        dia = diameter
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

    def _get_cfa_zed_center_at6(self, center_tube, diameter):
        # dia = int(re.search(r"\d+\.?\d*", diameter).group())
        dia = diameter
        center_tube_map = {
            # Hollow Bars
            'Hollow Bar - OD150mm ID120mm': "ZED Centre 150mm",
            'Hollow Bar - OD152mm WT 26mm': "ZED Centre 150mm",
            'Hollow Bar - OD152mm WT 33.5mm': "ZED Centre 150mm",
            'Hollow Bar - OD168mm WT 21.5mm': "ZED Centre 168mm",
            'Hollow Bar - OD168mm WT 29mm': "ZED Centre 168mm",
            'Hollow Bar - OD170mm ID140mm': "ZED Centre 168mm",
            'Hollow Bar - OD219mm WT 25mm': "ZED Centre 219mm",
            'Hollow bar - OD273mm WT14': "ZED Centre 273mm",
            'Hollow Bar - OD273mm WT 25mm': "ZED Centre 273mm",
            'Hollow Bar - OD273mm WT 32mm': "ZED Centre 273mm",
            # Pipes
            'Pipe - OD168mm WT4.8mm': "ZED Centre 168mm",
            'Pipe - OD168mm WT6.4mm': "ZED Centre 168mm",
            'Pipe - OD168mm WT11mm': "ZED Centre 168mm",
            'Pipe - OD219mm WT12.7mm': "ZED Centre 219mm",
            'Pipe - OD273mm WT12.7mm': "ZED Centre 273mm",
        }
        zed_center = [(center_tube_map.get(center_tube, ''), 1)]
        zed_flight = [('ZED Flight Stiffener (Under 600mm)', 2)] if dia < 600 else [('ZED Flight Stiffener (600mm+)', 2)]

        return zed_center + zed_flight

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
                ('Rock Auger Pilot - 25mm Shank 75mm square', 1),
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
                ('38/30mm Round Tooth Holder', 6)
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
            '19.4mm Teeth Pilot': [
                ('Rock Pilot suit 19mm Teeth 44mm Hex - RH / LH', 1),
                ('Pilot Support - Hex', 1),
                ('End Cap - Suit Hex Pilot Support', 1),
                ('BSK17 - 19.4mm Shank Teeth', 4)
            ],
            '22mm Teeth Pilot': [
                ('Rock Pilot suit 22mm Teeth 44mm Hex - RH / LH', 1),
                ('Pilot Support - Hex', 1),
                ('End Cap - Suit Hex Pilot Support', 1),
                ('BC86TB - TEBCO 22mm Teeth', 4)
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
                ('BC05TB - 22mm Shank Teeth', _get_teeth_qty(42)),
                ('BHR176 - 22mm Block Tooth Holder', _get_teeth_qty(42)),
                ('BA13 - Weld on Button Carbide', _get_teeth_qty(42) / 2)
            ],
            '25mm BTK03 Teeth w/ Flat Back Holder': [
                ('BTK03TB - 25mm Shank Teeth', _get_teeth_qty(44)),
                ('TB25 - 25mm Flat Back Holder', _get_teeth_qty(44)),
                ('BA13 - Weld on Button Carbide', _get_teeth_qty(42) / 2)
            ],
            '25mm BTK03 Teeth w/ Block Holder': [
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
        def _get_pilot_od(pilot_supp):
            items = {
                '19.4mm Teeth Pilot': 78,
                '22mm Teeth Pilot': 78,
                '25mm Teeth Pilot': 150,
                '38/30 Teeth Pilot': 200
            }
            return items.get(pilot_supp, 0)

        def round_nearest_odd(x):
            n = round(x)
            if n % 2 == 1:
                return n
            return n + 1 if x > n else n - 1
            
        def _get_teeth_qty(mm):
            Pilot_Support_OD = _get_pilot_od(pilot) # Get the pilot support OD
            qty = (dia - Pilot_Support_OD - 10) / mm + 8
            return round_nearest_odd(qty)

        teeth_map = {
            '19.4mm BK17 Teeth': [
                ('BSK17 - 19.4mm Shank Teeth', _get_teeth_qty(40)),
                ('BHR164 - 19.4mm Block Holder', _get_teeth_qty(40) - 4)
            ],
            '22mm BC86 Teeth': [
                ('BC86TB - TEBCO 22mm Teeth ', _get_teeth_qty(42)),
                ('BHR176 - 22mm Block Tooth Holder', _get_teeth_qty(42) - 4)
            ],
            '22mm BC05 Teeth': [
                ('BC05TB - 22mm Shank Teeth', _get_teeth_qty(42)),
                ('BHR176 - 22mm Block Tooth Holder', _get_teeth_qty(42) - 4)
            ],
            '25mm BTK03 Teeth w/ Flat Back Holder': [
                ('BTK03TB - 25mm Shank Teeth', _get_teeth_qty(44)),
                ('TB25 - 25mm Flat Back Holder', _get_teeth_qty(44) - 4)
            ],
            '25mm BTK03 Teeth w/ Block Holder': [
                ('BTK03TB - 25mm Shank Teeth', _get_teeth_qty(44)),
                ('BHR31 - 25mm Block Tooth Holder', _get_teeth_qty(44) - 4)
            ],
            '38/30 BKH105 Teeth': [
                ('BKH105TB - 38/30mm Shank Teeth', _get_teeth_qty(66)),
                ('BHR38 - 38/30mm Block Tooth Holder', _get_teeth_qty(66) - 4)
            ]
        }
        pilot_map = {
            '19.4mm Teeth Pilot': [
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
        #TODO: Ask the formula to get the inner tube length(metre) for the spacer ring
        """
        Return: list of tuples (item_name, qty) for Elbow, Pipe Extension, Spacer Ring, CFA Plug, CFA Plug Holder
        Elbow is always first in the list.
        """
        CFA_COUPLING_CONFIG = {
            # Center tube only (inner_tube = None/'-')
            ('Hollow bar - OD80mm ID60mm', None): {
                'elbow': ('50NB Elbow - Xstrong Long Radius Bend', 1),
            },
            ('Hollow Bar - OD80mm ID55mm', None): {
                'elbow': ('50NB Elbow - Xstrong Long Radius Bend', 1),
            },
            ('Hollow Bar - OD100mm ID80mm', None): {
                'elbow': ('75NB elbow - Xstrong Long radius', 1),
            },
            ('Hollow Bar - OD110 ID70', None): {
                'elbow': ('75NB elbow - Xstrong Long radius', 1),
            },
            ('Hollow Bar - OD128mm WT 11.5mm', None): {
                'elbow': ('105NB elbow - Xstrong Long radius', 1),
                'cfa_plug': ('105mm CFA Plug', 1),
                'cfa_plug_holder': ('105mm CFA Plug Holder', 1),
            },
            ('Hollow Bar - OD150mm ID120mm', None): {
                'elbow': ('105NB elbow - Xstrong Long radius', 1),
                'cfa_plug': ('105mm CFA Plug', 1),
                'cfa_plug_holder': ('105mm CFA Plug Holder', 1),
            },
            ('Hollow Bar - OD152mm WT 26mm', None): {
                'elbow': ('105NB elbow - Xstrong Long radius', 1),
                'pipe_extension': ('Hollow Bar - OD150mm ID120mm', 0.25),
                'cfa_plug': ('105mm CFA Plug', 1),
                'cfa_plug_holder': ('105mm CFA Plug Holder', 1),
            },
            ('Hollow Bar - OD152mm WT 33.5mm', None): {
                'elbow': ('105NB elbow - Xstrong Long radius', 1),
                'cfa_plug': ('105mm CFA Plug', 1),
                'cfa_plug_holder': ('105mm CFA Plug Holder', 1),
            },
            ('Hollow Bar - OD168mm WT 21.5mm', None): {
                'elbow': ('125NB elbow - Xstrong long radius', 1),
                'pipe_extension': ('Hollow Bar - OD170mm ID140mm', 0.25),
                'cfa_plug': ('125mm CFA Plug', 1),
                'cfa_plug_holder': ('125mm CFA Plug Holder', 1),
            },
            ('Hollow Bar - OD168mm WT 29mm', None): {
                'elbow': ('125NB elbow - Xstrong long radius', 1),
                'cfa_plug': ('125mm CFA Plug', 1),
                'cfa_plug_holder': ('125mm CFA Plug Holder', 1),
            },
            ('Hollow Bar - OD170mm ID140mm', None): {
                'elbow': ('125NB elbow - Xstrong long radius', 1),
                'cfa_plug': ('125mm CFA Plug', 1),
                'cfa_plug_holder': ('125mm CFA Plug Holder', 1),
            },
            ('Hollow Bar - OD180 ID150', None): {
                'elbow': ('125NB elbow - Xstrong long radius', 1),
            },
            ('Hollow bar - OD200 ID150', None): {
                'elbow': ('125NB elbow - Xstrong long radius', 1),
            },
            # Center tube + Inner tube combinations
            ('Pipe - OD114mm WT8.56mm', 'Pipe - OD44mm WT2.77mm'): {
                'elbow': ('125NB elbow - Xstrong long radius', 1),
            },
            ('Hollow Bar - OD219mm WT 25mm', 'Pipe - OD141mm WT6.6mm'): {
                'elbow': ('125NB elbow - Xstrong long radius', 1),
                'spacer_ring': ('219 CFA Spacer Ring (164mm OD 143mm ID 10mm)', 2),
                'cfa_plug': ('125mm CFA Plug', 1),
                'cfa_plug_holder': ('125mm CFA Plug Holder', 1),
            },
            ('Hollow bar - OD273mm WT14', 'Pipe - OD141mm WT6.6mm'): {
                'elbow': ('125NB elbow - Xstrong long radius', 1),
                'spacer_ring': ('273 CFA Spacer Ring (218mm OD 143mm ID 10mm)', 2),
                'cfa_plug': ('125mm CFA Plug', 1),
                'cfa_plug_holder': ('125mm CFA Plug Holder', 1),
            },
            ('Hollow Bar - OD273mm WT 25mm', 'Pipe - OD141mm WT6.6mm'): {
                'elbow': ('125NB elbow - Xstrong long radius', 1),
                'spacer_ring': ('273 CFA Spacer Ring (218mm OD 143mm ID 10mm)', 2),
                'cfa_plug': ('125mm CFA Plug', 1),
                'cfa_plug_holder': ('125mm CFA Plug Holder', 1),
            },
            ('Hollow Bar - OD273mm WT 32mm', 'Pipe - OD141mm WT6.6mm'): {
                'elbow': ('125NB elbow - Xstrong long radius', 1),
                'spacer_ring': ('273 CFA heavy wall Spacer Ring (207mm OD 143mm ID 10mm)', 3),
                'cfa_plug': ('125mm CFA Plug', 1),
                'cfa_plug_holder': ('125mm CFA Plug Holder', 1),
            },
            ('Hollow Bar - OD323mm WT25mm', 'Pipe - OD141mm WT6.6mm'): {
                'elbow': ('125NB elbow - Xstrong long radius', 1),
                'spacer_ring': ('323 CFA Spacer Ring (270mm OD 143mm ID 10mm)', 3),
                'cfa_plug': ('125mm CFA Plug', 1),
                'cfa_plug_holder': ('125mm CFA Plug Holder', 1),
            },
            ('Hollow Bar - OD323mm WT30mm', 'Pipe - OD141mm WT6.6mm'): {
                'elbow': ('125NB elbow - Xstrong long radius', 1),
                'spacer_ring': ('323 CFA Spacer Ring (270mm OD 143mm ID 10mm)', 3),
                'cfa_plug': ('125mm CFA Plug', 1),
                'cfa_plug_holder': ('125mm CFA Plug Holder', 1),
            },
        }
        # Fallback when only inner_tube matters (center_tube is "All")
        # Only returns elbow - no other items
        INNER_TUBE_FALLBACK = {
            'Pipe - OD88.9mm WT5.4mm': {
                'elbow': ('75NB elbow - Xstrong Long radius', 1),
            },
            'Pipe - OD114mm WT6.0mm': {
                'elbow': ('105NB elbow - Xstrong Long radius', 1),
                'cfa_plug': ('105mm CFA Plug', 1),
                'cfa_plug_holder': ('105mm CFA Plug Holder', 1),
            },
            'Hollow Bar - OD168mm WT 21.5mm': {
                'elbow': ('125NB elbow - Xstrong long radius', 1),
                'cfa_plug': ('125mm CFA Plug', 1),
                'cfa_plug_holder': ('125mm CFA Plug Holder', 1),
            },
        }
        def _build_result(config):
            """Convert config dict to list of tuples. Elbow is always first."""
            result = []
            component_order = ['elbow', 'pipe_extension', 'spacer_ring', 'cfa_plug', 'cfa_plug_holder']
            for component in component_order:
                if component in config:
                    result.append(config[component])
            return result

        # Normalize inner_tube
        normalized_inner = None if inner_tube in (None, '-', '') else inner_tube.strip()
        # Try exact match (center_tube, inner_tube)
        key = (center_tube, normalized_inner)
        if key in CFA_COUPLING_CONFIG:
            return _build_result(CFA_COUPLING_CONFIG[key])
        # Try center_tube only match
        key = (center_tube, None)
        if key in CFA_COUPLING_CONFIG:
            return _build_result(CFA_COUPLING_CONFIG[key])
        # Try inner_tube fallback
        if normalized_inner in INNER_TUBE_FALLBACK:
            return _build_result(INNER_TUBE_FALLBACK[normalized_inner])
        # No match found
        return []

    def _get_cfa_coupling_dhead_at2(self, cfa_type, lead_type, drive_head, center_tube, inner_tube, pilot_support, zed_center, elbow, overall_length):
        # Parse the pipe extension to get the length
        # def _get_pipe_extension_length(center_tube):
        #     pipe_extension = ['Hollow Bar - OD152mm WT 26mm', 'Hollow Bar - OD168mm WT 21.5mm']
        #     if center_tube not in pipe_extension:
        #         return 0

        #     od_match = re.search(r'OD(\d+)', center_tube)
        #     id_match = re.search(r'ID(\d+)', center_tube)
        #     extension_length = 0
        #     if od_match and id_match:
        #         od = int(od_match.group(1))
        #         id_ = int(id_match.group(1))
        #         extension_length = (od - id_) / 2
        #     return extension_length

        # Return items for the base plate
        def _get_base_plate(dhead):
            base = ""
            if dhead == 'Drive Head - 100mm Square':
                base = 'Base Plate - 100mm Head'
            elif dhead == 'Drive Head - 110mm Square':
                base = 'Base Plate - 110mm Head'
            elif dhead in ['Drive Head - 130mm Square DIGGA', 'Drive Head - 130mm Square']:
                base = 'Base Plate - 130mm Head'
            else:
                base = ""
            return base

        def _get_center_tube_qty(cfa_type, center_tube, o_length_mm, female_height, male_height, pilot_supp_height, b_plate, zed_cent_height):
            """
            Return center tube qty based on a formula.
            Final output is in meters (rounded up to 1 decimal place).
            """
            with_pipe_extension = ['Hollow Bar - OD152mm WT 26mm', 'Hollow Bar - OD168mm WT 21.5mm']
            excluded_lead_type = ['Dual Rock', 'Taper Rock', 'Clay/Shale', 'Single Cut']

            c_qty = 0
            pipe_extension_length = 0
            if center_tube in with_pipe_extension:
                # pipe_extension_length = _get_pipe_extension_length(center_tube)
                pipe_extension_length = 0.25  # Fixed Length

            if cfa_type == 'Lead':
                if lead_type in excluded_lead_type:
                    c_qty = o_length_mm - female_height - pilot_supp_height - b_plate - pipe_extension_length
                else:
                    c_qty = o_length_mm - female_height - zed_cent_height - b_plate - pipe_extension_length
                # raise ValidationError(f"{o_length_mm} {female_height} {pilot_supp_height} {pipe_extension_length} {b_plate} >> {c_qty}")
            elif cfa_type == 'Intermediate':
                c_qty = o_length_mm - female_height - male_height - b_plate
            else:
                c_qty = o_length_mm - female_height - male_height
            # Convert to meters
            c_qty_meters = round(abs(c_qty), 2)
            return c_qty_meters

        def _get_inner_tube_qty(cfa_type, female_height, female_slot, male_height, male_slot, pilot_supp_height, zed_cent_height, elbow_height, b_plate, o_length_mm):
            """
            Return inner tube qty based on a formula.
            Final output is in meters (rounded up to 1 decimal place).
            """
            reg_lead_type = ['Dual Rock', 'Taper Rock', 'Clay/Shale', 'Single Cut']
            in_qty = 0
            if cfa_type == 'Lead':
                if lead_type in reg_lead_type:
                    # raise ValidationError(f"{o_length_mm}, {female_height}, {pilot_supp_height}, {elbow_height}, {b_plate}, {female_slot}")
                    in_qty = o_length_mm - female_height - pilot_supp_height - elbow_height - b_plate + female_slot
                else:
                    in_qty = o_length_mm - female_height - zed_cent_height - elbow_height - b_plate + female_slot
            elif cfa_type == 'Intermediate':
                in_qty = o_length_mm - female_height - male_height - b_plate + female_slot + male_slot
            else:
                in_qty = o_length_mm - female_height - male_height + female_slot + male_slot

            c_qty_meters = round(abs(in_qty), 2)
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
            "75NB elbow - Xxstrong Long radius": 158,
            "50NB Elbow - Xxstrong Long Radius Bend": 106,
            "40NB Elbow": 81
        }
        base_plate_map = {
            "Drive Head - 100mm Square": 25,
            "Drive Head - 110mm Square": 25,
            "Drive Head - 130mm Square": 32,
            "Drive Head - 130mm Square DIGGA": 32
        }
        female = self._get_cfa_female_coupling(drive_head)
        male = self._get_cfa_male_coupling(drive_head)

        # Get the height for overall length
        o_length = re.search(r'([\d.]+)\s*m\b', overall_length)
        o_length_mm = float(o_length.group(1)) if o_length else 0

        # Get the height and slot for male and female
        female_height = female[1] / 1000.0 if female else 0
        female_slot = female[2] / 1000.0 if female else 0
        male_height = male[1] / 1000.0 if male else 0
        male_slot = male[2] / 1000.0 if male else 0

        # Get the height for pilot, zed, elbow, and drive head
        _pilot_support = ""
        if pilot_support in ['19mm Teeth Pilot', '22mm Teeth Pilot']:
            _pilot_support = 'Pilot Support - Hex'
        elif pilot_support == '25mm Teeth Pilot':
            _pilot_support = 'Pilot Support - 75mm Square'
        else:
            _pilot_support = 'Pilot Support - 100mm Square'

        pilot_supp = pilot_supp_map.get(_pilot_support, 0) / 1000.0
        zed_cent = zed_center_map.get(zed_center, 0) / 1000.0
        elbow = elbow_map.get(elbow, 0) / 1000.0
        b_plate = base_plate_map.get(drive_head, 0) / 1000.0

        # Get the qty of the center tube and the inner tube
        cent_tube_qty = _get_center_tube_qty(cfa_type, center_tube, o_length_mm, female_height, male_height, pilot_supp, b_plate, zed_cent)
        inn_tube_qty = _get_inner_tube_qty(cfa_type, female_height, female_slot, male_height, male_slot, pilot_supp, zed_cent, elbow, b_plate, o_length_mm)

        # list of item components
        _none = (None, 0)
        female_indx = female[0] if female else ''
        c_female = (female_indx, 1)
        male_indx = male[0] if male else ''
        c_male = (male_indx, 1) if cfa_type in ['Intermediate', 'Extension'] else _none
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
            "4\" Hex Coupling": ["4\" Hex Coupling - Female", 155, 0],
            "35TM Coupling": ["35TM Coupling - Female", 289, 10],
            "53TM Coupling": ["53TM Coupling - Female", 250, 10],
            "Carrendeena 5\" Coupling": ["Carrendeena 5\" Coupling - Female", 230, 0],
            "Casagrande 5\" Coupling": ["Casagrande 5\" Coupling - Female", 230, 10],
            "HD4 Coupling": ["HD4 Coupling - Female", 220, 0],
            "HD5 Coupling": ["HD5 Coupling - Female", 220, 0],
            "25XHD5 Coupling": ["25XHD5 Coupling - Female", 365, 10],
            "XHD5 Coupling": ["XHD5 Coupling - Female", 242, 10],
            "XHD5 Mini Coupling": ["XHD5 Mini Coupling - Female", 242, 10],
            "Llamada Coupling": ["Llamada Coupling - Female", 279, 0],
            "MAIT175 Coupling": ["MAIT175 Coupling - Female", 240, 10],
            "MAIT200 Coupling": ["MAIT200 Coupling - Female", 304, 10],
            "TB2/TB80/SW80 Coupling": ["TB80/SW80 Coupling - Female", 148, 0],
            "SW110 Coupling (TB3)": ["SW110 Female Coupling", 170, 0],
            "SW150 Bauer Coupling": ["SW150 Bauer Female Octagon Coupling", 258, 0],
            "SW150 EMDE Coupling": ["SW150 Bauer Female Octagon Coupling", 225, 0],
            "SW175 Coupling": ["SW150 EMDE Female", 400, 0],
            "SW190 Coupling": ["SW175 Coupling - Female", 400, 10],
            "SW200 Coupling": ["SW200 Female Coupling", 446, 10],
            "SW250 Coupling": ["SW250 Female Coupling", 585, 10],
            "TB46 Coupling": ["TB46 Coupling - Female", 250, 10],
            "Drive Head - 75mm Square": ["Drive Head - 75mm Square", 150, 0],
            "Drive Head - 100mm Square": ["Drive Head - 100mm Square", 175, 0],
            "Drive Head - 110mm Square": ["Drive Head - 110mm Square", 240, 0],
            "Drive Head - 130mm Square": ["Drive Head - 130mm Square", 260, 0],
            "Drive Head - 130mm Square DIGGA": ["Drive Head - 130mm Square DIGGA", 260, 0]
        }
        return female_map.get(drive_head, [])

    def _get_cfa_male_coupling(self, drive_head):
        male_map = {
            "3.5\" API Coupling": ["3.5\" API Male coupling", 50, 0],
            "2\" Hex Coupling": ["2\" Hex Coupling - Male Male Joiner", 155, 0],
            "3\" Hex Coupling": ["3\" Hex Coupling - Male Male Joiner", 155, 0],
            "4\" Hex Coupling": ["4\" Hex Coupling - Male Male Joiner", 155, 0],
            "35TM Coupling": ["35TM Coupling - Male", 85, 10],
            "53TM Coupling": ["53TM Coupling - Male", 85, 10],
            "Carrendeena 5\" Coupling": ["Carrendeena 5\" Coupling - Male", 55, 0],
            "Casagrande 5\" Coupling": ["Casagrande 5\" Coupling - Male", 60, 10],
            "HD4 Coupling": ["HD4 Coupling - Male", 85, 0],
            "HD5 Coupling": ["HD5 Coupling - Male", 80, 0],
            "25XHD5 Coupling": ["25XHD5 Coupling - Male", 70, 10],
            "XHD5 Coupling": ["XHD5 Coupling - Male", 58.5, 10],
            "XHD5 Mini Coupling": ["XHD5 Mini Coupling - Male", 58, 10],
            "Llamada Coupling": ["Llamada Coupling - Male", 41, 0],
            "MAIT175 Coupling": ["MAIT175 Coupling - Male", 65, 10],
            "MAIT200 Coupling": ["MAIT200 Coupling - Male", 55, 10],
            "SW80 Coupling": ["TB80/SW80 Coupling - Male", 20, 0],
            "SW110 Coupling": ["SW110 Male Coupling", 35, 0],
            "SW150 EMDE Coupling": ["SW150 Bauer Male Coupling", 50, 0],
            "SW150 Bauer Coupling": ["SW150 EMDE Male", 100, 0],
            "SW175 Coupling": ["SW175 Coupling - male", 85, 10],
            "SW190 Coupling": ["SW190 Coupling - Male", 85, 10],
            "SW200 Coupling": ["SW200 Male Coupling", 145, 10],
            "SW250 Coupling": ["SW250 Male Coupling", 100, 10],
            "TB46 Coupling": ["TB46 Coupling - Male", 75, 10],
            "Drive Head - 75mm Square": ["75mm Square Adapter Stubb", 40, 0],
            "Drive Head - 100mm Square": ["100mm square Stubb", 50, 0],
            "Drive Head - 110mm Square": ["110mm Drive Stubb", 40, 0],
            "Drive Head - 130mm Square": ["130mm Stubb", 40, 0],
            "Drive Head - 130mm Square DIGGA": ["130mm Stubb - Digga", 40, 0]
        }
        return male_map.get(drive_head, [])

    def _get_cfa_flight_combination(self, flight_od, flight_pt, co_flight_id, diameter, center_tube, rotation):
        """
        Builds a non-stocked flight string from the given values.

        Args:
            flight PT (str): PT
            flight OD (str): OD
            Coupling ID (str): ID
            diameter (int): Auger diameter
            center_tube (str): Center tube description
            rotation (str): 'RH' or 'LH'

        Returns:
            str: Formatted stock flight string
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

        if co_flight_id and not center_tube:
            return ""
        # ID based on center_tube table
        flight_id = ""
        # flight_od = ""
        
        od_match = re.search(r'OD(\d+)', flight_od)
        flight_od = int(od_match.group(1))

        id_match = re.search(r'OD(\d+)', center_tube)
        
        # mm_match = re.search(r'-\s*(\d+)', flight_od)
        co_match = re.search(r'ID(\d+)', center_tube)

        if co_match and co_flight_id:
            flight_id = int(co_match.group(1))
        
        elif id_match:
            flight_id = int(id_match.group(1))

        pitch, thickness, turns = _parse_flight_values(flight_pt)

        # Combine flight attribute name
        # od_value = f"OD{diameter - 20}" if diameter < 1500 else f"OD{diameter - 30}"
        od_value = f"OD{flight_od}"
        id_value = f"ID{flight_id}"
        pitch = f"P{pitch}"
        thickness = f"T{thickness}"
        f_rotation = "RH" if rotation == 'Right Hand Rotation' else "LH"
        turns = f"R{turns}" if turns > 1 else ""

        return f"Flight - {od_value} {id_value} {pitch} {thickness} {f_rotation} {turns}"

    def _get_cfa_lead_ca_co_flights(self, cfa_type, lead_type, diameter, center_tube, l_flight_od, l_flight_pt, c_flight_od, c_flight_pt, co_flight_id, rotation, o_length, drive_head, override_bom):
        """
        Returns a list of tuples (flight_string, quantity) for non-stock lead and carrier flights.
        """
        # Build flight strings for lead, carrier, and coupling
        lead_flight_str = self._get_cfa_flight_combination(l_flight_od, l_flight_pt, False, diameter, center_tube, rotation)
        carrier_flight_str = self._get_cfa_flight_combination(c_flight_od, c_flight_pt, False, diameter, center_tube, rotation)
        coupling_flight_str = self._get_cfa_flight_combination(l_flight_od, l_flight_pt, True, diameter, co_flight_id, rotation)

        def _check_flights(flight):
            return self.env['product.product'].search_count([
                ('name', '=', flight)
            ]) > 0

        l_flight = _check_flights(lead_flight_str)
        ca_flight = _check_flights(carrier_flight_str)
        co_flight = _check_flights(coupling_flight_str)

        # Add validation to check the flight availability
        self._check_flight_validation(l_flight, ca_flight, co_flight, override_bom)

        # Get the qty of the lead flight
        lead_qty = self._get_cfa_lead_flight_qty(cfa_type, lead_type)
        ca_qty, co_qty = self._get_cfa_carrier_coupling_flight_qty(cfa_type, lead_flight_str, carrier_flight_str, coupling_flight_str, o_length, drive_head)
        _none = (None, 0)

        lst = [
            (lead_flight_str, lead_qty) if not override_bom else _none,
            (carrier_flight_str, abs(ca_qty)) if not override_bom else _none,
            (coupling_flight_str, abs(co_qty)) if not override_bom else _none
        ]
        components = [r for r in lst if r[0]]
        return components

    def _check_flight_validation(self, l_flight, ca_flight, co_flight, override_bom):
        flight = ""

        if not l_flight and not ca_flight:
            flight = "Lead & Carrier Flights"
        elif not l_flight and not co_flight:
            flight = "Lead & Coupling Flights"
        elif not ca_flight and not co_flight:
            flight = "Carrier & Coupling Flights"
        elif not l_flight:
            flight = "Lead Flight"
        elif not ca_flight:
            flight = "Carrier Flight"
        elif not co_flight:
            flight = "Coupling Flight"
        else:
            return  # nothing missing → no validation

        if not override_bom:
            raise ValidationError(
                f"Oops! {flight} is not available. Please review the selection or override the BOM."
            )

    def _get_cfa_lead_flight_qty(self, cfa_type, lead_type):
        lead_qty = 0
        if cfa_type == 'Lead' and lead_type in ['Clay/Shale', 'Blade', 'Single Cut']:
            lead_qty = 1
        else:
            lead_qty = 2
        return lead_qty

    def _get_cfa_carrier_coupling_flight_qty(self, cfa_type, l_flight, ca_flight, co_flight, overall_length, drive_head):
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

        # Then handle cases without coupling
        if l_flight or ca_flight or co_flight:
            l_pitch, l_no_turn = _get_pitch(l_flight)
            ca_pitch, ca_no_turn = _get_pitch(ca_flight)
            co_pitch, co_no_turn = _get_pitch(co_flight)

        # Get the height of female coupling
        female = self._get_cfa_female_coupling(drive_head)
        female_height = female[1] if female else 0
        o_length = re.search(r'([\d.]+)\s*m\b', overall_length)
        o_length_mm = float(o_length.group(1)) if o_length else 0

        co_qty = self._get_cfa_coflight_qty(female_height, co_pitch, co_no_turn, co_flight)
        ca_qty = self._get_cfa_caflight_qty(cfa_type, l_pitch, l_no_turn, ca_pitch, ca_no_turn, co_qty, o_length_mm)

        return ca_qty, co_qty

    def _get_cfa_caflight_qty(self, cfa_type, le_pitch, l_no_turn, car_pitch, ca_no_turn, co_qty, overall_length):
        o_length = overall_length
        l_pitch = le_pitch / 1000.0
        ca_pitch = car_pitch / 1000.0
        if cfa_type == "Lead":
            if ca_pitch * ca_no_turn != 0:
                qty = ((o_length - (l_pitch * l_no_turn)) / (ca_pitch * ca_no_turn)) - co_qty
                qty = math.ceil(qty * 2) / 2
                # qty = math.ceil(qty) # 2.5 + .5
                return qty
            return 0

        if cfa_type == 'Intermediate':
            if ca_pitch * ca_no_turn != 0:
                qty = (o_length / (ca_pitch * ca_no_turn)) - co_qty
                qty = math.ceil(qty * 2) / 2  # round-up to the nearest 0.5
                return qty
            return 0
        return 0

    def _get_cfa_coflight_qty(self, female_height, co_pitch, co_no_turn, co_flight):
        if not co_flight:
            return 0

        qty = female_height / (co_pitch * co_no_turn)
        qty = math.floor(qty * 2) / 2
        return qty
