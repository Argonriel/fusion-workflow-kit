# fusion-guard: feature
import adsk.core
import adsk.fusion

def run(_context: str):
    app = adsk.core.Application.get()
    assert app.activeDocument.dataFile.id == 'REPLACE_WITH_REGISTERED_WORKING_FILE_ID'
    design = adsk.fusion.Design.cast(app.activeProduct)
    root = design.rootComponent
    sketch = root.sketches.itemByName('PlateProfile')
    assert sketch.profiles.count == 1
    extrudes = root.features.extrudeFeatures
    feature_input = extrudes.createInput(sketch.profiles.item(0), adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
    extent = adsk.fusion.DistanceExtentDefinition.create(adsk.core.ValueInput.createByString('plate_thickness'))
    assert feature_input.setOneSideExtent(extent, adsk.fusion.ExtentDirections.PositiveExtentDirection)
    feature = extrudes.add(feature_input)
    feature.name = 'Plate_Extrude'
