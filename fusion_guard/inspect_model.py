"""Read-only Fusion inspection, embedded by the hook; no design modifications.

The trusted hook can register a local directory for atomic inspection reports.
The _fg_ prefix is reserved. This file is executed inside Fusion, not locally.
"""
import adsk.core
import adsk.fusion
import json as _fg_json
import base64 as _fg_base64
import hashlib as _fg_hashlib
import zlib as _fg_zlib
import os as _fg_os

# Keep two full snapshots below Fusion's 1 MiB stdout limit. Fail rather than
# omit fields if a snapshot cannot fit. These limits match hook.py.
_fg_MAX_REPORT_RAW_BYTES = 16 * 1024 * 1024
_fg_MAX_REPORT_ENCODED_CHARS = 384 * 1024
_fg_report_directory = None


def _fg_items(collection):
    return [collection.item(i) for i in range(collection.count)]


def _fg_health(item):
    states = adsk.fusion.FeatureHealthStates
    value = item.healthState
    for name in ("HealthyFeatureHealthState", "WarningFeatureHealthState",
                 "ErrorFeatureHealthState", "SuppressedFeatureHealthState",
                 "UnknownFeatureHealthState"):
        if hasattr(states, name) and value == getattr(states, name):
            return name
    return str(value)


def _fg_snapshot():
    app = adsk.core.Application.get()
    doc = app.activeDocument
    design = adsk.fusion.Design.cast(app.activeProduct)
    if not doc or not design:
        raise RuntimeError("Fusion Guard: active document is not a Fusion design")
    rows, local_sketches = [], []

    def walk(item, key):
        if item.isGroup:
            group = adsk.fusion.TimelineGroup.cast(item)
            if group is None:
                raise RuntimeError("Fusion Guard: cannot inspect timeline group")
            for j in range(group.count):
                walk(group.item(j), key + "/" + str(j))
            return
        entity = item.entity
        rows.append({"key": key, "name": item.name,
                     "type": entity.objectType if entity else "unrepresented",
                     "health": _fg_health(item),
                     "message": item.errorOrWarningMessage,
                     "suppressed": item.isSuppressed,
                     "rolled_back": item.isRolledBack})
        if entity and entity.objectType == "adsk::fusion::Sketch":
            local_sketches.append((entity, len(rows) - 1))

    timeline = design.timeline
    for i in range(timeline.count):
        walk(timeline.item(i), str(i))
    sketches, components, bodies = [], [], []
    base_count = 0
    for ci, comp in enumerate(_fg_items(design.allComponents)):
        component_key = str(ci) + ":" + comp.name
        base_count += comp.features.baseFeatures.count
        components.append({"key": component_key, "name": comp.name,
                           "body_count": comp.bRepBodies.count})
        for si, sketch in enumerate(_fg_items(comp.sketches)):
            # External referenced sketches can return a timelineObject whose index
            # accessor throws InternalValidationError. Use the actual local timeline
            # traversal and compare API objects, never raw entity-token strings.
            local_order = next((order for entity, order in local_sketches if entity == sketch), -1)
            sketches.append({"key": component_key + "/" + str(si),
                             "name": sketch.name,
                             "timeline_index": local_order,
                             "fully_constrained": sketch.isFullyConstrained,
                             "compute_deferred": sketch.isComputeDeferred,
                             "curves": sketch.sketchCurves.count,
                             "points": sketch.sketchPoints.count,
                             "dimensions": sketch.sketchDimensions.count,
                             "constraints": sketch.geometricConstraints.count,
                             "point_positions": [[round(v, 9) for v in (p.geometry.x, p.geometry.y, p.geometry.z)]
                                                 for p in _fg_items(sketch.sketchPoints)],
                             "dimension_expressions": [{"name": d.parameter.name,
                                                        "expression": d.parameter.expression}
                                                       for d in _fg_items(sketch.sketchDimensions)]})
        for bi, body in enumerate(_fg_items(comp.bRepBodies)):
            box = body.boundingBox
            bodies.append({"key": component_key + "/" + str(bi), "name": body.name,
                           "volume": round(body.volume, 9), "area": round(body.area, 9),
                           "faces": body.faces.count, "edges": body.edges.count,
                           "bounds": [round(v, 9) for p in (box.minPoint, box.maxPoint)
                                      for v in (p.x, p.y, p.z)]})
    parameters = []
    for p in _fg_items(design.allParameters):
        parameters.append({"name": p.name, "expression": p.expression,
                           "unit": p.unit, "type": p.objectType})
    parameters.sort(key=lambda p: p["name"])
    users = sorted(p.name for p in _fg_items(design.userParameters))
    latest = max((s for s in sketches if s["timeline_index"] >= 0),
                 key=lambda s: s["timeline_index"], default=None)
    return {"document": {"creation_id": doc.creationId, "name": doc.name,
                         "file_id": doc.dataFile.id if doc.isSaved else None},
            "parametric": design.designType == adsk.fusion.DesignTypes.ParametricDesignType,
            "timeline_count": timeline.count, "marker_position": timeline.markerPosition,
            "timeline": rows, "newest": rows[-1] if rows else None,
            "base_feature_count": base_count, "components": components,
            "bodies": bodies, "parameters": parameters, "user_parameters": users,
            "sketches": sketches, "latest_sketch": latest}


def _fg_baseline_check(snapshot):
    if not snapshot["parametric"]:
        raise RuntimeError("Fusion Guard: enable capture design history before editing")
    if snapshot["marker_position"] != snapshot["timeline_count"]:
        raise RuntimeError("Fusion Guard: move the timeline marker to the end before editing")
    if any(s["compute_deferred"] for s in snapshot["sketches"]):
        raise RuntimeError("Fusion Guard: a sketch is still in deferred computation")


def _fg_emit(nonce, phase, snapshot, completed=False):
    raw = _fg_json.dumps(
        {"phase": phase, "snapshot": snapshot, "completed": completed},
        ensure_ascii=True, allow_nan=False, separators=(",", ":")).encode("utf-8")
    if len(raw) > _fg_MAX_REPORT_RAW_BYTES:
        raise RuntimeError("Fusion Guard: full inspection exceeds the raw report size limit")
    data = _fg_base64.b64encode(_fg_zlib.compress(raw, 9)).decode("ascii")
    if len(data) > _fg_MAX_REPORT_ENCODED_CHARS:
        raise RuntimeError("Fusion Guard: full inspection exceeds the compressed report size limit")
    envelope = {"encoding": "zlib+base64", "raw_bytes": len(raw),
                "sha256": _fg_hashlib.sha256(raw).hexdigest(), "data": data}
    if _fg_report_directory is not None:
        if phase not in ("before", "after", "inspect"):
            raise RuntimeError("Fusion Guard: invalid inspection phase")
        path = _fg_os.path.join(_fg_report_directory, phase + ".json")
        # The directory was created for this nonce by PreToolUse. Never create
        # or select an arbitrary path from model output. An interrupted write
        # leaves only .tmp, which PostToolUse never accepts.
        with open(path + ".tmp", "xb") as stream:
            stream.write(_fg_json.dumps({"nonce": nonce, "envelope": envelope},
                                       separators=(",", ":")).encode("utf-8"))
            stream.flush()
            _fg_os.fsync(stream.fileno())
        _fg_os.replace(path + ".tmp", path)
    else:
        print("FUSION_GUARD_V2:" + nonce + ":" + _fg_json.dumps(envelope, separators=(",", ":")))
