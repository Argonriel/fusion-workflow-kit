# fusion-guard: sketch
import adsk.core
import adsk.fusion

def run(_context: str):
    app = adsk.core.Application.get()
    assert app.activeDocument.dataFile.id == 'REPLACE_WITH_REGISTERED_WORKING_FILE_ID'
    design = adsk.fusion.Design.cast(app.activeProduct)
    root = design.rootComponent
    sketch = root.sketches.add(root.xYConstructionPlane)
    sketch.name = 'HoleCenters'
    lines = sketch.sketchCurves.sketchLines
    rectangle = lines.addTwoPointRectangle(adsk.core.Point3D.create(-3, -1.5, 0), adsk.core.Point3D.create(3, 1.5, 0))
    corners = []
    lower = None
    upper = None
    for i in range(rectangle.count):
        edge = rectangle.item(i)
        edge.isConstruction = True
        if abs(edge.startSketchPoint.geometry.y - edge.endSketchPoint.geometry.y) < 0.000001:
            sketch.geometricConstraints.addHorizontal(edge)
        else:
            sketch.geometricConstraints.addVertical(edge)
        corners.append(edge.startSketchPoint)
    for point in corners:
        if point.geometry.x < 0 and point.geometry.y < 0:
            lower = point
        if point.geometry.x > 0 and point.geometry.y > 0:
            upper = point
    assert lower and upper
    diagonal = lines.addByTwoPoints(lower, upper)
    diagonal.isConstruction = True
    sketch.geometricConstraints.addMidPoint(sketch.originPoint, diagonal)
    horizontal = sketch.sketchDimensions.addDistanceDimension(lower, upper, adsk.fusion.DimensionOrientations.HorizontalDimensionOrientation, adsk.core.Point3D.create(0, -2, 0))
    horizontal.parameter.expression = 'plate_length - 2 * edge_offset'
    vertical = sketch.sketchDimensions.addDistanceDimension(lower, upper, adsk.fusion.DimensionOrientations.VerticalDimensionOrientation, adsk.core.Point3D.create(4, 0, 0))
    vertical.parameter.expression = 'plate_width - 2 * edge_offset'
    for point in corners:
        circle = sketch.sketchCurves.sketchCircles.addByCenterRadius(point, 0.25)
        diameter = sketch.sketchDimensions.addDiameterDimension(circle, adsk.core.Point3D.create(point.geometry.x + 0.5, point.geometry.y + 0.5, 0))
        diameter.parameter.expression = 'hole_diameter'
    assert sketch.isFullyConstrained
