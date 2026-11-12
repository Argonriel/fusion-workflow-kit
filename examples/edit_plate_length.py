# fusion-guard: parameters
import adsk.core
import adsk.fusion


def run(_context: str):
    design = adsk.fusion.Design.cast(adsk.core.Application.get().activeProduct)
    parameter = design.userParameters.itemByName("plate_length")
    if parameter is None:
        raise RuntimeError("Expected pilot parameter plate_length was not found")
    parameter.expression = "96 mm"
