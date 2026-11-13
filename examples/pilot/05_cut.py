# fusion-guard: feature
import adsk.core
import adsk.fusion

def run(_context: str):
    app = adsk.core.Application.get()
    assert app.activeDocument.dataFile.id == 'REPLACE_WITH_REGISTERED_WORKING_FILE_ID'
    design = adsk.fusion.Design.cast(app.activeProduct)
    root = design.rootComponent
    sketch = root.sketches.itemByName('HoleCenters')
    assert sketch.profiles.count == 4
    profiles = adsk.core.ObjectCollection.create()
    for i in range(sketch.profiles.count):
        profiles.add(sketch.profiles.item(i))
    extrudes = root.features.extrudeFeatures
    feature_input = extrudes.createInput(profiles, adsk.fusion.FeatureOperations.CutFeatureOperation)
    assert feature_input.setOneSideExtent(adsk.fusion.ThroughAllExtentDefinition.create(), adsk.fusion.ExtentDirections.PositiveExtentDirection)
    feature = extrudes.add(feature_input)
    feature.name = 'Four_Through_Holes'
