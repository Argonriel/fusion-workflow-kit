# fusion-guard: sketch
import adsk.core
import adsk.fusion

def run(_context: str):
    app = adsk.core.Application.get()
    assert app.activeDocument.dataFile.id == 'REPLACE_WITH_REGISTERED_WORKING_FILE_ID'
    design = adsk.fusion.Design.cast(app.activeProduct)
    root = design.rootComponent
    sketch = root.sketches.add(root.xYConstructionPlane)
    sketch.name = 'PlateProfile'
    lines = sketch.sketchCurves.sketchLines
    rectangle = lines.addTwoPointRectangle(adsk.core.Point3D.create(-4, -2.5, 0), adsk.core.Point3D.create(4, 2.5, 0))
    for i in range(rectangle.count):
        edge = rectangle.item(i)
        if abs(edge.startSketchPoint.geometry.y - edge.endSketchPoint.geometry.y) < 0.000001:
            sketch.geometricConstraints.addHorizontal(edge)
        else:
            sketch.geometricConstraints.addVertical(edge)
    lower = None
    upper = None
    for i in range(sketch.sketchPoints.count):
        point = sketch.sketchPoints.item(i)
        if abs(point.geometry.x + 4) < 0.000001 and abs(point.geometry.y + 2.5) < 0.000001:
            lower = point
        if abs(point.geometry.x - 4) < 0.000001 and abs(point.geometry.y - 2.5) < 0.000001:
            upper = point
    assert lower and upper
    diagonal = lines.addByTwoPoints(lower, upper)
    diagonal.isConstruction = True
    sketch.geometricConstraints.addMidPoint(sketch.originPoint, diagonal)
    width = sketch.sketchDimensions.addDistanceDimension(lower, upper, adsk.fusion.DimensionOrientations.HorizontalDimensionOrientation, adsk.core.Point3D.create(0, -3, 0))
    width.parameter.expression = 'plate_length'
    height = sketch.sketchDimensions.addDistanceDimension(lower, upper, adsk.fusion.DimensionOrientations.VerticalDimensionOrientation, adsk.core.Point3D.create(5, 0, 0))
    height.parameter.expression = 'plate_width'
    assert sketch.isFullyConstrained
