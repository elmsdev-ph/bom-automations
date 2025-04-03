    def _create_bored_pile(self, product):
         """
         Create a BOM component for Bored Pile Auger
         """
         if product.product_tmpl_id.name != 'Bored Pile Auger':
             return
 
         reference = product.display_name
         components = self._get_bored_pile_component(product)
         _logger.info("bored pile components... %s", components)
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
         pilot = attributes.get('Pilot', '')
         center_tube = attributes.get('Centre Tube', '')
         lead_flight = attributes.get('>Lead Flight', '')
         carrier_flight = attributes.get('>Carrier Flight', '')
         non_lead_flight = attributes.get('* NON-STOCKED Lead Flight', '')
         non_carrier_flight = attributes.get('* NON-STOCKED Carrier Flight', '')
         carrier_type = attributes.get('Carrier Type (N/A if single or STD)', '')
 
         if type in ['Taper Rock', 'Dual Rock']:
             components = self._get_bp_dual_taper_rock(type, diameter, drive_head, overall_length, flighted_length, rotation, teeth, center_tube, lead_flight, carrier_flight, carrier_type, non_lead_flight, non_carrier_flight, pilot)
         elif type == 'Triad Rock':
             components = self._get_bp_triad_rock(type, diameter, drive_head, overall_length, flighted_length, rotation, teeth, center_tube, lead_flight, carrier_flight, carrier_type, non_lead_flight, non_carrier_flight, pilot)
         elif type in ['ZED 25mm', 'ZED 32mm', 'ZED 40mm', 'ZED 50mm']: 
             components = self._get_bp_zed(type, diameter, drive_head, overall_length, flighted_length, rotation, teeth, center_tube, lead_flight, carrier_flight, carrier_type, non_lead_flight, non_carrier_flight, pilot)
         elif type == 'Clay/Shale':
             components = self._get_bp_clay_shale(type, diameter, drive_head, overall_length, flighted_length, rotation, teeth, center_tube, lead_flight, carrier_flight, carrier_type, non_lead_flight, non_carrier_flight, pilot)
         else:
             # list of items for blade
             components = self._get_bp_blade(type, diameter, drive_head, overall_length, flighted_length, rotation, teeth, center_tube, lead_flight, carrier_flight, carrier_type, non_lead_flight, non_carrier_flight, pilot)
         return components
 
     def _get_bp_dhead_ears(self, dhead):
         if dhead not in ['Drive Head - 130mm Square DIGGA', 'Drive Head - 130mm Square']:
             return (None, 0)
 
         if dhead == 'Drive Head - 130mm Square':
             return (f"Drive Head EARS - 130mm Square", 2)
         else:
             return (f"Drive Head EARS - 130mm Square DIGGA", 4)
 
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
                 'Hollow Bar - OD128mm WT 11.5mm': "Gusset - 100mm Drive 150mm Tube",
                 'Hollow Bar - OD150mm ID120mm': "Gusset - 100mm Drive 150mm Tube",
                 'Hollow Bar - OD152mm WT 26mm': "Gusset - 100mm Drive 150mm Tube",
                 'Hollow Bar - OD152mm WT 33.5mm': "Gusset - 100mm Drive 150mm Tube",
                 'Hollow Bar - OD168mm WT 21.5mm': "Gusset - 100mm Drive 170mm Tube",
                 'Hollow Bar - OD168mm WT 29mm': "Gusset - 100mm Drive 170mm Tube",
                 'Hollow Bar - OD180mm ID140mm': "Gusset - 100mm Drive 170mm Tube",
                 'Hollow Bar - OD180 ID150': "Gusset - 100mm Drive 170mm Tube",
                 'Hollow bar - OD200 ID150': "Gusset - 100mm Drive 170mm Tube",
                 'Hollow Bar - OD219mm WT 25mm': "Gusset - 100mm Drive 219mm Tube ",
                 'Pipe - OD168mm WT11mm': "Gusset - 100mm Drive 170mm Tube",
                 'Pipe - OD219mm WT12.7mm': "Gusset - 100mm Drive 219mm Tube",
             },
             'dhead_130_mm': {
                 'Hollow Bar - OD150mm ID120mm': "Gusset - 130mm Drive 150mm Tube",
                 'Hollow Bar - OD152mm WT 26mm': "Gusset - 130mm Drive 150mm Tube",
                 'Hollow Bar - OD152mm WT 33.5mm': "Gusset - 130mm Drive 150mm Tube",
                 'Hollow Bar - OD168mm WT 21.5mm': "Gusset - 130mm Drive 170mm Tube",
                 'Hollow Bar - OD168mm WT 29mm': "Gusset - 130mm Drive 170mm Tube",
                 'Hollow Bar - OD180mm ID140mm': "Gusset - 130mm Drive 170mm Tube",
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
                 'Pipe - OD323mm WT12.7mm ': "Gusset - 130mm Drive 323mm Tube",
                 'Pipe - OD355mm WT12.7mm ': "Gusset - 130mm Drive 323mm Tube",
                 'Pipe - OD457mm WT15.9mm ': "Gusset - 130mm Drive 323mm Tube",
             },
             'dhead_150_mm': {
                 'Hollow Bar - OD150mm ID120mm': "Gusset - 150mm Drive 150mm Tube",
                 'Hollow Bar - OD152mm WT 26mm': "Gusset - 150mm Drive 150mm Tube",
                 'Hollow Bar - OD152mm WT 33.5mm': "Gusset - 150mm Drive 150mm Tube",
                 'Hollow Bar - OD168mm WT 21.5mm': "Gusset - 150mm Drive 170mm Tube",
                 'Hollow Bar - OD168mm WT 29mm': "Gusset - 150mm Drive 170mm Tube",
                 'Hollow Bar - OD180mm ID140mm': "Gusset - 150mm Drive 170mm Tube",
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
                 'Pipe - OD168mm WT11mm': "Gusset - 130mm Drive 170mm Tube",
                 'Pipe - OD219mm WT12.7mm': "Gusset - 130mm Drive 219mm Tube",
                 'Pipe - OD273mm WT12.7mm': "Gusset - 150mm Drive 273mm Tube",
                 'Pipe - OD323mm WT12.7mm ': "Gusset - 150mm Drive 273mm Tube",
                 'Pipe - OD355mm WT12.7mm ': "Gusset - 150mm Drive 273mm Tube",
                 'Pipe - OD457mm WT15.9mm ': "Gusset - 150mm Drive 273mm Tube",
             },
             'dhead_200_mm': {
                 'Hollow Bar - OD168mm WT 21.5mm': "Gusset - 200mm Drive 170mm Tube",
                 'Hollow Bar - OD168mm WT 29mm': "Gusset - 200mm Drive 170mm Tube",
                 'Hollow Bar - OD180mm ID140mm': "Gusset - 200mm Drive 170mm Tube",
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
                 'Pipe - OD323mm WT12.7mm ': "Gusset - 200mm Drive 273mm Tube",
                 'Pipe - OD355mm WT12.7mm ': "Gusset - 200mm Drive 273mm Tube",
                 'Pipe - OD457mm WT15.9mm ': "Gusset - 200mm Drive 273mm Tube",
             }
         }
 
         # Support for shared mapping between similar drive heads
         d_head = ''
         if drive_head in dhead_100_110_mm:
             d_head = 'dhead_100_110_mm'
         if drive_head in dhead_130_mm:
             d_head = 'dhead_130_mm'
         if drive_head in dhead_150_mm:
             d_head = 'dhead_150_mm'
         if drive_head in dhead_200_mm:
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
             "Drive Head - 65mm Round": 100,
             "Drive Head - 65mm Square": 100,
             "Drive Head - 75mm Square": 150,
             "Drive Head - 100mm Square": 175,
             "Drive Head - 110mm Square": 240,
             "Drive Head - 130mm Square": 260,
             "Drive Head - 130mm Square DIGGA": 260,
             "Drive Head - 150mm Square": 260,
             "Drive Head - 150mm Square IMT": 260,
             "Drive Head - 200mm Square Bauer": 475,
             "Drive Head - 200mm Square MAIT": 345,
             "Drive Head - 4\" Lo Drill": 332,
             "Drive Head - 3\" Hex": 155,
             "Drive Head - 2\" Hex": 135
         }
         drive_head_height = drive_head_map.get(drive_head, 0)
         zed_height_map = {
             "ZED Centre 150mm": o_length - drive_head_height - 133.5,
             "ZED Centre 168mm": o_length - drive_head_height - 147.5,
             "ZED Centre 219mm": o_length - drive_head_height - 163,
             "ZED Centre 273mm": o_length - drive_head_height - 25 - 163
         }
         return (center_tube, zed_height_map.get(zed_center, 0))
 
     def _get_center_tube(self, overall_length, drive_head, center_tube, pilot_height):
         match = re.search(r'\d+', overall_length)
         o_length = int(match.group()) if match else 0
 
         pilot_map = {
             "Pilot Support - Hex": 75,
             "Pilot Support - 75mm Square": 70,
             "Pilot Support - 100mm Square": 100,
             "Pipe - OD101mm WT4.0mm": 70,
         }
         drive_head_map = {
             "Drive Head - 65mm Round": o_length - 100 - pilot_map.get(pilot_height, 0),
             "Drive Head - 65mm Square": o_length - 100 - pilot_map.get(pilot_height, 0),
             "Drive Head - 75mm Square": o_length - 150 - pilot_map.get(pilot_height, 0),
             "Drive Head - 100mm Square": o_length - 175 - 25 - pilot_map.get(pilot_height, 0),
             "Drive Head - 110mm Square": o_length - 240 - 25 - pilot_map.get(pilot_height, 0),
             "Drive Head - 130mm Square": o_length - 260 - 32 - pilot_map.get(pilot_height, 0),
             "Drive Head - 130mm Square DIGGA": o_length - 260 - 32 - pilot_map.get(pilot_height, 0),
             "Drive Head - 150mm Square": o_length - 260 - 32 - pilot_map.get(pilot_height, 0),
             "Drive Head - 150mm Square IMT": o_length - 260 - 32 - pilot_map.get(pilot_height, 0),
             "Drive Head - 200mm Square Bauer": o_length - 475 - 32 - pilot_map.get(pilot_height, 0),
             "Drive Head - 200mm Square MAIT": o_length - 345 - 32 - pilot_map.get(pilot_height, 0),
             "Drive Head - 4\" Lo Drill": o_length - 332 - 25 - pilot_map.get(pilot_height, 0),
             "Drive Head - 3\" Hex": o_length - 155 - pilot_map.get(pilot_height, 0),
             "Drive Head - 2\" Hex": o_length - 135 - pilot_map.get(pilot_height, 0),
         }
         return (center_tube, drive_head_map.get(drive_head, 0))
 
     def _get_flight_brace_components(self, dhead, carrier_type):
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
             return (None, 0)
 
         fb_qty = 2 if carrier_type == "Dual Carrier" else 1
         return {
             (0, 750): (None, 0),
             (750, 900): ("750mm flight brace 180mm long", fb_qty),
             (900, 1050): ("900mm Flight brace 230mm long", fb_qty),
             (1050, 1200): ("1050mm flight brace 280mm long", fb_qty),
             (1200, 1350): ("1200mm Flight Brace 330mm long", fb_qty),
             (1350, 5000): ("1350mm+ flight brace 480mm long", fb_qty),
         }
 
     def _get_carrier_flight_qty(self, type, carrier_type, lead_flight, carrier_flight, n_lead_flight, n_carrier_flight, flighted_length):
         """ 
             We calculate the stock or non-stock carrier flight qty
         """
         flight_length = re.findall(r'\d+', flighted_length)[0]
         flight_length_num = int(flight_length)
 
         def _get_pitch(res):
             p_match = re.search(r'P(\d+)', res)
             r_match = re.search(r'R(\d+\.\d+)', res)
 
             pitch = int(p_match.group(1)) if p_match else 1
             turns = float(r_match.group(1)) if r_match else 1
 
             return pitch, turns
 
         l_pitch = l_no_turn = c_pitch = c_no_turn = 0
         if lead_flight and carrier_flight:
             l_pitch, l_no_turn = _get_pitch(lead_flight or "")
             c_pitch, c_no_turn = _get_pitch(carrier_flight or "")
         elif n_lead_flight and n_carrier_flight:
             l_pitch, l_no_turn = _get_pitch(n_lead_flight or "")
             c_pitch, c_no_turn = _get_pitch(n_carrier_flight or "")
         elif lead_flight and n_carrier_flight:
             l_pitch, l_no_turn = _get_pitch(lead_flight or "")
             c_pitch, c_no_turn = _get_pitch(n_carrier_flight or "")
         elif carrier_flight and n_lead_flight:
             l_pitch, l_no_turn = _get_pitch(carrier_flight or "")
             c_pitch, c_no_turn = _get_pitch(n_lead_flight or "")
 
         qty = self._get_cflight_qty(type, carrier_type, flight_length_num, l_pitch, l_no_turn, c_pitch, c_no_turn)
         return qty
 
     def _get_cflight_qty(self, type, carrier_type, flight_length_num, lead_pitch, l_no_turn, carrier_pitch, c_no_turn):
         auger_type = ['Dual Rock', 'Taper Rock', 'ZED 25mm', 'ZED 32mm', 'ZED 40mm', 'ZED 50mm']
 
         qty = 0
         if carrier_type == "Dual Carrier":
             if type in auger_type:
                 qty = (flight_length_num - (lead_pitch * l_no_turn)) / (carrier_pitch * c_no_turn) * 2
             else:
                 qty = 0
         else:
             if type in auger_type:
                 qty = (flight_length_num - (lead_pitch * l_no_turn)) / (carrier_pitch * c_no_turn)
             elif type in ['Clay/Shale', 'Blade']:
                 _logger.info(f"xx {flight_length_num}, {lead_pitch}, {l_no_turn}, {carrier_pitch}, {c_no_turn}")
                 qty = (flight_length_num - (lead_pitch * l_no_turn)) / (carrier_pitch * c_no_turn) * 2
             elif type in ['Triad Rock']:
                 qty = (flight_length_num - (lead_pitch * l_no_turn * 0.4)) / (carrier_pitch * c_no_turn)
             else:
                 qty = 0
 
         qty = math.ceil(qty * 2) / 2
         return qty
 
     def _get_center_tube_id(self):
         return {
                 "4340 Black bar - 50mm Diameter": "ID50",
                 "4140 Bright bar - 50mm": "ID50",
                 "4140 Black bar - 70mm": "ID70",
                 "4340 Black bar - 70mm": "ID70",
                 "4340 Black bar - 90mm": "ID90",
                 "4140 Bright bar - 90mm": "ID90",
                 "Hollow bar - OD70 ID40": "ID70",
                 "Hollow bar - OD75 ID50": "ID75",
                 "Hollow bar - OD75 ID55": "ID75",
                 "Hollow bar - OD85 ID70": "ID85",
                 "Hollow bar - OD90 ID60": "ID90",
                 "Hollow Bar - OD90 ID65": "ID90",
                 "hollow bar - OD90 ID70": "ID90",
                 "Hollow Bar - OD100 ID65mm": "ID100",
                 "Hollow Bar - OD100mm ID55mm": "ID100",
                 "Hollow Bar - OD100mm ID75mm": "ID100",
                 "Hollow Bar - OD100mm ID80mm": "ID100",
                 "Hollow Bar - OD110 ID70": "ID110",
                 "Hollow Bar - OD128mm WT 11.5mm": "ID128",
                 "Hollow Bar - OD150mm ID120mm": "ID150",
                 "Hollow Bar - OD152mm WT 26mm": "ID152",
                 "Hollow Bar - OD152mm WT 33.5mm": "ID152",
                 "Hollow Bar - OD168mm WT 21.5mm": "ID168",
                 "Hollow Bar - OD168mm WT 29mm": "ID168",
                 "Hollow Bar - OD170mm ID140mm": "ID170",
                 "Hollow Bar - OD180 ID150": "ID180",
                 "Hollow Bar - OD200 ID150": "ID200",
                 "Pipe - OD219mm WT 25mm": "ID219",
                 "Pipe - OD273mm WT14": "ID273",
                 "Pipe - OD273mm WT 25mm": "ID273",
                 "Pipe - OD273mm WT 32mm": "ID273",
                 "Pipe - OD323mm WT25mm": "ID323",
                 "Pipe - OD323mm WT30mm": "ID323",
                 "Pipe - OD356 ID306": "ID356",
                 "Pipe - OD457mm T35mm": "ID457",
                 "Pipe - OD457mm T25mm": "ID457",
                 "Pipe - OD101mm WT4.0mm": "ID101",
                 "Pipe - OD114mm WT6.0mm": "ID114",
                 "Pipe - OD114mm WT8.56mm": "ID114",
                 "Pipe - OD168mm WT11mm": "ID168",
                 "Pipe - OD219mm WT12.7mm": "ID219",
                 "Pipe - OD273mm WT12.7mm": "ID273",
                 "Pipe - OD323mm WT12.7mm": "ID323",
                 "Pipe - OD355mm WT12.7mm": "ID355",
                 "Pipe - OD457mm WT15.9mm": "ID457",
             }
 
     def _get_non_stock_lead_carrier_flight(self, auger_type, carrier_type, diameter, center_tube, non_lead_flight, non_carrier_flight, rotation, flighted_length, carrier_qty):
         """
         Returns a list of tuples (flight_string, quantity) for non-stock lead and carrier flights.
         """
         def _get_non_stock_flight(non_stock_flight, diameter, center_tube, rotation):
             """
             Builds a non-stocked flight string from the given values.
 
             Args:
                 non_stock_flight (str): e.g. 'P100 T6 R1.0 - Non-Stocked Lead Flight'
                 diameter (int): Auger diameter
                 center_tube (str): Center tube description
                 rotation (str): 'RH' or 'LH'
 
             Returns:
                 str: Formatted non-stocked flight string
             """
             if not non_stock_flight:
                 return ""
             # Step 1: OD based on auger diameter
             od_value = f"OD{diameter - 20}" if diameter < 1500 else f"OD{diameter - 30}"
 
             # Step 2: ID based on center_tube table
             id_map = self._get_center_tube_id()
             id_value = id_map.get(center_tube, "")
 
             # Setp 6: Rotation
             f_rotation = "RH" if rotation == 'Right Hand Rotation' else "LH"
 
             # Step 3-5: Parse non_stock_flight to get P, T, R
             pitch, thickness, turns = self._parse_flight_values(non_stock_flight)
             pitch = f"P{pitch}"
             thickness = f"T{thickness}"
             turns = f"R{turns}"
 
             return f"Flight - {od_value} {id_value} {pitch} {thickness} {f_rotation} {turns} - Non-Stocked"
 
         # Build flight strings
         lead_flight_str = _get_non_stock_flight(non_lead_flight, diameter, center_tube, rotation)
         carrier_flight_str = _get_non_stock_flight(non_carrier_flight, diameter, center_tube, rotation)
 
         # Non-stocked Quantities
         if auger_type == "Triad Rock":
             lead_qty = 3 if diameter > 650 else 1
         else:
             lead_qty = 2
 
         return [
             (lead_flight_str or None, lead_qty if lead_flight_str else 0),
             (carrier_flight_str or None, carrier_qty if carrier_flight_str else 0)
         ]
 
     def _get_stock_lead_carrier_flight(self, auger_type, carrier_type, diameter, lead_flight, carrier_flight, flighted_length, carrier_qty):
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
         Merge stock and non-stock flights, excluding any where the label is None.
         Returns only valid (non-None) entries.
         """
         stock = stock or []
         non_stock = non_stock or []
 
         result = []
 
         for (non_item, non_qty), (stock_item, stock_qty) in zip(non_stock, stock):
             if non_item:
                 result.append((non_item, non_qty))
             if stock_item:
                 result.append((stock_item, stock_qty))
 
         return result
 
     def _parse_flight_values(self, flight_string):
         """
         Extract pitch, thickness, and optionally turns from a flight string.
         """
         pitch = thickness = turns = 0
 
         # Look for Pitch (P...), Thickness (T...), and Turns (R...)
         p_match = re.search(r'P(\d+)', flight_string)
         t_match = re.search(r'T(\d+)', flight_string)
         r_match = re.search(r'R(\d+\.\d+)', flight_string)
 
         if p_match:
             pitch = int(p_match.group(1))
         if t_match:
             thickness = int(t_match.group(1))
         if r_match:
             turns = float(r_match.group(1))  # Only if R is present
 
         return pitch, thickness, turns
 
     # functions to get the teeth combination 
     def _get_teeth_qty(self, diameter, mm1, mm2, mm3):
         qty = ((diameter - mm1 - mm2) / mm3) + 8
         # Round up to the nearest integer first
         qty = round(qty)
         # If even, add 1 to make it odd
         if qty % 2 == 0:
             qty += 1
         return qty
 
     def _get_teeth_dual_taper_rock(self, diameter, teeth, pilot):
             
         if teeth == '19mm BK17 Teeth':
             teeth_qty = 0
             if diameter < 1500:
                 teeth_qty = self._get_teeth_qty(diameter, 78, 20, 40)
             else:
                 teeth_qty = self._get_teeth_qty(diameter, 78, 30, 40)
             return [
                 ('BSK17 - 19.4mm Shank Teeth', teeth_qty),
                 ('BHR164 - 19.4mm Block Holder', teeth_qty - 4),
                 ('Rock Pilot suit 19mm Teeth 44mm Hex - RH / LH', 1),
                 ('Pilot Support - Hex', 1),
                 ('End Cap - Suit Hex Pilot Support', 1)
             ]
         elif teeth in ['22mm BC86 Teeth', '22mm BC05 Teeth']:
             teeth_22mm = 'BC86 - 22mm Shank Teeth BETEK' if teeth == '22mm BC86 Teeth' else 'BC05 - 22mm Shank Teeth BETEK'
             teeth_qty = 0
             if diameter < 1500:
                 teeth_qty = self._get_teeth_qty(diameter, 78, 20, 42)
             else:
                 teeth_qty = self._get_teeth_qty(diameter, 78, 30, 42)
             return [
                 (teeth_22mm, teeth_qty),
                 ('BHR176 - 22mm Block Tooth Holder', teeth_qty - 4),
                 ('Rock Pilot suit 22mm Teeth 44mm Hex - RH / LH', 1),
                 ('Pilot Support - Hex', 1),
                 ('End Cap - Suit Hex Pilot Support', 1)
             ]
         elif teeth == '25mm BTK03 Teeth':
             teeth_qty = 0
             if diameter < 1500:
                 teeth_qty = self._get_teeth_qty(diameter, 150, 20, 44)
             else:
                 teeth_qty = self._get_teeth_qty(diameter, 150, 30, 44)
             return [
                 ('BTK03TB - 25mm Shank Teeth', teeth_qty),
                 ('BHR31 - 25mm Block Tooth Holder', teeth_qty - 4),
                 ('Rock Auger Pilot - 25mm Shank 75mm square', 1),
                 ('Pilot Support - 75mm Square', 1),
                 ('End Cap - Suit 75mm Square Pilot Support', 1)
             ]
         elif teeth in ['38/30 BKH105 Teeth', '38/30 BFZ162 Teeth']:
             teeth_qty = 0
             if diameter < 1500:
                 teeth_qty = self._get_teeth_qty(diameter, 200, 20, 66)
             else:
                 teeth_qty = self._get_teeth_qty(diameter, 200, 30, 66)
             return [
                 ('BKH105TB - 38/30mm Shank Teeth', teeth_qty),
                 ('BHR38 - 38/30mm Block Tooth Holder', teeth_qty - 4),
                 ('Rock Auger Pilot - 38/30mm Shank 100mm Square', 1),
                 ('Pilot Support - 100mm Square', 1),
                 ('End Cap - Suit 100mm Square Pilot Support', 1)
             ]
         else:
             return []
 
     def _get_teeth_zed(self, diameter, center_tube, teeth):
         # Parse to get the OD number of center tube
         od_match = re.search(r'OD(\d+)', center_tube)
         center_tube_od = int(od_match.group(1)) if od_match else 0
         
         teeth_qty = 0
         # Round the qty to the nearest integer
         teeth_qty = round(teeth_qty)
         # If the number is odd, make it even
         if teeth_qty % 2 != 0:
             teeth_qty += 1
 
         if teeth == '22mm BC05 Teeth':
             if diameter < 1500:
                 teeth_qty = ((diameter - center_tube_od - 20) / 42) * 2
             else:
                 teeth_qty = ((diameter - center_tube_od - 30) / 42) * 2
             # If even, add 1 to make it odd
             if teeth_qty % 2 == 0:
                 teeth_qty += 1
 
             lst = [
                 ('BC05 - 22mm Shank Teeth BETEK', teeth_qty),
                 ('BHR176 - 22mm Block Tooth Holder', teeth_qty),
                 ('BA13 - Weld on Button Carbide', teeth_qty / 2)
             ]
             item = (
                 'ZED Flight Stiffener (Under 600mm)', 2
             ) if diameter < 600 else (
                 'ZED Flight Stiffener (600mm+)', 2
             )
             lst.append(item)
             return lst
 
         elif teeth == '25mm BTK03 Teeth':
             if diameter < 1500:
                 teeth_qty = ((diameter - center_tube_od - 20) / 44) * 2
             else:
                 teeth_qty = ((diameter - center_tube_od - 30) / 44) * 2
             # If even, add 1 to make it odd
             if teeth_qty % 2 == 0:
                 teeth_qty += 1
 
             lst = [
                 ('BTK03TB - 25mm Shank Teeth', teeth_qty),
                 ('BHR31 - 25mm Block Tooth Holder', teeth_qty),
                 ('BA13 - Weld on Button Carbide', teeth_qty / 2),
             ]
             item = (
                 'ZED Flight Stiffener (Under 600mm)', 2
             ) if diameter < 600 else (
                 'ZED Flight Stiffener (600mm+)', 2
             )
             lst.append(item)
             return lst
 
         elif teeth in ['38/30 BKH105 Teeth', '38/30 BFZ162 Teeth']:
             if diameter < 1500:
                 teeth_qty = ((diameter - center_tube_od - 20) / 66) * 2
             else:
                 teeth_qty = ((diameter - center_tube_od - 30) / 66) * 2
             # If even, add 1 to make it odd
             if teeth_qty % 2 == 0:
                 teeth_qty += 1
 
             lst = [
                 ('BKH105TB - 38/30mm Shank Teeth', teeth_qty),
                 ('BHR38 - 38/30mm Block Tooth Holder', teeth_qty),
                 ('BA13 - Weld on Button Carbide', teeth_qty / 2),
             ]
             item = (
                 'ZED Flight Stiffener (Under 600mm)', 2
             ) if diameter < 600 else (
                 'ZED Flight Stiffener (600mm+)', 2
             )
             lst.append(item)
             return lst
 
         else:
             return []
 
     def _get_teeth_triad_rock(self, diameter, teeth):
         if teeth != '22mm BC86 Teeth':
             return
 
         teeth_qty = 0
         if diameter < 1500:
             teeth_qty = ((diameter - 78 - 20) / 84) * 3 + 4
         else:
             teeth_qty = ((diameter - 78 - 30) / 84) * 3 + 4
         # Round the qty to the nearest integer
         teeth_qty = round(teeth_qty)
         # If even, add 1 to make it odd
         if teeth_qty % 2 == 0:
             teeth_qty += 1
 
         return [
             ('BC86 - 22mm Shank Teeth BETEK', teeth_qty),
             ('BHR176 - 22mm Block Tooth Holder', teeth_qty - 4),
             ('Rock Pilot suit 22mm Teeth 44mm Hex - RH / LH', 1),
             ('Pilot Support - Hex', 1),
             ('End Cap - Suit Hex Pilot Support', 1)
         ]
 
     def _get_teeth_clay_shale(self, diameter, teeth, pilot):
         # if teeth != 'AR150 Teeth' and pilot != 'Hex Auger Torque Fishtail Pilot':
         #     return
 
         if diameter == 300:
             return [
                 ('AR150 Teeth', 4),
                 ('300mm Clay Shale Teeth Holder', 2),
                 ('Auger Pilot - Hex Auger Torque Fishtail', 1),
                 ('Pilot Support - Hex', 1),
                 ('End Cap - Suit Hex Pilot Support', 1)
             ]
         elif diameter == 400:
             return [
                 ('AR150 Teeth', 8),
                 ('400mm Clay Shale Teeth Holder', 2),
                 ('Auger Pilot - Hex Auger Torque Fishtail', 1),
                 ('Pilot Support - Hex', 1),
                 ('End Cap - Suit Hex Pilot Support', 1)
             ]
         elif diameter == 450:
             return [
                 ('AR150 Teeth', 8),
                 ('450mm Clay Shale Teeth Holder', 2),
                 ('Auger Pilot - Hex Auger Torque Fishtail', 1),
                 ('Pilot Support - Hex', 1),
                 ('End Cap - Suit Hex Pilot Support', 1)
             ]
         elif diameter == 600:
             return [
                 ('AR150 Teeth', 2),
                 ('600mm Clay Shale Teeth Holder', 2),
                 ('Auger Pilot - Hex Auger Torque Fishtail', 1),
                 ('Pilot Support - Hex', 1),
                 ('End Cap - Suit Hex Pilot Support', 1)
             ]
         else:
             return []
 
     def _get_teeth_blade(self, diameter, teeth, pilot):
         pilot = 'Auger Pilot - Hex Auger Torque Fishtail' if pilot == 'Hex Auger Torque Fishtail Pilot' else 'Blade Auger Fishtail Pilot'
         pilot_supp = 'Pilot Support - Hex' if pilot == 'Hex Auger Torque Fishtail Pilot' else 'Pipe - OD101mm WT4.0mm'
         end_cap = ('End Cap - Suit Hex Pilot Support', 1) if pilot_supp == 'Pilot Support - Hex' else (None, 0)
         if diameter == 300:
             return [
                 ('300mm Hardfaced Blade Teeth', 2),
                 ('300mm Blade Holder', 2), 
                 (pilot, 1),
                 (pilot_supp, 1),
                 end_cap
             ]
         elif diameter == 400:
             return [
                 ('400mm Hardfaced Blade Teeth', 2),
                 ('400mm Blade Holder', 2), 
                 (pilot, 1),
                 (pilot_supp, 1),
                 end_cap
             ]
         elif diameter == 450:
             return [
                 ('450mm Hardfaced Blade Teeth', 2),
                 ('450mm Blade Holder', 2), 
                 (pilot, 1),
                 (pilot_supp, 1),
                 end_cap
             ]
         else:
             return []
 
     def _get_bp_dual_taper_rock(self, type, diameter, drive_head, overall_length, flighted_length, rotation, teeth, center_tube, lead_flight, carrier_flight, carrier_type, non_lead_flight, non_carrier_flight, pilot):
         d_number = re.findall(r'\d+', diameter)[0]
         diameter = int(d_number)
         
         d_head_75mm = "Drive Head - 75mm Square"
         h_bar_od150 = "Hollow Bar - OD150mm ID120mm"
         stiffening_ring = "Stiffening Ring - 75mm Head" if drive_head == d_head_75mm and center_tube == h_bar_od150 else ""
 
         d_head_ears = self._get_bp_dhead_ears(drive_head)
         base_plate = self._get_base_plate(drive_head)
         tube_gusset = self._get_tube_guesset(drive_head, center_tube)
         fb_components = self._get_flight_brace_components(drive_head, carrier_type)
         flight_brace = self._get_range_per_diameter(fb_components, diameter)
 
         carrier_qty = self._get_carrier_flight_qty(type, carrier_type, lead_flight, carrier_flight, non_lead_flight, non_carrier_flight, flighted_length)
         non_stock_lead_carrier_flight = self._get_non_stock_lead_carrier_flight(type, carrier_type, diameter, center_tube, non_lead_flight, non_carrier_flight, rotation, flighted_length, carrier_qty)
         stock_lead_carrier_flight = self._get_stock_lead_carrier_flight(type, carrier_type, diameter, lead_flight, carrier_flight, flighted_length, carrier_qty)
         l_flight, c_flight = self._get_non_or_stock_flights(non_stock_lead_carrier_flight, stock_lead_carrier_flight)
         teeth, tooth_holder, pilot, pilot_support, end_cap = self._get_teeth_dual_taper_rock(diameter, teeth, pilot)
         _center_tube = self._get_center_tube(overall_length, drive_head, center_tube, pilot_support)
 
         fb_item, fb_qty = flight_brace if flight_brace else (None, 0)
         stiffening = (stiffening_ring, 1) if stiffening_ring else (None, 0) 
         _none = (None, 0)
     
         components = [
             (drive_head, 1),
             d_head_ears,
             stiffening, 
             base_plate,
             tube_gusset,
             (fb_item, fb_qty),
             _center_tube or _none,
             l_flight,
             c_flight,
             teeth,
             tooth_holder,
             pilot, 
             pilot_support,
             end_cap
         ]
         # exclude none values
         components = [c for c in components if c[0] and c[1]]
 
         return components
 
     def _get_bp_triad_rock(self, type, diameter, drive_head, overall_length, flighted_length, rotation, teeth, center_tube, lead_flight, carrier_flight, carrier_type, non_lead_flight, non_carrier_flight, pilot):
         d_number = re.findall(r'\d+', diameter)[0]
         diameter = int(d_number)
 
         carrier_qty = self._get_carrier_flight_qty(type, carrier_type, lead_flight, carrier_flight, non_lead_flight, non_carrier_flight, flighted_length)
         non_stock_lead_carrier_flight = self._get_non_stock_lead_carrier_flight(type, carrier_type, diameter, center_tube, non_lead_flight, non_carrier_flight, rotation, flighted_length, carrier_qty)
         stock_lead_carrier_flight = self._get_stock_lead_carrier_flight(type, carrier_type, diameter, lead_flight, carrier_flight, flighted_length, carrier_qty)
         l_flight, c_flight = self._get_non_or_stock_flights(non_stock_lead_carrier_flight, stock_lead_carrier_flight)
         teeth_triad_rock = self._get_teeth_triad_rock(diameter, teeth)
         teeth, tooth_holder, pilot, pilot_support, end_cap = teeth_triad_rock or (None, None, None, None, None)
         _center_tube = self._get_center_tube(overall_length, drive_head, center_tube, pilot_support)
         _none = (None, 0)
 
         components = [
             (drive_head, 1),
             _center_tube or _none,
             l_flight,
             c_flight,
             teeth,
             tooth_holder,
             pilot,
             pilot_support,
             end_cap
         ]
         # exclude none values
         components = [c for c in components if c and c[0] and c[1]]
 
         return components
 
     def _get_bp_zed(self, type, diameter, drive_head, overall_length, flighted_length, rotation, teeth, center_tube, lead_flight, carrier_flight, carrier_type, non_lead_flight, non_carrier_flight, pilot):
         d_number = re.findall(r'\d+', diameter)[0]
         diameter = int(d_number)
 
         pilot_support = "None"
         d_head_75mm = "Drive Head - 75mm Square"
         h_bar_od150 = "Hollow Bar - OD150mm ID120mm"
         stiffening_ring = "Stiffening Ring - 75mm Head" if drive_head == d_head_75mm and center_tube == h_bar_od150 else ""
 
         d_head_ears = self._get_bp_dhead_ears(drive_head)
         base_plate = self._get_base_plate(drive_head)
         tube_gusset = self._get_tube_guesset(drive_head, center_tube)
         fb_components = self._get_flight_brace_components(drive_head, carrier_type)
         flight_brace = self._get_range_per_diameter(fb_components, diameter) if fb_components else []
         fb_item, fb_qty = flight_brace if flight_brace else (None, 0)
 
         carrier_qty =  self._get_carrier_flight_qty(type, carrier_type, lead_flight, carrier_flight, non_lead_flight, non_carrier_flight, flighted_length)
         non_stock_lead_carrier_flight = self._get_non_stock_lead_carrier_flight(type, carrier_type, diameter, center_tube, non_lead_flight, non_carrier_flight, rotation, flighted_length, carrier_qty)
         stock_lead_carrier_flight = self._get_stock_lead_carrier_flight(type, carrier_type, diameter, lead_flight, carrier_flight, flighted_length, carrier_qty)
         l_flight, c_flight = self._get_non_or_stock_flights(non_stock_lead_carrier_flight, stock_lead_carrier_flight)
         zed_centre = self._get_zed_center_component_map(center_tube)
         _center_tube = self._get_center_tube_zed(overall_length, drive_head, center_tube, zed_centre)
         teeth_zed = self._get_teeth_zed(diameter, center_tube, teeth) 
         teeth, tooth_holder, weld, zed_flight = teeth_zed or (None, None, None, None)
 
         stiffening = (stiffening_ring, 1) if stiffening_ring else (None, 0)
         teeth_brace = ('ZED Auger Teeth Brace', 2)
         _none = (None, 0)
 
         components = [
             (drive_head, 1),
             d_head_ears,
             stiffening, 
             base_plate,
             tube_gusset,
             (fb_item, fb_qty),
             _center_tube or _none,
             l_flight,
             c_flight,
             teeth,
             tooth_holder,
             weld,
             teeth_brace,
             zed_flight,
             (zed_centre, 1)
         ]
         # exclude none e.g (None, (None, 0), ('', 0))
         components = [c for c in components if c and c[0] and c[1]]
 
         return components
 
     def _get_bp_clay_shale(self, type, diameter, drive_head, overall_length, flighted_length, rotation, teeth, center_tube, lead_flight, carrier_flight, carrier_type, non_lead_flight, non_carrier_flight, pilot):
         d_number = re.findall(r'\d+', diameter)[0]
         diameter = int(d_number)
 
         d_head_75mm = "Drive Head - 75mm Square"
         h_bar_od150 = "Hollow Bar - OD150mm ID120mm"
         stiffening_ring = "Stiffening Ring - 75mm Head" if drive_head == d_head_75mm and center_tube == h_bar_od150 else ""
 
         d_head_ears = self._get_bp_dhead_ears(drive_head)
         base_plate = self._get_base_plate(drive_head)
         tube_gusset = self._get_tube_guesset(drive_head, center_tube)
 
         carrier_qty =  self._get_carrier_flight_qty(type, carrier_type, lead_flight, carrier_flight, non_lead_flight, non_carrier_flight, flighted_length)
         non_stock_lead_carrier_flight = self._get_non_stock_lead_carrier_flight(type, carrier_type, diameter, center_tube, non_lead_flight, non_carrier_flight, rotation, flighted_length, carrier_qty)
         stock_lead_carrier_flight = self._get_stock_lead_carrier_flight(type, carrier_type, diameter, lead_flight, carrier_flight, flighted_length, carrier_qty)
         l_flight, c_flight = self._get_non_or_stock_flights(non_stock_lead_carrier_flight, stock_lead_carrier_flight)
         teeth_clay_shale = self._get_teeth_clay_shale(diameter, teeth, pilot)
         teeth, tooth_holder, pilot, pilot_support, end_cap = teeth_clay_shale or (None, None, None, None, None)
         _center_tube = self._get_center_tube(overall_length, drive_head, center_tube, pilot_support)
 
         stiffening = (stiffening_ring, 1) if stiffening_ring else (None, 0) 
         _none = (None, 0)
 
         components = [
             (drive_head, 1),
             d_head_ears,
             stiffening,
             base_plate,
             tube_gusset,
             _center_tube or _none,
             l_flight,
             c_flight,
             teeth,
             tooth_holder,
             pilot,
             pilot_support,
             end_cap
         ]
         # exclude none values
         components = [c for c in components if c and c[0] and c[1]]
 
         return components
 
     def _get_bp_blade(self, type, diameter, drive_head, overall_length, flighted_length, rotation, teeth, center_tube, lead_flight, carrier_flight, carrier_type, non_lead_flight, non_carrier_flight, pilot):
         d_number = re.findall(r'\d+', diameter)[0]
         diameter = int(d_number)
 
         carrier_qty =  self._get_carrier_flight_qty(type, carrier_type, lead_flight, carrier_flight, non_lead_flight, non_carrier_flight, flighted_length)
         non_stock_lead_carrier_flight = self._get_non_stock_lead_carrier_flight(type, carrier_type, diameter, center_tube, non_lead_flight, non_carrier_flight, rotation, flighted_length, carrier_qty)
         stock_lead_carrier_flight = self._get_stock_lead_carrier_flight(type, carrier_type, diameter, lead_flight, carrier_flight, flighted_length, carrier_qty)
         l_flight, c_flight = self._get_non_or_stock_flights(non_stock_lead_carrier_flight, stock_lead_carrier_flight)
         teeth_blade = self._get_teeth_blade(diameter, teeth, pilot)
         teeth, tooth_holder, pilot, pilot_support, end_cap = teeth_blade or (None, None, None, None, None)
         _center_tube = self._get_center_tube(overall_length, drive_head, center_tube, pilot_support)
         _none = (None, 0)
 
         components = [
             (drive_head, 1),
             _center_tube or _none,
             l_flight,
             c_flight,
             teeth,
             tooth_holder,
             pilot,
             pilot_support,
             end_cap
         ]
         # exclude none values
         # raise ValidationError("This is blade...")
         components = [c for c in components if c and c[0] and c[1]]
 
         return components
 
