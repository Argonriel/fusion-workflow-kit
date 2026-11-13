# fusion-guard: parameters
import adsk.core
import adsk.fusion

def run(_context: str):
    app = adsk.core.Application.get()
    assert app.activeDocument.dataFile.id == 'REPLACE_WITH_REGISTERED_WORKING_FILE_ID'
    design = adsk.fusion.Design.cast(app.activeProduct)
    parameters = design.userParameters
    parameters.add('plate_length', adsk.core.ValueInput.createByString('80 mm'), 'mm', 'Plate X extent')
    parameters.add('plate_width', adsk.core.ValueInput.createByString('50 mm'), 'mm', 'Plate Y extent')
    parameters.add('plate_thickness', adsk.core.ValueInput.createByString('4 mm'), 'mm', 'Plate Z extent')
    parameters.add('edge_offset', adsk.core.ValueInput.createByString('10 mm'), 'mm', 'Hole center distance from the nearest plate edge')
    parameters.add('hole_diameter', adsk.core.ValueInput.createByString('5 mm'), 'mm', 'Four equal through-hole diameters')
